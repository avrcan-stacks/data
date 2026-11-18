#!/usr/bin/env bash
# Do not run until separate written approval for F2 + PREPARED for this ID.
# The caller must provide the exact token; this driver never grants approval.
set -Eeuo pipefail
umask 077
trap 'unset CUTOVER_APPROVED' EXIT
[ "${CUTOVER_APPROVED:-}" = 20261115t150714z ] || { echo 'HALT: separate F2 approval token required' >&2; exit 1; }
[ "${CUTOVER_REHEARSAL:-0}" = 0 ] || { echo 'HALT: production driver rejects rehearsal profile' >&2; exit 1; }
# Eliminate caller overrides for both the Bash helpers and the Python profile.
unset CUTOVER_REHEARSAL CUTOVER_FAULT LB_BACKUP_ONLY_APPROVED LB_TEST LB_MDSTAT F2_EXISTING_POLICY
unset CUTOVER_IMMICH_DIR CUTOVER_DATA_DIR CUTOVER_BACKUPS_DIR CUTOVER_TARGET_DATADIR CUTOVER_DB CUTOVER_BRIDGE_CONTAINER
unset REHEARSAL_SRC_CONTAINER REHEARSAL_DB_CONTAINER REHEARSAL_SERVER_CONTAINER REHEARSAL_REDIS_CONTAINER REHEARSAL_ML_CONTAINER REHEARSAL_NETWORK
export CUTOVER_ID=20261115t150714z
export CV=/opt/stacks/data/immich-cutover
export EV=/opt/stacks/data/backups/immich-cutover-20261115t150714z
export PG_SRC=postgis PG_NEW=immich-db SRV=immich_server
export EVROOT=/opt/stacks/data/backups EVIDENCE_ROOT=/opt/stacks/data/backups
export IMMICH_ENV_FILE=/opt/stacks/immich/.env
export LB_ROOT=/home/immich-cutover-backups IMMICH_BACKUPS=/opt/stacks/immich/docker-data/library/backups
export PYTHONDONTWRITEBYTECODE=1
source "$CV/steps.sh" || exit "$?"
# No conditional/eval wrapper. The function also checks every mandatory status.
s_prepare_existing_target
rc=$?
[ "$rc" -eq 0 ] || exit "$rc"
_expect PREPARED _st
unset CUTOVER_APPROVED
printf 'F2_RC=0; PREPARED verified; approval token removed. STOP.\n'
