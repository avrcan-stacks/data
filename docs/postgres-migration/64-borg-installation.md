# BorgBackup Installation Report

## Execution
- **Date**: 2026-11-18
- **Time**: ~07:11 UTC (as reported by the installing session)
- **Host**: dedicated-hel1 (Ubuntu 22.04.5 LTS)

## Installed Version
- **Borg**: `1.2.0` (package `borgbackup 1.2.0-1ubuntu1.22.04.1`)
- **Additional package**: `python3-msgpack` (dependency)
- Command: `DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends borgbackup`
- Preflight: borg not previously installed; `apt-get -s install borgbackup` showed no conflicts.

## Verification (re-checked at report creation)
- `command -v borg` -> `/usr/bin/borg`
- `borg --version` -> `borg 1.2.0`
- `dpkg-query -W borgbackup` -> `borgbackup 1.2.0-1ubuntu1.22.04.1`

## Confirmations
- No Borg repository was created or initialized.
- No changes were made to PostgreSQL, Docker or Immich.
- Storage Box access (`ssh storagebox`) unchanged by this step.

## Final Marker
`BORG_CLIENT_INSTALLED — REPOSITORY_NOT_INITIALIZED`

## Next Step
Repository initialization on the Storage Box, only after explicit approval.
