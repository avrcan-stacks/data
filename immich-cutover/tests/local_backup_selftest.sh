#!/usr/bin/env bash
# Phase 7C: offline test of local_backup.sh on SYNTHETIC files under /tmp only (LB_TEST=1). No production file, container or directory is touched.
set -uo pipefail
cd "$(dirname "$0")/.."
T="$(mktemp -d /tmp/lbtest.XXXXXX)"; trap 'chmod -R u+w "$T" 2>/dev/null; rm -rf "$T"' EXIT
ok() { echo "PASS  $1"; }; bad() { echo "FAIL  $1"; FAILED=1; }; FAILED=0
mkdir -p "$T/imm" "$T/home"
printf 'Personalities : [raid1]\nmd2 : active raid1 nvme1n1p3[1] nvme0n1p3[0]\n      2111699968 blocks super 1.2 [2/2] [UU]\n\nunused devices: <none>\n' > "$T/md.ok"
F=immich-db-backup-20261115T020000-v3.3.5-pg16.13.sql.gz
(echo "-- synthetic"; head -c 150000 /dev/urandom | base64) | gzip > "$T/imm/$F"
mkE() { mkdir -p "$T/$1"; head -c 90000 /dev/urandom > "$T/$1/immich.full.dump"; head -c 80000 /dev/urandom > "$T/$1/immich.no-postgis.dump"; (cd "$T/$1"; sha256sum immich.full.dump > immich.full.dump.sha256; sha256sum immich.no-postgis.dump > immich.no-postgis.dump.sha256); }
R() { ( export LB_MDSTAT="${LB_MDSTAT:-$T/md.ok}" LB_TEST=1 LB_ROOT="$T/home/$1" EV="$T/$2" IMMICH_BACKUPS="$T/imm" LB_MIN_FREE_GIB="${3:-1}" CUTOVER_ID="$1"; mkdir -p "$T/$2"; source ./local_backup.sh; shift 3; "$@" ) > "$T/out" 2>&1; }
h0="$(sha256sum "$T/imm/$F" | cut -d' ' -f1)"
mkE ev1
R c1 ev1 1 lb_copy_app_backup && ok "app backup copied (hash original == copy)" || bad "copy app backup"
R c1 ev1 1 lb_copy_cutover_dumps && ok "cutover dumps copied (hash original == copy, test mode: no TOC check)" || bad "copy dumps"
R c1 ev1 1 lb_verify && grep -q "lb_verify OK" "$T/out" && ok "lb_verify passes on untouched copies" || bad "verify"
R c1 ev1 1 lb_copy_app_backup && bad "second copy must be refused" || { grep -q "never overwrite" "$T/out" && ok "no overwrite: a second copy into the same id is refused"; }
R c1 ev1 1 lb_copy_cutover_dumps && bad "second dump copy must be refused" || { grep -q "never overwrite" "$T/out" && ok "no overwrite: a second dump copy is refused"; }
chmod 600 "$T/home/c1/c1/dumps/immich.full.dump" 2>/dev/null || chmod 600 "$T/home/c1/dumps/immich.full.dump"
D1="$(find "$T/home/c1" -name immich.full.dump)"; chmod 600 "$D1"; printf X >> "$D1"
R c1 ev1 1 lb_verify && bad "tampered /home copy must FAIL" || { grep -q "FAIL  /home copy cutover dumps" "$T/out" && ok "tampered /home copy detected"; }
head -c 90000 /dev/urandom > "$T/ev1/immich.full.dump"
R c1 ev1 1 lb_verify && bad "changed original must FAIL" || { grep -q "FAIL  original cutover dumps" "$T/out" && ok "changed original detected"; }
mkE ev2; echo 'bogus' > "$T/ev2/immich.full.dump.sha256"
R c2 ev2 1 lb_copy_cutover_dumps && bad "dump that differs from the hash recorded by the cutover step must be refused" || { [ ! -e "$T/home/c2/dumps/immich.full.dump" ] && ok "dump differing from the recorded hash is refused before copying"; }
R c3 ev3 999999 lb_copy_app_backup && bad "low space must be refused" || { [ ! -e "$T/home/c3" ] && ok "insufficient free space refused, nothing created"; }
echo garbage > "$T/imm/immich-db-backup-20261116T020000-v3.3.5-pg16.13.sql.gz"
R c4 ev4 1 lb_copy_app_backup && bad "corrupt gzip must be refused" || { [ ! -e "$T/home/c4" ] && ok "corrupt newest backup refused, nothing created"; }
rm "$T/imm/immich-db-backup-20261116T020000-v3.3.5-pg16.13.sql.gz"; touch -d "3 days ago" "$T/imm/$F"
R c5 ev5 1 lb_copy_app_backup && bad "stale backup must be refused" || { grep -q "h old" "$T/out" && ok "backup older than 26 h refused"; }
( export CUTOVER_ID=c6 EV="$T/ev6" LB_ROOT="$T/home/c6"; unset LB_TEST CUTOVER_APPROVED; source ./local_backup.sh; lb_copy_app_backup ) > "$T/out" 2>&1 && bad "production mode without approval must be refused" || { [ ! -e "$T/home/c6" ] && grep -q "CUTOVER_APPROVED" "$T/out" && ok "production mode refuses without CUTOVER_APPROVED"; }
( export LB_TEST=1 CUTOVER_ID=c7 EV=/opt/stacks/data/backups/x LB_ROOT=/home/x IMMICH_BACKUPS=/tmp/x; source ./local_backup.sh; lb_copy_app_backup ) > "$T/out" 2>&1 && bad "LB_TEST outside /tmp must be refused" || ok "test mode refuses non-/tmp paths"
[ "$(sha256sum "$T/imm/$F" | cut -d' ' -f1)" = "$h0" ] && ok "the source backup file is byte-identical after every test (never modified)" || bad "source modified"

# ---- phase 7D: backup gate (G14)
printf 'Personalities : [raid1]\nmd2 : active raid1 nvme1n1p3[1] nvme0n1p3[0]\n      2111699968 blocks super 1.2 [2/2] [UU]\n\nunused devices: <none>\n' > "$T/md.ok"
printf 'Personalities : [raid1]\nmd2 : active raid1 nvme1n1p3[1]\n      2111699968 blocks super 1.2 [2/1] [U_]\n\nunused devices: <none>\n' > "$T/md.degraded"
printf 'Personalities : [raid1]\nmd2 : active raid1 nvme1n1p3[1] nvme0n1p3[0]\n      2111699968 blocks super 1.2 [2/2] [UU]\n      [==>..................]  resync = 12.0%% (1/10) finish=1.0min\n\nunused devices: <none>\n' > "$T/md.resync"
G() { # G <id> <mdstat> : run lb_gate_open for cutover <id>
  ( export LB_TEST=1 LB_ROOT="$T/home/$1" EV="$T/immich-cutover-$1" IMMICH_BACKUPS="$T/imm" LB_MIN_FREE_GIB=1 CUTOVER_ID="$1" LB_MDSTAT="$2"; source ./local_backup.sh; lb_gate_open ) > "$T/out" 2>&1; }
touch "$T/imm/$F"; mkE immich-cutover-g1
R g1 immich-cutover-g1 1 lb_copy_app_backup; R g1 immich-cutover-g1 1 lb_copy_cutover_dumps
G g1 "$T/md.ok" && ok "gate PASSES with both copies, valid manifests, equal hashes and a healthy (simulated) RAID1" || { bad "gate positive"; cat "$T/out"; }
G g1 "$T/md.degraded" && bad "degraded RAID must HALT the gate" || { grep -q "FAIL G2" "$T/out" && ok "gate HALTs on degraded RAID1 ([U_])"; }
G g1 "$T/md.resync" && bad "resync must HALT the gate" || { grep -q "FAIL G2" "$T/out" && ok "gate HALTs while a resync is running"; }
G g1 "$T/nonexistent" && bad "missing mdstat must HALT" || ok "gate HALTs when the RAID state cannot be read"
G g2 "$T/md.ok" && bad "wrong CUTOVER_ID must HALT" || { grep -q "FAIL G1" "$T/out" && ok "gate HALTs for a wrong CUTOVER_ID (directory, markers)"; }
( export LB_TEST=1 LB_ROOT="$T/home/g1" EV="$T/immich-cutover-g1" IMMICH_BACKUPS="$T/imm" LB_MIN_FREE_GIB=1 CUTOVER_ID=g1 LB_MDSTAT="$T/md.ok"; echo other > "$T/immich-cutover-g1/local-backup/cutover-id"; source ./local_backup.sh; lb_gate_open ) > "$T/out" 2>&1 && bad "foreign marker must HALT" || { grep -q "FAIL G1c" "$T/out" && ok "gate HALTs when the evidence marker belongs to another cutover"; }
echo g1 > "$T/immich-cutover-g1/local-backup/cutover-id"
mv "$T/home/g1/g1/dumps" "$T/dumps.away"; G g1 "$T/md.ok" && bad "missing copy must HALT" || { grep -q "FAIL G4" "$T/out" && ok "gate HALTs when the /home copy of the dumps is missing"; }; mv "$T/dumps.away" "$T/home/g1/g1/dumps"
chmod 600 "$T/home/g1/g1/dumps/immich.no-postgis.dump"; cp -p "$T/home/g1/g1/dumps/immich.no-postgis.dump" "$T/keep"; printf Z >> "$T/home/g1/g1/dumps/immich.no-postgis.dump"
G g1 "$T/md.ok" && bad "corrupt dump copy must HALT" || { grep -q "FAIL G5b" "$T/out" && ok "gate HALTs on a corrupted dump copy (hash differs)"; }; cp -p "$T/keep" "$T/home/g1/g1/dumps/immich.no-postgis.dump"
cp -p "$T/immich-cutover-g1/immich.full.dump" "$T/keepo"; printf Q >> "$T/immich-cutover-g1/immich.full.dump"
G g1 "$T/md.ok" && bad "changed original must HALT" || { grep -q "FAIL G5" "$T/out" && ok "gate HALTs when the ORIGINAL dump no longer matches its recorded hash"; }; cp -p "$T/keepo" "$T/immich-cutover-g1/immich.full.dump"
chmod 600 "$T/home/g1/g1/dumps/SHA256SUMS"; cp -p "$T/home/g1/g1/dumps/SHA256SUMS" "$T/keepm"; echo "not a manifest line" >> "$T/home/g1/g1/dumps/SHA256SUMS"
G g1 "$T/md.ok" && bad "invalid manifest must HALT" || { grep -q "FAIL G3d" "$T/out" && ok "gate HALTs on a malformed copy manifest"; }; cp -p "$T/keepm" "$T/home/g1/g1/dumps/SHA256SUMS"
cp -p "$T/immich-cutover-g1/local-backup/dumps.sha256" "$T/keepd"; sed -i 's/^./0/' "$T/immich-cutover-g1/local-backup/dumps.sha256"
G g1 "$T/md.ok" && bad "wrong manifest hash must HALT" || ok "gate HALTs when the original manifest carries a wrong hash"; cp -p "$T/keepd" "$T/immich-cutover-g1/local-backup/dumps.sha256"
rm "$T/immich-cutover-g1/local-backup/dumps.sha256"; G g1 "$T/md.ok" && bad "missing manifest must HALT" || { grep -q "FAIL G3b" "$T/out" && ok "gate HALTs when a manifest file is missing"; }; cp -p "$T/keepd" "$T/immich-cutover-g1/local-backup/dumps.sha256"
mv "$T/immich-cutover-g1/local-backup/COPIES_DONE" "$T/cd"; G g1 "$T/md.ok" && bad "missing COPIES_DONE must HALT" || { grep -q "FAIL G3f" "$T/out" && ok "gate HALTs without COPIES_DONE"; }; mv "$T/cd" "$T/immich-cutover-g1/local-backup/COPIES_DONE"
mv "$T/immich-cutover-g1/immich.no-postgis.dump" "$T/np"; G g1 "$T/md.ok" && bad "missing second dump must HALT" || { grep -q "FAIL G4" "$T/out" && ok "gate HALTs when the sanitized dump is missing"; }; mv "$T/np" "$T/immich-cutover-g1/immich.no-postgis.dump"
G g1 "$T/md.ok" && ok "gate PASSES again after every mutation was undone" || bad "gate recovery"
( export CUTOVER_ID=g1 EV="$T/immich-cutover-g1" LB_ROOT="$T/home/g1" IMMICH_BACKUPS="$T/imm" LB_MDSTAT="$T/md.degraded"; unset LB_TEST CUTOVER_REHEARSAL; source ./local_backup.sh; lb_check ) > "$T/out" 2>&1 && bad "LB_MDSTAT override must be refused in production mode" || { grep -q "override refused" "$T/out" && ok "a simulated mdstat is refused outside test/rehearsal mode"; }

# ---- phase 8F: separate backup-only approval LB_BACKUP_ONLY_APPROVED=F0:<CUTOVER_ID> (valid ONLY for lb_copy_app_backup). Production-mode gate, ISOLATED /tmp paths, no production file touched.
touch "$T/imm/$F"; h8="$(sha256sum "$T/imm/$F" | cut -d' ' -f1)"
PM() { # PM <id> <token-or-empty> <CUTOVER_APPROVED-or-empty> <function...> : production-mode gate (no LB_TEST, no rehearsal), isolated paths
  local id="$1" tok="$2" appr="$3"; shift 3
  ( unset LB_TEST CUTOVER_REHEARSAL CUTOVER_APPROVED LB_BACKUP_ONLY_APPROVED LB_MDSTAT
    export CUTOVER_ID="$id" EV="$T/immich-cutover-$id" LB_ROOT="$T/home8/lb" IMMICH_BACKUPS="$T/imm" LB_MIN_FREE_GIB=1
    [ -z "$tok" ] || export LB_BACKUP_ONLY_APPROVED="$tok"; [ -z "$appr" ] || export CUTOVER_APPROVED="$appr"
    mkdir -p "$T/immich-cutover-$id"; source ./local_backup.sh; "$@" ) > "$T/out" 2>&1; }
case "$T" in /tmp/*) ;; *) echo "unsafe test dir"; exit 1;; esac
ID=f0test-20261115
PM $ID "" "" lb_copy_app_backup && bad "8F: no token must be refused" || { [ ! -e "$T/home8" ] && grep -q "refused" "$T/out" && ok "8F: no token -> refused, nothing created"; }
PM $ID "F0:other-id-999" "" lb_copy_app_backup && bad "8F: wrong id must be refused" || { [ ! -e "$T/home8" ] && grep -q "must be exactly F0:$ID" "$T/out" && ok "8F: token for a different CUTOVER_ID -> refused"; }
PM $ID "1" "" lb_copy_app_backup && bad "8F: token 1 must be refused" || { [ ! -e "$T/home8" ] && ok "8F: token '1' -> refused"; }
PM $ID "F6b:$ID" "" lb_copy_app_backup && bad "8F: token for another step must be refused" || { [ ! -e "$T/home8" ] && ok "8F: token for another step (F6b:<id>) -> refused"; }
PM $ID "$ID" "" lb_copy_app_backup && bad "8F: bare id must be refused" || ok "8F: bare CUTOVER_ID without the F0: prefix -> refused"
PM "ab" "F0:ab" "" lb_copy_app_backup && bad "8F: too short id must be refused" || ok "8F: too short CUTOVER_ID (< 6) -> refused even with a matching token"
# the F0 token must unlock nothing else
mkE "immich-cutover-$ID"; PM $ID "F0:$ID" "" lb_copy_cutover_dumps && bad "8F: F0 token must not unlock lb_copy_cutover_dumps (F6b)" || { [ ! -e "$T/home8/lb/$ID/dumps" ] && grep -q "CUTOVER_APPROVED" "$T/out" && ok "8F: F0 token does NOT unlock lb_copy_cutover_dumps (F6b still needs CUTOVER_APPROVED)"; }
STUB="$T/stubcalls"; : > "$STUB"
( unset LB_TEST CUTOVER_REHEARSAL CUTOVER_APPROVED; export LB_BACKUP_ONLY_APPROVED="F0:$ID" CUTOVER_ID="$ID" EV="$T/immich-cutover-$ID"
  docker() { echo "UNEXPECTED docker $*" >> "$STUB"; return 99; }; python3() { echo "UNEXPECTED python $*" >> "$STUB"; return 99; }
  source ./steps.sh
  for f in s_prepare_target s_freeze s_dump_source s_bridge_sanitize s_bridge_cleanup s_restore_target s_validate_target s_dark_launch s_open s_open_abort s_manual_forward s_manual_rollback_accept_loss s_rollback_r1 s_unfence s_target_reset_after_rollback lb_copy_cutover_dumps; do $f >/dev/null 2>&1; echo "$f rc=$?"; done ) > "$T/out2" 2>&1
n="$(grep -c ' rc=' "$T/out2")"; nz="$(grep ' rc=' "$T/out2" | grep -vc 'rc=0')"
[ "$n" = 16 ] && [ "$nz" = 16 ] && [ ! -s "$STUB" ] && ok "8F: with ONLY the F0 token all 16 mutating steps (s_freeze, s_open, s_manual_forward, F6b ...) are refused and no docker/python call is made" || { bad "8F: F0 token unlocked something"; cat "$T/out2" "$STUB" | head; }
# CUTOVER_APPROVED keeps working exactly as before (unchanged semantics)
PM $ID "" "wrong" lb_copy_app_backup && bad "8F: wrong CUTOVER_APPROVED must be refused" || ok "8F: CUTOVER_APPROVED with a wrong value is still refused (logic unchanged)"
# successful F0 with the token, isolated environment, real lb_check (read-only host state)
PM $ID "F0:$ID" "" lb_copy_app_backup && ok "8F: F0 copy succeeds with LB_BACKUP_ONLY_APPROVED=F0:<id> (isolated /tmp environment)" || { bad "8F: F0 copy with the token failed"; tail -5 "$T/out"; }
D8="$T/home8/lb/$ID"; AB="$D8/app-backup"
[ "$(sha256sum "$AB/$F" | cut -d' ' -f1)" = "$h8" ] && ok "8F: SHA-256 of the copy equals the source" || bad "8F: copy hash"
[ "$(cut -d' ' -f1 "$T/immich-cutover-$ID/local-backup/app-backup.sha256")" = "$h8" ] && [ "$(cut -d' ' -f1 "$AB/SHA256SUMS")" = "$h8" ] && grep -qE "^[0-9a-f]{64}  $F\$" "$AB/SHA256SUMS" && ok "8F: both manifests exist, valid, and carry the source hash" || bad "8F: manifests"
[ "$(stat -c %a "$AB/$F")" = 400 ] && [ "$(stat -c %a "$D8")" = 700 ] && [ "$(stat -c %a "$AB")" = 700 ] && [ "$(cat "$D8/CUTOVER_ID")" = "$ID" ] && ok "8F: permissions (file 0400, directories 0700) and the cutover-id marker" || bad "8F: permissions"
[ "$(sha256sum "$T/imm/$F" | cut -d' ' -f1)" = "$h8" ] && [ "$(ls "$T/imm" | wc -l)" = 1 ] && ok "8F: the source backup is unchanged and nothing else was created/removed there" || bad "8F: source changed"
PM $ID "F0:$ID" "" lb_verify && grep -q "lb_verify OK" "$T/out" && ok "8F: lb_verify passes after the F0 copy (needs no approval, read-only)" || bad "8F: lb_verify"
PM $ID "F0:$ID" "" lb_copy_app_backup && bad "8F: repeating F0 must be refused" || { grep -q "never overwrite" "$T/out" && ok "8F: repeating F0 into the same id is refused (no overwrite)"; }
[ "$FAILED" = 0 ] && echo "LOCAL BACKUP SELFTEST PASSED" || { echo "LOCAL BACKUP SELFTEST FAILED"; exit 1; }
