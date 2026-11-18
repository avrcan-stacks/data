# 59 — Priprema PostgreSQL data checksums (servis `postgres`)

Datum: 2026-11-18
Referenca: `58-postgres-standard-service-prelaunch.md`

## 1. Vlasnikovo odobrenje

Vlasnik je izričito odobrio **uključivanje data checksums pri inicijalizaciji novog clustera `postgres`**.
Nije odobreno: pokretanje kontejnera, initdb, build, migracija/restore, restart/recreate, promjene na `postgis` ili `immich-db`.

## 2. Konfiguracijska izmjena

Datoteka: `docker-compose.postgres-new.yml`, servis `postgres` (redak 22):

```diff
-      POSTGRES_INITDB_ARGS: --encoding=UTF8 --locale=en_US.utf8
+      POSTGRES_INITDB_ARGS: --encoding=UTF8 --locale=en_US.utf8 --data-checksums
```

Servis `immich-db` (redak 88) ostao je nepromijenjen (`--encoding=UTF8 --locale=en_US.utf8`).

## 3. Validacija

- `docker compose -f docker-compose.postgres-new.yml config --quiet` → rc=0 (bez grešaka).
- Efektivne vrijednosti `POSTGRES_INITDB_ARGS` (ispisana samo ta varijabla):
  - `postgres`: `--encoding=UTF8 --locale=en_US.utf8 --data-checksums`
  - `immich-db`: `--encoding=UTF8 --locale=en_US.utf8`
- `git diff --stat`: 1 datoteka, 1 insertion, 1 deletion.

## 4. Stanje sustava

- Kontejner `postgres` ne postoji (`docker ps -a` ga ne navodi) — nije pokretan.
- `/opt/stacks/data/postgres-standard/data` je prazan (0 unosa) — PGDATA nije inicijaliziran.
- `postgis` (started 2026-06-26) i `immich-db` (started 2026-11-15) nisu dirani; izvršene su samo `docker ps`/`docker inspect` (read-only) i `compose config`.

## 5. Napomena

Data checksums postaju aktivni **tek pri budućem `initdb`** (prvi start s praznim PGDATA). Ne mogu se uključiti naknadno na postojeći cluster bez offline `pg_checksums --enable`. Izmjena sama po sebi ništa ne mijenja na postojećim servisima.

## 6. Preostale blokade iz dokumenta 58

- **B1 — Backup strategija:** vlasnik mora izričito prihvatiti start praznog clustera bez backupa novog servisa i odrediti obvezu (pg_dump -Fc po bazi, globals, SHA-256, off-host kopija, restore proba) prije prvog restorea.
- **B2 — Pokretanje bez recreatea:** odobriti isključivo naredbu iz §9.2 dokumenta 58; ne koristiti `up` bez navedenog servisa dok se hash-nesklad `immich-db` ne razriješi.

(Blokada B3 iz dokumenta 58 nije predmet ovog zadatka.)

## Status

`POSTGRES_CHECKSUMS_CONFIG_PREPARED — START_NOT_AUTHORIZED`
