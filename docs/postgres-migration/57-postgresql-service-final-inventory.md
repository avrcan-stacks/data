# 57 — Završni inventar PostgreSQL servisa (READ-ONLY audit)

Datum audita: 18.11.2026. Način: samo čitanje (Docker metapodaci, `pg_catalog` upiti u `BEGIN READ ONLY … ROLLBACK`, čitanje konfiguracija). Nijedna konfiguracija, kontejner, baza ni žurnal nije mijenjan. Lozinke i tajne nisu ispisivane. Veličine i veze su presjek živog sustava, ne transakcijski snapshot.

## 1. Sažetak aktualne arhitekture

- Planirana trostruka podjela (`postgres` / `postgis` / `immich-db`) **ostvarena je samo djelomično**: ostvaren je samo dio `immich-db`.
- **Servis `postgres` ne postoji kao kontejner.** `docker ps -a` nema kontejnera `postgres`; `/opt/stacks/data/postgres-standard/data` je prazan (nema `PG_VERSION`, nema clustera). Postoji samo konfiguracija (`docker-compose.postgres-new.yml`, `Dockerfile.postgres`) iz Phase 1 (dokument 07). Compose projekt `data-postgres-next` pokrenuo je samo servis `immich-db`.
- **`postgis` i dalje sadrži svih 31 izvornih korisničkih baza** (+ 3 template), uključujući `immich` kao zadržani izvor. Svih ~25 standardnih baza planiranih za `postgres` još je na `postgis`.
- **`immich-db`** radi (PG 16.16), aktivna baza `immich` s vector 0.8.2 i vchord 1.1.1; `immich_server` i `immich_media_operations` koriste `DB_HOSTNAME=immich-db`.
- Svi ostali aplikacijski kontejneri imaju `*_HOST=postgis` i aktivne veze na `postgis`.

## 2. Docker servisi koji sadrže PostgreSQL

| Kontejner | Compose projekt/servis | Image | PG verzija | Status / health | RestartCount | Mreže | PGDATA (host → kontejner) | Preload |
|---|---|---|---|---|---|---|---|---|
| `postgis` | `data` / `postgis` | `postgis-local:16-bookworm-postgis3-cron-vchord1.1.1` | 16.13 | running / healthy (od 26.06.2026.) | 0 | backend, data_default, hetzner_net, postgis | `/opt/stacks/data/postgres/data` → `/var/lib/postgresql/data`; + `/opt/stacks/data/backups`→`/backups`, `/srv/qubit/backups` | vchord, pg_cron |
| `immich-db` | `data-postgres-next` / `immich-db` | `immich-db-local:16.16-bookworm-vector0.8.2-vchord1.1.1` | 16.16 | running / healthy (od 15.11.2026.) | 0 | postgis | `/opt/stacks/data/immich-postgres/data` → `/var/lib/postgresql/data`; + `/backups` | vchord |
| `postgres` | — | — | — | **NE POSTOJI** (nije kreiran) | — | — | `/opt/stacks/data/postgres-standard/data` prazan | — |
| `chatwoot-backup` | `chatwoot` / `backup` | `postgres:16.13-alpine` | 16.13 (klijent) | running, bez healthchecka | 0 | postgis | volume bez aktivnog clustera; koristi se kao backup klijent (`PGHOST=postgis`, `PGUSER=chatwoot`) | — |

`chatwoot-backup` nije PostgreSQL server baza podataka nego backup-petlja prema `postgis`; nije klasificiran kao servis baza. `tailscale-postgis` je samo mrežni tunel za `postgis`. Drugi PostgreSQL kontejneri nisu pronađeni (MySQL kontejneri Domibus i Redis/Valkey izvan opsega).

Dostupne ekstenzije (`pg_available_extensions`): `postgis` — postgis 3.6.2, vector 0.8.2, vchord 1.1.1, pg_cron 1.6, cube/earthdistance 1.x. `immich-db` — vector 0.8.2, vchord 1.1.1, cube 1.5, earthdistance 1.2 (nema postgis ni pg_cron, što je ispravno).

## 3. Korisničke baze po servisu

### 3.1 `postgis` (PG 16.13) — 31 netemplate baza

Aktivne veze = klijentske veze u trenutku mjerenja. Klasifikacija „prod/test/arhiva” je preuzeta iz dokumenata 01/03 i imena baze; nije dokazana iz aplikacija osim gdje je navedeno.

| Baza | Owner | MiB | Ekstenzije (osim plpgsql) | PostGIS? | Vector/vchord | Veze | Klijent(i) | Tip |
|---|---|---|---|---|---|---|---|---|
| chatwoot | chatwoot | 21 | pg_stat_statements 1.10; pg_trgm 1.6; pgcrypto 1.3; vector 0.8.2 | ne | pgvector | 6 | chatwoot-sidekiq | prod |
| crowdsec | crowdsec | 38936 | — | ne | ne | 2 | crowdsec-importer, crowdsec-scheduler | prod |
| farma_db | farma_app | 39 | fuzzystrmatch 1.2; postgis 3.4.3; tiger_geocoder 3.4.3; topology 3.4.3 | **da** | ne | 3 | farma_backend | prod |
| finestar_erp_db | postgis | 133 | postgis 3.6.2 | instaliran | ne | 1 | finestar_erp_celery_beat | prod |
| fiskal | fiskal | 39 | postgis 3.6.2 | instaliran | ne | 5 | fiskal_api, fiskal_worker | prod |
| fiskal_f1_pts_smoke | fiskal | 9 | pgcrypto 1.3 | ne | ne | 1 | f1-pts-api | smoke/test (korišten) |
| headscale | headscale | 9 | uuid-ossp 1.1 | ne | ne | 0 | (headscale: `DATABASE_HOST=postgis`) | prod |
| immich | immich | 1191 | cube, earthdistance, pg_trgm, postgis 3.6.2, unaccent, uuid-ossp, vector 0.8.2, vchord 1.1.1 | instaliran | da | **0** | nitko | **zaštićeni izvor** |
| mailblocklist | mailblocklist | 36 | — | ne | ne | 2 | mailserver-mailindex-sync, mailserver-mail-mcp | prod |
| minidepo | postgres | 18 | postgis 3.6.2 | **da** | ne | 0 | (minidepo_web: `DB_HOST=postgis`) | prod |
| mozzart_db | postgis | 204 | postgis 3.4.3 | instaliran | ne | 0 | (mozzart kontejneri nisu u popisu env/host) | prod |
| nextcloud | nextcloud | 143 | — | ne | ne | 0 | (nextcloud, nextcloud-cron: `POSTGRES_HOST=postgis`) | prod |
| omnimsgio | omnimsgio | 8 | — | ne | ne | 3 | omnimsgio-api, -gateway, -worker | prod |
| parkschloss | parkschloss | 7 | — | ne | ne | 5 | parkschloss-api | prod |
| postgres | postgres | 67 | fuzzystrmatch, postgis 3.4.3, tiger_geocoder, topology | instaliran | ne | 1 | tailscale-booking-browser (Uzorita aplikacijski podaci, dok. 01) | prod (ne prazna admin baza) |
| powerdns | qubit | 7 | — | ne | ne | 0 | (powerdns) | prod |
| predix | predix | 136 | postgis 3.6.2 | instaliran | ne | 0 | (predix-api/worker/sync: `POSTGRES_HOST=postgis`) | prod |
| qubit_user | qubit | 22 | pg_cron 1.6 | ne | ne | 0 | (qubit) | prod |
| racunai_intermediary | postgis | 104 | — | ne | ne | 1 | racunai_mps | prod |
| roamkit | roamkit | 18 | — | ne | ne | 0 | roamkit staging | staging |
| roamkit_production | roamkit | 17 | — | ne | ne | 0 | roamkit production | prod |
| snappymail | snappymail | 7 | — | ne | ne | 0 | (snappymail) | prod |
| stay_platform_db | stay | 49 | pageinspect 1.12 | ne | ne | 12 | stay_django | prod |
| stay_platform_test_db | stay | 23 | postgis 3.6.2 | instaliran | ne | 0 | — | test |
| superclean_db | superclean | 17 | postgis 3.6.2 | instaliran | ne | 0 | (superclean_django) | prod |
| tablio_platform_db | tablio | 10 | — | ne | ne | 3 | tablio_django | prod |
| test_finestar_erp_db | postgis | 33 | postgis 3.6.2 | instaliran | ne | 0 | — | test |
| test_predix | predix | 13 | — | ne | ne | 0 | — | test |
| test_qubit_user | qubit | 12 | — | ne | ne | 0 | — | test |
| test_stay_platform_db | stay | 13 | — | ne | ne | 0 | — | test |
| test_stay_platform_test_db | stay | 25 | postgis 3.6.2 | instaliran | ne | 0 | — | test |

Template baze: `template0` (nema veze), `template1`, `template_postgis` (postgis/topology/tiger/fuzzystrmatch 3.4.3). Uz zagrade `( )` označeni su klijenti utvrđeni samo iz env varijable kontejnera, bez aktivne veze u trenutku mjerenja → veza **NOT VERIFIED** (aplikacija može koristiti pool/povremene veze).

Razlika instalirano ≠ potrebno: PostGIS je instaliran u 12 netemplate baza, a prema dokumentu 03 aplikacijske prostorne strukture potvrđene su samo za `farma_db` i `minidepo`. Za ostale baze (finestar_erp_db, fiskal, mozzart_db, postgres, predix, stay_platform_test_db, superclean_db, test_*, immich) potreba **nije potvrđena u ovom auditu**; ERP i Superclean imaju Django GIS backend (dok. 03), pa PostGIS za njih može biti stvarno potreban dok se backend ne promijeni.

### 3.2 `immich-db` (PG 16.16)

| Baza | Owner | MiB | Ekstenzije | PostGIS | Vector/vchord | Veze | Tip |
|---|---|---|---|---|---|---|---|
| immich | immich | 999 | cube 1.5, earthdistance 1.2, pg_trgm 1.6, unaccent 1.1, uuid-ossp 1.1, vchord 1.1.1, vector 0.8.2 | ne (namjerno izostavljen) | da | 19 (immich_server) | **aktivna produkcija** |
| immich_failed_20261115t150714z_ | immich | 995 | iste kao gore | ne | da | 0 | **arhivirani neuspjeli pokušaj** (zaštićen, dok. 56) |
| postgres | postgres | 7 | — | ne | ne | 0 | sistemska bootstrap baza |

Razlika u veličini `immich` (999 MiB) naspram izvora (1191 MiB) nije objašnjena ovim auditom (sanitizacija/izostanak PostGIS-a/bloat moguće) — **NOT VERIFIED**; migracijski dokazi su u dokumentima 46–48.

### 3.3 `postgres`
Servis ne postoji → nema baza.

## 4. Ekstenzije i verzije — sažetak

| Ekstenzija | Verzija | Gdje |
|---|---|---|
| PostgreSQL | 16.13 (postgis), 16.16 (immich-db) | — |
| postgis (+topology, tiger) | 3.6.2 (12 baza) / 3.4.3 SQL u farma_db, postgres, mozzart_db, template_postgis | postgis |
| vector | 0.8.2 | postgis: chatwoot, immich; immich-db: immich, arhiva |
| vchord | 1.1.1 | postgis: immich (izvor); immich-db: immich, arhiva |
| pg_cron | 1.6 | postgis: qubit_user |
| pg_trgm 1.6, pgcrypto 1.3, pg_stat_statements 1.10, uuid-ossp 1.1, cube 1.5, earthdistance 1.2, unaccent 1.1, fuzzystrmatch 1.2, pageinspect 1.12 | — | prema tablicama gore |

Napomena: neusklađena verzija kolacije (2.31 → 2.36) i dalje se prijavljuje u crowdsec, headscale, mozzart_db, powerdns, qubit_user, snappymail, template_postgis, test_qubit_user (WARNING iz upita), kako je već zabilježeno u dok. 01. Nije mijenjano.

## 5. Usporedba s početnim inventarom (dok. 01/03)

Početno stanje: 31 netemplate + 3 template baze na `postgis`. Sadašnje stanje na `postgis`: **isti skup — 31 + 3, bez razlike u popisu**. Ukupan broj baza u svim servisima je 31 + 2 (na immich-db: `immich`, `immich_failed_…`) = 33 netemplate (+ sistemska `postgres` na immich-db). Povećanje od 2 posljedica je isključivo migracije Immicha (aktivna kopija + arhivirani neuspjeli pokušaj).

| Baza | Početak | Sada | Migracija potvrđena | Stara kopija | Aplikacija preusmjerena | Status |
|---|---|---|---|---|---|---|
| immich | postgis | immich-db (aktivna) | da (dok. 46–48, 56; ovdje potvrđeno: 19 veza na immich-db) | postgis/immich (0 veza, zaštićeno) + immich_failed_… | da (immich_server, media_operations) | **COMPLETED** |
| farma_db | postgis | postgis | cilj je postgis | — | — | **NOT_REQUIRED** |
| minidepo | postgis | postgis | cilj je postgis | — | — | **NOT_REQUIRED** |
| stay_platform_test_db, test_finestar_erp_db, test_stay_platform_test_db | postgis | postgis | plan: ZADRŽATI na postgis | — | — | **NOT_REQUIRED** (dok. 03) |
| chatwoot, crowdsec, fiskal_f1_pts_smoke, mailblocklist, nextcloud, omnimsgio, parkschloss, racunai_intermediary, stay_platform_db, tablio_platform_db | postgis | postgis | ne | — | ne (`*_HOST=postgis`) | **PENDING** (cilj postgres) |
| finestar_erp_db, fiskal, headscale, mozzart_db, postgres, powerdns, predix, qubit_user, roamkit, roamkit_production, snappymail, superclean_db, test_predix, test_qubit_user, test_stay_platform_db | postgis | postgis | ne | — | ne | **PENDING** (cilj postgres, UVJETNO prema dok. 03) |

Sažetak: COMPLETED 1; NOT_REQUIRED 5; PENDING 25; NOT_VERIFIED 0 za izvorne baze (sve su dostupne i pregledane). Zbroj 31. Brojka 25 podudara se s planom iz dok. 03 (25 → postgres, 5 → postgis, 1 → immich-db).

## 6. Aktivne aplikacijske konekcije (u trenutku mjerenja)

`postgis`: chatwoot-sidekiq→chatwoot (6); crowdsec-importer, crowdsec-scheduler→crowdsec (2); farma_backend→farma_db (3); finestar_erp_celery_beat→finestar_erp_db (1); fiskal_api (4) + fiskal_worker (1)→fiskal; f1-pts-api→fiskal_f1_pts_smoke (1); mailserver-mailindex-sync + mailserver-mail-mcp→mailblocklist (2); omnimsgio-api/gateway/worker→omnimsgio (3); parkschloss-api→parkschloss (5); tailscale-booking-browser→postgres (1); racunai_mps→racunai_intermediary (1); stay_django→stay_platform_db (12); tablio_django→tablio_platform_db (3).
`immich-db`: immich_server→immich (19).

Runtime `DB_HOSTNAME`/`*_HOST` svih ostalih kontejnera (nextcloud, roamkit, predix, superclean, snappymail, headscale, qubit, minidepo, uzorita, stay celery/web, finestar_erp, …) je `postgis`.

Odstupanja Compose ↔ runtime:
- `nextcloud_immich_bridge` ima runtime `DB_HOSTNAME=postgis`, `DB_DATABASE_NAME=immich` (dok. 03 ga navodi kao potrošača Immich baze); `immich_machine_learning` također `DB_HOSTNAME=postgis`. Na `postgis/immich` je **0 aktivnih veza**, pa u trenutku mjerenja ne postoji dokaz da ih koriste — ali konfiguracija pokazuje na staru bazu. Ako bridge pristupa bazi (povremeno), to bi bila veza na zaštićeni izvor. **Ne mijenjano; NOT VERIFIED** koristi li bridge DB uopće. Preporuka: potvrditi i ujednačiti (`immich-db`) uz odobrenje.
- Nijedan drugi kontejner ne pokazuje na `immich-db`, osim `immich_server` i `immich_media_operations`.

## 7. Baze na pogrešnom servisu

Prema planu (dok. 02/03) na `postgis` smiju ostati farma_db, minidepo i tri zadržana testna PostGIS-a. Ostalih **25 baza** (popis PENDING iz §5, uključujući crowdsec 38,9 GiB, chatwoot, nextcloud, stay_platform_db, …) nalazi se na „pogrešnom” servisu u smislu ciljne arhitekture. Neke od njih (ERP, Superclean, fiskal, predix…) imaju UVJETNI cilj — PostGIS može biti stvarno potreban zbog Django GIS backenda, pa to nije nužno pogreška nego neriješen gate (dok. 03).
Dodatno: `postgis` još učitava `vchord` i `pg_cron` u preloadu, a plan predviđa uklanjanje nakon dovršene razdiobe.

## 8. Baze koje čekaju migraciju

25 baza iz §5 (PENDING). Preduvjet: kreiranje i pokretanje servisa `postgres` (trenutačno ne postoji), restore proba, validacija po aplikaciji i preusmjeravanje `*_HOST` varijabli (matrica dok. 03, valovi A–F).

## 9. Arhivske i zaštitne baze

Ne smiju se klasificirati kao nedovršena migracija (dok. 56, `PRESERVE_UNTIL_EXPLICIT_OWNER_DECISION`; `SOURCE_RETENTION_MINIMUM=2026-11-22T17:05:12Z`):
- `postgis/immich` — zaštićeni izvor, 0 veza (potvrđeno).
- `immich-db/immich_failed_20261115t150714z_` — arhivirani neuspjeli pokušaj, 0 veza.
- `template_postgis`, `template0`, `template1` — template baze.
- Testne/smoke baze (`test_*`, `stay_platform_test_db`, `fiskal_f1_pts_smoke`) — ne tretirati kao arhivu bez potvrde vlasnika.

## 10. Status ostvarenja početnog cilja

| Cilj | Status |
|---|---|
| Servis `immich-db` s vector/vchord, aktivna `immich-db/immich`, server koristi `immich-db` | **Ostvareno** |
| Stara `postgis/immich` samo kao zaštićeni izvor | **Potvrđeno** (0 veza; vidi napomenu o bridge/ML env) |
| Servis `postgres` za standardne baze | **Neostvareno** — kontejner ne postoji, data dir prazan |
| `postgis` samo za stvarne PostGIS baze | **Neostvareno** — sadrži svih 31 baza |

## 11. Preporučeni sljedeći korak

1. Odluka vlasnika: nastavak plana iz dok. 02–07 — kreirati i pokrenuti servis `postgres` (compose `docker-compose.postgres-new.yml`, **samo servis `postgres`**, jer je `immich-db` već pokrenut iz istog projekta; izbjeći recreate `immich-db`).
2. Pilot s niskorizičnim valom A/B (test_* baze, omnimsgio, parkschloss, tablio, roamkit staging) po runbooku (dok. 04/05) s backupom i restore probom.
3. Razriješiti nesklad `nextcloud_immich_bridge`/`immich_machine_learning` → `DB_HOSTNAME=postgis` (provjera, zatim usklađivanje).
4. Zasebno odlučiti o ERP/Superclean/fiskal PostGIS ovisnostima (dok. 03 gate D) i testnoj politici.

## 12. Potvrda da produkcija nije mijenjana

Izvršeni su isključivo: `docker ps/inspect`, `psql` upiti u `BEGIN READ ONLY` transakcijama (svi zatvoreni `ROLLBACK`-om; dva upita na nepostojeću tablicu završila su greškom i prekinula svoju sesiju bez posljedica), čitanje dokumentacije i Compose datoteka te pisanje ovog dokumenta (+ privremena datoteka s IP mapiranjem u scratchpadu). Nema INSERT/UPDATE/DELETE/ALTER/DROP/CREATE, restarta, recreatea, promjene mountova, rola, `.env`/Compose/Traefik datoteka, aplikacijskih konekcija, Redisa, Immich poslova, backupova ni migracijskih žurnala. Nema git commita.

## Završna oznaka

`POSTGRES_SERVICE_SPLIT_PARTIAL`
