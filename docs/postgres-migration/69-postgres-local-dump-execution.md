# 69 — B1: lokalni izvoz PostgreSQL baza (`postgis`)

Datum: 2026-11-18, 08:06:33–08:10:53 UTC (trajanje ≈ 4 min 20 s). Status: **`LOCAL_DUMP_PASS`** (Borg arhiviranje i restore test **nisu** izvršeni; to su B2/B3).

Izvršeno prema odobrenju vlasnika (B1). Dumpovi su izrađeni kroz `docker exec postgis` (PostgreSQL 16.13 klijentski alati, `nice -n 10`), samo čitanjem iz baza. Nisu mijenjane baze, role, ekstenzije ni konfiguracija; Docker servisi nisu zaustavljani ni restartani; nije pokrenut novi `postgres` servis; nema Git operacija; sadržaj `globals.sql` nije ispisan.

## Lokacija i dozvole

- Direktorij: `/opt/stacks/data/backups/b1-20261118T080633Z/` (mount `/backups` u kontejneru). **Izvan PGDATA** (`/opt/stacks/data/postgres/data`) — provjereno prije početka; direktorij je u gitignoriranom `backups/`.
- Dozvole: direktorij `0700` root; datoteke `0600` (`globals.sql`, dumpovi, `SHA256SUMS`); `crowdsec.dir` direktoriji `0700`, datoteke `0600`.
- Skripta: `/tmp/claude-0/-opt-stacks-data/620aaa91-5a04-418f-bd25-15f05daf2ede/scratchpad/b1-dump.sh` (bez tajni).

## Sigurnosni uvjeti i opterećenje

- Prag slobodnog prostora: 200 GB. Početno 414 GB slobodno; najmanje tijekom rada **412 GB**; nakon završetka **412G**. Watchdog (svakih 15 s) nije se aktivirao.
- Opterećenje (load): početno ≈ 4,3; najviše tijekom izvoza **8,09** (32 jezgre). I/O pressure (`full avg10`) tijekom izvoza: **0**.
- Disk: `/dev/md2` 79 % zauzet nakon završetka.

## Rezultati

- Globals: `pg_dumpall --globals-only` — **PASS**, 6 043 B (nije ispisan).
- Baze: **31/31 PASS** (`pg_dump` exit 0, veličina > 0, `pg_restore --list` exit 0).
- Ukupna veličina direktorija: **2803468461 B** (≈ 2,6 GiB); od toga `*.dump` datoteke 560350138 B, `crowdsec.dir` 2241182668 B (29 datoteka, `-Fd -j4`, gzip, 190 s).
- Najveća baza `crowdsec` (38 GB u bazi) izvezena je u 2,2 GB (kompresija gzip).

### Dumpovi (`-Fc`) — veličina B / trajanje s

| Baza | Veličina | Sekunde | Status |
|---|---|---|---|
| chatwoot | 446608 | 0 | PASS |
| farma_db | 1641012 | 1 | PASS |
| finestar_erp_db | 62227038 | 2 | PASS |
| fiskal | 6080309 | 1 | PASS |
| fiskal_f1_pts_smoke | 90102 | 0 | PASS |
| headscale | 171200 | 0 | PASS |
| immich | 354261795 | 40 | PASS |
| mailblocklist | 2174650 | 0 | PASS |
| minidepo | 79461 | 1 | PASS |
| mozzart_db | 13579738 | 1 | PASS |
| nextcloud | 12400451 | 2 | PASS |
| omnimsgio | 40208 | 0 | PASS |
| parkschloss | 8611 | 0 | PASS |
| postgres | 26096026 | 2 | PASS |
| powerdns | 21908 | 0 | PASS |
| predix | 10409227 | 1 | PASS |
| qubit_user | 1019889 | 0 | PASS |
| racunai_intermediary | 62804124 | 3 | PASS |
| roamkit | 506383 | 0 | PASS |
| roamkit_production | 452576 | 0 | PASS |
| snappymail | 13342 | 1 | PASS |
| stay_platform_db | 3345275 | 0 | PASS |
| stay_platform_test_db | 491681 | 1 | PASS |
| superclean_db | 108553 | 0 | PASS |
| tablio_platform_db | 109376 | 0 | PASS |
| test_finestar_erp_db | 379867 | 0 | PASS |
| test_predix | 365619 | 1 | PASS |
| test_qubit_user | 210038 | 0 | PASS |
| test_stay_platform_db | 323730 | 0 | PASS |
| test_stay_platform_test_db | 491341 | 0 | PASS |
| crowdsec (`-Fd -j4`) | 2241182668 | 190 | PASS |

### Provjera formata i metapodataka (`pg_restore --list`)

Svi arhivi: format `CUSTOM` odnosno `DIRECTORY` (crowdsec), „Dumped from database version: 16.13", exit 0. Broj TOC unosa:

| Baza | Unosa | Izlazni kod |
|---|---|---|
| chatwoot | 1036 | rc=0 |
| crowdsec | 264 | rc=0 |
| farma_db | 2580 | rc=0 |
| finestar_erp_db | 2154 | rc=0 |
| fiskal | 199 | rc=0 |
| fiskal_f1_pts_smoke | 201 | rc=0 |
| headscale | 50 | rc=0 |
| immich | 1725 | rc=0 |
| mailblocklist | 268 | rc=0 |
| minidepo | 133 | rc=0 |
| mozzart_db | 2010 | rc=0 |
| nextcloud | 2006 | rc=0 |
| omnimsgio | 63 | rc=0 |
| parkschloss | 18 | rc=0 |
| postgres | 325 | rc=0 |
| powerdns | 73 | rc=0 |
| predix | 917 | rc=0 |
| qubit_user | 1093 | rc=0 |
| racunai_intermediary | 51 | rc=0 |
| roamkit | 542 | rc=0 |
| roamkit_production | 541 | rc=0 |
| snappymail | 26 | rc=0 |
| stay_platform_db | 1058 | rc=0 |
| stay_platform_test_db | 1037 | rc=0 |
| superclean_db | 247 | rc=0 |
| tablio_platform_db | 251 | rc=0 |
| test_finestar_erp_db | 845 | rc=0 |
| test_predix | 849 | rc=0 |
| test_qubit_user | 484 | rc=0 |
| test_stay_platform_db | 698 | rc=0 |
| test_stay_platform_test_db | 1037 | rc=0 |

TOC datoteke (`*.toc`) spremljene su uz dumpove. `pg_restore --list` potvrđuje čitljivost zaglavlja/TOC-a; **nije** dokaz obnovljivosti (to je restore test, B3).

### Upozorenja

Jedina upozorenja (u `*.err`) su poznata `collation version mismatch` (2.31 → 2.36) za: crowdsec, headscale, mozzart_db, powerdns, qubit_user, snappymail, test_qubit_user. Ne utječu na ispravnost dumpa. Nema drugih grešaka.

## SHA-256 manifest

- Datoteka: `SHA256SUMS` (u istom direktoriju), **157 datoteka**, `sha256sum -c`: svi `OK`.
- SHA-256 same datoteke `SHA256SUMS`: `602ff48819f64069ba12413785c0e60d12fe404459842afefd23f6a1599703cb`
- Manifest ne uključuje `run.log` i `monitor.log` (pišu se i nakon izrade manifesta). Prva verzija manifesta uključivala je `run.log` pa je jedna stavka (`run.log`) javljala `FAILED` zbog naknadnog dopisivanja; manifest je ponovno izrađen bez njega — podaci dumpova nisu bili pogođeni.
- Hashevi `globals.sql` i dumpova nalaze se u manifestu; `globals.sql` sadrži hasheve lozinki i ne smije se ispisivati ni commitati.

## Preostalo / rizici

1. Podaci su samo lokalno, na istom disku kao PGDATA — **nema off-site kopije dok se ne izvrši B2 (Borg)**.
2. Dump je konzistentan po bazi, ne preko baza; aplikacije su radile tijekom izvoza (RPO = trenutak dumpa pojedine baze).
3. Obnovljivost nije dokazana (B3). Posebno provjeriti: `qubit_user` (pg_cron, scheduler ne smije raditi — vidjeti doc 68 R9), PostGIS 3.4.3/3.6.2, `vchord`/`vector` u `immich` i `chatwoot`.
4. Pristupna fraza Borg repozitorija prethodno izložena; potvrditi rotaciju prije B2 (doc 68 R4).
5. `globals.sql` sadrži hasheve lozinki — ostaje `0600` u `0700` direktoriju; brisanje lokalne kopije tek uz zasebno odobrenje.

Zaustavljeno nakon lokalnog izvoza. Migracija nije započeta.
