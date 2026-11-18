# Borg PostgreSQL Repository — Preflight

Read-only checks, performed 2026-11-18. **No repository was initialized.**

## Versions
- Local Borg: 1.2.0
- Remote Borg (Storage Box): 1.2.9 (compatible; Borg 1.2.x client/server)

## Remote path
- `/home/backups/postgres` exists, `drwx------ u722659 u722659`, empty.
- Planned repository path: `/home/backups/postgres/repository` — does not exist yet
  (parent directory is empty).
- Free space on `/home`: 1.0T (128K used).

## SSH
- `ssh storagebox ...` works non-interactively (BatchMode, strict host key checking).
- The earlier reported "SSH alias failure" did not reproduce; it was likely a quoting
  issue in the preflight command (`ls -ld ... 2>/dev/null || echo` on a restricted shell).

## Planned (not executed)
- `borg init --encryption=repokey-blake2 ssh://storagebox/home/backups/postgres/repository`
- Export and store the key off-server immediately (`borg key export`); passphrase kept
  out of git and out of this repo.

## Status
`BORG_REPOSITORY_PREFLIGHT_OK — NOT_INITIALIZED (awaiting approval and passphrase decision)`
