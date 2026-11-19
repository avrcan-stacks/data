#!/usr/bin/env bash
# Merge md3 (/home) into md2 (/). Phases: prep | free | repart | grow
# Only "prep" is non-destructive. Others require CONFIRM=yes.
set -euo pipefail

DISKS=(/dev/nvme0n1 /dev/nvme1n1)
P3_START=10489856
P4_START=4234153984
BK=/opt/stacks/data/backups/md3-merge
TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=$BK/merge-md3-$TS.log
mkdir -p "$BK"
exec > >(tee -a "$LOG") 2>&1

die() { echo "ASSERT FAILED: $*" >&2; exit 1; }
need_confirm() { [[ "${CONFIRM:-}" == yes ]] || die "set CONFIRM=yes for phase $1"; }

assert_layout() {
  for d in "${DISKS[@]}"; do
    s3=$(sgdisk -i 3 "$d" | awk '/First sector/{print $3}')
    [[ "$s3" == "$P3_START" ]] || die "$d p3 start=$s3 expected $P3_START"
  done
}
assert_raid_clean() {
  grep -q '^md2 .*' /proc/mdstat || die "md2 missing"
  ! grep -E '\[U?_|_U?\]' /proc/mdstat >/dev/null || die "degraded array in /proc/mdstat"
}

phase_prep() {
  echo "== prep $TS"
  assert_layout; assert_raid_clean
  for d in "${DISKS[@]}"; do
    n=$(basename "$d")
    sgdisk --backup="$BK/gpt-$n.bin" "$d"
    sgdisk -p "$d" > "$BK/gpt-$n.txt"
  done
  mdadm --detail --scan > "$BK/mdadm-detail-scan.txt"
  cp /etc/fstab "$BK/fstab.orig"; cp /etc/mdadm/mdadm.conf "$BK/mdadm.conf.orig"
  blkid > "$BK/blkid.txt"; cp /proc/mdstat "$BK/mdstat.txt"
  mkdir -p "$BK/home-copy"
  rsync -a --checksum /home/immich-cutover-backups /home/immich-post-cutover-protected "$BK/home-copy/"
  for dir in immich-cutover-backups immich-post-cutover-protected; do
    diff <(cd /home/$dir && find . -type f -print0 | sort -z | xargs -0 sha256sum) \
         <(cd "$BK/home-copy/$dir" && find . -type f -print0 | sort -z | xargs -0 sha256sum) \
      && echo "checksums OK: $dir"
  done
  echo "prep done. Log: $LOG"
}

phase_free() {
  need_confirm free
  assert_layout; assert_raid_clean
  [[ -z "$(lsof +D /home 2>/dev/null)" ]] || die "/home still in use (lsof)"
  umount /home
  sed -i.bak '/[[:space:]]\/home[[:space:]]/d' /etc/fstab
  mdadm --stop /dev/md3
  echo "md3 stopped"
}

phase_repart() {
  need_confirm repart
  assert_layout
  [[ ! -e /dev/md3 ]] || die "md3 still present"
  for d in "${DISKS[@]}"; do
    echo "-- $d before"; sgdisk -p "$d"
    sgdisk -d 4 -d 3 "$d"
    sgdisk -n 3:${P3_START}:0 -t 3:FD00 "$d"
    echo "-- $d after"; sgdisk -p "$d"
    s3=$(sgdisk -i 3 "$d" | awk '/First sector/{print $3}')
    [[ "$s3" == "$P3_START" ]] || die "$d new p3 start $s3"
    partx -u "$d" || echo "partx failed on $d -> use Rescue (Option 2); STOP"
  done
}

phase_grow() {
  need_confirm grow
  assert_raid_clean
  mdadm --grow /dev/md2 --size=max
  resize2fs /dev/md2
  sed -i.bak '\#/dev/md/3#d' /etc/mdadm/mdadm.conf
  update-initramfs -u
  df -h /; cat /proc/mdstat
}

case "${1:-}" in
  prep) phase_prep;; free) phase_free;; repart) phase_repart;; grow) phase_grow;;
  *) echo "usage: $0 {prep|free|repart|grow}"; exit 2;;
esac
