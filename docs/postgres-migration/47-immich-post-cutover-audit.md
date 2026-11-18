# 47 — Immich post-cutover audit: OPEN_CONFIRMED, otvorena odstupanja

CUTOVER_ID: **`20261115t150714z`**. Audit **18. studenoga 2026., 05:41:04–05:46:21 CET (Europe/Paris)**, odnosno **04:41:04–04:46:21 UTC**; izvještaj sastavljen odmah potom. Sve produkcijske radnje bile su read-only. Novi dokazi i ovaj izvještaj jedini su namjerni zapisi; operativni tokeni nisu postavljeni.

**Immich je dostupan na `immich-db`, žurnal OPEN_CONFIRMED valjan, HTTP 200, Q1–Q10 PASS.** Nema potvrde da je puni završni checklist zatvoren: ostaju 12 neispravnih MP4 datoteka, nove vrste JPEG grešaka, problemi u izvještaju bridgea i automatska rotacija triju starih aplikacijskih backupova. Nije izvršeno popravljanje ili rollback.

Pročitani su dokument 46 i relevantni dijelovi runbooka 17: F11/F12, retencija izvora i post-cutover provjere. Pregledani su postojeći API/žurnal/backup/snapshot alati te stvarni kod bridgea, media-operations i aplikacijskog backup servisa. OIDC ostaje odgođen prema ranijoj odluci vlasnika.

| Provjera | Aktualni rezultat |
| --- | --- |
| Novi žurnal | **OPEN_CONFIRMED**, 16 zapisa, `cutstate.py verify` rc 0, isti hash lanac/tip kao u 46 |
| Prethodni pokušaj | **ROLLED_BACK**, 9 zapisa, verify rc 0, isti tip |
| Server | healthy, `DB_HOSTNAME=immich-db`, bez restarta od cutovera |
| Media-operations | healthy, `DB_HOSTNAME=immich-db`; stvarni SELECT kao rola `immich` nad `immich-db/immich` u READ ONLY transakciji rc 0; `/healthz` status ok |
| Bridge | healthy; API `http://immich-server:2283/api` razriješen na aktualni server; ciklusi rade, ali postoje niže opisane poslovne greške |
| Javni `/`, `/api/server/ping` | **200 / 200** |
| API Q1–Q10 | **10 PASS, 0 FAIL / 0 WARN**, rc 0; oba ključa sigurno učitana, vrijednosti nisu ispisane |
| Redis | healthy; isti identitet/start `2026-06-26T21:46:10.698303676Z`, RestartCount 0 |
| Redovi | 19/19 nije pauzirano; active/waiting/delayed/held 0; samo postojeći facialRecognition failed=1 |
| Izvor i arhiva | pune nove read-only snimke 72 tablice, metapodaci, hashevi i sekvence identični svojim referencama |
| Lokalna zaštita | `lb_check` rc 0; `lb_verify` obaju pokušaja rc 0 |

Novi tip žurnala: `3b9f23ce2847848863d3ea709ca0005179f811ced2418fed5fa34e653c381fbf`. Prethodni: `c25c344676e5145e9b9cf23a5f74ed40410a5d695adc43a68593e29b3ccb85da`. Žurnali nisu mijenjani. Stanje žurnala ne briše raniji HALT završne verifikacije iz dokumenta 46.

Server i media-operations stvarno koriste novi cilj. Bridge **nema vlastiti pristup PostgreSQL-u**: kod koristi Immich API i Nextcloud OCC. Naslijeđeni `DB_HOSTNAME=postgis` u okolini bridgea postoji, ali ga njegov kod ne čita; sam po sebi nije dokaz pogrešne baze. API hostname razrješava se na IP aktualnog `immich_server`, koji koristi `immich-db`. Nije mijenjana okolina bridgea radi kozmetičkog usklađivanja.

U zadnjem izvještaju bridgea 04:42:58–04:43:03Z obrađeno je 7 korisnika / 8 izvora, 0 mismatches, ali **5 errors**: Nextcloud servisni računi bez adrese e-pošte. U 705 zadržanih post-cutover ciklusa broj errors bio je 3 u 238, 4 u 230 i 5 u 237 ciklusa. Već prije cutovera tri provjerena ciklusa imaju errors=3. Povećanje na 5 nije označeno PASS-om; nije dokazana njegova veza s promjenom baze. Log nema doslovni ERROR/FATAL, no poslovni izvještaj dokazuje greške. Time se precizira preširok opis bridgea „bez grešaka” iz 46.

API statistike odgovaraju frozen baselineu: 55.535 fotografija / 1.306 videa na provjeravanom skupu, 8 knjižnica, 6 albuma, 792 osobe. Smart-search overlap min/mean 1,00; warm p95 247 ms prema baselineu 252 ms, najveći prvi upit 221 ms. To je uspjeh definiranih Q1–Q10, a ne dokaz ispravnosti svih medijskih datoteka. `integrity_report` ostaje **8.033** na izvoru i cilju.

Pregledani su zadržani Docker logovi od **15.11.17:05:16Z**; serverski obuhvat završava **18.11.04:37:59Z** pri dohvaćanju. JSON-file konfiguracija nema eksplicitne limite rotacije. Izvan dostupnih Docker logova nije tvrđen potpuni pregled svih sistemskih datoteka logova.

- Server: **8.511 job-handler grešaka**: **8.496 AssetExtractMetadata/ffprobe** za točno istih 12 UUID-ova iz 46 te **15 AssetGenerateThumbnails/VipsJpeg** za 5 drugih asseta. Zajedno 17.022 ERROR redaka zbog dodatnog ispisa istog error objekta; to nisu 17.022 različita posla. **0 FATAL**.
- MP4: svih 12 datoteka postoji, SHA-1 odgovara checksumu frozen izvora, odabrani metapodaci cilja i izvora jednaki. Izravni read-only `ffprobe` ponovno vraća rc 1, `moov atom not found` / nevaljan ulaz. Nijedan posao nije ručno pokrenut ili ponovljen; vidljiva ponavljanja potječu od redovnog rada.
- JPEG: nove vrste grešaka `Failed to decode DCT block` i `End-of-block run too long`, po 5 događaja pri svakom od tri noćna skeniranja, prvi put **15.11.23:00Z = 16.11.00:00 CET**. Svih 5 asseta već postoji u izvoru, izabrani zapisi izvora i cilja jednaki, datoteke dostupne. Međutim **5/5 aktualnih SHA-1 ne odgovara checksumu u staroj bazi**. Njihovi mtime/ctime potječu iz travnja, prije T0, što podupire ranije odstupanje, ali bez snimke njihovih bajtova na T0 nije dokazan trenutak/promjena sadržaja. Ovo ostaje zaseban otvoren nalaz, ne zaključak da je migracija oštetila datoteke niti tvrdnja da su uredne.
- Media-operations u tom Docker log prozoru nema redaka; Redis i cilj nemaju ERROR/FATAL u početnom dohvaćanju. Zdravlje media-operations dodatno potvrđeno njegovim endpointom i stvarnim read-only DB upitom, ne samo odsutnošću logova.

Postojeći aplikacijski backupovi nalaze se u `/opt/stacks/immich/docker-data/library/backups/`. Trenutačno ih je **14**, od 05. do 18.11.; za **svih 14** izračunat je SHA-256 i `gzip -t` vraća rc 0. Jedanaest preostalih predmigracijskih datoteka identično je početnom popisu sadržajem, veličinom i mtime. Prava su root:root 0644. Nisu mijenjana.

**Automatski backup nakon migracije stvarno se izvršio tri puta**, u 02:00 CET / 01:00 UTC. Log sadrži Starting i Success, a datoteke imaju očekivanu verziju, završni dump marker, **7 CREATE EXTENSION**, **0 PostGIS DDL**. Header: server 16.16, korišteni pg_dump 16.15. Veličine su oko 355,17 MB, u ±10 % prethodnog backupa.

| Dan, 02:00 CET | Success UTC | Veličina |
| --- | --- | --- |
| 16.11.2026. | 01:00:47.328Z | 355.174.383 B |
| 17.11.2026. | 01:00:47.620Z | 355.168.041 B |
| 18.11.2026. | 01:00:47.245Z | 355.169.501 B |

**Nisu svi prvotni aplikacijski backupovi očuvani u izvornom direktoriju.** Nedostaju:

- `immich-db-backup-20261102T020000-v2.6.3-pg16.13.sql.gz`
- `immich-db-backup-20261103T020000-v2.6.3-pg16.13.sql.gz`
- `immich-db-backup-20261104T020000-v3.3.5-pg16.13.sql.gz`

Nisu pronađeni ni pretragom njihovih imena pod migracijskim `/opt/stacks/data/backups` i `/home/immich-cutover-backups`. Njihova dostupnost drugdje nije dokazana. Tri nova backupa, 14 ukupno i nestanak tri najstarija odgovaraju automatskom `keepLastAmount=14`; u dostupnom logu nema pojedinačnog unlink zapisa pa je atribucija cleanupu zaključak iz stanja i pregledanog koda. Ovo je odstupanje od zahtjeva da se stari backupovi ne brišu. **Audit nije pokrenuo backup ili cleanup i nije ništa brisao.** F0 kopije od 15.11. i migracijski dumpovi ostaju očuvani.

| Postojeći aplikacijski backup | Bajtova | SHA-256 | gzip |
| --- | --- | --- | --- |
| `immich-db-backup-20261105T020000-v3.3.5-pg16.13.sql.gz` | 348,704,885 | `1fdb955862d9903b6ad636d44238ddd44943bb98e14633c74b43771add68761c` | PASS |
| `immich-db-backup-20261106T020000-v3.3.5-pg16.13.sql.gz` | 348,704,783 | `ffc971b2111c1440fbd63c34f93ea276f7821bdd074cc6deca7bcbc8100a8fb0` | PASS |
| `immich-db-backup-20261107T020000-v3.3.5-pg16.13.sql.gz` | 348,701,991 | `36eddcc152a41076aee41134c809df6605abd37ff1b15edce4271cf816ab1515` | PASS |
| `immich-db-backup-20261108T020000-v3.3.5-pg16.13.sql.gz` | 348,703,926 | `09f5d8bb9336cd223561ba866a19be58084af4816449fe98c6c72e8d61b55e52` | PASS |
| `immich-db-backup-20261109T020000-v3.3.5-pg16.13.sql.gz` | 348,709,482 | `dcea38968303e9a78d961c7bea1e3c7358969b634135af2280c36cf5c41a5424` | PASS |
| `immich-db-backup-20261110T020000-v3.3.5-pg16.13.sql.gz` | 355,175,454 | `de9030ee1bf92a41577be052242dcc075b258c61907ec689a1667504cfdd0eb3` | PASS |
| `immich-db-backup-20261111T020000-v3.3.5-pg16.13.sql.gz` | 355,178,655 | `d0941d5675ba442c13b6cc8781cabbabf56e787e5d8881a7f675817f27dd00c8` | PASS |
| `immich-db-backup-20261112T020000-v3.3.5-pg16.13.sql.gz` | 355,175,816 | `f547a1b3e0bdcfa3fe941a71b724d02a4471bf11e6be3195e200381c8d6785e2` | PASS |
| `immich-db-backup-20261113T020000-v3.3.5-pg16.13.sql.gz` | 355,177,900 | `4d5b2c9a1b8e777b224cd5853a6096293d78e41ba1aaebb47508785a04c5fc1e` | PASS |
| `immich-db-backup-20261114T020000-v3.3.5-pg16.13.sql.gz` | 355,180,212 | `291d6d7be30c7a9cfd0e64b515b13206b4ec715aa43bf73c394a5e65c1a1ef78` | PASS |
| `immich-db-backup-20261115T020000-v3.3.5-pg16.13.sql.gz` | 355,181,926 | `25b7780f666822c99bc8bcfc50d3e9c5851f203f29d7149b65d429821d73b0fd` | PASS |
| `immich-db-backup-20261116T020000-v3.3.5-pg16.16.sql.gz` | 355,174,383 | `618fd80b3685f36e1aab69bd604647d1ffd48239431cfbeda6171a650f12ffd4` | PASS |
| `immich-db-backup-20261117T020000-v3.3.5-pg16.16.sql.gz` | 355,168,041 | `70dafb68358282233ddad7a0a64ef31031622cff10954d6667cb6ed02888f864` | PASS |
| `immich-db-backup-20261118T020000-v3.3.5-pg16.16.sql.gz` | 355,169,501 | `9b8243e71148bc7393f56410a22ab9fa1fc8ffbb70ad5ec12a0692471cd387c4` | PASS |

Siguran plan novog post-cutover backupa, **bez izvršenja u ovom auditu**:

1. Uz zasebno odobrenje najprije sačuvati postojeći odabrani/skup zaštićenih aplikacijskih backupova u novom root:root 0700 direktoriju izvan `/data/backups` i izvan dosega rutinske retencije, uz novu drugu kopiju na `/home`. Najnoviji već nastali backup od 18.11. valjan je kandidat za kopiranje, bez novog aplikacijskog posla. Kopiranje ne smije prepisati ranije F0/manifeste.
2. Ako je potreban **novi trenutni snapshot**, zaseban kontrolirani `pg_dump` aktivnog `immich-db/immich`, klijent **16.16 u `immich-db`** (provjerena verzija), u jedinstveni zaštićeni direktorij npr. `/opt/stacks/data/backups/immich-post-cutover-backup-<novi-UTC-ID>/` i druga kopija `/home/immich-post-cutover-backups/<novi-UTC-ID>/`. Ne koristiti rutinski handler `backup-database`, jer on bezuvjetno nakon stvaranja poziva cleanup.
3. Driver mora koristiti konzistentni pg_dump snapshot, privatne privremene datoteke, zabranu prepisivanja, provjeru rc svake faze/oba člana pipelinea, dovoljan prostor, sigurno rukovanje autentikacijom bez ispisa tajni, chmod 0600, fsync te završno objavljivanje samo po uspjehu. Provjeriti gzip/dump marker ili TOC prema izabranom formatu, odsutnost PostGIS-a, hash originala i druge kopije, manifest, verziju i vrijeme izvora. Puni restore test ide u izolirano okruženje uz zasebno odobrenje.
4. Bez promjene produkcijske konfiguracije, retencije, redova, migracijskog ID-a/žurnala i bez brisanja neuspjelih/starih kopija. Ne nazvati novi backup dovršenim prije svih provjera. Gornje je plan, nije nov izrađen/testiran produkcijski driver.

Aktualni backup servis bajt-za-bajt odgovara pregledanom kodu iz 46; nema persistiranog backup overridea, default je 14. Čuvanje trenutnih rutinskih datoteka samo u aplikacijskom direktoriju zato nije trajna zaštita: sljedeći očekivani cron je **19.11.2026. 02:00 CET / 01:00 UTC**. Audit nije mijenjao raspored niti sprečavao automatsku rotaciju.

Izvor **`postgis/immich`** i arhiva **`immich-db/immich_failed_20261115t150714z_`** imaju po **72 tablice / 57.627 asseta**. Nove pune read-only snimke obje baze daju identične metapodatke, sve hasheve i sekvence prema frozen izvoru odnosno arhivskoj referenci iz F3. Izvorni CONNECT za `immich` ostaje false, aplikacijskih klijenata 0. Izvor i arhiva nisu mijenjani. Izvor zadržati najmanje do **22.11.2026.18:05:12 CET / 17:05:12 UTC**, bez automatskog brisanja nakon tog roka.

**Sva četiri produkcijska migracijska dumpa iz obaju pokušaja i njihove četiri `/home` kopije prolaze manifest/SHA-256 provjeru.** `lb_verify` za oba ID-a rc 0, uključujući oba F0 originala i `/home` kopije. Rehearsal dumpovi dodatno su popisani, ali nisu svi zasebno ponovno hashirani; tvrdnja o četiri dumpa odnosi se na dva produkcijska pokušaja. Postojeći G14 dokaz nije mijenjan ili ponovno proglašen novim gateom otvaranja.

`postgis`, `immich-db`, Redis, ML i Traefik imaju identične potpune potpise konfiguracije/mountova/identiteta/vremena starta prema zaključanom policyju; mountovi uspoređeni kanonski po cijelom sadržaju. Svih 136 zaštićenih datoteka iz policyja osim namjerno promijenjenog `.env` ostaju iste. Aktualni `.env` potpuno odgovara odobrenom `immich.env.after` iz F10; Compose/Traefik nisu promijenjeni. Svi promatrani kontejneri imaju RestartCount 0.

Evidencija: `/opt/stacks/data/backups/immich-post-cutover-audit-20261118t044104z`. `audit.json`, `details.json`, `jpeg-more.json`, `bridge-cycles.json`, `service-checks.json`, `last-read.json`, `application-backups.json`, `media-checks.json`, nove snimke `source/` i `archive/`, zadržani sanitizirani logovi i popis naredbi/rc. API uzorak i potpuni receipt u tom direktoriju; postojeći API alat također je dodao novi `api-verify-20261118T044257.json` u aktualni EV, bez prepisivanja ranijih dokaza. Žurnali nisu mijenjani.

Dijagnostička odstupanja audita transparentno su sačuvana: prva dva pomoćna read-only prolaza završila su rc 1 zbog SELECT naredbi bez završnog `;` prije helperova ROLLBACK (psql rc 3); jedan nastavni pomoćni prolaz završio je rc 1 zbog nedostajuće lokalne Python varijable pri agregaciji. To nisu skriveni PASS rezultati. Popravljeni su samo novi privatni audit helperi, sačuvani prvi izlazi, dovršene nedostajuće provjere bez ponavljanja snapshotova ili promjene produkcije. Ciljni Docker log dodatno bilježi vlastitu dijagnostičku SQL syntax grešku **18.11.04:43:20Z**; nije klasificirana kao nova aplikacijska migracijska greška. Na izvoru je SELECT također odbijen; njegov Docker log ne sadrži taj redak. Svi SQL pristupi bili su READ ONLY transakcije, bez popravaka podataka.

**Preporuka:** zadržati dostupni Immich na novoj bazi, zasebno odobriti zaštitu preostalih backupova izvan rutinske retencije te odvojeno razriješiti medijske i bridge nalaze. Puni završni status iz 46 ostaje otvoren; OIDC nije provjeren ovim auditom. Nisu izvršeni rollback, restart/stop, konfiguracijske izmjene, ručni backup/cleanup, ponavljanje poslova, Git commit/push/PR ili drugi operativni mutirajući zahvati. **Nakon ovog izvještaja rad je zaustavljen.**
