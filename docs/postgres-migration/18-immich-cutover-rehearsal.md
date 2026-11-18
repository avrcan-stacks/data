# 18 — Immich cutover rehearsal (faza 6B)

Datum: 15. studenoga 2026. (Europe/Zagreb).
Privatni dokazi: `/opt/stacks/data/backups/immich-rehearsal-20261114t235658z-cab1a6` (0700, 1,8 GB; `rehearsal-results.json`, `audit.jsonl`, dump/snapshot/compare datoteke obaju prolaza).
Ulaz: [17](17-immich-production-cutover.md), [15](15-immich-application-retest.md), [16](16-immich-microservices-test.md), puni dump iz faze 4 (SHA-256 `9d901f55…32a5e`).

**Status: rehearsal je uspio, a runbook je ispravljen.** Cijeli lanac (preflight, zamrzavanje, dump, sanitizacija, restore, validacija, dark launch, rollback R1, otvaranje prometa, provjere nakon otvaranja) izveden je na izoliranoj kopiji; završno 122 od 124 zabilježena testa su PASS, a 2 zabilježena FAIL-a su **stvarne greške u mojim skriptama koje je rehearsal pronašao** i koje su ispravljene (pa je dio testova nakon ispravka ponovljen). Ukupno je pronađeno i ispravljeno **9 problema** u runbooku i skriptama. Produkcija nije dirana. Produkcijska migracija nije odobrena.

## 1. Infrastruktura rehearsala

Sve u jednom Compose projektu `immich-apptest-<ID>` na mreži `internal: true`, bez objavljenih portova, bez `docker.sock`, bez produkcijskih mountova, tajni i mreža:

| Uloga | Test kontejner | Napomena |
| --- | --- | --- |
| zamjena za `postgis` | `…-pgsrc` | isti image ID kao produkcijski `postgis` (PG 16.13 + PostGIS 3.6.2), puni dump iz faze 4 vraćen za 18,3 s, sekvenca `bigint` kao u produkciji |
| zamjena za `immich-db` | `…-immichdb` | PG 16.16 image iz faze 2, scram, `/backups` mount kao u produkciji, pokreće ga `s_prepare_target` |
| privremeni bridge | `…-bridge-*` | `--network none`, kao u runbooku |
| aplikacija | `…-server` | isti patchirani image `sha256:619fb163…`, `env_file` s lozinkom sa posebnim znakovima, label `traefik.enable=true`, workeri api + microservices |
| Redis, ML | `…-redis`, `…-ml` | zasebni; ML s kopijom model cachea |

Testni API ključevi i lozinke su nasumični i postoje samo u testnoj bazi. Podaci: administrator (bez podataka) i korisnik s 40.378 asseta, 6 albuma (4 vlastita neprazna) i 6 imenovanih osoba.

Zaštite rehearsal načina (`CUTOVER_REHEARSAL=1`): svaka naredba koju skripte izdaju prolazi kroz `guard()` (odbija produkcijska imena, `/opt/stacks/immich`, `/opt/stacks/nextcloud`, podatkovne direktorije produkcijskih baza i `docker.sock`; `docker exec/inspect/logs/stop/start/rm` moraju ciljati kontejner s prefiksom `immich-apptest-`), a `steps.sh` u tom načinu zamjenjuje `docker` omotačem `guarded_docker.py`; sve se zapisuje u audit log.

## 2. Rezultati po grupama

| Grupa | Što je testirano | Testova | Rezultat |
| --- | --- | --- | --- |
| g0 | `tests/offline_selftest.sh` | 1 | PASS |
| g1 | zaštite: produkcijska imena/putanje/socket odbijeni, 12 mutirajućih koraka odbijeno bez `CUTOVER_APPROVED`, audit log | 14 | PASS |
| g2 | učitavanje lozinke: 9 oblika zapisa → `getsecret` → `\getenv` → rola → scram prijava preko mrežne adrese uz odbijanje pogrešne lozinke | 9 | PASS |
| g4 | `api_checks`: baseline, verify, 7 vrsta oštećenog baselinea, ključ bez dozvole, pauza/drain/nastavak redova pod opterećenjem | 21 | PASS |
| gI | injekcije grešaka na klonovima ciljne baze (16 slučajeva) | 17 | PASS |
| gA, gA2, gA3 | run A: preflight, zamrzavanje, dump, bridge usporedbe, restore, validacija | 9 + 5 + 3 | 2 FAIL zabilježena (nalazi 3 i 8), nakon ispravka PASS |
| gD2, gD2b | rollback R1 iz dark stanja, odbijanje nakon T_open | 4 + 3 | PASS |
| gB, gStop | run B: reset cilja, STOP simulacije, cijeli put do otvaranja | 25 + 3 | PASS |
| gP | provjere nakon otvaranja (redovi, verify, backup na 16.16, logovi, izvor netaknut) | 10 | PASS |

Napomena o evidenciji: prve verzije grupa g2 (lažni "scram" test), gI i gD ponovljene su nakon ispravka skripti pa su prvi rezultati izbrisani iz sažetka; uzroci su opisani u odjeljku 4. Dva testa (STOP-1 i STOP-5) prvi su put pala/prošla zbog moje greške u testu (prekratak `CUTOVER_ID`) pa su ponovljena uz provjeru **razloga** zaustavljanja, ne samo exit koda.

## 3. Test po zahtjevima zadatka

| # | Zahtjev | Rezultat |
| --- | --- | --- |
| 1–2 | izolirani stack iz postojećeg sanitiziranog/punog dumpa, samo testni kontejneri, ključevi i lozinke | PASS |
| 3 | `tests/offline_selftest.sh` | PASS (12/12 provjera) |
| 4 | `db_snapshot.py`, `validate_target.py`, `api_checks.py`, preflight u `CUTOVER_REHEARSAL=1` | PASS (preflight: 0 FAIL na produkcijski sličnom stacku uz 1 WARN) |
| 5 | prepoznavanje neispravnih hasheva, tablica, ACL-ova, sekvenci, indeksa, ekstenzija | PASS, 16 od 16 injekcija prepoznato (odjeljak 5) |
| 6 | kontrolirano pauziranje i nastavak Redis redova | PASS (odjeljak 6) |
| 7 | GO/NO-GO i STOP uvjeti, simulirane greške, rollback na izoliranoj kopiji | PASS (odjeljak 7) |
| 8 | pregled i ispravak runbooka (6 navedenih točaka) | ispravljeno, odjeljak 4 |
| 9 | nijedna skripta u rehearsalu ne može dirati produkciju | PASS (odjeljak 8) |

## 4. Što je rehearsal ispravio u runbooku i skriptama

| # | Nalaz | Dokaz | Ispravak |
| --- | --- | --- | --- |
| 1 | `sed/cut` čitanje `DB_PASSWORD` iz `.env` krivo je za 3 od 9 oblika zapisa (escapeovi u navodnicima, `$`, komentar); produkcijska lozinka je alfanumerička (32 znaka) pa je rizik za nju nizak | g2: `old_sed_cut_method_equal=False` u 3 od 9 | lozinka iz okoline kontejnera (`getsecret.py`) + `\getenv` |
| 2 | login preko `127.0.0.1` ne provjerava lozinku (u imageu je `trust`); V6 i dokaz u F2 bili su bezvrijedni, a prvi g2 test lažno "prošao" | injekcija "password changed" prošla neopaženo dok se nije prešlo na mrežnu adresu | login preko adrese kontejnera + negativna kontrola (pogrešna lozinka mora pasti) u `s_prepare_target` i V6 |
| 3 | ACL baze izvora razlikuje se od bridgea/cilja jer je izvor zaštićen prije snapshota; usporedba nije mogla proći | A8 FAIL (`database` sekcija) | ACL baze se ne uspoređuje u `compare`; V4 provjerava cilj prema ACL-u prije zaštite; liste se sortiraju (nesortirana usporedba davala je lažni alarm na klonu) |
| 4 | nije postojala usporedba bridgea prije `DROP EXTENSION` | zahtjev zadatka | načini `source-bridge` i `source-bridge-after`, oba PASS u oba prolaza (1.083.961 i 1.084.237 redaka) |
| 5 | Immich odbija pauzu reda `backgroundTask` (HTTP 400); pauza je stajala na prvom redu i ostavljala redove napola pauzirane; `wait-drain` je čekao beskonačno | g4 | svi redovi se pokušavaju, iznimka je dokumentirana, ostale greške su STOP; prikaz `held` |
| 6 | **u dark fazi s workerima aplikacija sama nastavlja `metadataExtraction`** (potvrđeno u kodu: `MetadataService` ga `resume`-a pri svakom startu) i troši zadržane poslove na novoj bazi | `Q5 FAIL ['metadataExtraction']` u dark verify | dark launch samo s API workerom; STOP ako se pojavi "Starting microservices worker" |
| 7 | baseline za usporedbu uzet u F3 zastario je do zamrzavanja (korisnici pišu); verify bi dao lažni FAIL na statistikama | Q2: +25 fotografija = 25 testnih uploada | baseline se uzima nakon pražnjenja redova, neposredno prije zaustavljanja |
| 8 | V10 je uspoređivao brojeve redaka s preflight baselineom (zastarjelim) | A10 FAIL: asseti 57.772 naspram 57.747, a `compare` PASS | usporedba sa zamrznutim snapshotom izvora |
| 9 | skripte i obrasci exit kodova | više točaka | `steps.sh` (podljuske sa `set -Eeuo pipefail`, provjere praznih logova, veličine, TOC-a, hasha unutar ciljnog kontejnera, vrata odobrenja) |

Manje ispravke skripti: `preflight.py` se rušio na jednoj nedostajućoj datoteci i na praznom direktoriju backupova; `verify` na vlastitom baselineu padao je zbog razlike tipova (n-torke/liste); W4 sudi samo tople upite (prvi je hladan) jer je prvi upit nakon restorea/klona davao lažni FAIL; hladni prag smart searcha 5 s (ML model nakon 300 s mirovanja ponovno se učitava, izmjereno 2,27 s). Dva prijedloga pragova zahtijevaju pažnju: recall minimum 0,90 na 20 uzoraka bio je točno na granici za `face_index` (prosjek 0,995).

Traefik ruta: provjera bez izmjene usmjeravanja sastoji se od labela kontejnera (u rehearsalu `false` u dark fazi, `true` nakon otvaranja), preflight provjere TR1 (nema statičke Immich rute u `/opt/stacks/traefik/dynamic`) i neobvezne read-only GET provjere javnog ruba. Pravi Traefik ovdje nije pokretan pa to ponašanje nije dokazano (vidi odjeljak 9).

## 5. Injekcije grešaka na kloniranoj ciljnoj bazi

Svaki slučaj radi se na kopiji (`CREATE DATABASE … TEMPLATE`), pa glavna ciljna baza ostaje neizmijenjena. Kontrola bez izmjene: `compare` PASS i 0 FAIL u `validate_target`.

| Izmjena | `compare` (izvor → cilj) | `validate_target` |
| --- | --- | --- |
| kontrola bez izmjene | PASS | 0 FAIL |
| izmijenjen redak u `asset` | FAIL: hashevi tablica | (broj redaka isti, nije njegov posao) |
| obrisan embedding u `smart_search` | FAIL: hashevi | V10 (brojevi redaka) |
| oduzeto UPDATE pravo na `asset` | FAIL: metapodaci | V7 (prava) |
| ACL baze proširen (CREATE za PUBLIC) | PASS (ACL baze se tamo ne uspoređuje) | V4 |
| promijenjen vlasnik baze | FAIL: metapodaci | V4 |
| sekvenca `integer` | FAIL: sekvenca nije `bigint` | V9 |
| vrijednost sekvence snižena | FAIL: sekvenca niža od izvora | V9 |
| obrisan `clip_index` | FAIL: metapodaci | V8 (+ planer ne koristi indeks) |
| dodatni indeks | FAIL: metapodaci | V8 |
| **nevaljan** indeks (neuspjela `CONCURRENTLY` izgradnja) | FAIL: metapodaci | V8 |
| dodana ekstenzija (amcheck) | FAIL: ekstenzije | V3 |
| promijenjen vlasnik tablice | FAIL: metapodaci | V7 |
| oduzet EXECUTE na funkciji | FAIL: metapodaci | V7 |
| rola `immich` dobije CREATEDB (razina clustera) | PASS (role nisu u usporedbi) | V5 |
| promijenjena lozinka role (razina clustera) | PASS | V6 |

Podjela posla je namjerna: `compare` čuva podatke i definicije objekata, `validate_target` ovlasti, role, prijavu, indekse i vektore. Nakon testa uloga `immich` vraćena je (NOCREATEDB, izvorna lozinka) i klon je izbrisan.

## 6. Redovi pod opterećenjem

40 jedinstvenih sintetičkih slika učitano kao korisnik s podacima, pa odmah `queues pause --execute`: pauzirano 18 redova uz dokumentiranu iznimku `backgroundTask`; zadržani backlog **9.305 poslova** ostao je u Redisu nepromijenjen kroz 20 s (`active` 0); `wait-drain` je završio s DRAINED; `wait-drain --timeout 0` izlazi s TIMEOUT (STOP-1); nakon `queues resume --execute` backlog je obrađen do mirovanja za 47 s uz 0 neuspjelih poslova, a svih 40 asseta ima CLIP embedding (nijedan posao nije izgubljen). Ključ bez dozvole `queue.read` dobiva HTTP 403, a skripta izlazi nenulto; bez ključa daje jasnu grešku.

## 7. Simulirani STOP uvjeti i rollback

| Simulacija | Ishod |
| --- | --- |
| STOP-1: istek drain timeouta | `s_freeze` izlazi nenulto s TIMEOUT **prije** zaustavljanja kontejnera; aplikacija radi, izvor nije zaštićen; redovi se vraćaju `queues resume` |
| STOP-3: dump izvan dopuštene veličine | `s_dump_source` staje, konačna datoteka dumpa ne postoji |
| STOP-4: skraćeni dump | `pg_restore` na bridgeu pada, sanitizirani dump ne nastaje, bridge se uklanja provjerom labela i `realpath` |
| STOP-5: neispravan izvorni snapshot (promijenjen hash tablice) | `s_validate_target` izlazi nenulto jer je `compare` FAIL (`compare.json`: hashevi tablica) |
| STOP-6: pogrešna lozinka role | aplikacija ne postaje healthy, `s_dark_launch` izlazi nenulto; nakon ispravka lozinke prolazi |
| `s_open` ponovljen | odbijen (DB_HOSTNAME već promijenjen), ništa promijenjeno |
| `s_rollback_r1` nakon `T_open` | odbijen s exit 3 |
| Produkcijski način bez `CUTOVER_APPROVED` | svih 12 mutirajućih koraka odbijeno, nijedan `docker`/`python` poziv |
| Rollback R1 iz dark stanja | aplikacija na **izvornoj** bazi, `DB_HOSTNAME` izvor, ruta `true`, ACL izvora točno vraćen (prije = poslije), redovi nastavljeni; verify prema zastarjelom F3 baselineu razlikuje se samo u Q2 za točno +25 fotografija (testni uploadi), što je i razlog nalaza 7 |
| Odgoda i ponovni pokušaj | `s_target_reset_after_rollback`: neuspjela baza preimenovana (`immich_failed_…`), nije obrisana, nova prazna `immich` |

## 8. Cijeli put do otvaranja (run B) i provjere nakon otvaranja

Run B: reset cilja, preflight, baseline, zamrzavanje s aktivnim poslovima, dump, bridge (obje usporedbe PASS), restore + validacija (22 provjere, 0 FAIL; recall@10 clip 1,00, face 0,995; amcheck 0 grešaka), dark launch samo s API workerom, `s_open`, zatim:

| Provjera | Rezultat |
| --- | --- |
| `.env` | promijenjen samo redak `DB_HOSTNAME`, kopija prije promjene u evidenciji (0600) |
| aplikacija | na novoj bazi, ruta `true`, healthy |
| redovi | idle, 0 neuspjelih poslova |
| API verify prema zamrznutom baselineu | PASS (statistike, knjižnice, albumi, osobe, smart search) |
| Immich backup na PostgreSQL 16.16 | `…-v3.3.5-pg16.16.sql.gz`, 355,9 MB (prethodni 355,2 MB), `gzip -t` OK, 7 `CREATE EXTENSION` i 0 PostGIS DDL redaka |
| log nakon otvaranja | 0 ERROR/FATAL, 0 migracija, 0 reindeksiranja, "Database Backup Success" |
| veze | aplikacija na novoj bazi, izvor 0 veza |
| izvor | snapshot nakon otvaranja identičan zamrznutom (72 hasha i metapodaci): čuvanje 7 dana je sigurno |
| shema nove baze nakon rada aplikacije | nepromijenjena (0 odstupanja metapodataka) |

## 9. Produkcija i izolacija

| Provjera | Rezultat |
| --- | --- |
| kontejneri `postgis`, `immich_server`, `immich_redis`, `immich_machine_learning`, `immich_media_operations`, `nextcloud_immich_bridge`: Id, image, StartedAt, restart count, mreže, mountovi (sortirani), hash konfiguracije | identični zadnjem zabilježenom stanju prije rehearsala |
| hashevi `docker-compose*.yml`, Dockerfileova, `.env`, tailscale env, Immich compose i `.env` | identični |
| `immich-db` | ne postoji; `immich-postgres/data` i `postgres-standard/data` prazni |
| veze na produkcijsku bazu `immich` | samo `172.28.0.11` (immich_server), 10 praznih veza |
| ACL produkcijske baze `immich` | netaknut (`immich` smije CONNECT) |
| audit log skripti (8641 naredba kroz `cutlib`/`guarded_docker.py`) | 0 naredbi koje imenuju produkcijski kontejner, produkcijsku putanju ili `docker.sock` |
| `git status` | bez izmjena praćenih datoteka osim ranije izmijenjenog `.gitignore` |

Ograničenje dokaza: vlastite naredbe test drivera (`rehearse.py`) nisu prolazile kroz audit, ali ih gradi isključivo iz imena testnih kontejnera zapisanih u `state.json`; da produkcija nije dirana dokazuju prethodna usporedba stanja i audit skripti. Jedino čitanje produkcije bilo je kopiranje datoteka model cachea (`/var/lib/docker/volumes/immich_model-cache/_data`) u testni direktorij.

## 10. Što još blokira produkcijski GO

1. **Neodobrene odluke:** pragovi i ciljevi (G2, [17](17-immich-production-cutover.md) odjeljak 9), termin, odredište off-host kopije (G6), retencija i rollback (G7), odobrenje operacija (G8, O1–O14), privremeni API ključevi (G10), obavijest korisnicima i utišan monitoring (G11). Prag recall minimuma 0,90 je na granici za `face_index`; treba ga odobriti svjesno ili prilagoditi.
2. **Neprobano jer postoji samo u produkciji:** ponašanje pravog Traefika (label i TR1 su provjerene samo kao konfiguracija), `media-operations` (docker exec putanja na `immich-db`) i `nextcloud_immich_bridge` u cutoveru, OIDC prijava, video transkodiranje/trash/restore/storage template/skeniranje knjižnica nakon prebacivanja (kanarski testovi iz odjeljka 8 dokumenta 17), stvarni promet i vrijeme na produkcijskom hostu (rehearsal je radio na praznom hostu).
3. **Rizici koji ostaju:** korisnik koji uploada u sekundama između baselinea i zaustavljanja (razlika u Q2 mora se objasniti usporedbom baza), skala (57.627 asseta već je u testu, ali ne i produkcijska konkurentnost), ručna procjena nakon T_open (nema automatskog rollbacka).
4. **Preporuka:** prije stvarnog termina ponoviti `tests/offline_selftest.sh` i jedan kratak rehearsal ako se promijene skripte, `steps.sh` ili imageovi.

## 11. Čišćenje

Uklonjeni su isključivo test kontejneri, njihova mreža i `/tmp/immich-apptest-20261114t235658z-cab1a6` (provjereni labeli i `realpath`); u tom direktoriju bili su testna baza, kopija model cachea, testni medijski direktorij i fixture `.env`. Privatni dokazi u `/opt/stacks/data/backups/immich-rehearsal-20261114t235658z-cab1a6` ostaju (0700, gitignored). Postojeći backupovi i prethodni dokazi nisu dirani.

**Stati ovdje. Produkcijska migracija nije odobrena.**
