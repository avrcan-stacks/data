# 34 — Immich produkcijski cutover: F6 (sanitizacija na bridgeu)

Datum: 15. studenoga 2026. (izvedba 13:42–13:50 UTC).
**`CUTOVER_ID=20261115t130331z`** · evidencija `/opt/stacks/data/backups/immich-cutover-20261115t130331z` (`f6-sanitize.out`, `immich.no-postgis.dump`, `.sha256`, `.toc`, `.log`, `bridge.restore.log`, `bridge-before/`, `bridge-after/`, `compare-source-bridge.json`, `compare-source-bridge-after.json`).
Odobreno: samo F6 (`s_bridge_sanitize`). **F6b i kasniji koraci nisu pokrenuti.** Produkcijski Immich je i dalje **nedostupan** (zamrznut).

## 1. Sažetak

| Stavka | Rezultat |
| --- | --- |
| `s_bridge_sanitize` | **`s_bridge_sanitize OK`, exit 0** (HALT/STOP nije bilo) |
| Usporedba izvor ↔ bridge **prije** `DROP EXTENSION` | **PASS** — 72 tablice, 1.080.428 redaka, 0 problema |
| `DROP EXTENSION postgis RESTRICT` | uspio (samo na bridge kopiji) |
| Usporedba izvor ↔ bridge **poslije** | **PASS** — 72 tablice, 1.080.428 redaka, 0 problema |
| Restore log bridgea (`--exit-on-error`) | prazan (0 B) |
| `pg_dump` log sanitiziranog dumpa | prazan (0 B) |
| Sanitizirani dump | `/opt/stacks/data/backups/immich-cutover-20261115t130331z/immich.no-postgis.dump` |
| Veličina | **354.050.055 B** (≈338 MiB) |
| SHA-256 | `3a85087152e0344b5e405975a8e3366aade5da315246307972dac5eba45061dd` (`sha256sum -c` OK) |
| TOC (`pg_restore --list`) | **958** redaka |
| PostGIS / `spatial_ref_sys` u TOC-u | **0 pogodaka** (`grep -iE 'postgis|spatial_ref_sys'`) |
| Žurnal | **`SANITIZED`** (seq 5, `DUMPED` → `SANITIZED`, „sanitized dump written"), `cutstate.py verify` OK |
| Sigurno na F6b? | **Da**; čeka novu uputu |

## 2. Provjere prije F6 (sve prošle)

- Žurnal `DUMPED`, `cutstate.py verify` OK; `CUTOVER_ID` datoteka odgovara.
- `immich.full.dump` 354.261.789 B, SHA-256 `243e3830…5018` identičan zadanom.
- Izvor `postgis/immich`: ACL `{=T/immich,immich=CT/immich}` (bez CONNECT), 0 veza.
- `immich_server` (Exited 143), `immich_media_operations` i `nextcloud_immich_bridge` (Exited 137) zaustavljeni.
- `postgis`, `immich_redis`, `immich-db`: healthy, 0 restartova, `StartedAt` nepromijenjen.
- Bridge image `postgis-local:16-bookworm-postgis3-cron-vchord1.1.1` (`sha256:33e372cc…`) isti kao image produkcijskog `postgis`; `/tmp/immich-cutover-…` nije postojao; 426 GiB slobodno.
- Nema odstupanja od dokumenta 33.

## 3. Izvršenje

`( source immich-cutover/steps.sh; CUTOVER_APPROVED=$CUTOVER_ID s_bridge_sanitize )`, izlaz u `f6-sanitize.out`. `CUTOVER_APPROVED` postavljen samo prefiksom podljuske (nakon izvršenja nije postavljen u ljusci). Funkcija je izvršena nepromijenjena, bez dodatnog SQL-a: izolirani bridge kontejner (`--network none`, vlastiti PGDATA, `$EV` read-only) → restore svježeg dumpa → normalizacija identity sekvence → snapshot + usporedba prije → `DROP EXTENSION postgis RESTRICT` → snapshot + usporedba poslije → `pg_dump` → SHA-256 → TOC provjera → žurnal `SANITIZED`.

## 4. Status nakon F6

| Komponenta | Stanje |
| --- | --- |
| Izvor `postgis/immich` | **nepromijenjen**: ACL bez CONNECT, 0 veza, ekstenzije `plpgsql`, `postgis`, `cube`, … (PostGIS i dalje u izvoru, kako treba) |
| `postgis` kontejner | healthy, `StartedAt` 26.6.2026., 0 restartova |
| Ciljna baza `immich-db` | healthy, `StartedAt` 15.11. 13:19 (F2), 0 restartova, nije dirana, nema restorea |
| `immich_redis` | healthy, `StartedAt` 26.6.2026., 0 restartova |
| `immich_server`, `immich_media_operations`, `nextcloud_immich_bridge` | zaustavljeni |
| Privremeni bridge `immich-cutover-bridge-20261115t130331z` | **još radi** (`--network none`); `s_bridge_cleanup` nije pokrenut jer nije bio odobren |

## 5. Što nije dirano

Izvorna baza, produkcijski PostGIS, `.env`, Compose, Traefik, Redis; izvor nije odmrznut; nema F6b/F7/F8/F10, restorea u `immich-db` ni brisanja; `immich.full.dump`, F0 backup i ostali dumpovi netaknuti.

## 6. Je li sigurno prijeći na F6b?

**Da.** Sanitizirani dump je potpun i provjeren (obje usporedbe PASS, prazni logovi, TOC bez PostGIS-a, SHA-256 OK), stanje `SANITIZED` je preduvjet za F7. Prije F7 treba F6b (`lb_copy_cutover_dumps && lb_verify`, druga kopija dumpova na `/home`). Otvoreno za odluku: `s_bridge_cleanup` (uklanja privremeni bridge i `/tmp/immich-cutover-…`) — runbook ga veže uz F6, ali nije izvršen bez izričitog odobrenja. **Stajem nakon F6.**
