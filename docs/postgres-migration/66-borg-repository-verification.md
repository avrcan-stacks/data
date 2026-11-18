# Borg Repository Verification

Read-only verification performed 2026-11-18 after repository initialization (07:24 UTC).

## Repository
- **Location**: `storagebox:/home/backups/postgres/repository`
- **Repository id**: `0d89819fb0aa07c6adc1583c0f0696955391535a536b6645141b9bc10ce1b86b`
- **Format**: Borg 1.x repository (`version = 1`), `append_only = 0`, `storage_quota = 0`
- **Files**: `README`, `config`, `data/`, `hints.1`, `index.1`, `integrity.1`, `nonce`
- **Encryption**: key stored in repository `config` (repokey mode); passphrase-protected.
  Local security cache exists at `/root/.config/borg/security/<repo-id>/`.
- Remote permissions: all `700`/`600`, owner `u722659`.

## Sibling directories
- `/home/backups/postgis` and `/home/backups/immich`: empty, unchanged.

## Not verified
- Archive count / `borg list` / `borg check` (needs the passphrase; not accessed).
- Passphrase storage location and permissions.
- Key export: **not done**.

## Status
`BORG_POSTGRES_REPOSITORY_INITIALIZED — RECOVERY_KEY_BACKUP_PENDING`

## Required before first backup
1. Export key: `borg key export <repo> <file>` and store it off-server, separate from the passphrase.
2. Store the passphrase in a password manager (not in git).
3. Run `borg list` to confirm access with the passphrase and 0 archives.
