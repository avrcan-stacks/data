# PostGIS stack — agent rules

## Environments

| Environment | Host | Compose |
|---|---|---|
| Production | `dedicated-hel1:/opt/stacks/data` | `docker-compose.yml` (PostGIS + Tailscale, external nets) |
| Local (Docker Desktop / WSL) | `/opt/stacks/data` | `docker-compose.yml` + `docker-compose.local.yml` (PostGIS only) |

## Shared rules

- Never delete production data unless explicitly instructed. If reset is needed, ask first.
- Use Docker container named `postgis`.
- Dumps live in `/opt/stacks/data/backups/` (gitignored).
- Prefer safe, repeatable steps: verify → apply → verify.
- Log commands you run and paste key outputs.
- **Never commit secrets:** `.env`, `postgis-tailscale.env` stay out of git. Track `.env.example` (keys only).

## Production (`dedicated-hel1`)

```bash
cd /opt/stacks/data
docker compose up -d --build
```

- Volumes: `/opt/stacks/data/postgres/data`, `/opt/stacks/data/backups`, plus Tailscale state.
- Do not touch production `postgres/data` unless instructed.

## Local (WSL / Docker Desktop)

```bash
cd /opt/stacks/data
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

- Override disables Tailscale and external networks; binds `127.0.0.1:5432`.
- Sync config via git (`git pull` / `git push`). Copy secrets with:
  `scp dedicated-hel1:/opt/stacks/data/.env /opt/stacks/data/.env`
- Local cluster starts empty until a dump/restore is done (future step).

## Dump / restore (future)

Not required for local bring-up. When needed:

```bash
# on server
ssh dedicated-hel1 'docker exec postgis pg_dump -U "$POSTGRES_USER" -Fc -d "$POSTGRES_DB"' \
  > /opt/stacks/data/backups/${POSTGRES_DB}_$(date +%F).dump

# local restore (after backups/ is mounted)
docker exec -i postgis pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists /backups/FILE.dump
```
