# 68 — PostgreSQL backup, faza B1: READ-ONLY preflight

Datum: 2026-11-18. Način: samo čitanje. Izvršeni su isključivo `SELECT`/`SHOW` upiti kroz `docker exec postgis psql`, `ls`/`du`/`df`, pregled crontaba i systemd timera te `ssh storagebox df/du`. Nije pokrenut `pg_dump`/`pg_dumpall`, nema pisanja u baze, nema izmjena Dockera/Composea, nema novog servisa, brisanja ni Git operacija. Pristupna fraza nije korištena niti zapisana.

Status: `PREFLIGHT_COMPLETE_AWAITING_OWNER_APPROVAL`

---

## 1. Inventar `postgis` servisa

| Stavka | Vrijednost |
|---|---|
| Kontejner / image | `postgis` / `postgis-local:16-bookworm-postgis3-cron-vchord1.1.1`, up 4 mjeseca, healthy |
| Verzija | PostgreSQL 16.13 (Debian 16.13-1.pgdg12+1); `pg_dump`/`pg_dumpall` 16.13 (iste verzije kao server) |
| PGDATA | `/opt/stacks/data/postgres/data` — 41 GB (`base` 41 GB, `pg_wal` 81 MB) |
| Postavke | `data_checksums=off`, `wal_level=replica`, `archive_mode=off` (nema WAL arhiviranja ni PITR), `max_connections=100`, `shared_preload_libraries=vchord,pg_cron` |
| Aktivne konekcije | 44 (aplikacije su žive; backup ide na živom sustavu) |
| Tablespaceovi | samo `pg_default`, `pg_global` |
| `pg_cron` | ekstenzija 1.6 samo u `qubit_user`; `cron.database_name=postgres`; 7 poslova (neaktivnih u praksi) — vidjeti R9 |
| Baze | 34 ukupno: 31 običnih + `template_postgis` + `template0` + `template1`; za izvoz 32 (bez `template0`/`template1`) |
| Zbroj svih baza | ≈ 40,8 GB (`crowdsec` 38 GB + ostale ≈ 2,5 GB) |

### Baze po veličini

| Baza | Veličina | Vlasnik | Napomena |
|---|---|---|---|
| **crowdsec** | **38 GB** | crowdsec | 36 GB je jedna tablica `public.monitoring_attackevent`; 1,6 GB `iana_ipwhoislookup`. Vrlo aktivna (≈220 M commitova). Collation mismatch. **Dominira svim procjenama.** |
| immich | 1192 MB | immich | **Vjerojatno zastarjela kopija** — produkcijski Immich radi na `immich-db` (cutover izvršen, docs 55/56). Treba potvrditi s vlasnikom; preporuka je ipak arhivirati prije razdvajanja. |
| mozzart_db | 205 MB | postgis | collation mismatch |
| nextcloud | 143 MB | nextcloud | |
| predix | 137 MB | predix | |
| finestar_erp_db | 134 MB | postgis | |
| racunai_intermediary | 104 MB | postgis | |
| postgres | 68 MB | postgres | |
| stay_platform_db | 49 MB | stay | |
| fiskal | 40 MB | fiskal | |
| farma_db | 39 MB | farma_app | |
| mailblocklist | 37 MB | mailblocklist | |
| test_finestar_erp_db | 33 MB | postgis | testna |
| test_stay_platform_test_db | 25 MB | stay | testna |
| stay_platform_test_db | 24 MB | stay | testna |
| qubit_user | 22 MB | qubit | collation mismatch |
| chatwoot | 21 MB | chatwoot | ima i vlastiti dnevni backup (`chatwoot-backup`) |
| template_postgis | 19 MB | — | template (`datistemplate`) |
| minidepo | 18 MB | postgres | |
| roamkit / roamkit_production | 18 / 17 MB | roamkit | |
| superclean_db | 17 MB | superclean | |
| test_stay_platform_db, test_predix, test_qubit_user | 14 / 14 / 12 MB | — | testne; `test_qubit_user` ima collation mismatch |
| tablio_platform_db | 10 MB | tablio | |
| fiskal_f1_pts_smoke | 9,4 MB | fiskal | smoke baza |
| headscale | 9,3 MB | headscale | collation mismatch |
| omnimsgio, powerdns, snappymail, parkschloss | 8,5 / 8,2 / 8,0 / 7,8 MB | — | `powerdns` (vlasnik qubit) i `snappymail` imaju collation mismatch |

**Ekstenzije (ispravljeno 2026-11-18; prvi inventar bio je pogrešan, vidjeti napomenu ispod):** ekstenzije se razlikuju po bazi (`plpgsql` izostavljen):

| Baza(e) | Ekstenzije |
|---|---|
| postgres, farma_db, template_postgis | postgis 3.4.3, postgis_topology 3.4.3, postgis_tiger_geocoder 3.4.3, fuzzystrmatch 1.2 |
| mozzart_db | postgis 3.4.3 |
| finestar_erp_db, fiskal, minidepo, predix, stay_platform_test_db, superclean_db, test_finestar_erp_db, test_stay_platform_test_db | postgis **3.6.2** |
| immich | cube 1.5, earthdistance 1.2, pg_trgm 1.6, postgis 3.6.2, unaccent 1.1, uuid-ossp 1.1, **vchord 1.1.1**, **vector 0.8.2** |
| chatwoot | pg_stat_statements 1.10, pg_trgm 1.6, pgcrypto 1.3, **vector 0.8.2** |
| fiskal_f1_pts_smoke | pgcrypto 1.3 |
| headscale | uuid-ossp 1.1 |
| stay_platform_db | pageinspect 1.12 |
| **qubit_user** | **pg_cron 1.6** (jedina baza s `pg_cron`) |
| bez ekstenzija | crowdsec, mailblocklist, nextcloud, omnimsgio, parkschloss, powerdns, racunai_intermediary, roamkit, roamkit_production, snappymail, tablio_platform_db, test_predix, test_qubit_user, test_stay_platform_db, template1 |

Napomena: raniji inventar u ovom dokumentu (identičan PostGIS 3.4.3 skup u svim bazama, bez vchord/vector) bio je posljedica greške u mojoj pomoćnoj skripti (ime baze nije stiglo u kontejner pa su svi upiti išli na bazu `postgres`). Zamijenjen je ovim popisom. Posljedice: baze s PostGIS 3.6.2 (SQL verzija) i ekstenzije `vchord`/`vector` (immich, chatwoot) moraju se restaurirati u image koji ih sadrži (isti `postgis-local` image ih ima), a verzije biblioteka valja usporediti s dokumentom 05 (R02).

**Role (21 korisnička):** chatwoot, crowdsec, farma_app (**superuser**), fiskal, headscale, immich, mailblocklist, nextcloud, omnimsgio, parkschloss, postgis, postgres (superuser), powerdns, predix, qubit (**superuser**), roamkit, snappymail, stay, stay_uzorita_ro, superclean, tablio. Sve imaju `LOGIN`. `pg_dumpall --globals-only` mora ih obuhvatiti (uz hasheve lozinki — vidjeti §5).

**Collation:** 7 baza ima upozorenje „created using collation version 2.31, OS provides 2.36" (crowdsec, headscale, mozzart_db, powerdns, qubit_user, test_qubit_user, snappymail). Logički dump to ne prenosi (indeksi se grade na restoreu), ali na izvoru indeksi tekstualnih stupaca teoretski mogu biti nekonzistentni; ne blokira backup.

---

## 2. Postojeći backup mehanizmi

| Područje | Nalaz |
|---|---|
| Cron (korisnički) | Samo aplikacijski poslovi (uzorita, file2ban, dalekopro, barakags, stay, traefik). **Nema DB backupa.** `/etc/cron.d` bez backupa. |
| systemd timeri | Samo sustavski (dpkg-db-backup, logrotate, mdcheck…). **Nema DB backupa.** |
| `/opt/stacks/data/backups` | 15 GB, `root:root`. Najnoviji generički dumpovi iz **11.02.2026.** (`pg14_*`, `pg16_dump.sql.gz`, `pg16_globals.sql.gz`, `pg_dumps_2026-02-11.tar.gz`) — zastarjeli. Uz njih radni/neuspjeli artefakti (`*_restore.log`, `pg16_*filtered*.sql`, `pg16_powerdns_block_patched.sql`). Jedini pojedinačni: `finestar_erp_db_2026-06-09.dump` (338 KB). Većinu prostora (≈13 GB) zauzimaju `immich-*` cutover/rehearsal direktoriji — **nisu dio B1**. |
| Chatwoot | `chatwoot-backup` (postgres:16.13-alpine, `/backup-loop.sh`) radi dnevni dump u `backups/chatwoot/`. Zapažanje iz dokumenta 60 (identična veličina dumpova) i dalje neprovjereno. |
| `/srv/qubit/backups` | 104 KB (headscale/nginx konfiguracije), ne DB. |
| WAL arhiviranje / PITR | **Ne postoji** (`archive_mode=off`). |
| Off-site | Do ovog zadatka ništa. Postoji samo Borg repozitorij `ssh://storagebox/./backups/postgres/repository` s **jednim smoke arhivom** (doc 67). |
| Borg | `/usr/bin/borg` 1.2.0 na dedicated serveru, Borg cache u `/root/.cache/borg`. U `/root/` postoje `borg-postgres-recovery.key` i `borg-postgres-recovery-new.key` (sadržaj nije otvaran); vlasnik treba potvrditi je li rotacija fraze dovršena prije B1. |

Zaključak: **trenutačno ne postoji nijedan svjež, provjeren, off-site backup `postgis` baza.**

---

## 3. Slobodan prostor

| Lokacija | Stanje |
|---|---|
| Lokalno `/` (`/dev/md2`; ista particija za PGDATA, `backups/` i `/tmp`) | 2,0 TB ukupno, 1,5 TB zauzeto, **414 GB slobodno** (78 %) |
| Hetzner Storage Box (`u722659`) | 1,0 TB ukupno, **≈1,0 TB slobodno**; `backups/` trenutno ≈ 54 KB |
| RAM | 125 GiB ukupno, ≈75 GiB dostupno; 32 CPU jezgre |

Prostor je dostatan s velikom rezervom (v. §6). Napomena: lokalni staging i restore test dijele disk s PGDATA — pratiti `df` tijekom izvršenja.

---

## 4. Predloženi izvoz

Sve kroz kontejner `postgis` kao admin rola, bez lozinki u komandnoj liniji (lokalni socket; `docker exec` već radi bez lozinke). Staging direktorij: `/opt/stacks/data/backups/b1-<TS>/` (`chmod 700`, gitignoriran). Dumpovi se ne rade u `/tmp`.

```bash
TS=$(date -u +%Y%m%dT%H%M%SZ); S=/opt/stacks/data/backups/b1-$TS
umask 077; mkdir -p "$S"

# globals (role, hashevi lozinki, tablespaceovi) — NE ispisivati, NE u git
docker exec postgis sh -c 'pg_dumpall -U "$POSTGRES_USER" --globals-only' > "$S/globals.sql"

# lista baza (uključujući template_postgis; bez template0/template1)
docker exec postgis sh -c 'psql -U "$POSTGRES_USER" -d postgres -Atc \
  "select datname from pg_database where datname not in ($$template0$$,$$template1$$) order by 1"' > "$S/databases.txt"

# po bazi (serijski; crowdsec zasebno)
while read -r db; do
  docker exec postgis sh -c "pg_dump -U \"\$POSTGRES_USER\" -Fc -d '$db'" > "$S/$db.dump"
done < <(grep -v '^crowdsec$' "$S/databases.txt")

# crowdsec: directory format s paralelizmom, najviše 4 posla
docker exec postgis sh -c 'pg_dump -U "$POSTGRES_USER" -Fd -j4 -f /backups/b1-'$TS'/crowdsec.dir -d crowdsec'

# manifest i čitljivost
( cd "$S" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS )
for f in "$S"/*.dump "$S"/crowdsec.dir; do docker exec postgis pg_restore --list "/backups/b1-$TS/$(basename "$f")" >/dev/null || echo "TOC FAIL $f"; done
```

Napomene:
- `pg_dump` pravi konzistentan snapshot **po bazi**, ne atomaran snapshot svih baza zajedno. Za pred-migracijski sigurnosni backup to je prihvatljivo; za finalni cutover svake aplikacije vrijedi write-freeze iz dokumenta 60 §3.
- `-Fc` (zlib) je odabran radi jednostavnosti i pouzdanog `pg_restore`; `crowdsec` kao `-Fd -j4` skraćuje trajanje najveće baze i omogućava paralelni restore. Format i `-j` mogu se prilagoditi prije odobrenja.
- Izvoz kroz `/backups` mount za `-Fd` zahtijeva da `postgres` korisnik u kontejneru smije pisati u `backups/b1-<TS>/` (treba potvrditi; ako ne, izvoziti u `/tmp` kontejnera pa `docker cp`).
- `immich` baza u `postgis` se uključuje (arhiva prije gašenja); `test_*` i `*_smoke` baze uključene radi cjelovitosti (malene); vlasnik može isključiti.
- Chatwoot ima i vlastiti backup, ali se ovdje svejedno uključuje (jedinstven postupak, jedinstveni manifest).

---

## 5. Borg arhiviranje, integritet i izolirani restore

**Arhiviranje** (vlasnik, privatni terminal, fraza samo na prompt; automatizacija nije u opsegu B1):

```bash
export R='ssh://storagebox/./backups/postgres/repository'
cd /opt/stacks/data/backups/b1-$TS          # relativne putanje u arhivu
borg create --stats --list --compression zstd,3 "$R::postgis-b1-$TS" .
```

**Integritet:**
1. `borg list "$R::postgis-b1-$TS"` — broj i veličine datoteka jednaki lokalnom popisu.
2. `borg check --archives-only -a "postgis-b1-$TS" "$R"` (bez `--repair`).
3. `borg check --verify-data -a "postgis-b1-$TS" "$R"` — povlači i dekriptira sve podatke; trajanje ≈ vrijeme prijenosa. Preporučeno jednom za B1.
4. Restore u **novi prazan** direktorij `/opt/stacks/data/backups/b1-restore-$TS` (`borg extract`), zatim `sha256sum -c SHA256SUMS` — svi `OK`.

**Izolirani restore test:**
- Privremeni kontejner iz **istog image-a** (`postgis-local:16-bookworm-postgis3-cron-vchord1.1.1`), `--network none`, zasebno ime (npr. `pgbackup-restore-test`), zasebni prazan PGDATA (`…/b1-restore-$TS/pgdata`), bez portova, bez Tailscalea, bez veze na produkcijske mreže, bez cron/pg_cron.
- Redoslijed: `globals.sql` → za svaku bazu `createdb` + `pg_restore --exit-on-error -d …` (crowdsec `-j4`).
- Provjere po bazi: `pg_extension` prema tablici ekstenzija u §1 (uključujući verzije PostGIS 3.4.3/3.6.2, vchord, vector, pg_cron), broj tablica/sekvenci, `count(*)` za 5 najvećih tablica po bazi i usporedba s izvorom (izvor može imati novije retke jer je živ — razlika se dokumentira, ne tolerira se manjak), vlasnici/ACL-ovi, `spatial_ref_sys` broj.
- Ukloniti test kontejner i PGDATA **samo uz izričito odobrenje** (brisanje nije u opsegu ovog zadatka).

Ovaj korak uključuje kreiranje privremenog Docker kontejnera (nije mijenjanje `postgis`/`immich-db`) i traži zasebno odobrenje.

---

## 6. Procjena trajanja i prostora (procjena, nije mjereno)

| Korak | Procjena | Osnova |
|---|---|---|
| Izvoz 31 male baze (≈2,5 GB) + globals | 3–8 min | serijski `-Fc` |
| Izvoz `crowdsec` (36 GB jedna tablica) | **20–60 min** | `-Fd -j4`; ovisi o I/O opterećenju produkcije |
| Manifest + `pg_restore --list` | 2–5 min | čitanje dumpova |
| Veličina dumpova (komprimirano) | **≈ 5–15 GB** (ukupno); gornja granica ≈ 41 GB | stvarni omjer za `monitoring_attackevent` nepoznat dok se ne izvrši |
| `borg create` | 10–60 min | zavisi o propusnosti prema Storage Boxu (nije mjerena); dumpovi se slabo deduplikaciraju |
| `borg check --verify-data` | ≈ jednako `borg create` | |
| `borg extract` + `sha256sum -c` | 10–30 min | |
| Restore test svih baza | **1–3 h** (dominira `crowdsec`: 36 GB podataka + indeksi) | |
| Lokalni prostor | staging 5–15 GB (max 41) + extract 5–15 GB + restore PGDATA ≈ 45–60 GB | ukupno ≤ ≈ 160 GB od 414 GB slobodnih |
| Storage Box | 5–15 GB (max ≈ 41 GB) od ≈1,0 TB | |

---

## 7. Rizici

| # | Rizik | Ublažavanje |
|---|---|---|
| R1 | Dugotrajan `pg_dump` `crowdsec` drži snapshot i usporava vacuum na vrlo aktivnoj bazi (≈220 M commitova); dodatni I/O i CPU na produkcijskom disku. | Izvoditi izvan vršnih sati; `-j4` ograničeno; pratiti `df`, latenciju aplikacija i veličinu `crowdsec`; prekid je siguran (nema promjena u izvoru). |
| R2 | `globals.sql` sadrži hasheve lozinki 21 role. | `umask 077`, direktorij `700`, ne ispisivati, ne u git; u Borgu je šifriran; lokalna kopija se briše tek uz odobrenje. |
| R3 | Dump nije atomaran preko baza. | Prihvatljivo za B1; za cutover write-freeze (doc 60). |
| R4 | Pristupna fraza je ranije bila izložena u razgovoru. | Potvrditi dovršenu rotaciju prije B1 (postoji `borg-postgres-recovery-new.key`, nije otvaran). Bez rotacije repozitorij štiti samo pristup Storage Boxu. |
| R5 | Ključ repozitorija leži samo na istom serveru (`/root`). | Prije oslanjanja na backup pohraniti kopiju ključa i fraze izvan servera i izvan Storage Boxa. |
| R6 | Lokalni staging na istoj particiji kao PGDATA; puni disk bi ugrozio produkciju. | Prag: prekinuti ako slobodno < 150 GB; pratiti tijekom rada. |
| R7 | Restore test na istoj fizičkoj mašini opterećuje CPU/disk (`crowdsec`). | Ograničiti `-j`, `nice`/`ionice`, pokrenuti izvan vršnih sati. |
| R8 | Collation mismatch (7 baza); mješavina PostGIS 3.4.3 i 3.6.2 po bazama; `vchord`/`vector` u `immich` i `chatwoot`. | Restore u isti image (glibc/PostGIS/vchord jednaki izvoru); usporediti `postgis_full_version()` prije/poslije; odvojeno planirati `REFRESH COLLATION VERSION`. |
| R9 | **`pg_cron` nesklad konfiguracije; automatsko izvršavanje poslova.** Provjereno read-only 2026-11-18: `shared_preload_libraries = vchord,pg_cron`; `cron.database_name = postgres`; ekstenzija `pg_cron 1.6` instalirana je **samo u `qubit_user`** (u `postgres` nema ni sheme `cron` ni `cron.job` — upit završava greškom `relation "cron.job" does not exist`); procesi `pg_cron launcher`/`scheduler` rade. U `qubit_user.cron.job` postoji **7 aktivnih poslova** (`headscale_log_prune`, `headscale_log_export`, `user_log_prune`, `user_log_export`, `nginx_log_prune`, `nginx_log_export`, `nginx_log_partition_warmup`; raspored `15 2`, `15 3 * * 0`, `30 2`, `30 3 * * 0`, `0 2`, `0 3 * * 0`, `0 * * * *`; korisnik `qubit`; tekst naredbi nije čitan). Posljednja izvršavanja u `cron.job_run_details`: 29.03.2026. (poslovi 2, 4, 6; 13 od 20 izvršavanja neuspješno) i 04.04.2026. (poslovi 1, 3, 5, 7), nakon toga nema zapisa. **Zaključak (vjerojatno, nije promatrano uživo):** scheduler čita poslove samo iz baze `cron.database_name` (`postgres`), gdje ekstenzija ne postoji, pa se poslovi u `qubit_user` zbog nesklada konfiguracije ne izvršavaju. **Rizik:** ako se konfiguracija ikad uskladi (`cron.database_name=qubit_user`, ili `CREATE EXTENSION pg_cron` u `postgres`) ili se `qubit_user` restaurira u cluster u kojem `cron.database_name=qubit_user`, 7 poslova će se automatski početi izvršavati (prune/export logova, `nginx_log_partition_warmup` svakog sata), uz mogućnost brisanja/izvoza podataka ili pisanja datoteka. | **Backup:** ne mijenjati konfiguraciju; `qubit_user` se izvozi kao i ostale baze (dump uključuje ekstenziju i 7 redaka `cron.job`). **Restore test:** scheduler i stvarni zakazani poslovi **ne smiju se pokrenuti** — privremeni cluster pokreće se s `-c shared_preload_libraries=vchord` (bez `pg_cron`) ili s `-c cron.database_name=<nepostojeća/prazna baza>` i `-c cron.launch_active_jobs=off`; prije restorea `qubit_user` provjeriti da `cron.job` nema izvršavanja (`cron.job_run_details` nema novih zapisa nakon restorea); kontejner bez mreže (`--network none`) i bez mountova produkcijskih direktorija. Ako `pg_restore` zbog izostanka `pg_cron` biblioteke ne može kreirati ekstenziju, restore tu bazu s `--exit-on-error` isključenim samo za taj objekt i to dokumentirati. Prije bilo kakve buduće promjene konfiguracije pročitati naredbe poslova (uz maskiranje tajni) i odluka vlasnika. |
| R10 | Stari artefakti u `backups/` (zastarjeli dumpovi, neuspjeli logovi) mogu zavarati. | Ne dirati; B1 koristi zaseban `b1-<TS>` direktorij. |
| R11 | Nema WAL arhiviranja; dump daje samo točku u vremenu. | Prihvaćeno za pred-migracijsku sigurnosnu kopiju; RPO = trenutak dumpa. |
| R12 | Jedan Borg repozitorij, jedna lokacija (Storage Box), jedan korisnik. | Prihvaćeno za B1; razmotriti drugu kopiju u kasnijoj fazi. |
| R13 | Immich baza u `postgis` može biti zastarjela i zbunjujuća. | Potvrditi status s vlasnikom; označiti u manifestu kao „arhiva prije ukidanja". |

---

## 8. Odluke za vlasnika

1. **O1:** Odobriti izvoz (§4) za svih 32 baze (31 obična + `template_postgis`) + globals, ili navesti isključenja (npr. `test_*`, `*_smoke`, `immich`).
2. **O2:** Odobriti vremenski prozor (izvan vršnih sati) zbog `crowdsec`.
3. **O3:** Potvrditi da je rotacija Borg fraze dovršena (ili izričito prihvatiti rizik R4).
4. **O4:** Podjela posla: ja izvršavam izvoz, manifest i provjere TOC-a (bez fraze); vlasnik sam pokreće `borg create/check/extract` u privatnom terminalu.
5. **O5:** Odobriti privremeni izolirani Docker kontejner za restore test (§5), bez promjena postojećih servisa.
6. **O6:** Potvrditi pragove prostora (R6) i politiku čišćenja staginga (brisanje samo uz zasebno odobrenje).

Ništa od navedenog nije izvršeno. Zaustavljam se i čekam odobrenje.
