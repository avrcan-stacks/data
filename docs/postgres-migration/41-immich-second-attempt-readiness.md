# 41 — Immich: priprema drugog produkcijskog pokušaja

Datum: 15. studenoga 2026., provjere **15:07:14–15:10:27 UTC**.

**Produkcija je zdrava; novi pokušaj nije odobren niti pokrenut.** Status za izvršenje: **NO-GO do odobrenja novog F0, postupka pripreme postojećeg cilja i novog operativnog prozora/koraka.** Ovaj dokument je plan, ne odobrenje.

Pročitani [39](39-immich-r1-result.md), [40](40-immich-cutover-safety-hardening.md) i runbook [17](17-immich-production-cutover.md); za prethodne odluke pregledani 29–32 i 35–37. Povijesne tvrdnje iz 17/30 prije prvog pokušaja ne zamjenjuju aktualne provjere.

## 1. Aktualna produkcija

| Provjera | Rezultat |
| --- | --- |
| Immich server | Running, healthy, v3.3.5; `DB_HOSTNAME=postgis`, `DB_DATABASE_NAME=immich`, `DB_USERNAME=immich`; standardni workeri, `traefik.enable=true`. |
| Javna dostupnost | `/` i `/api/server/ping`: **HTTP 200**, curl rc 0. |
| Izvor `postgis/immich` | **57.627 asseta**, CONNECT dopušten; ACL `{=Tc/immich,immich=CTc/immich}`. Izvor ispravno služi produkciji nakon R1 i sada nije zamrznut. |
| Bridge / media-operations | Oba running, healthy; konfiguracija na izvoru. |
| Redis | Healthy, restart count 0, `StartedAt=2026-06-26T21:46:10.698303676Z`; nije restartan. |
| Ostali servisi | `postgis`, ML, `immich-db` healthy; Traefik running. |
| Preflight | `preflight.py --phase target-ready`: **PASS, 0 FAIL / 0 WARN**, s oba API ključa i bez `--skip-api` / `--ignore-window`. |
| API proba | Novi trenutni baseline i verify: **Q1–Q10 PASS, 0 FAIL / 0 WARN**. 55.535 fotografija, 1.306 videa, 8 knjižnica; smart overlap 1,00, warm p95 239 ms naspram baselinea 272 ms, cold max 227 ms. |
| Ključevi | Postojeći admin/user ključevi učitani pomoću `keys_env.sh`; metadata provjera 3 × PASS: točno 7 admin i 3 korisničke dozvole, nema `all`. Vrijednosti nisu ispisane ni zapisane. |
| Monitoring | Uptime Kuma: 17 monitora, 0 pogodaka za Immich / `media.finestar`; samo čitanje konfiguracije. |

`target-ready` potvrđuje zdravlje postojećeg kontejnera i produkcije, **ne potvrđuje da je ciljna baza prazna**. `before-target` pretpostavlja nepostojeći kontejner i prazan PGDATA, pa nije prikladan kao neizmijenjeni kriterij za ovaj ponovljeni pokušaj. Nijedna njegova provjera nije preinačena ili označena lažnim PASS-om.

API baseline iz ove pripreme je proba alata na aktivnoj produkciji. Ne smije postati frozen baseline za budući R1/F8; novi frozen baseline nastaje u novom F4.

## 2. Prvi pokušaj i sigurnosni kod

Prethodni ID ostaje **`20261115t130331z`**. `cutstate.load` provjerio je lanac: **ROLLED_BACK**, 9 zapisa, tip `c25c344676e5145e9b9cf23a5f74ed40410a5d695adc43a68593e29b3ccb85da`; `T_open` ne postoji.

Ponovno izračunati hashovi **107 datoteka** iz snimke dokumenta 40 (prethodni dokazi, dumpovi, `/home` kopije, konfiguracija i datoteka ključeva): **0 razlika**. `lb_verify` za prethodni ID: **OK**, originali i kopije aplikacijskog backupa te oba dumpa jednaki manifestima. Prethodni žurnal i dokazi nisu mijenjani. Stari dumpovi ostaju arhiva prvog pokušaja.

**29 izvornih datoteka** alata uspoređeno sa završnim hashovima dokumenta 40: **0 razlika**; `bash -n` prolazi. Pregled potvrđuje:

- Izričitu propagaciju grešaka umjesto oslanjanja na `set -e`, uključujući R1 stop/inspect, SQL/ACL, recreate, health, API i zapis završnog stanja.
- Oba ključa, puni API uzorak i novu strojno provjerenu potvrdu Q1–Q10 prije uspješnog F8.
- `dark-verified.json` s identitetom i hashovima dokaza; provjeru potvrde i G14 u F10 prije promjena.
- Zaštitu dumpova od prepisivanja, provjeru hashova/TOC-a i pohrane žurnala.

Dokazi testiranja iz 40 ostaju primjenjivi: 352/352 sigurnosne provjere, offline selftest PASS i završni rehearsal review 18/18. Nisu ponovno pokretani mutirajući koraci ni rehearsal u ovoj pripremi; kod je identičan provjerenoj inačici.

## 3. Predloženi novi identitet

| Namjena | Predložena vrijednost |
| --- | --- |
| Novi `CUTOVER_ID` | **`20261115t150714z`** — prijedlog vezan uz početak ove pripreme, nije termin odobrenog prekida. |
| Produkcijski `$EV` | `/opt/stacks/data/backups/immich-cutover-20261115t150714z` |
| Nova druga kopija | `/home/immich-cutover-backups/20261115t150714z/` s poddirektorijima `app-backup/` i kasnije `dumps/`. |
| Privremeni bridge | `immich-cutover-bridge-20261115t150714z`, radni direktorij `/tmp/immich-cutover-20261115t150714z`. |

Sve tri predložene putanje provjerene su kao **nepostojeće**. Nisu stvorene, a novi produkcijski žurnal nije inicijaliziran. Prije budućeg stvaranja ponovno provjeriti nekorišten identitet i odsutnost putanja; pri koliziji odabrati novi ID, bez prepisivanja.

Dokazi **ove pripreme**, odvojeni od budućeg produkcijskog `$EV`, nalaze se u `/opt/stacks/data/backups/immich-second-readiness-20261115t150714z/`. Njegov `checks/immich-cutover-20261115t150714z/` sadrži samo izlaze read-only alata; nije produkcijski žurnal niti dovršeni F0.

Za budući pokušaj `EVROOT` i `EVIDENCE_ROOT` moraju oba pokazivati na `/opt/stacks/data/backups`, a `$EV` izravno pod tim direktorijem zbog target mounta `/backups`. Ne naslijediti readiness `EVIDENCE_ROOT` iz ove provjere. Svi markeri, potvrde i budući dumpovi moraju pripadati novom ID-u.

## 4. Postojeći cilj i plan ponovne pripreme — NIJE IZVRŠENO

`immich-db` je healthy, PG **16.16**, 0 restartova, isti `StartedAt=2026-11-15T13:19:51.520224608Z`. Na mreži je samo `postgis`, nema objavljenih portova; mountovi su vlastiti PGDATA i `/backups`.

Baza `immich` ima **72 tablice, 57.627 asseta**, približno **1,04 GB**, vlasnika `immich`, UTF8 i `en_US.utf8`. Postoje samo netemplate baze `postgres` i `immich`. Instalirano je očekivanih osam ekstenzija; PostGIS nije dostupan. **0 drugih veza** na ciljnu bazu tijekom provjere.

Rola `immich` već postoji, LOGIN, bez povišenih ovlasti. Dodatna samo čitajuća provjera prijave preko mrežne adrese prošla je s lozinkom iz okoline produkcijskog servera; pogrešna lozinka odbačena je s rc 2 i potvrđenom porukom autentikacijske greške. Lozinke ostaju samo u memoriji procesa.

Najsigurniji dokumentirani plan iz 17 §6:

1. **Zasebno odobrenje vlasnika** za `s_target_reset_after_rollback`, uz novi ID/EV i `PREV_EV=/opt/stacks/data/backups/immich-cutover-20261115t130331z`. Ponovno potvrditi stari `ROLLED_BACK`, aktualni server/`.env` na izvoru, odsutnost ciljnih klijenata i slobodno arhivsko ime. Sačuvati popis baza, brojke i identitet cilja kao novi dokaz prije radnje.
2. Koristiti postojeću funkciju, bez brisanja kontejnera, PGDATA ili baze. Funkcija prekida veze na ciljnu `immich`, **preimenuje je** i stvara novu praznu `immich`; produkcijski `postgis/immich` nije predmet tih SQL naredbi. Ako se pojave neočekivani klijenti, HALT prije radnje.
3. S predloženim ID-om postojeći kod daje arhivsko ime **`immich_failed_20261115t150714z_`** (završna donja crta proizlazi iz postojeće funkcije). Zabilježiti da ta arhiva sadrži podatke **prvog** pokušaja; postojeće ime trenutno je slobodno. Ne mijenjati ime ručnim SQL-om mimo odobrenog postupka.
4. Nakon uspješnog reseta dokazati: arhiva postoji i očuvala je prethodne brojke; nova `immich` ima 0 aplikacijskih tablica, odgovarajućeg vlasnika/encoding/collation; rola i pozitivna/negativna SCRAM kontrola ispravne; image/mountovi/mreža ostali isti. Ponoviti `target-ready` i backup provjere prije F4.
5. Pri djelomičnoj SQL grešci HALT: arhiviranje i stvaranje nisu jedna transakcija; moguća je sačuvana arhiva bez nove baze. Ne ponavljati funkciju naslijepo niti improvizirati oporavak.

**Operativna prepreka za izravno ponavljanje F1/F2:** `s_prepare_target` bezuvjetno izvodi `CREATE ROLE immich` i `CREATE DATABASE immich`, pa ne smije slijediti reset postojeće role. Njegov se očekivani neuspjeh ne smije zanemariti. `s_target_reset_after_rollback` sam ne zapisuje `PREPARED`; novo stanje ostaje `NONE` dok se cilj ne potvrdi. `s_freeze` tehnički prihvaća i `NONE`, ali to nije razlog za preskakanje provjera.

Prije izvršenja odobriti konkretan F2 postupak za **ponovnu uporabu postojeće role**: dokumentirani reset + sve navedene read-only provjere + tek potom početni zapis `PREPARED` u **novi** žurnal provjerenim `cutstate.py`. Ne pokretati originalni F2 s duplikatom role, ne mijenjati stari žurnal i ne tretirati puki reset kao dokaz spremnosti. Izvršni driver za taj odobreni slijed treba pripremiti/provjeriti prije prozora; ovom uputom nije odobreno njegovo izvršenje niti izmjena koda.

Sačuvana arhiva nije izvor podataka za drugi restore. F7 smije koristiti isključivo novi sanitizirani dump nastao iz novog frozen izvora.

## 5. Backup i novi F0

- Postoji **14** aplikacijskih `.sql.gz` backupova, od toga **12** za v3.3.5; različiti brojevi nisu gubitak dviju datoteka nego dva starija v2.6.3 backupa.
- Najnoviji odgovarajući backup: `immich-db-backup-20261115T020000-v3.3.5-pg16.13.sql.gz`, **355.181.926 B**, mtime **01:00:47 UTC**, star oko **14,1 h** pri provjeri. Naziv koristi lokalno vrijeme.
- SHA-256: `25b7780f666822c99bc8bcfc50d3e9c5851f203f29d7149b65d429821d73b0fd`; `gzip -t` PASS u preflightu. To je još uvijek isti najnoviji aplikacijski backup, što ne dopušta preuzimanje starih migracijskih dumpova.
- `lb_check` OK: RAID1 zdrav, NVMe provjere prolaze, slobodno približno **421 GiB na /** i **1453 GiB na /home**; zasebni filesystemi, isti fizički host.

Novi F0, **tek nakon zasebnog odobrenja**, koristi `lb_copy_app_backup`: izvor je najnoviji odgovarajući `.sql.gz` **iz aplikacijskog direktorija** `/opt/stacks/immich/docker-data/library/backups/`, odabran u trenutku izvođenja po mtime. Provjerava dob <26 h, gzip, slobodan prostor i nepostojeće odredište, zatim kopira u **novi** `/home/.../<novi-ID>/app-backup`, postavlja nove markere/manifeste, uspoređuje SHA-256 i izvršava se `lb_verify`. Usko odobrenje za taj budući F0 je `LB_BACKUP_ONLY_APPROVED=F0:20261115t150714z`; danas nije postavljeno. `CUTOVER_APPROVED` nije potreban za F0 i nije postavljen.

Ako do izvođenja stigne noviji aplikacijski backup, kopira se on i bilježi njegov novi hash. Ne kopirati staru `/home` kopiju ili `immich.full.dump` / `immich.no-postgis.dump` prvog pokušaja u novi F0. F0 je zaštitna kopija; **migracijski izvor ostaje živi `postgis/immich`, zamrznut u novom F4**. F5/F6 proizvode nove dumpove, F6b njihove nove kopije. G14 novog ID-a danas je **PENDING**, ne nasljeđuje stari PASS.

Nijedan novi backup nije kopiran u ovoj pripremi.

## 6. F8/F10 i odluke vlasnika

Postojeći API ključevi mogu se ponovno koristiti: učitavanje, minimalne dozvole, trenutačna autentikacija i svih deset API provjera prošli su. Ne trebaju se ponovno stvarati ni mijenjati. Ponoviti učitavanje u pouzdanoj ljusci neposredno prije koraka; greška učitavanja je HALT.

Novi pokušaj koristi ispravljeni kod iz 40 bez zaobilaženja: novi F4 baseline, novi F7 dokazi, nova F8 API potvrda i `dark-verified.json`. F10 zahtijeva **novi** G14 i cjelovit F8 dokaz. Staro `DARK_VERIFIED`, stari API PASS ili stari backup manifest ne mogu odobriti novi F10. Djelomični open i dalje zahtijeva dokumentirani abort/ručni postupak; naknadna health greška ne jamči da ruta još nije bila dostupna.

| Odluka / činjenica | Prijenos na drugi pokušaj |
| --- | --- |
| Arhitektura odvojenog PG 16.16, verzije imageova, ekstenzije, čuvanje izvora i zabrana diranja Redisa | Prenose se kao tehnički plan i sigurnosna ograničenja; aktualni imageovi potvrđeni preflightom. To nije odobrenje novih mutacija. |
| Postojeći ključevi i minimalne dozvole | Prenose se; sada potvrđeni, bez novog kreiranja/rotacije. |
| Lokalna zaštita RAID1 + druga kopija na `/home`, bez off-host kopije | Dokumentirana odluka vlasnika prenosi se kao strategija; isti rizik gubitka hosta ostaje. Novi GO treba referencirati prihvaćeni rizik, a novi G14 mora se stvarno izvršiti. Ne tvrdi se da G6 postaje ispunjen. |
| Izostanak obavijesti korisnicima | Izričita odluka iz 31 može se prenijeti kao postojeća preferencija ako vlasnik ne promijeni zahtjev. Ne predstavlja odobrenje novog prekida. |
| Nema Immich monitora u Kumi | Ponovno potvrđena činjenica, ne odobrenje promjene; generički monitori drugih usluga ostaju uključeni. |
| Recall/latencija i pravila R1/abort iz 17, prihvaćeni minimum recall 0,90 iz 36 | Mogu se predložiti isti kriteriji za istu verziju. Novi GO mora nedvosmisleno navesti važeće pragove; nema automatskog prijenosa iznimke za prekoračenje vremena. |
| Ranije pojedinačno odobreni F0–F8, odobreni R1 i njegov retry | Iscrpljeni su prethodnim pokušajem. **Ne odobravaju novi F0, reset, freeze, restore, dark start ili otvaranje.** |
| Postojeći cilj / arhiviranje i stvaranje prazne baze | Potrebno novo izričito odobrenje za navedeni reset i F2 slijed. Brisanje PGDATA/kontejnera/baze nije predloženo. |
| Termin i prozor prekida | Potrebno novo odobrenje. Pragovi se računaju od **novog T0**: cilj 30 min, odluka na 45, obvezni R1 na 60 prije PONR-a. Stare UTC granice i iznimka prekoračenja 30 min ne prenose se. Danas je nedjelja; termin izvan preporučenog radnog dana zahtijeva izričitu odluku. |
| Retencija ≥7 dana, OIDC osoba i ovlaštena osoba za odluke nakon HALT-a | Za novi prozor jasno zabilježiti važeći rok i odgovorne osobe; u pregledanim završnim izvještajima nema potpunog novog operativnog zapisnika. Raniji R1 nalog nije opća ovlast za prihvaćanje budućeg gubitka podataka. |
| F9/F10 i kanarski testovi | Novo zasebno odobrenje u odgovarajućoj fazi; mutirajući kanarski testovi i njihovo čišćenje nisu uključeni u ovu pripremu. |

## 7. Evidencija, izvršene radnje i završni status

Privatna evidencija: `/opt/stacks/data/backups/immich-second-readiness-20261115t150714z/`: `live-state.json`, `target-login-check.json`, `read-checks.sh`, `preflight.out`, `key-metadata.out`, trenutni API baseline/rezultat, `backup-health.out`, `old-backup-verify.out`, `final-check.json` i izlazi alata u `checks/`.

Ključne provjere: `date -u`, `docker inspect`, `cutstate.load` (stvarno verificiranje hash lanca), SHA-256 datoteka, READ ONLY SQL nad izvorom/ciljem, mrežna SCRAM provjera SELECT-om, GET javnog URL-a, `keys_load` / `keys_verify_meta`, `preflight.py --phase target-ready`, `api_checks.py baseline/verify/check-result`, `lb_check`, read-only `lb_verify` prethodnog ID-a i SQLite `-readonly` nad monitoringom. Pametno pretraživanje koristi nemutirajući `POST /search/smart`; nema mutirajućih API operacija.

Proces read-only provjera završio je **rc 0**. Završna usporedba u **15:10:27 UTC**: nema promjene Id/StartedAt/restart count osam pregledanih kontejnera, nema promjene 107 prethodno provjerenih datoteka. Pisani su samo novi dokazi pripreme i ovaj dokument. Nisu postavljeni operativni tokeni, pokrenuti cutover/reset/rollback, zaustavljeni ili restartani kontejneri, mijenjani SQL podaci/`.env`/Compose/Redis/ključevi, kopirani backupovi ni mijenjani stari žurnal/dokazi.

**Sljedeći siguran korak je odobriti novi F0 i konkretni plan očuvanja/pripreme postojećeg cilja, zatim novi operativni prozor i opseg izvršenja. Ovdje stajem bez izvršenja plana.**
