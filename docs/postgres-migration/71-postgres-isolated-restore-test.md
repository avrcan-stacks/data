# 71 — B3: izolirani restore test (B1 dumpovi)

Datum: 2026-11-18. Pokušaj 1: 08:30:27–08:30:43 UTC (zaustavljen na `farma_db`); pokušaj 2 (nastavak, opcija A): 08:36:38–08:45:32 UTC; **B3.1 (`qubit_user`): 08:49–09:01 UTC**. Status: **`B3_RESTORE_TEST_PARTIAL_29_OF_31_PASS`** — **29 PASS, 2 FAIL (`farma_db`, `mozzart_db`), 0 NOT TESTED**. Ukupni ishod testa: **FAIL** (dvije baze nisu obnovljive pod strogim `--exit-on-error`; uzrok PostGIS 3.4.3 → 3.6.2).

Izvor: `/opt/stacks/data/backups/b1-20261118T080633Z/` (SHA-256 manifest prije testa: 157/157 OK). Skripta: `/tmp/claude-0/-opt-stacks-data/620aaa91-5a04-418f-bd25-15f05daf2ede/scratchpad/b3-restore.sh` (bez tajni). Radni direktorij testa: `/opt/stacks/data/backups/b3-restore-test-20261118T083027Z/` (`0700`, 526 MB; logovi i rezultati).

## Okruženje testa (provjereno)

| Stavka | Vrijednost |
|---|---|
| Kontejner | `pgrestore-test-b3-20261118T083027Z`, iz `postgis-local:16-bookworm-postgis3-cron-vchord1.1.1` |
| Mreža | `--network none`, 0 objavljenih portova, `listen_addresses=''` (samo unix socket u kontejneru) |
| Mountovi | samo novi PGDATA `…/b3-restore-test-…/pgdata` (rw) i B1 direktorij kao `/b1` **read-only**; nema produkcijskih volumena ni Docker socketa |
| Resursi | 8 CPU, 24 GiB RAM (swap isti), `--pids-limit 2000`, `--cap-drop ALL` uz minimalne `CHOWN/SETUID/SETGID/DAC_OVERRIDE/FOWNER`, `no-new-privileges` |
| Ekstenzije u imageu | postgis/topology/tiger_geocoder **3.6.2** (jedina instalacijska verzija), vchord 1.1.1, vector 0.8.2, pg_cron 1.6, pgcrypto, pg_trgm, cube, earthdistance, unaccent, uuid-ossp, pg_stat_statements, pageinspect, fuzzystrmatch — sve potrebne prisutne |
| pg_cron | `shared_preload_libraries=vchord,pg_cron`, `cron.database_name=postgres` (u toj bazi nema ekstenzije, kao u produkciji), **`cron.launch_active_jobs=off`** (uključeno od inicijalizacije); `log_min_error_statement=panic` (da se SQL s hashevima ne zapisuje u logove) |
| Zaštite | watchdog: prag 200 GB slobodno (najmanje izmjereno 408 GB), I/O pressure; opterećenje ≤ 4,05 |
| Bootstrap superuser | `restore_admin` (da globals ne kolidira s ulogom `postgres`) i pomoćna baza `restore_boot` — nisu dio usporedbe |

## Rezultati

| Korak | Izlazni kod | Napomena |
|---|---|---|
| Globals (`psql -v ON_ERROR_STOP=1 -f globals.sql`) | **0** | 0 redaka na stderr; sadržaj nije ispisan |
| Kreiranje 31 baze (vlasnik, kodiranje, locale iz produkcije) | 0 | |
| `chatwoot` (`pg_restore --exit-on-error`) | **0** | |
| `farma_db` | **1** | **ZAUSTAVLJENO** (vidjeti niže) |
| 29 preostalih baza (uključujući `crowdsec`, `qubit_user`, `immich`) | — | **nisu pokrenute** |
| Usporedba baza/rola/ekstenzija/objekata/redaka, pg_cron provjere | — | **nisu izvršene** (test prekinut prije verifikacije) |

Test kontejner je zaustavljen (`Exited (0)`), **kontejner i PGDATA su zadržani** za pregled (brisanje samo uz tvoje odobrenje). Produkcijski `postgis` i `immich-db` rade neizmijenjeno (healthy); lokalni B1 backup i Borg arhive nisu diran; nema Git operacija.

## Pogreška: `farma_db`

```
pg_restore: error: could not execute query: ERROR:  function "st_asgeojson" already exists with same argument types
Command was: CREATE FUNCTION public.st_asgeojson(r record, geom_column text DEFAULT ''::text, maxdecimaldigits integer DEFAULT 9, pretty_bool boolean DEFAULT false, id_column text DEFAULT ''::text) ... AS '$libdir/postgis-3', 'ST_AsGeoJsonRow';
```

**Uzrok (potvrđen read-only upitima nad produkcijom):**
- U produkcijskoj `farma_db` PostGIS ekstenzija je u SQL verziji **3.4.3**, a biblioteka je **3.6.2** (`postgis_lib_version()=3.6.2`, `postgis_scripts_installed()=3.4.3`). Ekstenzija nikad nije nadograđena (`ALTER EXTENSION UPDATE`).
- U shemi `public` te baze postoji **12 „labavih" `st_*` funkcija koje nisu dio ekstenzije** (ostaci starijih nadogradnji), među njima `st_asgeojson(record, text, int, bool, text)`.
- `pg_dump` ne bilježi verziju ekstenzije, pa `CREATE EXTENSION postgis` na restoreu instalira **3.6.2** (jedina instalacijska verzija u imageu). PostGIS 3.6.2 sam kreira funkciju iste signature, a dump je zatim pokušava ponovno kreirati kao samostalnu → `already exists`.
- Isto vrijedi za svaku bazu s PostGIS SQL 3.4.3: `farma_db`, `postgres`, `mozzart_db`. Samo `farma_db` ima labave funkcije (kontrolirano: `postgres` i `mozzart_db` 0 labavih `st_asgeojson`; ostale baze nemaju labavih `st_*` funkcija), pa bi se ostale dvije trebale restaurirati, ali nije provjereno.

Dump je **cjelovit i čitljiv** (TOC i checksumi prolaze); problem je kompatibilnost restorea s `--exit-on-error` na ovom imageu, ne oštećenje podataka.

## Dodatni nalazi

1. **Praznina B1 sigurnosne kopije:** `pg_dump` bez `--create` i `pg_dumpall --globals-only` ne bilježe **ACL-ove baza** (`datacl` postavljen na 15 od 31 baza) niti **postavke po bazi** (`pg_db_role_setting` s `setdatabase<>0`: 3 retka). Test je zato kreirao baze samo s vlasnikom/kodiranjem/locale-om. Preporuka: dodatni izvoz tih metapodataka (read-only upit u `pg_database`/`pg_db_role_setting`) u dopunu B1 prije migracije.
2. **PostGIS neusklađenost u produkciji** (3.4.3 SQL / 3.6.2 lib u `farma_db`, `postgres`, `mozzart_db`) ostaje; svaka buduća nadogradnja ili migracija ekstenzije pogodit će `farma_db` istom greškom.
3. `pg_cron` provjere (7 poslova u `qubit_user`, nema izvršavanja) **nisu izvršene** jer `qubit_user` nije dosegnut.

## Odluka vlasnika (iz pokušaja 1; vlasnik je odabrao A uz ograničenja — vidjeti pokušaj 2)

- **A (preporuka):** nastaviti restore preostalih 29 baza na istom (zadržanom) PGDATA-u. Za `farma_db` (i `postgres`/`mozzart_db` ako zatreba): prethodno `CREATE EXTENSION postgis` pa `pg_restore` **bez `--exit-on-error`** za taj jedan objekt, ili `--exclude`/popis bez 12 labavih funkcija; izvedeno i dokumentirano kao izuzetak. Ostalih 28 baza ostaje na strogom `--exit-on-error`.
- **B:** ponoviti cijeli test na čistom PGDATA-u (uklanja djelomično stanje; zahtijeva brisanje testnog PGDATA-a uz tvoje odobrenje).
- **C:** prije nastavka riješiti labave funkcije u produkcijskoj `farma_db` (izmjena produkcije — nije u opsegu).


---

## Pokušaj 2 — nastavak (opcija A s ograničenjima vlasnika)

Skripta: `/tmp/claude-0/-opt-stacks-data/620aaa91-5a04-418f-bd25-15f05daf2ede/scratchpad/b3-continue.sh` (bez tajni). Zadržani su isti izolirani kontejner (`--network none`, 8 CPU / 24 GiB) i isti testni PGDATA; kontejner je samo ponovno pokrenut (`docker start`) s istom konfiguracijom (`cron.launch_active_jobs=off`, `shared_preload_libraries=vchord,pg_cron`, `cron.database_name=postgres`). `--exit-on-error` ostao je uključen za **svaku** bazu; nijedan konflikt nije tolerirana. `farma_db` nije ponovno pokušavana i ostaje FAIL/PENDING. Produkcijske baze nisu mijenjane (samo SELECT upiti).

### Tablica svih 31 baza

| # | Baza | Status | pg_restore rc | Napomena |
|---|---|---|---|---|
| 1 | chatwoot | **PASS** | 0 | |
| 2 | crowdsec | **PASS** | 0 | `-Fd -j4`, 440 s; 38 GB baza; ekstenzije/objekti isti |
| 3 | farma_db | **FAIL (PENDING)** | 1 | PostGIS 3.4.3 SQL → 3.6.2; labava funkcija `st_asgeojson(record,…)` već postoji (pokušaj 1); nije tolerirano |
| 4 | finestar_erp_db | **PASS** | 0 | |
| 5 | fiskal | **PASS** | 0 | |
| 6 | fiskal_f1_pts_smoke | **PASS** | 0 | |
| 7 | headscale | **PASS** | 0 | |
| 8 | immich | **PASS** | 0 | vchord 1.1.1 / vector 0.8.2 / PostGIS 3.6.2 isti kao izvor |
| 9 | mailblocklist | **PASS** | 0 | |
| 10 | minidepo | **PASS** | 0 | |
| 11 | mozzart_db | **FAIL** | 1 | `GRANT ALL ON FUNCTION public._st_concavehull(geometry) TO postgis` → *function does not exist* (funkcija iz PostGIS 3.4.3 SQL skripti ne postoji u 3.6.2); ista klasa uzroka kao `farma_db` |
| 12 | nextcloud | **PASS** | 0 | |
| 13 | omnimsgio | **PASS** | 0 | |
| 14 | parkschloss | **PASS** | 0 | |
| 15 | postgres | **PASS** (s napomenom) | 0 | PostGIS family obnovljen kao **3.6.2** (izvor 3.4.3); funkcije 947 → 952, indeksi 177 → 176 — posljedica verzije ekstenzije, ne gubitka podataka |
| 16 | powerdns | **PASS** | 0 | |
| 17 | predix | **PASS** | 0 | |
| 18 | qubit_user | **PASS (B3.1)** | 0 | pokušaj 2: FAIL (`CREATE EXTENSION pg_cron` → *can only create extension in database postgres*); B3.1 s `cron.database_name=qubit_user` + `cron.launch_active_jobs=off`: PASS, strogi `--exit-on-error`; vidjeti B3.1 |
| 19 | racunai_intermediary | **PASS** | 0 | |
| 20 | roamkit | **PASS** | 0 | |
| 21 | roamkit_production | **PASS** | 0 | |
| 22 | snappymail | **PASS** | 0 | |
| 23 | stay_platform_db | **PASS** | 0 | |
| 24 | stay_platform_test_db | **PASS** | 0 | |
| 25 | superclean_db | **PASS** | 0 | |
| 26 | tablio_platform_db | **PASS** | 0 | |
| 27 | test_finestar_erp_db | **PASS** | 0 | |
| 28 | test_predix | **PASS** | 0 | |
| 29 | test_qubit_user | **PASS** | 0 | nema pg_cron |
| 30 | test_stay_platform_db | **PASS** | 0 | |
| 31 | test_stay_platform_test_db | **PASS** | 0 | |

**Zbroj (nakon B3.1): 29 PASS, 2 FAIL, 0 NOT TESTED** (u pokušaju 2: 28/3/0). Globals: PASS (rc 0).

### Provjere nad 28 uspjelih baza

- **Baze i role:** svih 31 baza kreirano; popis baza i 21 korisnička rola s atributima **identični produkciji** (`diff` prazan).
- **Ekstenzije:** identične izvoru u 27 od 28 baza; razlika samo `postgres` (PostGIS 3.4.3 → 3.6.2, očekivano jer `pg_dump` ne bilježi verziju ekstenzije).
- **Broj objekata** (tablice, indeksi, sekvence, viewovi, funkcije, okidači): identičan u 27/28; razlika samo `postgres` (vidjeti gore).
- **Retci (3 najveće tablice po bazi, 84 uzorka):** 74 jednaka, 10 s malom razlikom (≤ 0,3 %) — u svih 9 egzaktnih usporedbi produkcija ima **više** redaka od obnovljene kopije, što je očekivano jer je produkcija živa (dump 08:06–08:10 UTC): iana_ipwhoislookup 3 771 138 vs 3 770 711; fiskal.worker_metrics 188 454 vs 188 416; nextcloud.oc_activity/oc_filecache/oc_job_runs; predix.bets_walletbalancesnapshot; racunai_intermediary.idempotency_keys/outbox_events; roamkit_production.esims_esimlifecycleevent. `crowdsec.monitoring_attackevent` (36 GB): produkcija je samo procjena (`reltuples` 41 507 640) nasuprot egzaktnom broju obnovljene kopije 41 754 683 — nije izravno usporedivo; nema znakova gubitka.
- **Veličina i resursi:** testni PGDATA 39 GB; najmanje slobodno 371 GB (prag 200 GB); I/O pressure najviše 2; opterećenje domaćina najviše 11,8 (8 CPU ograničenje testa); test kontejner bez restartova i OOM-a.

### `qubit_user` i `pg_cron`

- Restore ne uspijeva pod konfiguracijom `cron.database_name=postgres`: `CREATE EXTENSION pg_cron` dopušten je samo u toj bazi. Produkcijska ekstenzija postoji u `qubit_user`, pa je vjerojatno kreirana dok je `cron.database_name` bio `qubit_user` (dosljedno s nalazom iz doc 68 R9 da scheduler u produkciji ne vidi te poslove). Za pun restore te baze test kontejner treba pokrenuti s `cron.database_name=qubit_user` **uz** `cron.launch_active_jobs=off`; to zahtijeva ponovno kreiranje kontejnera s drugom konfiguracijom nad istim PGDATA-om i nije izvedeno bez tvog odobrenja.
- **Nijedan pg_cron posao nije pokrenut:** `qubit_user` nije obnovljen pa u test clusteru ne postoji `cron.job`/`cron.job_run_details` (nema što pokrenuti); `cron.launch_active_jobs=off` provjeren pri svakom startu; log sadrži samo pokretanje/gašenje schedulera i pad launchera (exit 1) uz poruku da poslovi moraju biti zakazani iz baze `cron.database_name` (posljedica pokušaja `CREATE EXTENSION`). Provjera podataka `cron.job` (7 poslova, 3895 zapisa) **nije izvršena** — NOT VERIFIED.
- **Utjecaj na produkciju:** nema — `postgis` i `immich-db` prije i poslije: running, healthy, 0 restartova, isti `StartedAt` (diff prazan); testna mreža `none`.

## Preostalo

1. **Tri baze nisu obnovljive strogim `--exit-on-error`** (`farma_db`, `mozzart_db`: PostGIS 3.4.3→3.6.2; `qubit_user`: pg_cron konfiguracija). Podaci u dumpovima su cjeloviti; potrebne su dokumentirane prilagodbe restorea ili ispravak izvora (PostGIS `ALTER EXTENSION UPDATE`, čišćenje labavih funkcija u `farma_db`, usklađivanje `cron.database_name`) — nijedna nije izvedena.
2. Praznina B1: ACL-ovi baza (15) i postavke po bazi (3) nisu u dumpovima (vidjeti gore).
3. Testni kontejner (zaustavljen) i testni PGDATA (39 GB) zadržani; brisanje samo uz tvoje odobrenje.
4. Nema novih Git operacija; `71-…md` je neposnimljen u Gitu.


---

## B3.1 — `qubit_user` (pg_cron), 2026-11-18

Odobreno od vlasnika; bez promjena produkcije, Gita i migracije. Produkcija je samo čitana (SELECT).

**Priprema i izolacija**
- Prethodni test kontejner `pgrestore-test-b3-20261118T083027Z` bio je zaustavljen (`exited`, mreža `none`; mountovi samo testni PGDATA i B1 `ro`). Njegovi argumenti ne mogu se mijenjati, pa je nad **istim testnim PGDATA-om** pokrenut **novi** kontejner `pgrestore-test-b3-qubit-20261118T083027Z` iz iste slike `postgis-local:16-bookworm-postgis3-cron-vchord1.1.1`; stari kontejner **nije obrisan** ni pokretan istodobno.
- Novi kontejner: `--network none`, 0 portova, bez Docker socketa, mountovi samo testni PGDATA (rw) i `/b1` (**ro**), 8 CPU / 24 GiB, `cap-drop ALL` uz minimalne capove; `listen_addresses=''`.
- Postavke: `shared_preload_libraries=vchord,pg_cron`, **`cron.database_name=qubit_user`**, **`cron.launch_active_jobs=off`** (potvrđeno `show` upitom prije restorea i nakon njega).
- Prije restorea provjerena testna `qubit_user`: **nema ostataka** prethodnog neuspjelog pokušaja (samo `plpgsql`, shema `public`, 0 korisničkih relacija i funkcija, nema sheme `cron`, 7 487 kB = prazna baza). Resetiranje/brisanje stoga **nije bilo potrebno** i ništa nije obrisano.

**Restore:** `pg_restore -U restore_admin -d qubit_user --exit-on-error /b1/qubit_user.dump` → **rc 0**, 1 s, bez ijedne pogreške. Ekstenzije u testu = produkcija (`pg_cron 1.6`, `plpgsql 1.0`); 123 korisničke tablice u obje baze.

**Poslovi `pg_cron`** (tekst naredbi nije čitan ni ispisan; samo duljina):

| jobid | raspored | naziv | aktivan | korisnik | baza | usporedba s produkcijom |
|---|---|---|---|---|---|---|
| 1 | `15 2 * * *` | headscale_log_prune | da | qubit | qubit_user | identično |
| 2 | `15 3 * * 0` | headscale_log_export | da | qubit | qubit_user | identično |
| 3 | `30 2 * * *` | user_log_prune | da | qubit | qubit_user | identično |
| 4 | `30 3 * * 0` | user_log_export | da | qubit | qubit_user | identično |
| 5 | `0 2 * * *` | nginx_log_prune | da | qubit | qubit_user | identično |
| 6 | `0 3 * * 0` | nginx_log_export | da | qubit | qubit_user | identično |
| 7 | `0 * * * *` | nginx_log_partition_warmup | da | qubit | qubit_user | identično |

Povijest `cron.job_run_details` (usporedba u UTC): **3 895 zapisa, isto kao u produkciji**; po poslu identično (poslovi 1/3/5: 142 izvršavanja, zadnje 2026-04-04 ≈02:xx UTC; poslovi 2/4/6: 20 izvršavanja, 13 neuspjelih, zadnje 2026-03-29; posao 7: 3 409 izvršavanja, zadnje 2026-04-04 21:00 UTC). Raniji prikaz razlike u `max(start_time)` bio je samo razlika vremenske zone sesije (+02 prema UTC).

**Nijedan posao nije izvršen:**
- Nakon restorea (≈08:50 UTC): 0 zapisa novijih od 2026-04-04; 0 zapisa započetih u zadnjih 30 min.
- Dodatna provjera nakon **09:00 UTC** (posao 7 je satni, `0 * * * *`, i bio bi izvršen u 09:00 da je scheduler aktivan): provjera u 09:01:31 UTC — `run_details_total=3895`, `max(runid)=3895`, **0 zapisa iz 2026-11-18**, posao 7 aktivan i zakazan, `cron.launch_active_jobs=off`. Log sadrži samo „pg_cron scheduler started" (1 redak), nema zapisa o pokretanju poslova.
- Poslovi su zakazani (aktivni) u testnoj kopiji, ali scheduler ih ne pokreće zbog `launch_active_jobs=off`; kontejner nema mrežu.

**Utjecaj na produkciju:** nema. `postgis` i `immich-db` prije/poslije: running, healthy, 0 restartova, nepromijenjen `StartedAt`; produkcijska `pg_cron` konfiguracija i poslovi nisu dirani. Test kontejner je na kraju zaustavljen (`exited`, exit 0); oba test kontejnera i testni PGDATA (≈39 GB) zadržani. Slobodno 371 GB.

**Zaključak B3.1: PASS.** `qubit_user` je obnovljen strogo, 7 `pg_cron` poslova i povijest identični produkciji, nijedan posao nije pokrenut.

**Ostaje FAIL:** `farma_db` (labava funkcija `st_asgeojson` + PostGIS 3.4.3→3.6.2) i `mozzart_db` (`GRANT` na `_st_concavehull`, funkcija ne postoji u PostGIS 3.6.2). Nisu mijenjane ni tolerirane.

**B3_RESTORE_TEST_PARTIAL_29_OF_31_PASS** (B3.1 `qubit_user`: PASS; preostala FAIL: farma_db, mozzart_db)
