#!/usr/bin/env bash
# Local backup protection for the Immich cutover (phase 7C). SOURCE this file; call the functions in runbook order.
# NOT EXECUTED AGAINST PRODUCTION. Decision: no off-host backup; the accepted protection is RAID1 on this host + a SECOND COPY on /home (separate filesystem, same two NVMe disks).
#
#   lb_check             read-only: RAID1 state, NVMe state/temperature, free space on both filesystems          (F0 and again in F1; no approval needed)
#   lb_copy_app_backup   F0: copies the newest Immich-made database backup to /home + SHA-256 on both sides      (needs CUTOVER_APPROVED)
#   lb_copy_cutover_dumps F6: copies immich.full.dump and immich.no-postgis.dump from $EV to /home + SHA-256      (needs CUTOVER_APPROVED)
#   lb_verify            re-hashes BOTH copies against their manifests and against each other; exit 0 only if all match (read-only)
#
# Rules: never overwrites (noclobber + refuses an existing destination), never moves or deletes anything, never touches the source database or the
# existing backup directories (they are only READ); manifests of the originals live in $EV/local-backup/, manifests of the /home copies next to the copies.
# Test mode (LB_TEST=1) only works with LB_ROOT/EV/IMMICH_BACKUPS under /tmp and never calls docker.

LB_ROOT="${LB_ROOT:-/home/immich-cutover-backups}"
IMMICH_BACKUPS="${IMMICH_BACKUPS:-/opt/stacks/immich/docker-data/library/backups}"
LB_MIN_FREE_GIB="${LB_MIN_FREE_GIB:-50}"            # free space required on EACH filesystem before copying
LB_MAX_TEMP_C="${LB_MAX_TEMP_C:-70}"                # NVMe warning threshold (device max 79, critical 82)
LB_MAX_AGE_H="${LB_MAX_AGE_H:-26}"                  # the Immich backup being copied must be younger than this
LB_IMMUTABLE="${LB_IMMUTABLE:-0}"                   # 1 = chattr +i the /home copies (deliberate: to delete them later chattr -i is needed)
PG_SRC="${PG_SRC:-postgis}"

_lb_fail() { echo "LB FAIL: $*" >&2; return 1; }
# _lb_gate [F0]: with the argument F0 (only lb_copy_app_backup passes it) a SEPARATE, narrower approval is accepted in production mode:
#   LB_BACKUP_ONLY_APPROVED=F0:<CUTOVER_ID>   (exact; "1", another id, another step or an empty id are refused)
# It never replaces CUTOVER_APPROVED: steps.sh (_gate) and lb_copy_cutover_dumps (no argument) still require CUTOVER_APPROVED=$CUTOVER_ID.
_lb_gate() {
  [ -n "${CUTOVER_ID:-}" ] && [ -n "${EV:-}" ] || { echo "CUTOVER_ID/EV not set" >&2; return 1; }
  if [ "${LB_TEST:-0}" = 1 ]; then
    case "$LB_ROOT:$EV:$IMMICH_BACKUPS" in /tmp/*:/tmp/*:/tmp/*) ;; *) echo "LB_TEST allows only /tmp paths" >&2; return 1;; esac
  elif [ "${CUTOVER_REHEARSAL:-0}" = 1 ]; then
    case "$LB_ROOT:$IMMICH_BACKUPS" in /tmp/immich-apptest-*:/tmp/immich-apptest-*) ;; *) echo "REHEARSAL GUARD: LB_ROOT and IMMICH_BACKUPS must be under /tmp/immich-apptest-*" >&2; return 1;; esac
  else
    if [ "${1:-}" = F0 ] && [ -n "${LB_BACKUP_ONLY_APPROVED:-}" ]; then
      [ "${#CUTOVER_ID}" -ge 6 ] && [ "$LB_BACKUP_ONLY_APPROVED" = "F0:$CUTOVER_ID" ] && return 0
      echo "production F0 copy refused: LB_BACKUP_ONLY_APPROVED must be exactly F0:$CUTOVER_ID (it is not valid for another id or step)" >&2; return 1
    fi
    [ "${CUTOVER_APPROVED:-}" = "$CUTOVER_ID" ] || { echo "production copy refused: export CUTOVER_APPROVED=$CUTOVER_ID only after the written approval (O16); for the F0 app-backup copy alone the separate token LB_BACKUP_ONLY_APPROVED=F0:$CUTOVER_ID is accepted" >&2; return 1; }
  fi
}
_lb_dest() { echo "$LB_ROOT/$CUTOVER_ID"; }
_lb_sha() {
  local h
  h="$(sha256sum "$1" 2>/dev/null)" || return "$?"
  h="${h%% *}"
  [[ "$h" =~ ^[0-9a-f]{64}$ ]] || return 1
  printf '%s\n' "$h"
}
# every critical command is guarded explicitly: errexit is NOT relied upon (it was found to be ineffective in this function context during the 7C test)
_ok() { "$@" || { echo "LB FAIL: mandatory command failed" >&2; exit 1; }; }

# ---- read-only health and space check
lb_check() {
  local bad=0 m free_s free_h MD="${LB_MDSTAT:-/proc/mdstat}" real=1
  if [ "$MD" != /proc/mdstat ]; then      # a simulated mdstat is accepted ONLY in test/rehearsal mode (degraded-RAID simulation); never in production
    if [ "${LB_TEST:-0}" = 1 ] || [ "${CUTOVER_REHEARSAL:-0}" = 1 ]; then real=0; else _lb_fail "LB_MDSTAT override refused outside test/rehearsal mode"; return 1; fi
  fi
  grep -qE '^md[0-9]+ : active raid1' "$MD" || { _lb_fail "no active raid1 in $MD"; bad=1; }
  if grep -E '\[[U_]+\]' "$MD" | grep -q '_'; then _lb_fail "a RAID1 array is DEGRADED (see $MD)"; bad=1; fi
  if grep -qiE 'recovery|resync|reshape|check *=' "$MD"; then _lb_fail "a RAID1 resync/recovery/check is running (see $MD)"; bad=1; fi
  if [ "${LB_TEST:-0}" != 1 ] && [ "$real" = 1 ]; then
    for m in md0 md1 md2 md3; do
      md_detail="$(mdadm --detail /dev/$m 2>/dev/null)" || { _lb_fail "cannot read mdadm"; return 1; }
      [ "$(printf '%s\n' "$md_detail" | awk -F': ' '/Active Devices/ {print $2}')" = 2 ] || { _lb_fail "$m: not 2 active devices"; bad=1; }
      st="$(set -o pipefail; mdadm --detail /dev/$m 2>/dev/null | awk -F' : ' '/ State :/ {print $2}')" || { _lb_fail "cannot read RAID state"; return 1; }
      case "$st" in *degraded*|*recover*|*resync*|*fail*|"") _lb_fail "$m: state '$st'"; bad=1;; esac
      [ "$(cat /sys/block/$m/md/mismatch_cnt 2>/dev/null)" = 0 ] || { _lb_fail "$m: mismatch_cnt != 0"; bad=1; }
      [ "$(cat /sys/block/$m/md/sync_action 2>/dev/null)" = idle ] || { _lb_fail "$m: a resync/check is running"; bad=1; }
    done
    local n t
    for n in nvme0 nvme1; do
      [ "$(cat /sys/class/nvme/$n/state 2>/dev/null)" = live ] || { _lb_fail "$n: state is not live"; bad=1; }
      t=$(set -o pipefail; cat /sys/class/nvme/$n/hwmon*/temp1_input 2>/dev/null | head -1) || { _lb_fail "cannot read NVMe temperature"; return 1; }; [ -n "$t" ] && [ $((t/1000)) -lt "$LB_MAX_TEMP_C" ] || { _lb_fail "$n: temperature unknown or >= ${LB_MAX_TEMP_C}C"; bad=1; }
    done
    echo "INFO  SMART wear/media-error counters are not readable here (smartmontools/nvme-cli not installed): hardware health is only judged by md state, nvme state and temperature"
  fi
  for d in "${LB_ROOT%/*}" "$(dirname "$IMMICH_BACKUPS")"; do
    [ -n "$d" ] && [ -d "$d" ] || continue
    free_s=$(set -o pipefail; df -B1 --output=avail "$d" | tail -1) || { _lb_fail "cannot read free space"; return 1; }; [[ "$free_s" =~ ^[[:space:]]*[0-9]+$ ]] || return 1; free_h=$((free_s/1073741824))
    if [ "$free_h" -ge "$LB_MIN_FREE_GIB" ]; then echo "PASS  free space on $(df --output=target "$d" | tail -1): ${free_h} GiB >= ${LB_MIN_FREE_GIB}"; else _lb_fail "free space on $d: ${free_h} GiB < ${LB_MIN_FREE_GIB}"; bad=1; fi
  done
  [ "$(df --output=source "${LB_ROOT%/*}" | tail -1)" != "$(df --output=source "$IMMICH_BACKUPS" | tail -1)" ] && echo "PASS  the second copy is on a different filesystem than the main backups" || echo "WARN  the second copy is on the SAME filesystem as the main backups"
  [ "$bad" = 0 ] && echo "lb_check OK" || return 1
}

# ---- F0: second copy of the newest Immich backup (the Immich-made .sql.gz)
lb_copy_app_backup() { _lb_gate F0 || return 1; (
  set -Eeuo pipefail; set -o noclobber; umask 077
  lb_check || exit 1
  f="$(ls -t "$IMMICH_BACKUPS"/immich-db-backup-*-v3.3.5-pg16.*.sql.gz | head -1)" || exit 1
  [ -n "$f" ] && [ -s "$f" ] || exit 1
  now_epoch="$(date +%s)" || exit 1
  backup_epoch="$(stat -c %Y "$f")" || exit 1
  [[ "$now_epoch:$backup_epoch" =~ ^[0-9]+:[0-9]+$ ]] || exit 1
  age=$(( ( now_epoch - backup_epoch ) / 3600 )); [ "$age" -lt "$LB_MAX_AGE_H" ] || { echo "LB FAIL: newest Immich backup is ${age} h old (max $LB_MAX_AGE_H)" >&2; exit 1; }
  gzip -t "$f" || { echo "LB FAIL: source backup is not a valid gzip" >&2; exit 1; }
  D="$(_lb_dest)"; [ ! -e "$D" ] || { echo "LB FAIL: $D already exists (never overwrite)" >&2; exit 1; }
  _ok mkdir -p -m 700 "$LB_ROOT"; _ok mkdir -m 700 "$D" "$D/app-backup"; _ok mkdir -p -m 700 "$EV/local-backup"
  echo "$CUTOVER_ID" > "$D/CUTOVER_ID" || exit 1; [ -e "$EV/local-backup/cutover-id" ] || { echo "$CUTOVER_ID" > "$EV/local-backup/cutover-id" || exit 1; }
  [ ! -e "$EV/local-backup/app-backup.sha256" ] || { echo "LB FAIL: manifest exists" >&2; exit 1; }
  s1="$(_lb_sha "$f")" || { echo "LB FAIL: cannot hash the original" >&2; exit 1; }; echo "$s1  $(basename "$f")" > "$EV/local-backup/app-backup.sha256" || exit 1          # manifest of the ORIGINAL, outside the backup directory
  _ok cp -p -- "$f" "$D/app-backup/"
  s2="$(_lb_sha "$D/app-backup/$(basename "$f")")" || { echo "LB FAIL: cannot hash the copy" >&2; exit 1; }
  [ "$s1" = "$s2" ] || { echo "LB FAIL: hash differs after the copy" >&2; exit 1; }
  [ "$(_lb_sha "$f" || echo x)" = "$s1" ] || { echo "LB FAIL: the original changed while copying" >&2; exit 1; }
  ( cd "$D/app-backup" && echo "$s2  $(basename "$f")" > SHA256SUMS ) || exit 1
  _ok gzip -t "$D/app-backup/$(basename "$f")"
  _ok chmod 400 "$D/app-backup"/*; [ "$LB_IMMUTABLE" != 1 ] || _ok chattr +i "$D/app-backup"/*
  echo "lb_copy_app_backup OK: $(basename "$f") sha256 $s1 (original and copy)"
); }

# ---- F6: second copy of the cutover dumps (after s_bridge_sanitize); the dumps are files in $EV, the source database is not touched
lb_copy_cutover_dumps() { _lb_gate || return 1; (
  set -Eeuo pipefail; set -o noclobber; umask 077
  lb_check || exit 1
  { [ -s "$EV/immich.full.dump" ] && [ -s "$EV/immich.no-postgis.dump" ] && [ -s "$EV/immich.full.dump.sha256" ] && [ -s "$EV/immich.no-postgis.dump.sha256" ]; } || { echo "LB FAIL: dumps or their sha256 files are missing in $EV" >&2; exit 1; }
  D="$(_lb_dest)"; _ok mkdir -p -m 700 "$LB_ROOT"; [ ! -e "$D/dumps" ] || { echo "LB FAIL: $D/dumps already exists (never overwrite)" >&2; exit 1; }; _ok mkdir -p -m 700 "$D"; _ok mkdir -m 700 "$D/dumps"; _ok mkdir -p -m 700 "$EV/local-backup"
  [ -e "$D/CUTOVER_ID" ] || echo "$CUTOVER_ID" > "$D/CUTOVER_ID" || exit 1; [ -e "$EV/local-backup/cutover-id" ] || { echo "$CUTOVER_ID" > "$EV/local-backup/cutover-id" || exit 1; }
  [ "$(cat "$D/CUTOVER_ID")" = "$CUTOVER_ID" ] && [ "$(cat "$EV/local-backup/cutover-id")" = "$CUTOVER_ID" ] || { echo "LB FAIL: the copy directory belongs to another cutover id" >&2; exit 1; }
  [ ! -e "$EV/local-backup/dumps.sha256" ] || { echo "LB FAIL: manifest exists" >&2; exit 1; }
  for n in immich.full.dump immich.no-postgis.dump; do
    rec="$(cut -d' ' -f1 "$EV/$n.sha256")" || exit 1; now="$(_lb_sha "$EV/$n")" || { echo "LB FAIL: cannot hash $n" >&2; exit 1; }
    [ "$rec" = "$now" ] || { echo "LB FAIL: $n differs from the hash recorded by the cutover step" >&2; exit 1; }       # the original is intact before it is copied
    echo "$now  $n" >> "$EV/local-backup/dumps.sha256" || exit 1
    _ok cp -p -- "$EV/$n" "$D/dumps/"
    [ "$(_lb_sha "$D/dumps/$n" || echo x)" = "$now" ] || { echo "LB FAIL: $n differs after the copy" >&2; exit 1; }
    if [ "${LB_TEST:-0}" != 1 ]; then      # the copy must be a readable pg_dump archive (TOC lines equal to the ones counted by the step); read through the source container's pg_restore, no database access
      copy_toc="$(docker exec -i "$PG_SRC" pg_restore --list < "$D/dumps/$n")" || exit 1
      original_toc="$(docker exec -i "$PG_SRC" pg_restore --list < "$EV/$n")" || exit 1
      [ -n "$copy_toc" ] && [ "$copy_toc" = "$original_toc" ] || { echo "LB FAIL: TOC differs or is empty" >&2; exit 1; }
    fi
  done
  ( cd "$D/dumps" && sha256sum immich.full.dump immich.no-postgis.dump > SHA256SUMS ) || exit 1
  _ok chmod 400 "$D/dumps"/*; [ "$LB_IMMUTABLE" != 1 ] || _ok chattr +i "$D/dumps"/*
  _ok touch "$EV/local-backup/COPIES_DONE"
  echo "lb_copy_cutover_dumps OK"
); }

# ---- read-only verification of both copies (run after each copy, before F10, at T+24 h, weekly, and before any decision to delete the source after day 7)
lb_verify() { _lb_gate_ro || return 1; (
  set -Eeuo pipefail; bad=0
  D="$(_lb_dest)"
  chk() { # chk <manifest> <dir> <label> : every file in the manifest must hash to the recorded value in <dir>
    [ -s "$1" ] || { echo "FAIL  $3: manifest $1 missing"; bad=1; return; }
    while read -r h n; do
      [[ "$h" =~ ^[0-9a-f]{64}$ ]] && [[ "$n" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "FAIL  $3: malformed manifest"; bad=1; continue; }
      [ -f "$2/$n" ] || { echo "FAIL  $3: $n missing in $2"; bad=1; continue; }
      [ "$(_lb_sha "$2/$n" || echo x)" = "$h" ] && echo "PASS  $3: $n sha256 ${h:0:16}…" || { echo "FAIL  $3: $n sha256 differs"; bad=1; }
    done < "$1"
  }
  if [ -s "$EV/local-backup/app-backup.sha256" ]; then
    chk "$EV/local-backup/app-backup.sha256" "$IMMICH_BACKUPS" "original app backup"; chk "$D/app-backup/SHA256SUMS" "$D/app-backup" "/home copy app backup"
    [ "$(cut -d' ' -f1 "$EV/local-backup/app-backup.sha256")" = "$(cut -d' ' -f1 "$D/app-backup/SHA256SUMS")" ] && echo "PASS  app backup: original and /home copy have the same hash" || { echo "FAIL  app backup: original and copy differ"; bad=1; }
  else echo "INFO  no app-backup manifest yet"; fi
  if [ -s "$EV/local-backup/dumps.sha256" ]; then
    chk "$EV/local-backup/dumps.sha256" "$EV" "original cutover dumps"; chk "$D/dumps/SHA256SUMS" "$D/dumps" "/home copy cutover dumps"
    [ "$(sort "$EV/local-backup/dumps.sha256" | cut -d' ' -f1)" = "$(sort "$D/dumps/SHA256SUMS" | cut -d' ' -f1)" ] && echo "PASS  dumps: originals and /home copies have the same hashes" || { echo "FAIL  dumps: originals and copies differ"; bad=1; }
  else echo "INFO  no dump manifest yet"; fi
  [ "$bad" = 0 ] && echo "lb_verify OK" || { echo "lb_verify FAILED" >&2; exit 1; }
); }
_lb_gate_ro() { [ -n "${CUTOVER_ID:-}" ] && [ -n "${EV:-}" ] || { echo "CUTOVER_ID/EV not set" >&2; return 1; }; }

# ---- G14: the backup gate in front of every step that opens traffic (s_open, s_manual_forward). READ-ONLY on production: it changes no .env, no container, no database;
# its only writes are evidence files in $EV/local-backup. Returns 0 ONLY if every check is PASS; any FAIL/UNKNOWN => 1 (the caller must HALT without opening anything).
_lb_manifest_ok() {  # _lb_manifest_ok <file> <expected line count>: every line is "<64 hex>  <plain file name>", no duplicates, exact count
  [ -s "$1" ] || return 1
  [ "$(grep -cEv '^[0-9a-f]{64}  [A-Za-z0-9._-]+$' "$1")" = 0 ] || return 1
  [ "$(wc -l < "$1")" = "$2" ] && [ "$(cut -d' ' -f3 "$1" | sort | uniq -d | wc -l)" = 0 ]
}
lb_gate_open() {
  [ -n "${CUTOVER_ID:-}" ] && [ -n "${EV:-}" ] || { echo "LB GATE FAIL: CUTOVER_ID/EV not set" >&2; return 1; }
  local bad=0 g="$EV/local-backup/gate.log" D="$LB_ROOT/$CUTOVER_ID" f n an
  mkdir -p -m 700 "$EV/local-backup" 2>/dev/null || return 1; : >| "$g" 2>/dev/null || { echo "LB GATE FAIL: cannot write $g" >&2; return 1; }
  gp() { echo "$1 $2 $3" >> "$g" || { bad=1; return 1; }; echo "$1 $2 $3" >&2; [ "$1" = PASS ] || bad=1; }
  # G1 identity: the evidence directory and BOTH copy locations must belong to exactly this cutover id
  [ "$(basename "$EV")" = "immich-cutover-$CUTOVER_ID" ] && gp PASS G1a "evidence directory name matches CUTOVER_ID" || gp FAIL G1a "evidence directory $(basename "$EV") does not match CUTOVER_ID $CUTOVER_ID"
  [ -d "$D" ] && gp PASS G1b "copy directory $D exists" || gp FAIL G1b "copy directory $D is missing"
  [ "$(cat "$EV/local-backup/cutover-id" 2>/dev/null)" = "$CUTOVER_ID" ] && gp PASS G1c "evidence marker cutover-id matches" || gp FAIL G1c "evidence marker cutover-id missing or for another cutover"
  [ "$(cat "$D/CUTOVER_ID" 2>/dev/null)" = "$CUTOVER_ID" ] && gp PASS G1d "copy marker CUTOVER_ID matches" || gp FAIL G1d "copy marker CUTOVER_ID missing or for another cutover"
  # G2 RAID1 (and space) right now
  if lb_check >> "$g" 2>&1; then gp PASS G2 "RAID1 healthy and space sufficient (lb_check)"; else gp FAIL G2 "RAID1 degraded/resyncing/unknown or space insufficient (lb_check)"; fi
  # G3 manifests exist and are well formed
  _lb_manifest_ok "$EV/local-backup/app-backup.sha256" 1 && gp PASS G3a "original app-backup manifest valid" || gp FAIL G3a "original app-backup manifest missing or malformed"
  _lb_manifest_ok "$EV/local-backup/dumps.sha256" 2 && gp PASS G3b "original dumps manifest valid" || gp FAIL G3b "original dumps manifest missing or malformed"
  _lb_manifest_ok "$D/app-backup/SHA256SUMS" 1 && gp PASS G3c "/home app-backup manifest valid" || gp FAIL G3c "/home app-backup manifest missing or malformed"
  _lb_manifest_ok "$D/dumps/SHA256SUMS" 2 && gp PASS G3d "/home dumps manifest valid" || gp FAIL G3d "/home dumps manifest missing or malformed"
  for n in immich.full.dump immich.no-postgis.dump; do
    grep -qE "^[0-9a-f]{64}  $n\$" "$EV/local-backup/dumps.sha256" 2>/dev/null && grep -qE "^[0-9a-f]{64}  $n\$" "$D/dumps/SHA256SUMS" 2>/dev/null && gp PASS G3e "both manifests list $n" || gp FAIL G3e "a manifest does not list $n"
  done
  [ -e "$EV/local-backup/COPIES_DONE" ] && gp PASS G3f "COPIES_DONE marker present" || gp FAIL G3f "COPIES_DONE marker missing (lb_copy_cutover_dumps did not finish)"
  # G4 both dumps and the app backup exist, originals and copies
  for f in "$EV/immich.full.dump" "$EV/immich.no-postgis.dump" "$D/dumps/immich.full.dump" "$D/dumps/immich.no-postgis.dump"; do [ -s "$f" ] && gp PASS G4 "exists: ${f#$EV/}" || gp FAIL G4 "missing or empty: $f"; done
  an="$(cut -d' ' -f3 "$EV/local-backup/app-backup.sha256" 2>/dev/null)"
  if [ -n "$an" ] && [ -s "$IMMICH_BACKUPS/$an" ] && [ -s "$D/app-backup/$an" ]; then gp PASS G4 "app backup $an exists as original and as copy"; else gp FAIL G4 "app backup original or copy missing"; fi
  # G5 hashes: the hash recorded by the cutover step, the original manifest, the original file, the copy manifest and the copy file must ALL agree
  for n in immich.full.dump immich.no-postgis.dump; do
    r="$(cut -d' ' -f1 "$EV/$n.sha256" 2>/dev/null)"; m="$(grep -E "  $n\$" "$EV/local-backup/dumps.sha256" 2>/dev/null | cut -d' ' -f1)"
    [ -n "$r" ] && [ "$r" = "$m" ] && gp PASS G5a "$n: hash recorded by the cutover step equals the manifest" || gp FAIL G5a "$n: hash recorded by the cutover step differs from the manifest"
  done
  if ( lb_verify ) >> "$g" 2>&1; then gp PASS G5b "lb_verify: all originals and copies re-hashed, all equal"; else gp FAIL G5b "lb_verify FAILED (hash differs or file missing)"; fi
  if [ "$bad" != 0 ]; then
    { echo "BACKUP GATE (G14) FAILED for cutover $CUTOVER_ID at $(date -u +%FT%TZ): traffic was NOT opened; .env, containers and the source database were not touched."; echo "See $g. Fix the cause (or the owner accepts the risk in writing and re-runs the copy steps), then repeat the step."; } > "$EV/local-backup/BACKUP-GATE-HALT.txt" 2>/dev/null
    return 1
  fi
  rm -f "$EV/local-backup/BACKUP-GATE-HALT.txt" || return 1
  echo "lb_gate_open OK" >> "$g" || return 1
  echo "lb_gate_open OK" >&2
}
