#!/usr/bin/env bash
# Generates .env.test for ONE isolated test case. Does not start or create anything else.
# Refuses to overwrite. Random throw-away passwords only; production secrets are never read.
set -euo pipefail
cd "$(dirname "$0")"
umask 077
[ ! -e .env.test ] || { echo ".env.test already exists; refuse to overwrite" >&2; exit 1; }
CASE_ID="$(date -u +%Y%m%dt%H%M%Sz)-$(head -c3 /dev/urandom | od -An -tx1 | tr -d ' \n')"
ROOT="/tmp/immich-apptest-${CASE_ID}"
[ ! -e "$ROOT" ] || { echo "$ROOT exists" >&2; exit 1; }
CLIENT_IMAGE="$(docker image inspect python:3.12-slim --format '{{.Id}}')"
rnd() { head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
sed -e "s|^CASE_ID=.*|CASE_ID=${CASE_ID}|" \
    -e "s|^TEST_ROOT=.*|TEST_ROOT=${ROOT}|" \
    -e "s|^TEST_CLIENT_IMAGE=.*|TEST_CLIENT_IMAGE=${CLIENT_IMAGE}|" \
    -e "s|^TEST_DB_ADMIN_PASSWORD=.*|TEST_DB_ADMIN_PASSWORD=$(rnd)|" \
    -e "s|^TEST_DB_APP_PASSWORD=.*|TEST_DB_APP_PASSWORD=$(rnd)|" \
    -e "s|^TEST_ADMIN_PASSWORD=.*|TEST_ADMIN_PASSWORD=$(rnd)|" \
    env.test.example > .env.test
chmod 600 .env.test
echo "CASE_ID=${CASE_ID}"
echo "Next: see docs/postgres-migration/13-immich-application-test-plan.md, stage 0 (gates) before creating ${ROOT}."
