# Storage Box Backup Directories Report

## Execution Time
- **Date**: November 18, 2026
- **Time**: 07:11 (UTC)

## Created Directories
- `/home/backups`
- `/home/backups/postgres`
- `/home/backups/postgis`
- `/home/backups/immich`

## Initial Permissions
- All directories had permissions: `drwxrwxr-x`

## Permissions Hardening
- Executed: `chmod 700` on all directories.
- **Final Permissions**: `drwx------` (only owner `u722659` has access).

## Verification
- Directories were successfully hardened and verified.

## Confirmations
- **No data was transferred**.
- **No changes were made to PostgreSQL or Docker infrastructure**.

## Final Marker
`STORAGEBOX_BACKUP_DIRECTORIES_READY`