# 46 — Immich drugi pokušaj: OPEN_CONFIRMED; završna provjera HALT

Datum: **15. studenoga 2026., UTC**. CUTOVER_ID **`20261115t150714z`**.

**Promet je prebačen na `immich-db`; žurnal je valjan OPEN_CONFIRMED od 17:05:16Z. F4–F10 završili su s rc 0.** Javni `/` i `/api/server/ping` vraćaju **HTTP 200**, server i pomoćni servisi su healthy, API Q1–Q10 prolazi, redovi su nastavljeni, G14 PASS.

**Završna provjera nije proglašena potpuno uspješnom.** Stala je s **rc 1: 31 PASS / 1 FAIL** zbog ERROR zapisa radnika pri obradi **12 postojećih MP4 datoteka**. Nakon toga obustavljene su daljnje mutacije i provedena samo read-only dijagnostika. Stvarno stanje žurnala ostaje **OPEN_CONFIRMED**, a operativni status završne verifikacije **HALT_FINAL_VALIDATION**. Nije ručno upisan HALT_MANUAL niti prikriven prvi neuspjeh.

## Odobrenje, runbookovi i F3

Vlasnik je u ovoj uputi odobrio završni F3 i uvjetni nastavak dokumentiranog cutovera, siguran R1 kada je dopušten, te čuvanje izvora najmanje 7 dana. Nije odobreno prihvaćanje gubitka, ručni forward, zaobilaženje provjera ili brisanje starih baza/backupova. To odobrenje nije korišteno za naknadni popravak medija ili promjenu kontrola.

Pregledani dokumenti **17, 20, 22, 30, 39, 40, 41, 42, 43, 44 i 45**, aktualni `steps.sh`, `cutstate.py`, `preflight.py`, API/backup/snapshot/validator/seal alati i posebna F2 putanja. Kod, policy i pragovi nisu mijenjani. Hashovi odgovaraju testiranoj verziji iz 44 i ostalim sigurnosnim ovisnostima iz 40.

Prvo `date -u`: **16:51:09Z**. Novi F3 izvršen je bez CUTOVER_APPROVED, bez `--skip-api`, `--ignore-window`, preskakanja prijave ili ublažavanja pragova:

- Novi žurnal **PREPARED**, valjan hash lanac; stari **ROLLED_BACK**, isti tip i 9 zapisa.
- Immich na **postgis/immich**, javni URL-ovi HTTP 200; bridge/media-operations/Redis/PostgreSQL healthy.
- Aktualni `preflight.py --phase target-ready`: **0 FAIL / 0 WARN**. Slobodno približno **421 GiB na /** i **1453 GiB na /home**; RAID1 i NVMe/temperaturne provjere `lb_check` prošle. SMART brojači ostaju nedostupni kao ranije dokumentirano.
- Oba API ključa sigurno učitana; metadata 7+3 dozvole, bez `all`; autentikacija i nova proba **Q1–Q10 PASS, 0 FAIL/0 WARN**.
- Novi cilj prazan, očekivani OID/owner/ACL/locale i rola; stvarna mrežna SCRAM prijava rc 0, pogrešna lozinka rc 2 uz autentikacijsku grešku; nema neočekivanih ciljnih/arhivskih klijenata.
- F0 original i `/home` kopija: `lb_verify`, gzip, identitet/manifesti i dob <26 h PASS; backup star oko **15,9 h**.
- Svih **137** zaključanih datoteka i kanonski sadržaj mountova/config/lifetime osam kontejnera odgovaraju policyju. Nova read-only snimka arhive, 72 hasha, metapodaci, sekvence i write-probe ponovno PASS.
- Nema starog T0/T_open, novih dumpova ili zauzete privremene bridge putanje. Trenutačno odobreni nadzirani prozor ima više od 75 min do cron isključenja. Nije korištena ranija vremenska iznimka.

**F3 GO** donesen je prije zamrzavanja, na temelju ovih novih provjera. Ranije odluke o lokalnoj RAID1 + `/home` zaštiti, bez off-host kopije, i izostanku obavijesti zadržane su prema 41; off-host G6 nije preoznačen kao ispunjen.

## Vremena i rezultati faza

Sve faze pozvane su pojedinačno kroz privatni driver koji učitava oba ključa, postavlja točan ID/putanje, provjerava prethodnik i vrijeme, poziva postojeću funkciju samostalno te bilježi stvarni rc i novo verificirano stanje. Nema `if`/`&&`/`||`/`eval` wrappera oko poziva mutirajućih funkcija. Svaka faza ima zaseban izlaz i JSON evidenciju; kod funkcija ostao je nepromijenjen.

| Faza | UTC početak → kraj | Trajanje | rc / završno stanje |
| --- | --- | --- | --- |
| F4 `s_freeze` | **16:54:17.494 → 16:57:14.328** | 176,83 s | **0 / FROZEN** |
| F5 `s_dump_source` | **16:57:20.875 → 16:58:23.977** | 63,10 s | **0 / DUMPED** |
| F6 `s_bridge_sanitize` | **16:58:32.034 → 17:00:08.708** | 96,67 s | **0 / SANITIZED** |
| F6b `lb_copy_cutover_dumps`, `lb_verify` | **17:00:24.884 → 17:00:38.034** | 13,15 s | **0 / SANITIZED** |
| F7 `s_restore_and_validate` | **17:01:07.590 → 17:02:15.671** | 68,08 s | **0 / VALIDATED** |
| F8 `s_dark_launch` | **17:02:40.446 → 17:03:44.260** | 63,81 s | **0 / DARK_VERIFIED** |
| F9 `s_backup_gate`, F8 seal check | **17:03:53.228 → 17:03:59.546** | 6,32 s | **0 / DARK_VERIFIED** |
| F9 neovisni GO | **17:04:27Z**, T0 + 610,3 s | — | **GO** |
| F10 `s_open` | **17:04:33.451 → 17:05:16.443** | 42,99 s | **0 / OPEN_CONFIRMED** |

Dokumentirani `s_bridge_cleanup` nakon uspješnog F7 završio je **rc 0**. Uklonjeni su samo označeni privremeni bridge i njegov `/tmp` PGDATA; nova arhivirana baza, izvor, cilj, dumpovi i backupovi nisu brisani.

### Novi sat i pragovi

Postojeći neizmijenjeni `s_freeze` upisuje `$EV/T0` **na početku F4**, prije zaustavljanja svih pisaca: **16:54:17Z**. Stvarno uspješno zamrzavanje potvrđeno je stanjem **FROZEN u 16:57:14Z**. Za nadzor je korišten **raniji, stroži sat** iz datoteke T0; vrijeme nije pomaknuto unaprijed radi dodatnog roka.

Redoslijed `freeze-order.log`:

1. Bridge i media-operations zaustavljeni **16:56:19Z**.
2. Redovi pauzirani/prazni **16:56:22Z**; `backgroundTask` je dokumentirana nepausabilna iznimka.
3. Javni server zaustavljen **16:56:24Z**.
4. Novi baseline iz API-only instance bez javne rute na izvoru **16:57:12Z**.
5. Izvor zaštićen i sonda A **16:57:14Z**.

**T_open=17:05:12Z; OPEN_CONFIRMED=17:05:16Z.** Konzervativno T0 → potvrda: **659 s = 10 min 59 s**; od uspješno potvrđenog FROZEN oko **8 min 2 s**. Opaženi interval odsutnosti javnog servera do T_open oko **8 min 48 s**; stvarna ruta mogla je postati dostupna malo prije T_open, tijekom dokumentiranog recreatea.

Cilj 30 min bio je **17:24:17Z**, STOP/odluka na 45 min **17:39:17Z**, a granica 60 min **17:54:17Z**. Nijedna nije prekoračena; ne postoji odobrenje za njihovo ignoriranje. Nakon OPEN_CONFIRMED protek vremena ne otključava R1.

## Novi podaci, dumpovi, F7 i F8

F5/F6 koristili su isključivo novi zamrznuti izvor. `freeze-gap-proof.json` **C0–C5 PASS**, bez allow-liste. Obje bridge usporedbe prije/poslije DROP EXTENSION postgis RESTRICT i ciljna usporedba: **72/72 tablice**, metapodaci i sekvence PASS. Dump logovi prazni, TOC provjeren, sanitizirani TOC bez PostGIS-a.

| Novi dump | Bajtova | SHA-256 |
| --- | --- | --- |
| `immich.full.dump` | **354.261.795** | `f9ac4f8baff5d9d49321263492a9ea8a406c0fbfe86d0208be8ec2493d7115bf` |
| `immich.no-postgis.dump` | **354.050.061** | `daee02e37b7e16af1e09f543ca8e42a03e966c027dc5da0e8c83a54f81f8274e` |

Originali su u novom `$EV`; obje druge kopije u `/home/immich-cutover-backups/20261115t150714z/dumps/`. SHA-256 i TOC originala/kopija jednaki; COPIES_DONE i novi manifesti postoje. Stari dumpovi nisu korišteni ni prepisani.

F7 validator: **22 provjere, 0 FAIL / 0 WARN**, 254 indeksa, 243 provjerena btree indeksa, 0 heap korupcija, amcheck ekstenzija nije ostala instalirana. Recall clip **mean/min 1,000/1,00**, face **0,995/0,90**; najsporiji topli ANN oko **9,8/9,4 ms**. Brojevi redaka i sekvenca uspoređeni sa zamrznutim snapshotom, ne zastarjelim preflightom. System-config hash identičan.

F8: API-only, bez javne rute, HTTP 404 izvana; oba ključa, **Q1–Q10 PASS**, 0 FAIL/0 WARN; smart overlap min/mean **1,00**, warm p95 **229 ms**, cold max **402 ms**. Nova API receipt, `dst2`, write-probe i **`dark-verified.json`** proizvedeni su za ovaj ID i verificirani prije F10. Ne koriste se dokazi prvog pokušaja.

**G14 PASS** u F9 i ponovno unutar F10 prije prve promjene. Posljednji `gate.log` ima SHA-256 **`85df351b126110069363bb220cc0039befb39c4800037615aa8827f3960223cb`**. Nakon otvaranja `lb_check` i `lb_verify` ponovno prošli; kasniji read-only `lb_verify` također rc 0.

## Stvarno stanje nakon otvaranja

Ponovne read-only provjere do **17:11:10Z**:

- Novi žurnal **OPEN_CONFIRMED**, **16 zapisa**, hash lanac valjan; tip **`3b9f23ce2847848863d3ea709ca0005179f811ced2418fed5fa34e653c381fbf`**. Provjeren i `cutstate.py verify`, rc 0.
- Server healthy na **immich-db/immich**, javna ruta HTTP 200. Media-operations healthy s DB_HOSTNAME=immich-db; bridge healthy, bez novih ERROR/FATAL/DB lookup grešaka u provjerenim logovima.
- Dvije nove post-open API verifikacije prema frozen baselineu: **Q1–Q10 PASS, 0 FAIL/0 WARN**. Fotografije **55.535**, videi **1.306**, 8 knjižnica, 6 albuma i 792 osobe na provjeravanom korisničkom računu odgovaraju baselineu.
- Svih 19 redova nastavljeno, active/waiting/delayed=0. Jedini failed ostaje poznati **facialRecognition=1**, bez povećanja. Medijske ERROR poruke dolje nisu povećale taj brojač redova u opaženim provjerama.
- Redis healthy, isti Id/StartedAt **2026-06-26T21:46:10.698303676Z**, restart count **0**. Nije restartan ili recreatean.
- `postgis`, `immich-db`, ML i Traefik zadržali su svoje identitete, konfiguraciju, mountove i start vremena. Server/media-operations namjerno su recreateani dokumentiranim postupkom, bridge zaustavljen/pokrenut.
- Jedina izmjena produkcijske datoteke `.env` je točan odobreni DB_HOSTNAME postgis → immich-db. Ostalih **136** zaštićenih datoteka hashom nepromijenjeno, uključujući Compose/Traefik, ključeve, stare dokaze i F0. Sve prethodne **14 aplikacijske backup datoteke** ostale su iste sadržajem, veličinom i mtime; nije nastala rotacija.
- Izvor `postgis/immich` zaštićen, CONNECT ulozi immich=false, 0 aplikacijskih klijenata. Novi read-only snapshot nakon otvaranja pokazuje svih **72 hasha, metapodatke i sekvence identične frozen `$EV/src`**.
- Arhiva **immich_failed_20261115t150714z_**, isti OID 16385/owner/ACL/locale, **72 tablice / 57.627 asseta**, strogi no-write probe PASS. Nije mijenjana.
- Prethodni pokušaj **20261115t130331z** ostaje valjan **ROLLED_BACK**, isti tip `c25c344676e5145e9b9cf23a5f74ed40410a5d695adc43a68593e29b3ccb85da`.

## Razlog HALT-a završne verifikacije

Prva neovisna `final.sh` završila je s **rc 1**. `final-failed.json` čuva **31 PASS i 1 FAIL**: `no unexpected startup/runtime errors immich_server`. Nema završnog `final.json` koji bi taj prolaz lažno označio uspješnim. Sve kasnije radnje bile su samo čitanja, provjere, kopiranje aplikacijskog koda radi pregleda i novi dokazi/izvještaj.

U logu nakon nastavka microservices radnika pojavile su se greške:

`Unable to run job handler (AssetExtractMetadata): ffprobe exited with code 1`

`moov atom not found` / `Invalid data found when processing input`.

Početno **12 ERROR zapisa za 12 asseta**; do **17:10:46Z** ukupno **24 ERROR zapisa**, svi istog tipa, za iste postojeće medijske probleme. Nisu zabilježene druge vrste ERROR/FATAL u tom sažetku.

Read-only dijagnostika dokazala je:

- Svih **12 asseta već postoji u frozen izvoru**, createdAt prije T0; provjereni odabrani metapodaci izvora i cilja jednaki.
- Datoteke postoje i dostupne su; riječ je o MP4 datotekama, ne nedostajućim mountovima ili Appledouble datotekama.
- Stvarni SHA-1 svih **12/12 datoteka odgovara checksumu u sačuvanoj izvornoj bazi**. Mtime i ctime svih datoteka prethode T0.
- To podupire zaključak da se radi o **postojećim nevaljanim/nepotpunim MP4 sadržajima**, a ne promjeni bajtova tih datoteka migracijom. Datoteke nisu popravljane, brisane ili ponovno uploada­ne; poslovi nisu ručno ponavljani ili čišćeni.

Prvi FAIL ostaje sačuvan. Naknadni API PASS i objašnjenje medijskih grešaka **nisu preoznačili taj prolaz u sve-PASS završetak**. Potrebna je zasebna odluka o obradi/prihvaćanju tih postojećih problema; puni završni checklist nije zatvoren.

### Zašto nema rollbacka ili s_open_abort

Stanje je već **OPEN_CONFIRMED**, redovi su nastavljeni i radnici pišu u novu bazu. R1 bi mogao izgubiti nove zapise i prema runbooku je zabranjen. **Nisu pokrenuti R1, s_manual_forward ili s_manual_rollback_accept_loss.**

`s_open_abort` služi za djelomično otvorene faze OPEN_BEGIN…AUX_STARTED, uz E1–E7 dokaz. **Nije primjenjiv nakon OPEN_CONFIRMED i nije pozvan.** Nisu zaustavljani novi javni server ili Redis, mijenjan žurnal radi prividnog povratka ili izvršavani improvizirani SQL/Docker popravci.

## F11/F12 i preostale provjere

- **OIDC:** vlasnik je tijekom rada odgovorio **„Provjera će biti naknadno”**. Web/mobilna prijava nije označena provjerenom. Migrirani system-config identičan je izvoru, ali to nije dokaz stvarne OIDC prijave.
- **Ručni aplikacijski backup F11 nije pokrenut nakon HALT-a.** Dodatno je pregled stvarnog koda potvrdio da `handleBackupDatabase()` nakon stvaranja poziva cleanup. Persistirani config nema backup override, default `keepLastAmount=14`; uz postojećih 14 backupova novi rutinski backup uzrokovao bi brisanje najstarijeg. To nije izvršeno, u skladu sa zabranom brisanja backupova. Novi frozen dumpovi i obje `/home` kopije ostaju verificirani; F0 i G14 PASS nisu zamjena za post-open aplikacijski backup.
- Neobavezni dijagnostički SQL upit za backup postavke prvo je vratio SQL NULL koji parser nije prihvatio kao JSON; nije proglašen PASS-om. Zasebni validni JSON upit potvrdio je jedan system-config redak bez spremljenog backup overridea, a default 14 potvrđen je iz stvarnog aplikacijskog koda. Nije promijenjena konfiguracija ili prag.
- Kanarski upload/video/trash/restore, 60-minutno praćenje, sljedeći 02:00 backup, noćni scan/integrity, T+24 h i T+7 d nisu proglašeni dovršenima. Nisu uvedene dodatne mutacije nakon HALT-a.

**Izvor čuvati najmanje do 2026-11-22T17:05:12Z**, uz zadržanu zaštitu i bez zamjene/nadogradnje postgis kontejnera. Izvor, arhivu, oba nova/stara dumpa, backupove i dokaze ne brisati ili prepisivati bez zasebne upute. Buduća odluka o vraćanju podataka ne smije se temeljiti na pretpostavci da je zastarjeli izvor bezgubitan rollback.

## Evidencija i preporuka

Produkcijski dokazi: `/opt/stacks/data/backups/immich-cutover-20261115t150714z/` — novi preflight/baseline, frozen snapshot/sonde, oba dumpa/manifesti, bridge usporedbe, restore/validator, novi F8 API receipt/seal, G14, žurnal i post-open API rezultati.

Privatni audit izvršenja: `/opt/stacks/data/backups/immich-execution-20261115t165227z/`:

- `context.sh`, `phase.sh`, `code-hashes.json`, `f3.sh`, `f3.out`, `f3-extra.json`, `F3-GO.json`.
- `F4`–`F10` `.out`/`.json`, `F9-GO.json`, `cleanup.out`, `archive-f3/` i sonde.
- `final.sh`, `final.out`, `final-failed.json`, `source-after-open/`, `archive-final-probe.json`.
- `error-assets-*.json`, `error-asset-ids.json`, sanitizirani logovi, `latest-errors.json`.
- `halt-read.out`, `halt-read.json`, `queues-latest.json`, `retention-obligation.json`, pregledani backup/config kod.

Najsigurnije je **zadržati dostupni Immich na novoj bazi, bez automatskog rollbacka**, te zasebno odlučiti o 12 postojećih MP4 grešaka i završiti odgođene post-cutover provjere. Iz ovog rada nije pokrenut commit, push ili PR; produkcijski migracijski kod i kontrole nisu mijenjani.

**Ovdje stajem: stvarni žurnal OPEN_CONFIRMED; završna verifikacija HALT, bez tvrdnje da je cjelokupan završni postupak prošao.**
