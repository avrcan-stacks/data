# 17 — Immich: priprema produkcijskog cutovera (postgis → immich-db)

Datum: 14. studenoga 2026. (Europe/Zagreb).
Status: **priprema; cutover nije odobren ni pokrenut.** Produkcijski kontejneri, Compose, `.env`, baze, lozinke i backupovi nisu mijenjani. Nijedna skripta nije izvršena nad produkcijom.

**Revizija nakon faze 6B (rehearsal na izoliranom stacku, [18](18-immich-cutover-rehearsal.md)):** runbook je ispravljen u 9 točaka koje je rehearsal otkrio (dolje, odjeljak 1.1). Postupak je sada u izvršivoj datoteci `immich-cutover/steps.sh`; naredbe iz ovog dokumenta ispravno su probane na izoliranoj kopiji.

**Revizija nakon faze 7B ([20](20-immich-cutover-safety.md)):** zatvorena je praznina u `s_open` (eksplicitna stanja cutovera u hash-lančanom žurnalu umjesto datoteke `T_open`, `s_open_abort` samo uz dokaz da nova baza nije primila pisanje, inače HALT i ručni GO/NO-GO), a zamrzavanje ima novi redoslijed (bridge i `media-operations` prvi; baseline i snapshot nakon što su svi pisci zamrznuti). Odjeljci 3–6, 9 i 10 su prepravljeni.

**Revizija nakon faze 7C ([21](21-immich-local-backup-plan.md)):** off-host backup **nije** dio plana (odluka vlasnika); zamijenjen je izričito prihvaćenim rizikom lokalne RAID1 zaštite uz **drugu kopiju na `/home`** (`local_backup.sh`, SHA-256 obje kopije). G6 (off-host) ostaje **neispunjen**; dodan je G14.

**Revizija nakon faze 7D ([22](22-immich-backup-gate.md)):** provjera lokalnih kopija je **obavezna i ugrađena**: `s_open` (i `s_manual_forward`) prije bilo kakve promjene pokreću `lb_gate_open` (uvjet G14); pri neuspjehu HALT (exit 6), promet ostaje zatvoren, `.env`, kontejneri, žurnal i izvorna baza ostaju netaknuti.

Nadovezuje se na [13](13-immich-application-test-plan.md), [15](15-immich-application-retest.md) i [16](16-immich-microservices-test.md). Sve brojke u odjeljku 9 (pragovi) su **prijedlozi, nisu odobreni**; odgovarajući uvjeti ostaju otvoreni GO/NO-GO uvjeti.

## 0. Sažetak

**Što je spremno**
- Provjereni tehnički postupak prebacivanja: zamrzavanje pisanja, dump, sanitizacija bez PostGIS-a, restore u `immich-db`, normalizacija sekvence, usporedba izvor/cilj (72 tablice), validacija ciljne baze i VectorChorda, "dark launch" servera na novoj bazi bez javne rute, validacija, otvaranje prometa.
- Alati u [immich-cutover/](../../immich-cutover/): `steps.sh` (mutirajući koraci), `preflight.py`, `db_snapshot.py`, `validate_target.py`, `api_checks.py`, `getsecret.py`, `docker-compose.dark.yml`, `rehearsal/` i `tests/offline_selftest.sh`. Cijeli lanac probao je rehearsal na izoliranom stacku (124 testa, vidi [18](18-immich-cutover-rehearsal.md)).
- Točne Docker i SQL naredbe, STOP uvjeti, rollback prije i poslije točke bez povratka, plan čuvanja izvorne baze 7 dana, provjere nakon cutovera (backup, video, skeniranje, trash/restore, storage template, OIDC).
- Tehnički uvjeti G4 i G5 potvrđeni (image `immich-db` postoji, mreža `postgis` slobodna, ime `immich-db` slobodno, prazan data direktorij, 439 GiB slobodno).

**Što još nedostaje (otvoreno)**
- Odobrenje pragova i ciljeva (recall, latencija, RPO/RTO, maks. prekid) te termina (G2).
- Off-host kopija **ne postoji** (odluka vlasnika: prihvaćen rizik lokalne RAID1 zaštite, doc 21), odobrenje retencije i rollbacka (G7), odobrenje operacija (G8).
- Privremeni API ključevi (admin i jedan korisnik s podacima) jer ključ koji koristi bridge nema `queue.*` dozvole.
- G9 je ispunjen rehearsalom ([18](18-immich-cutover-rehearsal.md)). Nije probano samo ono što postoji isključivo u produkciji: `preflight.py` provjere za `media-operations`, `traefik` i statične Traefik rute (TR1), stvarni HTTP prema javnom rubu te stvarne količine podataka/prometa.
- Ručna provjera OIDC prijave (vlasnik) i odluka tko ima ovlast za rollback.

**Očekivano trajanje:** DB koraci oko 3 min (mjereno na testnim kopijama), planirani prekid T0 → otvaranje prometa ≤ 30 min, najviše 45 min, tvrdi STOP i rollback na 60 min. To su prijedlozi, ne SLA.

## 1. Što je provjereno u ovoj fazi

| Tema | Nalaz |
| --- | --- |
| Backup u 02:00 | `database-backup.service.js` bira `/usr/lib/postgresql/<major>/bin/pg_dump` prema verziji **servera** (16 → klijent `pg_dump` **16.15** u imageu; podržani 14–18), spaja se na `DB_HOSTNAME` kao rola `immich` s `--clean --if-exists`, piše `immich-db-backup-<ts>-v3.3.5-pg<verzija servera>.sql.gz` u `/data/backups`, čuva `keepLastAmount` (14). Danas: dnevni backupovi `…-pg16.13.sql.gz` (≈355 MB); nakon cutovera imena će nositi `pg16.16`. Klijent 16.15 prema serveru 16.16 je dopušten (klijent ne smije biti stariji od glavne verzije servera). Backup u testovima nije izvršen (isključen), pa se provjerava nakon cutovera (odjeljak 8). |
| Raspored Immich cron poslova | knjižnice i noćni poslovi 00:00, backup 02:00, integrity 03:00 (do 1 h), provjera verzije svaki sat; bridge svakih 300 s. Preporučeni termin: 04:30–22:00; `preflight.py` odbija prozor 23:40–04:15. |
| API ključ bridgea | dozvole samo `adminUser.*` i `library.*`; **nema `queue.*`**, `job.*`, `asset.read`, `album.read`, `person.read`. Za pauziranje redova i validaciju treba privremene ključeve (odjeljak 5, F0). |
| `media-operations` | pristupa bazi preko `docker exec <DB_HOSTNAME> psql` (docker.sock), pa novi kontejner mora imati ime točno `immich-db` (compose ga ima). Čita `DB_HOSTNAME`/`DB_USERNAME`/`DB_PASSWORD` iz zajedničkog `/opt/stacks/immich/.env`. SQL upiti testirani u fazi 5C. |
| `nextcloud_immich_bridge` | ne koristi bazu (nema DB varijabli ni psql); koristi samo Immich API ključ i `docker.sock`; nije potrebna promjena. |
| OIDC | konfiguracija je u bazi (`system-config`), a izdavatelj je Nextcloud; baza se kopira zajedno s postavkama (SHA-256 `system-config` uspoređuje se prije/poslije). Prijava lozinkom ostaje uključena kao rezervna. Provjera OIDC prijave je ručna. |
| Traefik | `--providers.docker.exposedbydefault=false`, nema statičkih Immich ruta u `/dynamic`; ruta postoji samo dok kontejner ima `traefik.enable=true`. Zato `traefik.enable=false` u override-u skriva "dark" instancu. Override je provjeren protiv produkcijskog Composea (samo parsiranje): `DB_HOSTNAME=immich-db`, `traefik.enable=false`, `.env` netaknut. |
| Mreže | `immich_server` je na `default`, `postgis`, `proxy`; `immich-db` je u Composeu samo na `postgis`, bez objavljenih portova; `media-operations` i bridge ne trebaju mrežu prema bazi. Sudionika mreže `postgis` je 42, ime `immich-db` je slobodno. |
| Redis | `immich_redis` nema volumen: pri restartu ili recreateu gube se redovi i stanje pauze. Ne smije se dirati (`--no-deps`). |
| Jedini klijent produkcijske baze | `immich_server` (172.28.0.11, 11 praznih veza); nema drugih potrošača. |
| Data direktorij `immich-postgres/data` | postoji, prazan; image `immich-db-local:16.16-bookworm-vector0.8.2-vchord1.1.1` (`sha256:e21ee65b…`) prisutan. |
| Prostor | 439 GiB slobodno; puna baza 1,16 GiB, dump ≈0,34 GiB. |

### 1.1 Što je rehearsal (faza 6B) ispravio u ovom runbooku

| # | Nalaz u rehearsalu | Ispravak |
| --- | --- | --- |
| 1 | `sed/cut` čitanje `DB_PASSWORD` iz `.env` daje pogrešnu vrijednost za 3 od 9 oblika zapisa (escapeovi u navodnicima, `$` interpolacija, komentar); produkcijska lozinka je alfanumerička (32 znaka), pa je rizik nizak, ali nije nula | lozinka se čita iz **okoline pokrenutog kontejnera** (`getsecret.py immich_server DB_PASSWORD`), točno onako kako ju aplikacija prima; `\getenv` u psql-u; nikad parsiranje `.env` |
| 2 | Provjera lozinke preko `127.0.0.1` ne provjerava ništa: u imageu postgres je `127.0.0.1` `trust` (V6 i dokaz u F2 bili su bezvrijedni) | prijava preko **mrežne adrese kontejnera** uz obaveznu **negativnu kontrolu** (pogrešna lozinka mora biti odbijena) u `s_prepare_target` i `validate_target` V6 |
| 3 | Snapshot izvora uzima se nakon zaštite (`REVOKE CONNECT`), pa se ACL baze izvora razlikuje od bridgea/cilja (ACL baze nije u dumpu) | usporedba ne uspoređuje ACL baze; ACL cilja provjerava `validate_target` V4 prema ACL-u zapisanom prije zaštite (sortirane liste; nesortirana usporedba davala je lažni alarm) |
| 4 | Usporedba podataka i metapodataka bridgea **prije** `DROP EXTENSION` nije postojala | `s_bridge_sanitize` uspoređuje izvor ↔ bridge strogo (načini `source-bridge` i `source-bridge-after`), uključujući owner, ACL, sekvence, indekse, ekstenzije i 72 hasha |
| 5 | Redovi: Immich **ne dopušta** pauziranje reda `backgroundTask` (HTTP 400); stara naredba stala bi na prvom redu i ostavila redove napola pauzirane | `queues pause` pokušava sve redove, `backgroundTask` je dokumentirana iznimka, ostale greške su STOP; `wait-drain` traži `active == 0` svugdje i pauzu svih pauzabilnih redova; status prikazuje i `held` (zadržani poslovi, BullMQ ih broji kao `paused`) |
| 6 | **U dark fazi s microservices workerom aplikacija sama nastavlja red `metadataExtraction`** (`MetadataService` ga bezuvjetno `resume`-a pri svakom startu) i obrađuje zadržane poslove na novoj bazi te ih briše iz Redisa; time bi rollback R1 izgubio posao | dark launch radi s `IMMICH_WORKERS_INCLUDE=api` (bez workera poslova); `s_dark_launch` pada ako se u logu pojavi "Starting microservices worker" |
| 7 | Baseline za usporedbu statistika uzet u F3 zastario je do zamrzavanja (korisnici pišu); verify bi dao lažni FAIL na Q2 | baseline za verify uzima se **nakon pražnjenja redova, neposredno prije zaustavljanja** (`$EV/api-baseline.json`); F3 baseline je samo proba alata (`api-baseline-pre.json`) |
| 8 | `validate_target` V10 uspoređivao je brojeve redaka s baselineom iz preflighta (zastario) | uspoređuje se sa **zamrznutim snapshotom izvora** (`--source-snapshot`) |
| 9 | Nenulti exit kodovi: obrasci `cmd > log; test $? -eq 0 && …` | svaki korak je funkcija u podljusci s `set -Eeuo pipefail`; provjere praznih logova, veličine dumpa, TOC-a, hasha dumpa unutar ciljnog kontejnera; svaki korak odbija pokretanje bez `CUTOVER_APPROVED` |

Dodatno ispravljeno u skriptama: `preflight.py` se više ne ruši zbog jedne nedostajuće datoteke; `verify` na vlastitom baselineu davao je lažni FAIL zbog razlike tipova n-torki i listi; W4 (ANN latencija) sudi samo "tople" upite (prvi upit nakon restorea je hladan); hladni smart-search prag je 5 s jer ML model nakon 300 s mirovanja ponovno učitava (prvi upit ≈2,3 s); provjera backupa traži PostGIS samo u DDL retcima (OCR tekst u podacima može sadržavati riječ "postgis").

## 2. Uvjeti G1–G8 i preostali rizici

| Uvjet | Status | Dokaz / što nedostaje |
| --- | --- | --- |
| G1 Stage A i B PASS | **ispunjen** | [15](15-immich-application-retest.md), [16](16-immich-microservices-test.md) |
| G2 Pragovi recall/latencije i prozor prekida | **OTVOREN** | prijedlozi u odjeljku 9; treba odobrenje |
| G3 Postupak za OIDC | **otvoren (pripremljen)** | ručna provjera u F11; treba imenovati osobu |
| G4 `immich-db` image, mreža, ime, upiti `media-operations` | **ispunjen (tehnički)** | image, mreža, ime provjereni; SQL upiti 5C; kontejner još ne postoji (stvara se u F2) |
| G5 Slobodan prostor ≥ 96 GiB | **ispunjen** | 439 GiB; ponovno u `preflight.py` (H1) |
| G6 Off-host kopija pune produkcijske baze prije prozora | **NIJE ISPUNJEN: off-host kopije nema i neće je biti** | vlasnik je odlučio da se ne koristi; zamjenjuje ga G14 uz izričito prihvaćen rizik (doc 21: RAID1 nije backup; gubitak hosta ili oba diska = gubitak svih kopija) |
| G14 (novo) Lokalna zaštita: RAID1 zdrav, druga kopija na `/home` s jednakim SHA-256 prije T0 i prije F10 | **OTVOREN (kod i vrata ugrađeni i testirani; kopije na produkciji još ne postoje)** | `lb_gate_open` u `s_open`; `tests/local_backup_selftest.sh` (30 provjera) + rehearsal ([22](22-immich-backup-gate.md)); izvršava se tek uz odobrenje O16 |
| G7 Provjeren rollback i odobrena retencija | **OTVOREN** | rollback R1 dokumentiran, nije probano na produkciji; retencija 7 dana je prijedlog |
| G8 Odobrenje promjene `.env`/recreate i zaštite izvora | **OTVOREN** | popis operacija u odjeljku 10 |
| G9 (novo) Skripte probane na izoliranom stacku | **ispunjen** | [18](18-immich-cutover-rehearsal.md): 124 testa, 9 ispravaka; ostaje neprobano samo produkcijski specifično (TR1, M1, javni rub) |
| G10 (novo) Privremeni API ključevi kreirani | **OTVOREN** | admin i jedan korisnik s podacima, vidi F0 |
| G11 (novo) Obavijest korisnicima i utišani monitoring (Uptime Kuma) | **OTVOREN** | |

| Rizik | Kontrola |
| --- | --- |
| Lozinka `DB_PASSWORD` se iz `.env` čita drukčije nego u Composeu (posebni znakovi) | lozinka se uzima iz okoline kontejnera (`getsecret.py`); prijava preko mrežne adrese s negativnom kontrolom u F2 i `validate_target` V6 |
| Skrivanje rute (`traefik.enable=false`) nije isprobano na pravom Traefiku | rehearsal provjerava label (false u dark fazi, true nakon otvaranja); preflight TR1 provjerava da nema statičke Immich rute; neobvezna read-only GET provjera javnog ruba u F8 |
| `docker stop` zaustavljenih kontejnera: restart hosta tijekom prozora | `unless-stopped` ih ne vraća nakon ručnog zaustavljanja; svejedno prozor ne treba preklapati s održavanjem hosta |
| Redis stanje | pauza i pražnjenje aktivnih poslova; čekajući poslovi ostaju u Redisu i obrađuju se nakon nastavka; Redis se ne dira |
| Neuspješan backup u 02:00 nakon cutovera | ručni backup odmah nakon otvaranja (F11), provjera imena `pg16.16`, `gzip -t` i veličine |
| Gubitak zapisa nakon otvaranja prometa | točka bez povratka (odjeljak 6); nakon nje nema automatskog rollbacka |
| Rizik skale i vremena obrade | test je rađen s 12 slika; produkcijsko opterećenje nije mjereno |
| Neprobano: video transkodiranje, trash/restore, storage template, skeniranje knjižnica | kanarski testovi u odjeljku 8 |
| Pragovi nisu odobreni | blokira GO |

## 3. Arhitektura i definicije

- **T0**: početak zamrzavanja (prva pauza reda).
- **Dark launch**: `immich-server` startan s override-om (`DB_HOSTNAME=immich-db`, `traefik.enable=false`, **`IMMICH_WORKERS_INCLUDE=api`**) dok su redovi pauzirani, a bridge i `media-operations` zaustavljeni. Korisnici ne mogu doći do servera, nijedan worker ne troši redove (aplikacija inače sama nastavlja `metadataExtraction`), a API se poziva samo iznutra (`docker exec`).
- **Stanja cutovera** (žurnal `$EV/state.log`, hash-lančan, uz `$EV/state`; svaka izmjena ili brisanje = `CORRUPT` = HALT bez ikakve automatske radnje): `PREPARED → FREEZING → FROZEN → DUMPED → SANITIZED → RESTORED → VALIDATED → DARK_VERIFIED → OPEN_BEGIN → ENV_CHANGED → RECREATING → RECREATED → ROUTE_LIVE → AUX_STARTED → RESUMING → OPEN_CONFIRMED`; izlazi: `ABORT_BEGIN → ABORT_VERIFIED`, `HALT_MANUAL`, `ROLLED_BACK`, `ROLLED_BACK_LOSS_ACCEPTED`. Svaki korak odbija rad (exit 5) ako stanje nije točno njegov prethodnik.
- **Točka bez povratka (PONR)** više nije "postoji li datoteka `T_open`". Određuju ju stanje u žurnalu **i** žive provjere: od `OPEN_BEGIN` nadalje skriptirani rollback R1 je zabranjen; djelomično otvoreno stanje (`OPEN_BEGIN`…`AUX_STARTED`) smije napustiti samo `s_open_abort`, i to samo uz dokaz da nova baza nije primila pisanje; od `RESUMING` (workeri nastavljaju redove) ne postoji automatski povratak. `T_open` (datoteka) bilježi prvi trenutak kada su korisnici mogli doći do nove baze (`ROUTE_LIVE`) i služi samo za logove i unakrsnu provjeru.
- **Svaka nejasnoća = HALT**: oštećen žurnal, `.env` koji nije točno zabilježeni sadržaj, nedostajući ili nepotpun dokaz, bilo koja aktivnost pisanja u novoj bazi, neuspjelo zaustavljanje servera. HALT znači: nikakav automatski rollback; potrebna je ručna odluka s upisanim tokenom (`s_manual_forward` ili `s_manual_rollback_accept_loss`).
- **Izvor** (`postgis/immich`) ostaje netaknut i zaštićen (REVOKE CONNECT), čuva se najmanje 7 dana.
- **RPO prije `ROUTE_LIVE` = 0**: dump se uzima nakon zamrzavanja, pa nijedna potvrđena transakcija nije izgubljena; zahtjevi klijenata tijekom prekida nisu prihvaćeni (mobilne aplikacije ponavljaju kasnije).

Redoslijed: F0 pripreme → F1 preflight → F2 priprema `immich-db` → F3 baseline → **F4 zamrzavanje (T0)** → F5 dump → F6 sanitizacija → F7 restore i validacija → F8 dark launch i validacija → F9 odluka → **F10 otvaranje (T_open)** → F11 provjere → F12 praćenje.

## 4. Datoteke i skripte

| Datoteka | Namjena | Mutira? |
| --- | --- | --- |
| `cutstate.py` | žurnal stanja cutovera (hash lanac, `get/set/verify/can-rollback/can-abort`); oštećenje = HALT | piše samo u `$EV` |
| `write_probe.py` | sonda aktivnosti pisanja baze (statistika tablica, sekvence, restart); `capture`/`check`, UNKNOWN = nedokazano | ne (samo čitanje) |
| `docker-compose.frozen.yml` | override za baseline iz zamrznutog stanja (API-only, bez rute, baza izvora) | ne mijenja produkcijske datoteke |
| `local_backup.sh`, `tests/local_backup_selftest.sh` | druga kopija na `/home` + SHA-256 (`lb_check`, `lb_copy_app_backup`, `lb_copy_cutover_dumps`, `lb_verify`, **`lb_gate_open`** = G14; `steps.sh` ga poziva u `s_open` i `s_manual_forward`, `s_backup_gate` ga pokreće izolirano); ne prepisuje, ne briše, ne dira bazu; produkcijski način traži `CUTOVER_APPROVED` | `lb_copy_*` pišu samo u `/home/immich-cutover-backups/<ID>` i `$EV/local-backup` |
| `steps.sh` | **jedini izvor istine za mutirajuće korake** (funkcije `s_prepare_target`, `s_freeze`, `s_dump_source`, `s_bridge_sanitize`, `s_bridge_cleanup`, `s_restore_target`, `s_validate_target`, `s_restore_and_validate`, `s_dark_launch`, `s_open`, `s_open_abort`, `s_manual_forward`, `s_manual_rollback_accept_loss`, `s_rollback_r1`, `s_unfence`, `s_target_reset_after_rollback`); podljuska s `set -Eeuo pipefail`; produkcijski način traži `CUTOVER_APPROVED=$CUTOVER_ID` | da, samo uz odobrenje |
| `preflight.py` | read-only provjera (kontejneri, image ID-evi, izvorna baza, backup, mreže, Traefik TR1/TR2, API ključevi, prozor); piše `preflight-*.json` i `baseline-*.json` | ne |
| `db_snapshot.py` | `snapshot`, `compare` (načini `source-bridge`, `source-bridge-after`, `source-target`), `delta` | ne |
| `validate_target.py` | provjera ciljne baze: verzije, ekstenzije, ACL, rola, prijava (mrežna adresa + negativna kontrola), prava, indeksi, sekvenca, brojevi redaka prema zamrznutom izvoru, vektori (recall, latencija toplih upita), opcionalno amcheck | ne (amcheck: poništena transakcija na cilju) |
| `api_checks.py` | `baseline`/`verify`, `queues status/pause/resume/wait-drain`, `job backup-database` | `pause`, `resume`, `job` samo uz `--execute` |
| `getsecret.py` | vrijednost iz okoline kontejnera (npr. `DB_PASSWORD`) bez parsiranja `.env` | ne |
| `docker-compose.dark.yml` | override za dark launch (`DB_HOSTNAME`, `traefik.enable=false`, `IMMICH_WORKERS_INCLUDE=api`) | ne mijenja produkcijske datoteke |
| `guarded_docker.py`, `rehearsal/` | zaštitni omotač i izolirani rehearsal stack (samo `immich-apptest-*`); produkcijska imena, putanje i `docker.sock` odbijeni | samo test kontejneri |
| `tests/offline_selftest.sh` | offline test usporedbe, `delta`, blokada `--execute`, zaštite rehearsal načina | ne |

Pozivi API-ja idu kroz `docker exec <server> node` na `127.0.0.1:2283`, pa rade i u dark fazi i ne trebaju host port. Ključevi se čitaju iz okoline operatera i ne zapisuju. Rehearsal način (`CUTOVER_REHEARSAL=1` s imenima `immich-apptest-*`) odbija sve naredbe koje imenuju produkcijski kontejner, produkcijsku putanju ili Docker socket i zapisuje svaku naredbu u audit log.

## 5. Runbook

Svi koraci traže prethodno odobrenje (odjeljak 10). **STOP** znači: ne nastavljati, zabilježiti stanje, odlučiti o rollbacku. Svaki mutirajući korak je funkcija iz `steps.sh`; nenulti exit kod **bilo koje** naredbe u njemu zaustavlja korak i vraća nenulti status. Vremena su prijedlog.

### Priprema ljuske
~~~bash
export CUTOVER_ID="$(date -u +%Y%m%dt%H%M%Sz)"            # jednom po cutoveru
export CV=/opt/stacks/data/immich-cutover EVROOT=/opt/stacks/data/backups
export EV="$EVROOT/immich-cutover-$CUTOVER_ID" BR="immich-cutover-bridge-$CUTOVER_ID" WB="/tmp/immich-cutover-$CUTOVER_ID"
umask 077; mkdir -p -m 700 "$EV"; cd "$CV"; source ./steps.sh
# tek nakon pisanog odobrenja operacija: export CUTOVER_APPROVED="$CUTOVER_ID"
~~~

### F0 — pripreme (T-7 d … T-1 d, bez prekida)
1. Odobrenja iz odjeljka 10. Termin (04:30–22:00, radni dan), osobe za odluku o rollbacku i OIDC provjeru.
2. Dva **privremena API ključa** u Immich UI-ju (redak u `api_key`, ulazi u dump):
   - admin (najmanje potrebno, provjereno prema kontrolerima u imageu i pozivima `api_checks.py`, vidi [19](19-immich-production-readiness.md)): `queue.read queue.update job.create server.about server.statistics library.read library.statistics`
   - korisnik s podacima: `asset.read album.read person.read`
   ~~~bash
   read -rs IMMICH_ADMIN_API_KEY; export IMMICH_ADMIN_API_KEY
   read -rs IMMICH_USER_API_KEY;  export IMMICH_USER_API_KEY
   ~~~
3. Obavijest korisnicima; utišati monitoring (Uptime Kuma); bez nadogradnji Immicha, Nextclouda i PostGIS-a.
4. **Lokalna druga kopija** najnovijeg Immich backupa na `/home` (zamjena za off-host; doc 21), tek uz odobrenje O16:
   (F0 se smije izvršiti s **zasebnom oznakom** `export LB_BACKUP_ONLY_APPROVED=F0:$CUTOVER_ID`, koja vrijedi samo za `lb_copy_app_backup`; `CUTOVER_APPROVED` nije potreban i ne smije se postavljati za F0, doc 28.)
   ~~~bash
   source ./local_backup.sh
   lb_check                      # RAID1 [UU] na md0-md3, mismatch_cnt 0, nvme live, temperatura, prostor na / i /home (samo čitanje)
   lb_copy_app_backup            # kopija u /home/immich-cutover-backups/$CUTOVER_ID/app-backup + SHA-256 oba (original: $EV/local-backup/app-backup.sha256)
   lb_verify                     # mora završiti "lb_verify OK"
   ~~~
   Postojeći backupovi i baza `postgis/immich` se samo čitaju; ništa se ne briše, ne premješta ni prepisuje.

### F1 — preflight (T-60 min)
~~~bash
python3 -I preflight.py --phase before-target; echo "exit=$?"       # mora biti 0 (0 FAIL); piše baseline-*.json u $EV
~~~
**STOP** pri bilo kojem FAIL-u (WARN pročitati i zabilježiti).

### F2 — priprema `immich-db` (T-45 min, bez prekida za korisnike)
~~~bash
s_prepare_target
~~~
Korak: `docker compose -f docker-compose.postgres-new.yml up -d --no-build --pull never immich-db`, čeka zdravlje, provjerava 16.16 i da PostGIS nije dostupan, kreira rolu `immich` (LOGIN, bez ovlasti) i bazu `immich` (owner immich, `template0`, UTF8, `en_US.utf8`) s lozinkom iz **okoline aplikacijskog kontejnera** (`getsecret.py`), zatim dokazuje scram prijavu preko mrežne adrese i odbijanje pogrešne lozinke. **STOP** pri bilo kojem neuspjehu. Za sigurnu vrijednost nitko ne ispisuje lozinku.

**Ponovljeni pokušaj s postojećom rolom/bazom:** nakon očuvanog target reseta iz [43](43-immich-second-attempt-target-reset.md) gornji `s_prepare_target` nije prikladan. Za ID `20261115t150714z` pripremljen je zasebni `s_prepare_existing_target` i zaključani driver `immich-cutover/run_f2_existing.sh`, opisani u [44](44-immich-second-attempt-f2-preparation.md). Nema CREATE ROLE/DATABASE ni Compose up; živi dokazi postojećeg cilja/arhive i F0 moraju proći prije PREPARED. **Priprema i rehearsal nisu odobrenje produkcijskog F2**; driver se smije izvršiti tek uz zasebnu pisanu uputu za F2 i PREPARED. Bez odobrenja ne pokretati nijedan F2 put.

### F3 — proba alata prije zamrzavanja (T-15 min)
~~~bash
python3 -I preflight.py --phase target-ready                         # 0 FAIL
python3 -I api_checks.py baseline --out "$EV/api-baseline-pre.json"   # proba ključeva i alata; NIJE baseline za usporedbu
python3 -I api_checks.py queues status
~~~

### F4 — ZAMRZAVANJE (T0)
~~~bash
s_freeze
~~~
Redoslijed (faza 7B, probano u rehearsalu): (1) bilježi se ACL izvora (`source-db-acl.before`); (2) **prvo se zaustavljaju skriptirani pisci** `nextcloud_immich_bridge` i `immich_media_operations`; (3) pauziraju se svi redovi koje Immich dopušta (`backgroundTask` je poznata iznimka) i čeka se `active == 0` (STOP-1 pri isteku `DRAIN_TIMEOUT`, zadano 600 s); (4) zaustavlja se `immich_server` (korisnici odsječeni); (5) provjera 0 veza (STOP-2); (6) **baseline** (`$EV/api-baseline.json`) uzima se iz privremenog **API-only servera bez rute** na *izvornoj* bazi (`docker-compose.frozen.yml`: bez workera, `traefik.enable=false`), dakle nakon što su svi pisci zamrznuti i nitko ne može pisati; instanca se zaustavlja, ponovno 0 veza; (7) zaštita izvora (`REVOKE CONNECT … FROM PUBLIC, immich`); (8) **sonda pisanja A** (`write-probe-frozen-A.json`). Vremenske oznake su u `freeze-order.log`. Snapshot izvora (F5) uzima se tek poslije i **sonda B** mora biti identična sondi A (`freeze-gap-proof.json`): dokaz da između zamrzavanja i snapshota nije bilo nijednog zapisa. STOP-1 više ne ostavlja sve netaknuto: bridge i `media-operations` ostaju zaustavljeni, pa je oporavak `s_rollback_r1` iz stanja `FREEZING`. Redis se ne dira.

### F5 — snapshot i dump izvora (≈1,5 min)
~~~bash
s_dump_source
~~~
Korak: `db_snapshot.py snapshot` izvora, `pg_dump -Fc` u `.partial`, prazan log, veličina 200–500 MB (STOP-3), čitljiv TOC (`pg_restore --list` > 1000 stavki), tek tada preimenovanje u `immich.full.dump`, SHA-256 i CSV sidecar `spatial_ref_sys`.

### F6 — sanitizacija bez PostGIS-a na privremenom bridgeu (≈2 min)
~~~bash
s_bridge_sanitize && s_bridge_cleanup
~~~
Korak: kontejner iz postojećeg `postgis` imagea (`--network none`, vlastiti PGDATA, `$EV` samo za čitanje), restore s `--exit-on-error` (prazan log, STOP-4), normalizacija identity sekvence (`AS bigint`, bez RESTART-a), **usporedba izvor ↔ bridge prije `DROP EXTENSION`** (72 hasha, owneri, ACL-ovi, sekvence, indeksi, ekstenzije; `compare-source-bridge.json`), `DROP EXTENSION postgis RESTRICT` (nikad CASCADE), usporedba poslije (`compare-source-bridge-after.json`), sanitizirani dump, TOC bez `postgis`/`spatial_ref_sys`. `s_bridge_cleanup` uklanja bridge tek nakon provjere labela i `realpath`.

### F6b — druga kopija dumpova na `/home` (odmah nakon F6, prije F7)
~~~bash
lb_copy_cutover_dumps && lb_verify        # immich.full.dump + immich.no-postgis.dump -> /home/immich-cutover-backups/$CUTOVER_ID/dumps, SHA-256 + usporedba TOC-a kopije
~~~
**STOP-8** pri bilo kojem neuspjehu kopiranja: ne ići dalje dok se ne ispravi. Od faze 7D to nije samo preporuka: `s_open` i `s_manual_forward` **tvrdo odbijaju rad** (exit 6) dok `lb_gate_open` nije PASS. Isti prolaz može se pokrenuti bez posljedica u F9 kao `s_backup_gate`.

### F7 — restore u `immich-db` i validacija (≈4 min)
~~~bash
s_restore_and_validate
~~~
Korak `s_restore_target`: dump mora biti čitljiv u ciljnom kontejneru na `/backups/immich-cutover-$CUTOVER_ID/` (`$EV` mora biti izravno pod `$EVROOT` koji je mountan na `/backups`), SHA-256 unutar kontejnera jednak izvornom, `pg_restore --exit-on-error --jobs=2` s praznim logom, DB ACL i normalizacija sekvence. Korak `s_validate_target`: snapshot cilja, `compare --mode source-target`, `validate_target.py --amcheck --source-snapshot "$EV/src"` (brojevi redaka i sekvenca prema zamrznutom izvoru), `ANALYZE`. **STOP-5** pri svakom FAIL-u. Jedina dopuštena razlika metapodataka je tekst `pg_get_indexdef` za `asset_localDateTime_month_idx` ([12](12-immich-index-validation.md)).

### F8 — dark launch i validacija (≈5 min)
~~~bash
s_dark_launch
~~~
Korak: `idcd up -d --no-deps --no-build --pull never --force-recreate immich-server` s override-om (samo API worker), čeka healthy, provjerava da je `traefik.enable=false` i `DB_HOSTNAME=immich-db`, log: "Starting api worker", "No schema drift detected", "Finished running migrations", `targetLists=1`, **bez** "Starting microservices worker", migracija, reindeksiranja, promjene ekstenzije, ERROR/FATAL; `api_checks.py verify --allow-paused` prema `$EV/api-baseline.json`; `delta` (samo `system_metadata`, `session`, `plugin*`, `version_history`); izvor i dalje bez veza. **STOP-6** pri bilo čemu. Na kraju se bilježi sonda pisanja nove baze (`write-probe-dark.json`) i stanje `DARK_VERIFIED`; nakon `s_open_abort` dark launch prvo ponovno pauzira redove (aplikacija je pri startu workera sama nastavila `metadataExtraction`), pa tek onda verificira.

Provjera rute bez izmjene usmjeravanja: (1) label (`docker inspect`, već u koraku), (2) preflight TR1: nema statičke Immich rute u `/opt/stacks/traefik/dynamic`, (3) neobvezno, samo čitanje: `curl -sk --resolve media.finestar.hr:443:127.0.0.1 -o /dev/null -w '%{http_code}\n' https://media.finestar.hr/api/server/ping` mora dati 404 (nema rute) u dark fazi i 200 nakon otvaranja. Ništa od toga ne mijenja Traefik.

### F9 — odluka GO/NO-GO (T0 + ≤ 25 min)
Kriteriji iz odjeljka 9; odluku donosi imenovana osoba. NO-GO → `s_rollback_r1` (dopušten samo u stanjima `FREEZING … DARK_VERIFIED` i `ABORT_VERIFIED`).

### F10 — OTVARANJE PROMETA (PONR se određuje stanjima)
~~~bash
s_open
~~~
Korak traži stanje `DARK_VERIFIED`, zatim **prije svake promjene** prolazi **G14 backup gate** (`lb_gate_open`: identitet cutovera, RAID1 `[UU]` bez resynca, oba dumpa i app backup u originalu i kopiji, 4 manifesta i oblik njihovih redaka, SHA-256 originala/manifesta/kopija/hasha koji je zabilježio korak, `COPIES_DONE`); pri bilo kojem FAIL: **HALT, exit 6**, `BACKUP-GATE-HALT.txt`, ništa se ne mijenja (stanje ostaje `DARK_VERIFIED`, nema `OPEN_BEGIN`). Zatim traži `write-probe-dark.json`. Slijed (svako stanje se upisuje u žurnal **prije** sljedeće radnje): privatna kopija `.env` i njezin SHA-256 → `OPEN_BEGIN` → očekivani novi sadržaj (`immich.env.after`, jedina razlika je `DB_HOSTNAME`) i njegov SHA-256 se zapisuju **prije** izmjene → upis u `.env` → `ENV_CHANGED` → `RECREATING` → `up -d --force-recreate --no-deps --no-build --pull never immich-server` bez dark override-a → `RECREATED` → healthy, label `true`, host nove baze → `ROUTE_LIVE` (+ datoteka `T_open`) → `media-operations`, bridge → `AUX_STARTED` → `RESUMING` → `queues resume --execute` → `OPEN_CONFIRMED`. Pri svakom neuspjehu skripta ispisuje: **ne improvizirati, pokrenuti `s_open_abort`**, nikad `s_rollback_r1`.

#### `s_open_abort` — oporavak djelomično otvorenog stanja (samo uz dokaz)
~~~bash
s_open_abort     # exit 0 = dokazano bez pisanja, oporavljeno; exit 4 = HALT; exit 3 = nakon PONR-a; exit 5 = nema što prekidati
~~~
Dopušteno u stanjima `OPEN_BEGIN … AUX_STARTED`. Prvo se zaustavljaju svi mogući pisci (bridge, `media-operations`, server; zaustavljanje može samo smanjiti pisanje), zatim se skupljaju dokazi i **svi** moraju biti PASS (`$EV/abort-evidence.log`):

| ID | Dokaz |
| --- | --- |
| E1 | bridge, `media-operations` i server nisu pokrenuti |
| E2 | žurnal (hash lanac) je valjan |
| E3 | nijedna veza uloge `immich` na novu bazu |
| E4 | sonda pisanja: od `write-probe-dark.json` nepromijenjeni `postmaster_start`, `stats_reset`, brojači `n_tup_ins/upd/del` svih tablica izvan `system_metadata, version_history, plugin, plugin_method` te vrijednosti **svih sekvenci** (i poništen INSERT ili `nextval` se vide) |
| E5 | 72 hasha tablica i metapodaci jednaki snapshotu nakon dark launcha (`dst2`) |
| E6 | nijedna datoteka u `upload` direktoriju nema `ctime` poslije T0 (`mtime` je beskoristan: Immich zadržava vrijeme datoteke klijenta) |
| E7 | `.env` je točno zabilježeni sadržaj prije ili poslije (SHA-256) |

Ako je sve PASS: `.env` se vraća bajt-u-bajt iz `immich.env.before`, server ostaje zaustavljen, stanje `ABORT_VERIFIED`; zatim `s_rollback_r1` (natrag na izvor) ili `s_dark_launch` (ponovni pokušaj). Ako je **bilo što** FAIL ili UNKNOWN: stanje `HALT_MANUAL`, `$EV/HALT-REPORT.txt`, server ostaje zaustavljen, ništa se ne briše, a automatski rollback je zabranjen. Posebno: nakon što je server s workerima bio zdrav, zadržani poslovi (`metadataExtraction`) obično se već obrađuju na novoj bazi, pa abort iz `ROUTE_LIVE`/`AUX_STARTED` s pozadinom reda tipično završi u HALT-u (to je ispravno ponašanje).

#### Ručna odluka nakon `HALT_MANUAL`
Dvije funkcije, obje traže stanje `HALT_MANUAL` i token za točno ovaj cutover:
- **GO** (zadržati novu bazu): `export CUTOVER_MANUAL_DECISION=FORWARD:$CUTOVER_ID; s_manual_forward` → dovršava otvaranje na novoj bazi → `OPEN_CONFIRMED`.
- **NO-GO** (natrag na izvor, uz prihvaćanje gubitka svega zapisanog u novu bazu): `export CUTOVER_MANUAL_DECISION=ROLLBACK_ACCEPT_LOSS:$CUTOVER_ID; s_manual_rollback_accept_loss` → vraća `.env`, ACL izvora, server na izvoru → `ROLLED_BACK_LOSS_ACCEPTED`. Nova baza **nije obrisana**.
Prije odluke procijeniti što je zapisano (novi redovi u `asset`, `session`, `album`; datoteke s `ctime` > T0 u `upload`).

### F11 — provjere nakon otvaranja (stanje `OPEN_CONFIRMED`; `T_open` + 0…60 min)
~~~bash
python3 -I api_checks.py queues status                                          # idle, failed=0
python3 -I api_checks.py verify --baseline "$EV/api-baseline.json" --out "$EV/api-after.json"
python3 -I api_checks.py job backup-database --execute                            # ručni backup na PG 16.16
docker logs --since "$(cat "$EV/T_open")" immich_server 2>&1 | grep -E '\bERROR\b|\bFATAL\b' | sed -E 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+/<email>/g' | head
~~~
Backup: nova datoteka `…-v3.3.5-pg16.16.sql.gz`, `gzip -t`, veličina u ±10 % prethodnog, `zcat | grep -E '^(CREATE|DROP|COMMENT|ALTER|GRANT|REVOKE).*(postgis|spatial_ref_sys)'` mora dati 0 (sirovo `grep postgis` može pogoditi OCR tekst u podacima), 7 naredbi `CREATE EXTENSION` (plpgsql je ugrađen).

### F12 — praćenje
`T_open`+1 h, 02:00 sljedećeg dana (backup), T+24 h i T+7 dana (odjeljci 8 i 9). Bridge se već uklanja u F6 (`s_bridge_cleanup`).

### STOP uvjeti (svi su simulirani u rehearsalu)
| STOP | Uvjet | Ponašanje |
| --- | --- | --- |
| 1 | redovi se ne isprazne u roku, ili zaustavljanje pisca/baseline ne uspije | `s_freeze` izlazi nenulto; bridge i `media-operations` već su zaustavljeni, server radi, izvor nije zaštićen; oporavak `s_rollback_r1` (stanje `FREEZING`) |
| 2 | veze na izvornu bazu ≠ 0 nakon zaustavljanja | `s_freeze` staje prije zaštite |
| 3 | dump izvan veličine/log nije prazan | nema konačne datoteke dumpa |
| 4 | bridge restore greška, usporedba bridgea, `DROP EXTENSION` odbijen, PostGIS u TOC-u | nema sanitiziranog dumpa |
| 5 | restore ili usporedba izvor/cilj, `validate_target` FAIL | dark launch se ne pokreće |
| 6 | dark start nije healthy, zabranjeni redci u logu, verify FAIL, worker poslova pokrenut | rollback R1 |
| 8 | backup gate G14 pada (kopija nedostaje, hash različit, manifest neispravan, RAID1 degradiran ili se sinkronizira, pogrešan `CUTOVER_ID`) | `s_open` / `s_manual_forward`: exit 6, HALT bez ikakve promjene; ispraviti uzrok pa ponoviti |
| 7 | `s_open` zakaže u bilo kojem stanju | `s_open_abort` (dokaz ili HALT); nikad izravno R1 |
| HALT | žurnal oštećen, dokaz nedostaje/ne uspije, pisanje u novu bazu, `.env` neočekivan, `ENV` upućuje na novu bazu dok žurnal kaže drugo | nikakva automatska radnja; `HALT-REPORT.txt`; ručni GO/NO-GO s tokenom |

## 6. Točka bez povratka i rollback

**Točka bez povratka** određuje žurnal stanja (odjeljak 3), ne jedna datoteka: do `DARK_VERIFIED` izvor je netaknut i R1 je dopušten; `OPEN_BEGIN … AUX_STARTED` je "djelomično otvoreno" (samo `s_open_abort` uz dokaz, inače HALT); `RESUMING` i `OPEN_CONFIRMED` su nakon točke bez povratka.

**R1 — F4–F9 i `ABORT_VERIFIED`, ≈10 min, bez gubitka podataka** (probano u rehearsalu, i iz `FREEZING`, `RESTORED` i `DARK_VERIFIED`):
~~~bash
s_rollback_r1
~~~
Korak provjerava stanje (`cutstate.py can-rollback`: exit 3 u zabranjenom stanju, exit 4 pri oštećenom žurnalu) i **žive unakrsne provjere neovisne o žurnalu**: `.env` mora upućivati na izvor, `T_open` ne smije postojati, aplikacija ne smije raditi s rutom na novoj bazi; inače HALT (exit 4). Zatim zaustavlja dark instancu, vraća ACL izvora (`GRANT CONNECT … TO PUBLIC, immich`; identičan zapisanom `source-db-acl.before`), recreate servera iz **bazne** compose datoteke (`DB_HOSTNAME=postgis`, ruta vraćena), pokreće `media-operations` i bridge, `queues resume --execute`, `api_checks.py verify` prema `$EV/api-baseline.json` (preskače se uz WARN samo ako baseline još ne postoji, tj. STOP-1 prije baselinea). Zbog dark faze bez workera nijedan zadržani posao nije izvršen na novoj bazi. Prije novog pokušaja **novi `CUTOVER_ID`/`EV`** i `PREV_EV=<prethodni EV> s_target_reset_after_rollback` (dopušteno samo ako je prethodni EV `ROLLED_BACK` ili `ROLLED_BACK_LOSS_ACCEPTED`; neuspjela baza se **preimenuje**, ne briše).

**R2 — nakon `RESUMING`/`OPEN_CONFIRMED` (nema automatskog rollbacka; svaka odluka je ručna i traži odobrenje).**
1. Odmah procijeniti gubitak: broj novih zapisa u `immich-db` (`SELECT count(*) FROM asset WHERE "createdAt" > '<T_open>'`, `session`, `album`) i nove datoteke u `/data/upload` (`find … -newerct '<T0>'`; ne `-newermt`: Immich zadržava vrijeme datoteke klijenta).
2. **Opcija A — povratak na staru bazu uz prihvaćanje gubitka** novih zapisa od `T_open`: zaustaviti servise, vratiti `DB_HOSTNAME=postgis` iz `$EV/immich.env.before`, ukloniti zaštitu izvora, recreate. Nove datoteke ostaju na disku i popisuju se, ne brišu; mobilne aplikacije ponovno učitavaju.
3. **Opcija B — povratna migracija:** zamrznuti, `pg_dump` iz `immich-db`, restore u novu bazu na `postgis`, preimenovati staru u `immich_pre_cutover`, vratiti `.env`; zahtijeva zasebno odobrenje i nije probana.
4. **Opcija C — ispravak unaprijed** na `immich-db`.

Skriptirani povratak postoji samo prije točke bez povratka (R1) i kao ručna odluka nakon HALT-a (`s_manual_rollback_accept_loss`, uz token). Nakon `OPEN_CONFIRMED` sve skripte odbijaju povratak (exit 3 ili 5).

## 7. Čuvanje izvorne baze najmanje 7 dana

- Baza `immich` ostaje u kontejneru `postgis` neizmijenjena i zaštićena (`REVOKE CONNECT`), uključujući proces `postgres` kontejnera. Superuser ju i dalje može čitati (npr. za usporedbu) uz pravilo da se u nju ne piše.
- Provedivo: baza zauzima 1,16 GiB, na disku ima 439 GiB; nema automatskog brisanja (Immich ne dira tuđe baze); `postgis` se ne smije zamijeniti ni nadograditi dok traje retencija (val J iz [04](04-migration-runbook.md) ostaje na čekanju).
- Čuvaju se i `immich.full.dump`, `immich.no-postgis.dump`, `spatial_ref_sys.source.csv`, hashevi, `immich.env.before` i **druga kopija na `/home`** (SHA-256 provjeren `lb_verify`; ponavlja se T+24 h, tjedno i prije bilo koje odluke o brisanju). Off-host kopije nema (prihvaćen rizik, doc 21).
- Tjedna provjera: `db_snapshot.py snapshot --container postgis` na bazi `immich` i `compare` prema `$EV/src` mora biti PASS (rehearsal P7: izvor ostaje identičan i nakon otvaranja); ACL (`REVOKE` još važi); `docker inspect postgis` (isti Id i StartedAt).
- **Važno:** nakon `OPEN_CONFIRMED` izvorna baza **nije** praktičan rollback (zastarjela je koliko je prošlo vremena). Služi za forenziku i usporedbu, a stvarna zaštita su 02:00 backupovi nove baze.
- Dan 7: formalna odluka (zasebno odobrenje) o brisanju ili daljnjem čuvanju; brisanje nije dio ovog plana.

## 8. Provjere nakon cutovera

| Provjera | Postupak | Kriterij |
| --- | --- | --- |
| Backup (ručni) | `api_checks.py job backup-database --execute`; nova datoteka `…-pg16.16.sql.gz` u `/opt/stacks/immich/docker-data/library/backups`; `gzip -t`; DDL provjera iz F11 | probano u rehearsalu na PG 16.16: ime `pg16.16`, 355,9 MB (prethodni 355,2 MB), `gzip -t` OK, 7 `CREATE EXTENSION`, 0 PostGIS DDL; u produkciji ±10 % prethodnog |
| Backup u 02:00 | sljedeće jutro: log "Database Backup Success", nova datoteka, rotacija po `keepLastAmount` | uspjeh |
| OIDC | vlasnik se prijavljuje preko Nextclouda (web i mobilna aplikacija); prijava lozinkom kao rezerva | uspješna prijava istog računa, bez duplikata korisnika |
| `media-operations` | `docker logs immich_media_operations` bez grešaka veze na bazu; jedna read-only akcija utility sučelja | bez `Postgres lookup failed` |
| Bridge | jedan ciklus (300 s) bez greške u logu | bez greške |
| Skeniranje knjižnica | primarno: noćno skeniranje u 00:00 (logovi i redovi nakon njega); opcionalno ručno na najmanjoj knjižnici (zahtijeva `library.update` na privremenom ključu) | skeniranje završi, 0 neuspjelih poslova, brojevi asseta bez neočekivane promjene |
| Storage template | provjera da je ostao isključen (`system-config` nema `storageTemplate.enabled=true`) i da nema `StorageTemplateMigration` aktivnosti u logu | ostaje isključen |
| Video transkodiranje | kanarski korisnik (kreira admin u UI-ju) uploada sintetički HEVC klip (npr. `docker exec immich_server ffmpeg -f lavfi -i testsrc=duration=3:size=320x240:rate=15 -c:v libx265 -pix_fmt yuv420p /tmp/canary.mp4`) i jednu sliku; u `/data/encoded-video/<korisnik>` mora nastati H.264 inačica | `encoded-video` datoteka nastala, 0 neuspjelih poslova |
| Trash/restore | kanarski asset: premjestiti u trash, vratiti, ponovno u trash, trajno obrisati | stanja u UI-ju i API-ju odgovaraju; kanarski asset nije u managed knjižnici pa `media-operations` ne radi ništa na Nextcloudu |
| Čišćenje kanara | obrisati kanarske assete i kanarskog korisnika (uz odobrenje) | broj korisnika i asseta vraćen na početni |
| Redovi | `queues status` | svi `active/waiting/delayed` 0 nakon obrade, `failed` 0 |
| Logovi 24 h | `docker logs` filtriran na ERROR | 0 neočekivanih |
| Integrity (03:00) | sljedeće jutro: broj redaka `integrity_report` usporediti s baselineom (8033) | bez neočekivanog skoka |

Kanarski testovi (video, trash/restore) pišu u produkcijsku bazu i medije kao zaseban privremeni korisnik pa traže izričito odobrenje (O12).

## 9. Kriteriji GO/NO-GO (PRIJEDLOZI — nisu odobreni)

| ID | Kriterij | Prijedlog praga | Status |
| --- | --- | --- | --- |
| K1 | Preflight | 0 FAIL, uključujući disk ≥ 96 GiB, backup mlađi od 26 h, **`lb_check` OK** (RAID1 `[UU]`, `mismatch_cnt` 0, nijedan resync) | OTVOREN |
| K2 | Termin | izvan 23:40–04:15 (cron sudari), radni dan | OTVOREN |
| K3 | Pražnjenje redova | `active == 0` u ≤ 10 min | OTVOREN |
| K4 | Dump izvora | exit 0, prazan log, veličina 200–500 MB, SHA-256 zapisan | OTVOREN |
| K5 | Sanitizacija | restore i drugi dump bez greške, TOC bez PostGIS-a | OTVOREN |
| K6 | Integritet cilja | `compare` PASS: 72/72 hasha, metapodaci jednaki, sekvenca `bigint`, ekstenzije točno 8 | OTVOREN |
| K7 | Validacija cilja | `validate_target` 0 FAIL; recall@10 prosjek ≥ 0,95 i minimum ≥ 0,90 na 20 uzoraka po indeksu (u rehearsalu: clip 1,00/1,00, face 0,995/0,90, pa je minimum 0,90 na granici i treba ga odobriti svjesno); ANN topli upiti (bez prvog) najviše 250 ms; amcheck 0 grešaka | OTVOREN |
| K8 | Dark start | healthy ≤ 180 s; 0 migracija; "No schema drift detected"; 0 reindeksiranja; 0 ERROR; promjene samo `system_metadata`, `session`, `plugin*`, `version_history` | OTVOREN |
| K9 | API usporedba | statistike (fotografije, videi, korištenje, po korisniku), knjižnice, albumi i osobe identični baselineu iz **zamrznutog stanja** (`api-baseline.json`, uzet iz API-only instance bez rute nakon što su svi pisci zaustavljeni); razlika nije dopuštena: svaka razlika = NO-GO. Dokaz bez vremenskog razmaka: `freeze-gap-proof.json` = PASS (sonda B identična sondi A) i broj fotografija iz baselinea jednak broju iz baze izvora | OTVOREN |
| K10 | Smart search | preklapanje top-20 ≥ 0,90 za svih 10 upita; p95 topli ≤ max(250 ms, 2 × baseline); prvi (hladni, ML model se ponovno učitava) upit ≤ 5 s | OTVOREN |
| K11 | Trajanje prekida | planirano T0 → `OPEN_CONFIRMED` ≤ 30 min; maksimum 45 min; pri 60 min obavezan rollback R1 | OTVOREN |
| K12 | RPO / RTO | RPO = 0 prije `ROUTE_LIVE`; RTO rollbacka R1 ≤ 15 min; nakon `OPEN_CONFIRMED` RPO ≤ 24 h (02:00 backup) uz ručni backup odmah nakon otvaranja | OTVOREN |
| K13 | Nakon otvaranja (60 min) | redovi mirni, `failed` ne više od baselinea (poznato: `facialRecognition` = 1, doc 24/26), 0 neočekivanih ERROR, ručni backup uspješan, OIDC prijava uspješna, `media-operations` i bridge bez grešaka | OTVOREN |
| K14 | 24 h i 7 d | 02:00 backup uspješan, noćno skeniranje i integrity bez neočekivanih promjena, veze i disk stabilni, 0 restarta | OTVOREN |
| K18 | Lokalne kopije | **tvrdo vrata u `s_open`**: `lb_gate_open` PASS (inače HALT, exit 6); `lb_verify OK` nakon F0 i nakon F6b (SHA-256 original == kopija na `/home`, TOC kopije jednak), `lb_check` OK neposredno prije F10 i nakon njega; nijedna DEGRADED/resync pojava na RAID1 tijekom prozora | OTVOREN |
| K15 | Žurnal stanja | lanac valjan i točno očekivani slijed stanja do `DARK_VERIFIED` prije `s_open`; `write-probe-dark.json` postoji; nijedno stanje preskočeno | OTVOREN |
| K16 | Zamrzavanje bez razmaka | redoslijed u `freeze-order.log` = bridge/`media-operations` → redovi → server → baseline → fence; `freeze-gap-proof.json` PASS (strogo, bez allow-liste) | OTVOREN |
| K17 | Abort/HALT | `s_open_abort` smije se prihvatiti samo uz E1–E7 PASS; svaki HALT_MANUAL traži zasebnu pisanu odluku imenovane osobe (GO ili NO-GO s gubitkom) | OTVOREN |

Mjerenja iz testova za usporedbu (faza 4C, 5C, 5D; izolirani host u mirovanju): restore 18 s, dump 41 s, hash 72 tablice 21 s, recall@10 1,00, ANN do 8 ms, smart search 36–40 ms (toplo). Produkcijski baseline latencije izmjerit će `api_checks.py baseline` u F3.

## 10. Operacije koje zahtijevaju vaše odobrenje

| ID | Operacija | Utjecaj / reverzibilnost |
| --- | --- | --- |
| O1 | termin prozora, pragovi iz odjeljka 9, osobe za odluku i OIDC provjeru | |
| O2 | kreiranje dva privremena API ključa (redak u `api_key`; revokacija nakon retencije) | mala promjena produkcijske baze, reverzibilno |
| O3 | pokretanje trajnog servisa `immich-db`, stvaranje role i baze (F2) | novi servis i data direktorij; ništa u produkciji se ne mijenja |
| O4 | pauziranje redova i zaustavljanje `nextcloud_immich_bridge`, `immich_media_operations`, `immich_server` (F4) | **prekid usluge** |
| O5 | zaštita izvorne baze `REVOKE CONNECT` i prekid sesija (F4) | reverzibilno `GRANT` |
| O6 | novi dump izvora, privremeni bridge kontejner, sanitizirani dump (F5, F6) | privatni direktorij `$EV`, `/tmp` |
| O7 | restore u `immich-db`, normalizacija sekvence, `ANALYZE` (F7) | samo nova baza |
| O8 | dark launch servera s override-om (F8) | dodatni recreate servera |
| O9 | izmjena `/opt/stacks/immich/.env` (`DB_HOSTNAME`) i recreate `immich-server` i `media-operations` bez builda (F10) | **djelomično otvoreno stanje do `AUX_STARTED`; točka bez povratka od `RESUMING`** |
| O10 | nastavak redova, start bridgea, ručni backup (F10, F11) | normalan rad |
| O11 | ~~off-host kopija~~ **ukinuto odlukom vlasnika**; zamjena: izričito prihvaćen rizik lokalne RAID1 zaštite (G6 ostaje neispunjen) | prihvaćanje rizika, doc 21 |
| O16 | druga kopija na `/home` (`lb_copy_app_backup`, `lb_copy_cutover_dumps`; ~1,1 GiB; novi direktorij, ništa se ne prepisuje) i neobvezni `chattr +i` | dodaje datoteke na `/home`; reverzibilno (`chattr -i`, brisanje samo uz odobrenje) |
| O12 | kanarski testovi: privremeni korisnik, video, trash/restore, ručno skeniranje (odjeljak 8) | piše u produkciju, čisti se |
| O13 | čuvanje izvorne baze 7 dana i zabrana zamjene `postgis` u tom razdoblju (odjeljak 7) | |
| O14 | opcija R2 B/A kao postupak odluke i tko je odlučuje; **tko smije izdati token za `s_manual_forward` / `s_manual_rollback_accept_loss` nakon HALT-a** | |
| O15 | privremeni zaobilazni baseline: kratki start `immich-server` (API-only, bez rute) na izvornoj bazi unutar `s_freeze` (`docker-compose.frozen.yml`) | dodatni recreate servera, reverzibilno |

## 11. Što je izvršeno

- **Faza 6:** čitanje (dokumentacija, kod Immicha, `docker inspect`, read-only SQL nad `postgis/immich`), parsiranje Composea, izrada skripti i dokumenta.
- **Faza 6B (rehearsal):** skripte i `steps.sh` izvedene su isključivo na izoliranom stacku (`immich-apptest-*`, interna mreža, bez portova, bez `docker.sock` i produkcijskih mountova) iz postojećeg punog dumpa; produkcijski kontejneri, `.env`, Compose, baze i Traefik nisu dirani, a audit log od 8641 naredbe ne sadrži nijedan produkcijski resurs ([18](18-immich-cutover-rehearsal.md)). Jedino čitanje produkcije bilo je kopiranje datoteka model cachea iz Docker volumena u testni direktorij.

- **Faza 7B:** nova stanja, `s_open_abort`, ručne odluke i novi redoslijed zamrzavanja izvedeni su i testirani isključivo na izoliranom stacku (vidi [20](20-immich-cutover-safety.md)); produkcija nije dirana.

**Nije izvršeno:** `preflight.py`, `api_checks.py`, `validate_target.py`, `db_snapshot.py` i `steps.sh` nad produkcijom; nikakvo zaustavljanje kontejnera, pauziranje redova, dump, restore, promjena `.env`/Composea/lozinki, pokretanje `immich-db`; nikakvo brisanje backupova.

**Stati ovdje. Produkcijski cutover nije odobren.**
