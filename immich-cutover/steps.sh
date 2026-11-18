#!/usr/bin/env bash
# Immich cutover steps (postgis -> immich-db). SOURCE this file, then call the step functions in runbook order.
# It is the single source of truth for the mutating commands of docs/postgres-migration/17-immich-production-cutover.md.
#
#   PRODUCTION : export CUTOVER_ID=...; export CUTOVER_APPROVED=$CUTOVER_ID   (only after written approval of the operations)
#   REHEARSAL  : export CUTOVER_REHEARSAL=1 and the isolated names (immich-apptest-*); production names are refused.
#
# Every mandatory operation checks its status explicitly. set -e is only a secondary guard;
# Bash disables it for functions called from if/&&/|| (including nested subshells).
# Nothing here prints a secret: the DB password is taken from the environment of the running application container (getsecret.py).

CV="${CV:-/opt/stacks/data/immich-cutover}"
PG_SRC="${PG_SRC:-postgis}"; PG_NEW="${PG_NEW:-immich-db}"; SRV="${SRV:-immich_server}"
MOPS="${MOPS-immich_media_operations}"; BRG="${BRG-nextcloud_immich_bridge}"            # empty in rehearsal (no such containers)
ENV_FILE="${IMMICH_ENV_FILE:-/opt/stacks/immich/.env}"
EVROOT="${EVROOT:-/opt/stacks/data/backups}"                                           # host directory that the target container mounts at /backups
BRIDGE_IMG="${BRIDGE_IMG:-sha256:33e372cc42ccaa91156d5072e48836abb2e532063dfdc79aa30e17df333a3bf0}"
DUMP_MIN_BYTES="${DUMP_MIN_BYTES:-200000000}"; DUMP_MAX_BYTES="${DUMP_MAX_BYTES:-500000000}"
DRAIN_TIMEOUT="${DRAIN_TIMEOUT:-600}"
PY="python3 -I"

declare -F idc  >/dev/null || idc()  { docker compose -p immich --project-directory /opt/stacks/immich -f /opt/stacks/immich/docker-compose.yml "$@"; }
declare -F idcd >/dev/null || idcd() { docker compose -p immich --project-directory /opt/stacks/immich -f /opt/stacks/immich/docker-compose.yml -f "$CV/docker-compose.dark.yml" "$@"; }
declare -F idb_up >/dev/null || idb_up() { ( cd /opt/stacks/data && docker compose -f docker-compose.postgres-new.yml up -d --no-build --pull never immich-db ); }

# Rehearsal: every docker call made by these steps goes through the guard + audit log (production names/paths/docker.sock are refused).
if [ "${CUTOVER_REHEARSAL:-0}" = 1 ]; then docker() { python3 -I "$CV/guarded_docker.py" "$@"; }; fi
HEALTH_TIMEOUT="${HEALTH_TIMEOUT:-180}"
# phase 7D: local backup protection (G14). lb_check / lb_copy_app_backup / lb_copy_cutover_dumps / lb_verify / lb_gate_open; sourced AFTER the rehearsal docker() wrapper so its docker calls are guarded too
. "$CV/local_backup.sh" || return 1

# Do not print command arguments: a future caller could pass a secret.
_die() { local rc="$1"; [ "$rc" -ne 0 ] || rc=1; echo "HALT: $2 (rc=$rc)" >&2; exit "$rc"; }
_must() { "$@" || _die "$?" "mandatory operation failed"; }
_expect() { local expected="$1" value; shift; value="$("$@")" || _die "$?" "cannot read mandatory evidence"; [ "$value" = "$expected" ] || _die 1 "mandatory evidence differs"; }
_server_host() { docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$SRV" | sed -n 's/^DB_HOSTNAME=//p' || return "$?"; }
_keys_required() { local k; for k in IMMICH_ADMIN_API_KEY IMMICH_USER_API_KEY; do [ -n "${!k:-}" ] || { echo "HALT: $k is not set" >&2; return 1; }; done; }
_api_verify() {
  _keys_required || _die "$?" "API keys required"
  local result
  result="$(mktemp "$EV/api-result.XXXXXX.json")" || _die "$?" "API receipt creation"
  $PY "$CV/api_checks.py" verify "$@" --result "$result" || _die "$?" "API verification failed"
  $PY "$CV/api_checks.py" check-result "$result" || _die "$?" "API verification receipt invalid"
  API_RESULT="$result"
}
_x() { echo "+ mandatory operation" >&2; _must "$@"; }
_wait_healthy() {
  local n="$1" t="${2:-180}" i health
  for ((i=0;i<t;i+=3)); do
    health="$(docker inspect -f '{{.State.Health.Status}}' "$n")" || return "$?"
    [ "$health" != healthy ] || return 0
    sleep 3 || return "$?"
  done
  echo "STOP: $n not healthy after ${t}s" >&2; return 1
}
_sql() { local c="$1"; shift; docker exec -i "$c" psql -X -U postgres -v ON_ERROR_STOP=1 "$@"; }

# ---- cutover state journal (phase 7B): the point of no return is decided by an explicit, hash-chained state and by live checks, never by the mere existence of a file
CS="$PY $CV/cutstate.py"
_st() { $CS get "$EV" || _die "$?" "journal read failed"; }                                                    # NONE | <STATE> | CORRUPT
_state_in() {
  local current allowed="$1"
  current="$(_st)" || _die "$?" "journal read failed"
  case ",$allowed," in *",$current,"*) return 0;; *) echo "REFUSED: state $current, expected $allowed" >&2; return 5;; esac
}
_st_set() { $CS set "$EV" --to "$1" --from "$2" --note "${3:-}" || _die "$?" "journal write failed"; }          # _st_set NEW "FROM1,FROM2" [note]
_mark() { local timestamp; timestamp="$(date -u +%FT%TZ)" || return "$?"; echo "$1 $timestamp" >> "$EV/freeze-order.log"; }
# fault injection for the rehearsal ONLY (ignored in production): CUTOVER_FAULT=<point> makes the step fail exactly there, as a killed script would
_fp() { if [ "${CUTOVER_REHEARSAL:-0}" = 1 ] && [ "${CUTOVER_FAULT:-}" = "$1" ]; then echo "FAULT INJECTED at $1" >&2; return 1; fi; return 0; }
declare -F idcf >/dev/null || idcf() { docker compose -p immich --project-directory /opt/stacks/immich -f /opt/stacks/immich/docker-compose.yml -f "$CV/docker-compose.frozen.yml" "$@"; }
declare -F _start_mops >/dev/null || _start_mops() { idc up -d --force-recreate --no-deps --no-build --pull never media-operations; }
ALLOW_STARTUP="${ALLOW_STARTUP:-system_metadata,version_history,plugin,plugin_method}"          # tables an application START may touch (everything else is a user/job write)

_gate() {
  [ -n "${CUTOVER_ID:-}" ] || { echo "CUTOVER_ID is not set" >&2; return 1; }
  [ -n "${EV:-}" ] || { echo "EV (evidence dir) is not set" >&2; return 1; }
  if [ "${CUTOVER_REHEARSAL:-0}" = 1 ]; then
    local n; for n in "$PG_SRC" "$PG_NEW" "$SRV"; do case "$n" in immich-apptest-*) ;; *) echo "REHEARSAL GUARD: $n is not an immich-apptest-* container" >&2; return 1;; esac; done
    for n in "$MOPS" "$BRG"; do [ -z "$n" ] || case "$n" in immich-apptest-*) ;; *) echo "REHEARSAL GUARD: $n" >&2; return 1;; esac; done
  else
    [ "${CUTOVER_APPROVED:-}" = "$CUTOVER_ID" ] || { echo "production step refused: export CUTOVER_APPROVED=$CUTOVER_ID only after the written approval of the operation" >&2; return 1; }
  fi
  $CS verify "$EV" >/dev/null || { echo "HALT: invalid journal" >&2; return 4; }
}

# ------------------------------------------------------------------ F2: target database role + database (needs the application container to exist: its environment is the password source)
s_prepare_target() { _gate || return "$?"; (
  set -Eeuo pipefail
  _state_in NONE,PREPARED || exit 5
  idb_up || _die "$?" "mandatory operation failed"
  _wait_healthy "$PG_NEW" "$HEALTH_TIMEOUT" || _die "$?" "mandatory operation failed"
  ver="$(docker exec "$PG_NEW" psql -X -U postgres -d postgres -Atc 'SHOW server_version')" || _die "$?" "mandatory evidence read failed"; case "$ver" in 16.16*) ;; *) echo "STOP: target version $ver" >&2; exit 1;; esac
  _expect 0 docker exec "$PG_NEW" psql -X -U postgres -d postgres -Atc "SELECT count(*) FROM pg_available_extensions WHERE name ILIKE 'postgis%'" || { echo "STOP: PostGIS available on target" >&2; exit 1; }
  # the exact string the application will present; trailing newlines/whitespace are preserved by the x-sentinel
  NEWPW="$($PY "$CV/getsecret.py" "$SRV" DB_PASSWORD && printf x)" || _die "$?" "password load failed"
  NEWPW="${NEWPW%x}"; export NEWPW
  docker exec -e NEWPW -i "$PG_NEW" psql -X -U postgres -d postgres -v ON_ERROR_STOP=1 <<'SQL' || _die "$?" "PostgreSQL operation failed"
\getenv pw NEWPW
CREATE ROLE immich LOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'pw';
CREATE DATABASE immich WITH OWNER immich TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'en_US.utf8' LC_CTYPE 'en_US.utf8';
SQL
  # prove a real scram login. 127.0.0.1 is `trust` inside the postgres image, so connect to the container's NETWORK address; a wrong password must be rejected.
  ip="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$PG_NEW" | awk '{print $1}')" || _die "$?" "mandatory evidence read failed"; [ -n "$ip" ] || _die 1 "target address missing"
  who="$(docker exec -e NEWPW "$PG_NEW" sh -c "PGPASSWORD=\"\$NEWPW\" psql -X -h $ip -U immich -d immich -Atc 'select current_user'")" || _die "$?" "mandatory evidence read failed"
  [ "$who" = immich ] || { echo "STOP: login as immich failed" >&2; exit 1; }
  if bad_login="$(docker exec "$PG_NEW" sh -c "PGPASSWORD='definitely-wrong' psql -X -h $ip -U immich -d immich -Atc 'select 1'" 2>&1)"; then
    _die 1 "wrong password was accepted"
  else
    bad_rc=$?
    [ "$bad_rc" = 2 ] && [[ "$bad_login" == *'password authentication failed'* ]] || _die 1 "negative login control inconclusive (Docker/network/SQL failure)"
  fi
  unset NEWPW; _st_set PREPARED NONE,PREPARED "target role+db ready"; echo "s_prepare_target OK"
); }

# F2 alternative ONLY for a reviewed existing role + empty template0 database.
# No Compose, CREATE/ALTER ROLE, CREATE DATABASE or extension DDL. Requires a
# separate approval; the Python process validates live evidence before journaling.
s_prepare_existing_target() { _gate || return "$?"; (
  set -Eeuo pipefail
  _state_in NONE || exit 5
  policy="$CV/policies/f2-20261115t150714z.json"
  if [ "${CUTOVER_REHEARSAL:-0}" = 1 ]; then
    : "${F2_EXISTING_POLICY:?isolated rehearsal policy required}"
    policy="$F2_EXISTING_POLICY"
  fi
  $PY "$CV/prepare_existing_target.py" --policy "$policy" --prepare || _die "$?" "existing-target F2 failed"
  _expect PREPARED _st
  echo "s_prepare_existing_target OK"
); }

# ------------------------------------------------------------------ F4: freeze ALL writers (order matters), drain, take the baseline from a frozen read-only instance, fence the source
# Order (phase 7B):  1 scripted writers stop (bridge, media-operations)  2 queues paused + drained  3 users cut (server stopped)  4 baseline from a
# route-less API-only instance on the SOURCE database  5 that instance stopped, 0 connections  6 source fenced  7 write probe A. Baseline and snapshot are therefore taken after every writer is frozen.
s_freeze() { _gate || return "$?"; (
  set -Eeuo pipefail
  service="$(_svc_name)" || _die "$?" "service lookup"
  _must _keys_required
  _must mkdir -p -m 700 "$EV"
  _st_set FREEZING NONE,PREPARED "freeze begins" || _die "$?" "mandatory operation failed"
  date -u +%FT%TZ | tee "$EV/T0" || _die "$?" "record T0"
  # ACL of the source database, saved for an exact rollback
  _sql "$PG_SRC" -d postgres -At -c "SELECT COALESCE(g.rolname,'PUBLIC')||'|'||x.privilege_type FROM pg_database d CROSS JOIN LATERAL aclexplode(COALESCE(d.datacl,acldefault('d',d.datdba))) x LEFT JOIN pg_roles g ON g.oid=x.grantee WHERE d.datname='immich' ORDER BY 1" > "$EV/source-db-acl.before" || _die "$?" "read source ACL"
  for c in $BRG $MOPS; do _x docker stop -t 60 "$c" || _die "$?" "stop writer"; _expect false docker inspect -f '{{.State.Running}}' "$c" || { echo "STOP-1: $c is still running" >&2; exit 1; }; done
  _mark scripted_writers_stopped || _die "$?" "mandatory operation failed"
  $PY "$CV/api_checks.py" queues pause --execute || _die "$?" "mandatory operation failed"
  $PY "$CV/api_checks.py" queues wait-drain --timeout "$DRAIN_TIMEOUT" || _die "$?" "mandatory operation failed" # exit != 0 => STOP-1 (recovery: s_rollback_r1)
  _mark queues_paused_and_drained || _die "$?" "mandatory operation failed"
  _x docker stop -t 60 "$SRV" || _die "$?" "stop server"; _expect false docker inspect -f '{{.State.Running}}' "$SRV" || { echo "STOP-1: $SRV is still running" >&2; exit 1; }
  _mark users_cut_server_stopped || _die "$?" "mandatory operation failed"
  n="$(docker exec "$PG_SRC" psql -X -U postgres -d postgres -Atc "SELECT count(*) FROM pg_stat_activity WHERE datname='immich'")" || _die "$?" "mandatory evidence read failed"
  [ "$n" = 0 ] || { echo "STOP-2: $n connections to the source database" >&2; exit 2; }
  # the verification baseline comes from a route-less, API-only instance on the (still unfenced) SOURCE: nobody can write through it
  TSF="$(date -u +%FT%TZ)" || _die "$?" "mandatory evidence read failed"
  idcf up -d --no-deps --no-build --pull never --force-recreate "$service" || _die "$?" "mandatory operation failed"
  _wait_healthy "$SRV" "$HEALTH_TIMEOUT" || _die "$?" "mandatory operation failed"
  _expect false docker inspect -f '{{index .Config.Labels "traefik.enable"}}' "$SRV" || { echo "STOP-1: frozen-read instance has a route" >&2; exit 1; }
  _expect "$PG_SRC" _server_host || { echo "STOP-1: frozen-read instance is not on the source database" >&2; exit 1; }
  docker logs --since "$TSF" "$SRV" 2>&1 | sed -E 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+/<email>/g' > "$EV/server-frozen-read.log" || _die "$?" "mandatory operation failed"
  _no_match -q 'Starting microservices worker' "$EV/server-frozen-read.log"
  $PY "$CV/api_checks.py" baseline --out "$EV/api-baseline.json" || _die "$?" "mandatory operation failed"
  _mark baseline_taken_after_all_writers_frozen || _die "$?" "mandatory operation failed"
  _x docker stop -t 60 "$SRV" || _die "$?" "stop server"
  _expect false docker inspect -f '{{.State.Running}}' "$SRV"
  n="$(docker exec "$PG_SRC" psql -X -U postgres -d postgres -Atc "SELECT count(*) FROM pg_stat_activity WHERE datname='immich'")" || _die "$?" "mandatory evidence read failed"
  [ "$n" = 0 ] || { echo "STOP-2: $n connections to the source database after the baseline" >&2; exit 2; }
  s_fence_inner || _die "$?" "mandatory operation failed"
  _mark source_fenced || _die "$?" "mandatory operation failed"
  $PY "$CV/write_probe.py" capture --container "$PG_SRC" --out "$EV/write-probe-frozen-A.json" || _die "$?" "mandatory operation failed"
  _st_set FROZEN FREEZING "all writers frozen, baseline taken, source fenced" || _die "$?" "mandatory operation failed"
  echo "s_freeze OK"
); }
s_fence_inner() { _sql "$PG_SRC" -d postgres <<'SQL' || _die "$?" "PostgreSQL operation failed"
REVOKE CONNECT ON DATABASE immich FROM PUBLIC;
REVOKE CONNECT ON DATABASE immich FROM immich;
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='immich' AND pid<>pg_backend_pid();
SQL
}
s_unfence() { _gate || return "$?"; ( set -Eeuo pipefail; [ -s "$EV/source-db-acl.before" ] || _die 1 "source ACL evidence missing"; _sql "$PG_SRC" -d postgres <<'SQL' || _die "$?" "PostgreSQL operation failed"
GRANT CONNECT ON DATABASE immich TO PUBLIC;
GRANT CONNECT ON DATABASE immich TO immich;
SQL
  rc=$?; [ "$rc" -eq 0 ] || exit "$rc"
  _sql "$PG_SRC" -d postgres -At -c "SELECT COALESCE(g.rolname,'PUBLIC')||'|'||x.privilege_type FROM pg_database d CROSS JOIN LATERAL aclexplode(COALESCE(d.datacl,acldefault('d',d.datdba))) x LEFT JOIN pg_roles g ON g.oid=x.grantee WHERE d.datname='immich' ORDER BY 1" > "$EV/source-db-acl.after" || exit "$?"
  diff "$EV/source-db-acl.before" "$EV/source-db-acl.after" || exit "$?"
  echo "source ACL restored exactly"
); }

# ------------------------------------------------------------------ F5: snapshot + dump of the (frozen) source
s_dump_source() { _gate || return "$?"; (
  set -Eeuo pipefail
  _state_in FROZEN || exit 5
  _absent "$EV/immich.full.dump" "$EV/immich.full.dump.partial" "$EV/immich.full.dump.sha256"
  $PY "$CV/db_snapshot.py" snapshot --container "$PG_SRC" --out "$EV/src" || _die "$?" "mandatory operation failed"
  # proof that nothing wrote between "all writers frozen" (probe A) and the snapshot/dump: strict, no allow-list
  $PY "$CV/write_probe.py" capture --container "$PG_SRC" --out "$EV/write-probe-frozen-B.json" || _die "$?" "mandatory operation failed"
  $PY "$CV/write_probe.py" check --before "$EV/write-probe-frozen-A.json" --after "$EV/write-probe-frozen-B.json" --allow '' --report "$EV/freeze-gap-proof.json" || _die "$?" "mandatory operation failed"
  docker exec "$PG_SRC" pg_dump -U postgres -d immich --format=custom --compress=gzip:6 --lock-wait-timeout=5s > "$EV/immich.full.dump.partial" 2> "$EV/immich.full.dump.log" || _die "$?" "mandatory operation failed"
  [ ! -s "$EV/immich.full.dump.log" ] || { echo "STOP-3: pg_dump wrote to its log" >&2; exit 1; }
  sz="$(stat -c %s "$EV/immich.full.dump.partial")" || _die "$?" "mandatory evidence read failed"; { [ "$sz" -ge "$DUMP_MIN_BYTES" ] && [ "$sz" -le "$DUMP_MAX_BYTES" ]; } || { echo "STOP-3: dump size $sz outside [$DUMP_MIN_BYTES,$DUMP_MAX_BYTES]" >&2; exit 1; }
  docker exec -i "$PG_SRC" pg_restore --list < "$EV/immich.full.dump.partial" | wc -l > "$EV/immich.full.dump.toc-lines" || _die "$?" "mandatory operation failed" # archive must be readable
  toc_lines="$(cat "$EV/immich.full.dump.toc-lines")" || _die "$?" "read archive TOC size"
  [[ "$toc_lines" =~ ^[[:space:]]*[0-9]+$ ]] && [ "$toc_lines" -gt 1000 ] || _die 1 "archive TOC too small or invalid"
  _must mv -n "$EV/immich.full.dump.partial" "$EV/immich.full.dump"
  sha256sum "$EV/immich.full.dump" | tee "$EV/immich.full.dump.sha256" || _die "$?" "hash or comparison failed"
  docker exec "$PG_SRC" psql -X -U postgres -d immich -At -c "COPY (SELECT * FROM public.spatial_ref_sys ORDER BY srid) TO STDOUT WITH (FORMAT CSV, HEADER)" > "$EV/spatial_ref_sys.source.csv" || _die "$?" "mandatory operation failed"
  [ -s "$EV/spatial_ref_sys.source.csv" ] || _die "$?" "mandatory assertion failed"
  dump_hash="$(_file_sha "$EV/immich.full.dump")" || _die "$?" "dump hash"
  _st_set DUMPED FROZEN "dump sha ${dump_hash:0:16}" || _die "$?" "mandatory operation failed"
  echo "s_dump_source OK"
); }

# ------------------------------------------------------------------ F6: sanitize on a private bridge container; data+metadata compared BEFORE and AFTER DROP EXTENSION
s_bridge_sanitize() { _gate || return "$?"; (
  set -Eeuo pipefail
  : "${BR:?set BR (bridge container name)}" "${WB:?set WB (bridge work dir)}"
  _state_in DUMPED,SANITIZED || exit 5
  _absent "$EV/immich.no-postgis.dump" "$EV/immich.no-postgis.dump.partial" "$EV/immich.no-postgis.dump.sha256"
  _must sha256sum --check "$EV/immich.full.dump.sha256"
  export CUTOVER_BRIDGE_CONTAINER="$BR"
  [ ! -e "$WB" ] || { echo "STOP: $WB already exists" >&2; exit 1; }
  _must mkdir -m 700 "$WB" "$WB/bridge-data"; _must chown 999:999 "$WB/bridge-data"
  _x docker run -d --name "$BR" --label immich.cutover="$CUTOVER_ID" --network none --restart no --memory 4g --cpus 2 --shm-size 1g \
    --mount type=bind,src="$WB/bridge-data",dst=/var/lib/postgresql/data --mount type=bind,src="$EV",dst=/restore,readonly \
    -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_USER=postgres -e POSTGRES_DB=postgres -e 'POSTGRES_INITDB_ARGS=--encoding=UTF8 --locale=en_US.utf8' \
    "$BRIDGE_IMG" postgres -c shared_preload_libraries=vchord -c shared_buffers=256MB -c max_connections=20 -c TimeZone=Europe/Zagreb || _die "$?" "start bridge"
  for ((i=0;i<120;i++)); do docker exec "$BR" pg_isready -U postgres -d postgres >/dev/null 2>&1 && [ "$(docker exec "$BR" cat /proc/1/comm)" = postgres ] && break; sleep 1; done
  _must sleep 2; _must docker exec "$BR" pg_isready -U postgres -d postgres
  _expect postgres docker exec "$BR" cat /proc/1/comm
  _sql "$BR" -d postgres <<'SQL' || _die "$?" "PostgreSQL operation failed"
CREATE ROLE immich NOLOGIN INHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE DATABASE immich_restore_stage WITH OWNER immich TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'en_US.utf8' LC_CTYPE 'en_US.utf8';
SQL
  docker exec "$BR" pg_restore -U postgres --dbname=immich_restore_stage --exit-on-error --jobs=2 /restore/immich.full.dump > "$EV/bridge.restore.log" 2>&1 || _die "$?" "mandatory operation failed"
  [ ! -s "$EV/bridge.restore.log" ] || { echo "STOP-4: bridge restore log not empty" >&2; exit 1; }
  # identity sequence: pg_restore re-derives integer; normalise (same statement as on the target) so the strict comparison is meaningful
  _sql "$BR" -d immich_restore_stage -c "ALTER SEQUENCE public.naturalearth_countries_tmp_id_seq1 AS bigint MINVALUE 1 MAXVALUE 2147483647 START WITH 1 INCREMENT BY 1 CACHE 1 NO CYCLE;" || _die "$?" "mandatory operation failed"
  # DATA + METADATA of the bridge copy vs the frozen source, BEFORE PostGIS is dropped (owners, ACLs, sequences, indexes, extensions, 72 hashes)
  $PY "$CV/db_snapshot.py" snapshot --container "$BR" --db immich_restore_stage --out "$EV/bridge-before" || _die "$?" "mandatory operation failed"
  $PY "$CV/db_snapshot.py" compare --mode source-bridge --source "$EV/src" --target "$EV/bridge-before" --report "$EV/compare-source-bridge.json" > /dev/null || _die "$?" "mandatory operation failed"
  _sql "$BR" -d immich_restore_stage -c 'DROP EXTENSION postgis RESTRICT;' || _die "$?" "mandatory operation failed" # never CASCADE
  $PY "$CV/db_snapshot.py" snapshot --container "$BR" --db immich_restore_stage --out "$EV/bridge-after" || _die "$?" "mandatory operation failed"
  $PY "$CV/db_snapshot.py" compare --mode source-bridge-after --source "$EV/src" --target "$EV/bridge-after" --report "$EV/compare-source-bridge-after.json" > /dev/null || _die "$?" "mandatory operation failed"
  docker exec "$BR" pg_dump -U postgres -d immich_restore_stage --format=custom --compress=gzip:6 > "$EV/immich.no-postgis.dump.partial" 2> "$EV/immich.no-postgis.dump.log" || _die "$?" "mandatory operation failed"
  [ ! -s "$EV/immich.no-postgis.dump.log" ] || _die "$?" "mandatory assertion failed"
  _must mv -n "$EV/immich.no-postgis.dump.partial" "$EV/immich.no-postgis.dump"
  sha256sum "$EV/immich.no-postgis.dump" | tee "$EV/immich.no-postgis.dump.sha256" || _die "$?" "hash or comparison failed"
  docker exec "$BR" pg_restore --list /restore/immich.no-postgis.dump > "$EV/immich.no-postgis.toc" || _die "$?" "mandatory operation failed"
  _no_match -qiE 'postgis|spatial_ref_sys' "$EV/immich.no-postgis.toc"
  _st_set SANITIZED DUMPED,SANITIZED "sanitized dump written" || _die "$?" "mandatory operation failed"
  echo "s_bridge_sanitize OK"
); }
s_bridge_cleanup() { _gate || return "$?"; ( set -Eeuo pipefail
  : "${BR:?}" "${WB:?}"
  _expect "$CUTOVER_ID" docker inspect -f '{{index .Config.Labels "immich.cutover"}}' "$BR" || { echo "label mismatch: refusing to remove $BR" >&2; exit 1; }
  bridge_real="$(realpath "$WB")" || _die "$?" "bridge realpath"
  case "$bridge_real" in /tmp/immich-cutover-*|/tmp/immich-apptest-*) ;; *) echo "refusing to delete $WB" >&2; exit 1;; esac
  _must docker rm -f "$BR"; _must rm -rf -- "$WB"; echo "bridge removed"
); }

# ------------------------------------------------------------------ F7: restore into the target, ACL + sequence, compare, validate
s_restore_target() { _gate || return "$?"; (
  set -Eeuo pipefail
  _state_in SANITIZED || exit 5
  [ "${EV%/*}" = "$EVROOT" ] || { echo "STOP: $EV must be directly under $EVROOT (the directory mounted at /backups in $PG_NEW)" >&2; exit 1; }
  dumppath="/backups/${EV##*/}/immich.no-postgis.dump"
  docker exec "$PG_NEW" test -r "$dumppath" || { echo "STOP: $dumppath is not readable inside $PG_NEW" >&2; exit 1; }
  recorded_hash="$(cut -d' ' -f1 "$EV/immich.no-postgis.dump.sha256")" || _die "$?" "read dump hash"
  [[ "$recorded_hash" =~ ^[0-9a-f]{64}$ ]] || _die 1 "malformed dump hash"
  target_hash="$(docker exec "$PG_NEW" sha256sum "$dumppath")" || _die "$?" "hash target dump"
  [ "${target_hash%% *}" = "$recorded_hash" ] || _die 1 "target dump hash differs"
  docker exec "$PG_NEW" pg_restore -U postgres --dbname=immich --exit-on-error --jobs=2 "$dumppath" > "$EV/target.restore.log" 2>&1 || _die "$?" "mandatory operation failed"
  [ ! -s "$EV/target.restore.log" ] || { echo "STOP-5: target restore log not empty" >&2; exit 1; }
  _sql "$PG_NEW" -d immich <<'SQL' || _die "$?" "PostgreSQL operation failed"
SET ROLE immich;
REVOKE ALL ON DATABASE immich FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE immich TO PUBLIC;
GRANT CREATE, CONNECT, TEMPORARY ON DATABASE immich TO immich;
RESET ROLE;
ALTER SEQUENCE public.naturalearth_countries_tmp_id_seq1 AS bigint MINVALUE 1 MAXVALUE 2147483647 START WITH 1 INCREMENT BY 1 CACHE 1 NO CYCLE;
SQL
  _st_set RESTORED SANITIZED "restored into the target" || _die "$?" "mandatory operation failed"
  echo "s_restore_target OK"
); }
# validation of the restored target against the frozen source snapshot (SRC_SNAPSHOT_DIR defaults to $EV/src)
s_validate_target() { _gate || return "$?"; (
  set -Eeuo pipefail
  _state_in RESTORED,VALIDATED || exit 5
  $PY "$CV/db_snapshot.py" snapshot --container "$PG_NEW" --out "$EV/dst" || _die "$?" "mandatory operation failed"
  $PY "$CV/db_snapshot.py" compare --mode source-target --source "${SRC_SNAPSHOT_DIR:-$EV/src}" --target "$EV/dst" --report "$EV/compare.json" > /dev/null || _die "$?" "mandatory operation failed"
  BASELINE="$(ls -t "$EV"/baseline-*.json | head -1)" || _die "$?" "mandatory evidence read failed"
  $PY "$CV/validate_target.py" --baseline "$BASELINE" --source-snapshot "${SRC_SNAPSHOT_DIR:-$EV/src}" ${VALIDATE_ARGS:---amcheck} || _die "$?" "mandatory operation failed"
  _sql "$PG_NEW" -d immich -c 'ANALYZE;' || _die "$?" "mandatory operation failed"
  _st_set VALIDATED RESTORED,VALIDATED "validate_target PASS" || _die "$?" "mandatory operation failed"
  echo "s_validate_target OK"
); }
s_restore_and_validate() { s_restore_target || return "$?"; s_validate_target || return "$?"; }

# retry after rollback R1: the failed attempt's database is renamed (never dropped) and an empty one is created
s_target_reset_after_rollback() { _gate || return "$?"; ( set -Eeuo pipefail
  : "${PREV_EV:?set PREV_EV to the evidence directory of the rolled-back attempt}"
  prev_state="$($CS get "$PREV_EV")" || _die "$?" "previous journal read"
  case "$prev_state" in ROLLED_BACK|ROLLED_BACK_LOSS_ACCEPTED) ;; *) echo "REFUSED: $PREV_EV is not in a rolled-back state" >&2; exit 3;; esac
  _state_in NONE,PREPARED || exit 3
  rename_suffix="$(echo "$CUTOVER_ID" | tr -c 'A-Za-z0-9' '_')" || _die "$?" "target archive name"
  _sql "$PG_NEW" -d postgres <<SQL || _die "$?" "PostgreSQL operation failed"
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='immich' AND pid<>pg_backend_pid();
ALTER DATABASE immich RENAME TO immich_failed_${rename_suffix};
CREATE DATABASE immich WITH OWNER immich TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'en_US.utf8' LC_CTYPE 'en_US.utf8';
SQL
  echo "target database renamed, empty immich created"
); }

# ------------------------------------------------------------------ F8: dark launch (no Traefik route) + validation
s_dark_launch() { _gate || return "$?"; (
  set -Eeuo pipefail
  service="$(_svc_name)" || _die "$?" "service lookup"
  _must _keys_required
  prev="$(_st)" || _die "$?" "mandatory evidence read failed"
  case "$prev" in VALIDATED|DARK_VERIFIED|ABORT_VERIFIED) ;; *) echo "REFUSED: s_dark_launch needs state VALIDATED or ABORT_VERIFIED (is: $(_st))" >&2; exit 5;; esac
  if [ -e "$EV/dark-verified.json" ]; then
    archive="$(mktemp "$EV/dark-verified.previous.XXXXXX.json")" || _die "$?" "archive old dark seal"
    _must mv "$EV/dark-verified.json" "$archive"
  fi
  TS="$(date -u +%FT%TZ)" || _die "$?" "mandatory evidence read failed"
  idcd up -d --no-deps --no-build --pull never --force-recreate "$service" || _die "$?" "mandatory operation failed"
  _wait_healthy "$SRV" "$HEALTH_TIMEOUT" || _die "$?" "mandatory operation failed"
  _expect false docker inspect -f '{{index .Config.Labels "traefik.enable"}}' "$SRV" || { echo "STOP-6: traefik.enable is not false in dark mode" >&2; exit 1; }
  _expect "$PG_NEW" _server_host || { echo "STOP-6: DB_HOSTNAME is not $PG_NEW" >&2; exit 1; }
  docker logs --since "$TS" "$SRV" 2>&1 | sed -E 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+/<email>/g' > "$EV/server-dark.log" || _die "$?" "mandatory operation failed"
  _no_match -q 'Starting microservices worker' "$EV/server-dark.log"
  for p in 'Starting api worker' 'No schema drift detected' 'Finished running migrations' 'targetLists=1, current=1 for clip_index' 'targetLists=1, current=1 for face_index'; do grep -q "$p" "$EV/server-dark.log" || { echo "STOP-6: missing log line: $p" >&2; exit 1; }; done
  _no_match -E 'Migration ".+" succeeded|Reindex|(Creating|Dropping|Updating) .* extension|\bERROR\b|\bFATAL\b' "$EV/server-dark.log"
  # after s_open_abort from a state in which the full server ran, the application has itself RESUMED metadataExtraction (MetadataService does that at every microservices start); nothing could run
  # (server stopped, write-freedom proven), so the queues are paused again here, before the verification, to restore the frozen state
  if [ "$prev" = ABORT_VERIFIED ]; then _must $PY "$CV/api_checks.py" queues pause --execute; fi
  _api_verify --baseline "$EV/api-baseline.json" --allow-paused --out "$EV/api-dark.json" || _die "$?" "mandatory operation failed"
  if [ -e "$EV/dst2" ]; then
    previous_snapshot="$(mktemp -d "$EV/dst2.previous.XXXXXX")" || _die "$?" "archive old snapshot"
    _must mv "$EV/dst2" "$previous_snapshot/snapshot"
  fi #          # a retry after s_open_abort keeps the earlier evidence
  $PY "$CV/db_snapshot.py" snapshot --container "$PG_NEW" --out "$EV/dst2" || _die "$?" "mandatory operation failed"
  $PY "$CV/db_snapshot.py" delta --before "$EV/dst" --after "$EV/dst2" > "$EV/dark-delta.json" || _die "$?" "mandatory operation failed"
  _expect 0 docker exec "$PG_SRC" psql -X -U postgres -d postgres -Atc "SELECT count(*) FROM pg_stat_activity WHERE datname='immich'" || { echo "STOP-6: source has connections in dark phase" >&2; exit 1; }
  # baseline of write activity on the target at the moment it is proven clean: s_open_abort compares against this
  $PY "$CV/write_probe.py" capture --container "$PG_NEW" --out "$EV/write-probe-dark.json" || _die "$?" "mandatory operation failed"
  $PY "$CV/safety_evidence.py" seal "$EV" "$CUTOVER_ID" "$PG_NEW" "$API_RESULT" || _die "$?" "F8 evidence seal failed"
  _st_set DARK_VERIFIED VALIDATED,DARK_VERIFIED,ABORT_VERIFIED "dark launch verified; write probe recorded" || _die "$?" "mandatory operation failed"
  echo "s_dark_launch OK"
); }
declare -F _svc_name >/dev/null || _svc_name() { echo immich-server; }


# ------------------------------------------------------------------ F10: OPEN TRAFFIC (explicit state machine, see cutstate.py)
# DARK_VERIFIED -> OPEN_BEGIN -> ENV_CHANGED -> RECREATING -> RECREATED -> ROUTE_LIVE (users can reach the new database from here) -> AUX_STARTED -> RESUMING -> OPEN_CONFIRMED
# Up to AUX_STARTED a failure can be recovered by s_open_abort, but ONLY with proof that the new database received no write. RESUMING/OPEN_CONFIRMED = point of no return (workers resumed).
_file_sha() {
  local value
  value="$(sha256sum "$1")" || return "$?"
  value="${value%% *}"
  [[ "$value" =~ ^[0-9a-f]{64}$ ]] || return 1
  printf '%s\n' "$value"
}
_env_sha() { _file_sha "$ENV_FILE"; }
_no_match() { local rc; if grep "$@"; then _die 1 "forbidden match"; else rc=$?; [ "$rc" -eq 1 ] || _die "$rc" "grep failed"; fi; }
_absent() { local f; for f in "$@"; do [ ! -e "$f" ] || _die 1 "refusing to overwrite existing evidence"; done; }
s_open() { _gate || return "$?"; (
  set -Eeuo pipefail
  service="$(_svc_name)" || _die "$?" "service lookup"
  _must _keys_required
  _state_in DARK_VERIFIED || exit 5
  # G14 backup gate: BEFORE any change (no .env edit, no container action, no journal entry). Failure = HALT (exit 6), traffic stays closed, state stays DARK_VERIFIED.
  lb_gate_open || { echo "HALT (G14): the local backup gate failed; nothing was changed. See $EV/local-backup/BACKUP-GATE-HALT.txt. s_open will not run until lb_gate_open passes." >&2; exit 6; }
  $PY "$CV/safety_evidence.py" check "$EV" "$CUTOVER_ID" "$PG_NEW" || _die "$?" "complete F8 evidence required before opening"
  trap 'rc=$?; [ $rc -eq 0 ] || echo "s_open FAILED (rc=$rc) in state $(_st): do NOT improvise. Run s_open_abort (it proves or refuses safety). Never run s_rollback_r1 now." >&2' EXIT
  [ -s "$EV/write-probe-dark.json" ] || { echo "STOP: write-probe-dark.json missing" >&2; exit 1; }
  grep -q "^DB_HOSTNAME=$PG_SRC\$" "$ENV_FILE" || { echo "STOP: DB_HOSTNAME=$PG_SRC not found in $ENV_FILE (already switched?)" >&2; exit 1; }
  _expect false docker inspect -f '{{index .Config.Labels "traefik.enable"}}' "$SRV" || { echo "STOP: s_open is only valid after a successful dark launch" >&2; exit 1; }
  _must cp -p "$ENV_FILE" "$EV/immich.env.before"; _must chmod 600 "$EV/immich.env.before"
  _env_sha > "$EV/env.before.sha256" || _die "$?" "record before hash"
  before_hash="$(cat "$EV/env.before.sha256")" || _die "$?" "read before hash"
  _expect "$before_hash" _file_sha "$EV/immich.env.before"
  date -u +%FT%TZ > "$EV/T_open_begin" || _die "$?" "record open begin"
  gate_hash="$(_file_sha "$EV/local-backup/gate.log")" || _die "$?" "backup gate hash"
  _st_set OPEN_BEGIN DARK_VERIFIED "env before ${before_hash:0:16}; backup gate PASS ${gate_hash:0:12}" || _die "$?" "mandatory operation failed"
  _fp before-env-edit || _die "$?" "mandatory operation failed"
  # the expected new content is built and its hash recorded BEFORE .env is touched, so a crash at any moment leaves a recoverable, provable state
  sed "s/^DB_HOSTNAME=$PG_SRC\$/DB_HOSTNAME=$PG_NEW/" "$EV/immich.env.before" > "$EV/immich.env.after" || _die "$?" "build expected env"
  _must chmod 600 "$EV/immich.env.after"
  sha256sum "$EV/immich.env.after" | cut -d' ' -f1 > "$EV/env.after.sha256" || _die "$?" "hash or comparison failed"
  $PY - "$EV/immich.env.before" "$EV/immich.env.after" "$PG_SRC" "$PG_NEW" <<'PYENV' || _die "$?" "unexpected env change"
import pathlib, sys
before, after = (pathlib.Path(p).read_bytes() for p in sys.argv[1:3])
old, new = (('DB_HOSTNAME='+s).encode() for s in sys.argv[3:5])
lines = before.splitlines(keepends=True)
assert sum(line.rstrip(b'\r\n') == old for line in lines) == 1
assert after == b''.join(new+line[len(old):] if line.rstrip(b'\r\n') == old else line for line in lines)
PYENV
  _expect 1 grep -c "^DB_HOSTNAME=$PG_NEW\$" "$EV/immich.env.after"
  cat "$EV/immich.env.after" > "$ENV_FILE" || _die "$?" "write env"
  after_hash="$(cat "$EV/env.after.sha256")" || _die "$?" "read after hash"
  _expect "$after_hash" _env_sha
  _st_set ENV_CHANGED OPEN_BEGIN "env after ${after_hash:0:16}" || _die "$?" "mandatory operation failed"
  _fp after-env-edit || _die "$?" "mandatory operation failed"
  _st_set RECREATING ENV_CHANGED "compose recreate starting" || _die "$?" "mandatory operation failed"
  idc up -d --force-recreate --no-deps --no-build --pull never "$service" || _die "$?" "mandatory operation failed"
  _fp during-recreate || _die "$?" "mandatory operation failed"
  _st_set RECREATED RECREATING "compose recreate returned" || _die "$?" "mandatory operation failed"
  _fp before-health || _die "$?" "mandatory operation failed"
  _wait_healthy "$SRV" "$HEALTH_TIMEOUT" || _die "$?" "mandatory operation failed"
  _expect true docker inspect -f '{{index .Config.Labels "traefik.enable"}}' "$SRV" || { echo "STOP: route label not restored" >&2; exit 1; }
  _expect "$PG_NEW" _server_host
  date -u +%FT%TZ > "$EV/T_open" || _die "$?" "record public route time"                                   # first moment users can reach the new database (informational; the journal decides)
  _st_set ROUTE_LIVE RECREATED "healthy with route label true" || _die "$?" "mandatory operation failed"
  _fp after-route || _die "$?" "mandatory operation failed"
  if [ -n "$MOPS" ]; then _must _start_mops; fi
  if [ -n "$BRG" ]; then _must docker start "$BRG"; fi
  _st_set AUX_STARTED ROUTE_LIVE "media-operations and bridge started" || _die "$?" "mandatory operation failed"
  _fp before-resume || _die "$?" "mandatory operation failed"
  _st_set RESUMING AUX_STARTED "resuming queues: point of no return" || _die "$?" "mandatory operation failed"
  $PY "$CV/api_checks.py" queues resume --execute || _die "$?" "mandatory operation failed"
  _st_set OPEN_CONFIRMED RESUMING "queues resumed" || _die "$?" "mandatory operation failed"
  echo "s_open OK (POINT OF NO RETURN passed)"
); }

# ------------------------------------------------------------------ s_open_abort: recover a PARTIALLY failed open, only with PROOF that the new database received no write
_halt_report() { {
  echo "HALT: automatic rollback is FORBIDDEN. Cutover $CUTOVER_ID, state $(_st), $(date -u +%FT%TZ)."
  echo "Reason: $1"; echo "Evidence: $EV/abort-evidence.log"; echo
  echo "Manual GO/NO-GO is required. The new database may hold data that does not exist in the source."
  echo "  1. Assess: new rows in the target (asset/session/album createdAt > $(cat "$EV/T_open_begin" 2>/dev/null)), new files under the upload directory."
  echo "  2. GO  (keep the new database, finish the opening):   export CUTOVER_MANUAL_DECISION=FORWARD:$CUTOVER_ID; s_manual_forward"
  echo "  3. NO-GO (back to the source, ACCEPT loss of everything written to the new database; it is kept, not deleted):"
  echo "                                                      export CUTOVER_MANUAL_DECISION=ROLLBACK_ACCEPT_LOSS:$CUTOVER_ID; s_manual_rollback_accept_loss"
  echo "Nothing was deleted. The server is stopped. Do not run s_rollback_r1 (it will refuse)."
} > "$EV/HALT-REPORT.txt" || _die "$?" "write HALT report"; _must cat "$EV/HALT-REPORT.txt" >&2; }

s_open_abort() { _gate || return "$?"; (
  set -Eeuo pipefail
  cur="$(_st)" || _die "$?" "mandatory evidence read failed"
  case "$cur" in
    CORRUPT) echo "HALT: the state journal is corrupt; no automatic action is taken (nothing changed). Manual decision required." >&2; exit 4;;
    RESUMING|OPEN_CONFIRMED) echo "REFUSED: state $cur is past the point of no return; there is no automatic abort (R2 is a manual decision)" >&2; exit 3;;
    HALT_MANUAL) echo "HALT: already in HALT_MANUAL; see $EV/HALT-REPORT.txt" >&2; exit 4;;
    OPEN_BEGIN|ENV_CHANGED|RECREATING|RECREATED|ROUTE_LIVE|AUX_STARTED|ABORT_BEGIN) ;;
    *) echo "REFUSED: nothing to abort in state $cur" >&2; exit 5;;
  esac
  [ "$cur" = ABORT_BEGIN ] || _st_set ABORT_BEGIN "$cur" "abort from $cur" || exit 5
  : > "$EV/abort-evidence.log" || _die "$?" "create abort evidence"
  _must chmod 600 "$EV/abort-evidence.log"
  ev() { echo "$1 $2 $3" >> "$EV/abort-evidence.log" || _die "$?" "write abort evidence"; echo "$1 $2 $3" >&2; [ "$1" = PASS ] || bad=1; }
  bad=0
  # 1) cut every possible writer first (stopping can only reduce writes), then collect the evidence
  for c in $BRG $MOPS "$SRV"; do
    _must docker stop -t 60 "$c"
    _expect false docker inspect -f '{{.State.Running}}' "$c"
  done
  for c in $BRG $MOPS "$SRV"; do
    _expect false docker inspect -f '{{.State.Running}}' "$c"
    ev PASS E1 "$c is stopped"
  done
   $CS verify "$EV" >/dev/null 2>&1 && ev PASS E2 "state journal chain valid" || ev FAIL E2 "state journal corrupt"
  nconn="$(docker exec "$PG_NEW" psql -X -U postgres -d postgres -Atc "SELECT count(*) FROM pg_stat_activity WHERE datname='immich' AND usename='immich'" 2>/dev/null)" || _die "$?" "mandatory evidence read failed"
  [ "$nconn" = 0 ] && ev PASS E3 "no application connection to the new database" || ev FAIL E3 "application connections to the new database: ${nconn:-unknown}"
  # 2) database evidence: statistics/sequences since the dark-launch probe, and content hashes against the dark-launch snapshot
  if [ -s "$EV/write-probe-dark.json" ] && $PY "$CV/write_probe.py" capture --container "$PG_NEW" --out "$EV/write-probe-abort.json" >/dev/null 2>&1; then
    if $PY "$CV/write_probe.py" check --before "$EV/write-probe-dark.json" --after "$EV/write-probe-abort.json" --allow "$ALLOW_STARTUP" --report "$EV/abort-write-probe.json" >> "$EV/abort-evidence.log" 2>&1; then ev PASS E4 "write probe: no insert/update/delete/sequence activity outside $ALLOW_STARTUP"; else ev FAIL E4 "write probe: activity or not provable (see abort-write-probe.json)"; fi
  else ev FAIL E4 "write probe unavailable (UNKNOWN is not proof)"; fi
  abort_snapshot="$(mktemp -d "$EV/dst-abort.XXXXXX")" || _die "$?" "abort snapshot directory"
  if [ -d "$EV/dst2" ] && $PY "$CV/db_snapshot.py" snapshot --container "$PG_NEW" --out "$abort_snapshot" >/dev/null 2>&1 && $PY "$CV/db_snapshot.py" delta --before "$EV/dst2" --after "$abort_snapshot" --allow "$ALLOW_STARTUP" > "$EV/abort-delta.json" 2>/dev/null; then ev PASS E5 "72 table hashes and metadata equal to the dark-launch snapshot (allow-list $ALLOW_STARTUP)"; else ev FAIL E5 "table content or metadata differs from the dark-launch snapshot, or snapshot failed"; fi
  # 3) file evidence: no file written under the upload directory since T0
  UPD="$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$SRV" 2>/dev/null)/upload" || _die "$?" "mandatory evidence read failed"
  if [ -d "$UPD" ] && [ -s "$EV/T0" ]; then
    if [ "${CUTOVER_REHEARSAL:-0}" = 1 ]; then case "$UPD" in /tmp/immich-apptest-*) ;; *) echo "REHEARSAL GUARD: $UPD" >&2; exit 1;; esac; fi
    t0="$(cat "$EV/T0")" || _die "$?" "read T0"
    newf="$(find "$UPD" -type f -newerct "$t0" ! -name '.immich' -print -quit 2>/dev/null)" || _die "$?" "upload scan failed"
    [ -z "$newf" ] && ev PASS E6 "no file under the upload directory was created/changed (ctime) since T0" || ev FAIL E6 "a file under the upload directory has ctime after T0 (a user upload reached the server; mtime is useless: Immich keeps the client's file time)"
  else ev FAIL E6 "upload directory or T0 not found: cannot prove"; fi
  # 4) .env must be exactly the recorded before/after content (nobody edited it by hand)
  cs="$(_env_sha)" || _die "$?" "read env hash"
  eb="$(cat "$EV/env.before.sha256")" || _die "$?" "read before hash"
  ea=""
  if [ -e "$EV/env.after.sha256" ]; then ea="$(cat "$EV/env.after.sha256")" || _die "$?" "read after hash"; fi
  recorded_before="$(_file_sha "$EV/immich.env.before")" || _die "$?" "hash saved env"
  if [ -n "$eb" ] && [ "$cs" = "$eb" -o "$cs" = "$ea" ] && [ "$recorded_before" = "$eb" ]; then ev PASS E7 ".env equals the recorded before/after content"; else ev FAIL E7 ".env differs from the recorded content"; fi
  if [ "$bad" != 0 ]; then
    _st_set HALT_MANUAL ABORT_BEGIN "evidence not proven" || _die "$?" "record HALT_MANUAL"
    _halt_report "write-free state of the new database could not be proven (see FAIL lines above)"; exit 4
  fi
  # 5) proven clean: restore .env exactly and leave the server stopped (route off)
  if [ "$cs" = "$ea" ] && [ "$cs" != "$eb" ]; then _must cp -p "$EV/immich.env.before" "$ENV_FILE"; fi
  restored_hash="$(_env_sha)" || _die "$?" "hash restored env"
  [ "$restored_hash" = "$eb" ] && grep -q "^DB_HOSTNAME=$PG_SRC\$" "$ENV_FILE" || { _st_set HALT_MANUAL ABORT_BEGIN ".env restore failed" || _die "$?" "record HALT_MANUAL"; _halt_report ".env could not be restored exactly"; exit 4; }
  _must rm -f "$EV/T_open"
  if [ -e "$EV/T_open_begin" ]; then
    aborted_time="$(mktemp "$EV/T_open_begin.aborted.XXXXXX")" || _die "$?" "archive aborted timestamp"
    _must mv "$EV/T_open_begin" "$aborted_time"
  fi
  _st_set ABORT_VERIFIED ABORT_BEGIN "proven: no write reached the new database; .env restored; server stopped" || _die "$?" "mandatory operation failed"
  echo "s_open_abort OK: next is s_rollback_r1 (back to the source) or s_dark_launch (retry)" >&2
); }

# ------------------------------------------------------------------ R1: rollback BEFORE the open (also the tail of the manual NO-GO)
_r1_failed() { local rc="$1"; echo "HALT R1: $2 (rc=$rc)" >&2; exit "$rc"; }
_r1_core() {
  docker stop -t 30 "$SRV" || _r1_failed "$?" "stop server"
  local r1_running r1_route r1_host service
  service="$(_svc_name)" || _r1_failed "$?" "service lookup"
  r1_running="$(docker inspect -f '{{.State.Running}}' "$SRV")" || _r1_failed "$?" "inspect stopped server"
  [ "$r1_running" = false ] || _r1_failed "$?" "server must be stopped"
  s_unfence || _r1_failed "$?" "restore source ACL"
  idc up -d --force-recreate --no-deps --no-build --pull never "$service" || _r1_failed "$?" "recreate on source"
  _wait_healthy "$SRV" "$HEALTH_TIMEOUT" || _r1_failed "$?" "server health"
  r1_route="$(docker inspect -f '{{index .Config.Labels "traefik.enable"}}' "$SRV")" || _r1_failed "$?" "inspect route label"
  [ "$r1_route" = true ] || _r1_failed "$?" "public route label"
  r1_host="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "$SRV" | sed -n 's/^DB_HOSTNAME=//p')" || _r1_failed "$?" "inspect DB hostname"
  [ "$r1_host" = "$PG_SRC" ] || _r1_failed "$?" "source DB hostname"
  for c in $MOPS $BRG; do docker start "$c" || _r1_failed "$?" "start auxiliary container"; done
  $PY "$CV/api_checks.py" queues resume --execute || _r1_failed "$?" "resume queues"
  if [ -s "$EV/api-baseline.json" ]; then
    if [ "${R1_SKIP_VERIFY:-0}" = 1 ]; then
      [ "${CUTOVER_REHEARSAL:-0}" = 1 ] || _r1_failed 1 "R1_SKIP_VERIFY refused in production"
    else _api_verify --baseline "$EV/api-baseline.json" || _r1_failed "$?" "API baseline verification"; fi
  else
    case "$(_st)" in FREEZING) ;; *) _r1_failed 1 "frozen API baseline missing";; esac
    echo "WARN: no frozen baseline yet (stopped before the baseline step): API verify skipped; run api_checks.py baseline later for comparison" >&2; fi
}
s_rollback_r1() { _gate || return "$?"; (
  set -Eeuo pipefail
  if [ "${R1_SKIP_VERIFY:-0}" = 1 ] && [ "${CUTOVER_REHEARSAL:-0}" != 1 ]; then _die 1 "R1_SKIP_VERIFY refused in production"; fi
  _must _keys_required
  if cur="$($CS can-rollback "$EV")"; then rc=0; else rc=$?; fi
  case "$rc" in
    0) ;;
    6) echo "HALT: the state journal is corrupt; automatic rollback is forbidden (nothing changed)" >&2; exit 4;;
    *) echo "REFUSED: state $cur does not allow the scripted rollback R1 (partially opened -> s_open_abort; HALT_MANUAL -> manual GO/NO-GO; after OPEN_CONFIRMED there is no automatic rollback)" >&2; exit 3;;
  esac
  # live cross-checks, independent of the journal: anything unexpected is a HALT, never a rollback
  _expect 1 grep -c "^DB_HOSTNAME=$PG_SRC\$" "$ENV_FILE" || { echo "HALT: $ENV_FILE does not point at the source; automatic rollback forbidden" >&2; exit 4; }
  [ ! -e "$EV/T_open" ] || { echo "HALT: T_open exists although the journal says $cur (inconsistent); automatic rollback forbidden" >&2; exit 4; }
  r1_running="$(docker inspect -f '{{.State.Running}}' "$SRV")" || _die "$?" "R1 inspect running"
  r1_route="$(docker inspect -f '{{index .Config.Labels "traefik.enable"}}' "$SRV")" || _die "$?" "R1 inspect route"
  r1_host="$(_server_host)" || _die "$?" "R1 inspect database"
  case "$r1_running:$r1_route:$r1_host" in
    true:true:"$PG_NEW") _die 4 "public server on new database: R1 forbidden";;
  esac
  if [ -s "$EV/api-baseline.json" ]; then
    _must $PY "$CV/api_checks.py" check-sample "$EV/api-baseline.json"
  else [ "$cur" = FREEZING ] || _die 1 "frozen API baseline missing"; fi
  _r1_core || _r1_failed "$?" "rollback core"
  _st_set ROLLED_BACK FREEZING,FROZEN,DUMPED,SANITIZED,RESTORED,VALIDATED,DARK_VERIFIED,ABORT_VERIFIED "rollback R1 from $cur" || _r1_failed "$?" "record ROLLED_BACK"
  echo "s_rollback_r1 OK"
); }

# ------------------------------------------------------------------ manual decisions after HALT_MANUAL (each needs the typed token; neither runs automatically)
s_manual_forward() { _gate || return "$?"; (
  set -Eeuo pipefail
  service="$(_svc_name)" || _die "$?" "service lookup"
  _must _keys_required
  _state_in HALT_MANUAL || exit 5
  [ "${CUTOVER_MANUAL_DECISION:-}" = "FORWARD:$CUTOVER_ID" ] || { echo "REFUSED: export CUTOVER_MANUAL_DECISION=FORWARD:$CUTOVER_ID after the manual GO" >&2; exit 3; }
  lb_gate_open || { echo "HALT (G14): the local backup gate failed; nothing was changed (server stays stopped). See $EV/local-backup/BACKUP-GATE-HALT.txt" >&2; exit 6; }
  for c in $BRG $MOPS "$SRV"; do
    _must docker stop -t 60 "$c"
    _expect false docker inspect -f '{{.State.Running}}' "$c"
  done
  if ! grep -q "^DB_HOSTNAME=$PG_NEW\$" "$ENV_FILE"; then
    _must grep -q "^DB_HOSTNAME=$PG_SRC\$" "$ENV_FILE"
    _must sed -i "s/^DB_HOSTNAME=$PG_SRC\$/DB_HOSTNAME=$PG_NEW/" "$ENV_FILE"
  fi
  _expect 1 grep -c "^DB_HOSTNAME=$PG_NEW\$" "$ENV_FILE"
  idc up -d --force-recreate --no-deps --no-build --pull never "$service" || _die "$?" "mandatory operation failed"
  _wait_healthy "$SRV" "$HEALTH_TIMEOUT" || _die "$?" "mandatory operation failed"
  _expect true docker inspect -f '{{index .Config.Labels "traefik.enable"}}' "$SRV"
  _expect "$PG_NEW" _server_host
  date -u +%FT%TZ > "$EV/T_open" || _die "$?" "record public route time"
  if [ -n "$MOPS" ]; then _must _start_mops; fi
  if [ -n "$BRG" ]; then _must docker start "$BRG"; fi
  $PY "$CV/api_checks.py" queues resume --execute || _die "$?" "mandatory operation failed"
  _st_set OPEN_CONFIRMED HALT_MANUAL "manual GO: opened on the new database" || _die "$?" "mandatory operation failed"
  echo "s_manual_forward OK"
); }
s_manual_rollback_accept_loss() { _gate || return "$?"; (
  set -Eeuo pipefail
  _must _keys_required
  _state_in HALT_MANUAL || exit 5
  [ "${CUTOVER_MANUAL_DECISION:-}" = "ROLLBACK_ACCEPT_LOSS:$CUTOVER_ID" ] || { echo "REFUSED: export CUTOVER_MANUAL_DECISION=ROLLBACK_ACCEPT_LOSS:$CUTOVER_ID only if everything written to the new database may be abandoned" >&2; exit 3; }
  for c in $BRG $MOPS "$SRV"; do
    _must docker stop -t 60 "$c"
    _expect false docker inspect -f '{{.State.Running}}' "$c"
  done
  eb="$(cat "$EV/env.before.sha256")" || _die "$?" "read before hash"
  ea=""
  if [ -e "$EV/env.after.sha256" ]; then ea="$(cat "$EV/env.after.sha256")" || _die "$?" "read after hash"; fi
  cs="$(_env_sha)" || _die "$?" "read env hash"
  if [ "$cs" != "$eb" ]; then [ -n "$ea" ] && [ "$cs" = "$ea" ] || { echo "STOP: .env is neither the recorded before nor after content" >&2; exit 4; }; _must cp -p "$EV/immich.env.before" "$ENV_FILE"; fi
  _expect "$eb" _env_sha
  _r1_core || _die "$?" "mandatory operation failed"
  _st_set ROLLED_BACK_LOSS_ACCEPTED HALT_MANUAL "manual NO-GO: data written to the new database abandoned (database kept)" || _die "$?" "mandatory operation failed"
  echo "s_manual_rollback_accept_loss OK (the new database was NOT deleted)"
); }

# read-only check of G14 on demand (F9 checklist item); changes nothing but evidence files in $EV/local-backup
s_backup_gate() { ( [ -n "${CUTOVER_ID:-}" ] && [ -n "${EV:-}" ] || { echo "CUTOVER_ID/EV not set" >&2; exit 1; }; lb_gate_open ); }
