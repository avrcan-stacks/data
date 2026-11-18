# 43 — Immich drugi pokušaj: kontrolirani target reset

Datum: 15. studenoga 2026., UTC. Novi ID **`20261115t150714z`**; prethodni **`20261115t130331z`**.

**Odobreni SQL reset izvršen je jednom, rc 0.** Postojeća ciljna baza sačuvana je kao **`immich_failed_20261115t150714z_`**; nova `immich` je prazna. Produkcijski Immich ostaje na `postgis`, HTTP **200**. Novi žurnal ostaje **NONE**. **F2 i zamrzavanje nisu pokrenuti.**

**Odstupanje validacije:** prva završna skripta stala je s **rc 1** na usporedbi kontejnera `postgis`. Sve mutacije tada su zaustavljene. Zasebna samo čitajuća dijagnostika reproducirala je pogrešku usporedbe redoslijeda mountova, a završni read-only audit prošao je **25/25** provjera. Prvi FAIL nije izbrisan niti preoznačen; detalji su u odjeljku 5.

## 1. Odobrenje i precheck

Pročitani dokumenti [17](17-immich-production-cutover.md), [20](20-immich-cutover-safety.md), [39](39-immich-r1-result.md), [40](40-immich-cutover-safety-hardening.md), [41](41-immich-second-attempt-readiness.md) i [42](42-immich-second-attempt-f0.md). Pregledane stvarne funkcije `s_target_reset_after_rollback`, `_gate`, `_state_in` i `_sql`.

Prvi sat: **15:49:11 UTC**. Precheck: **37/37 PASS, rc 0**, prije prve mutacije:

| Uvjet | Dokaz |
| --- | --- |
| Putanje i identiteti | Novi i stari `$EV`, novi `/home` direktorij i PGDATA postoje, odgovaraju kanonskim putanjama; ni oni ni njihove nadređene komponente nisu symlinkovi. Novi markeri točno `20261115t150714z`. |
| Stari žurnal | Valjan hash lanac, **ROLLED_BACK**, 9 zapisa, tip `c25c344676e5145e9b9cf23a5f74ed40410a5d695adc43a68593e29b3ccb85da`. |
| Novi žurnal | **NONE**; nema `state` ni `state.log`. |
| F0 | Originalni i kopijski manifest postoje i strukturno su valjani; `lb_verify` za novi ID **rc 0 / OK**. |
| Produkcija | Server healthy na `postgis/immich`; bridge i media-operations healthy; javni `/` i `/api/server/ping` HTTP 200. |
| Redis | Healthy, restart count 0, izvorni StartedAt `2026-06-26T21:46:10.698303676Z`. |
| Cilj | Healthy, StartedAt `13:19:51.520224608Z`, 0 restartova; produkcijski server i media-operations konfigurirani na izvor, ne cilj. |
| Ciljni podaci | PG 16.16, **72 tablice, 57.627 asseta**, očekivanih 8 ekstenzija, vlasnik `immich`, UTF8 i `en_US.utf8`. |
| Ciljni klijenti | **0**, i prije i nakon read-only snapshota; ponovno provjereno neposredno pred poziv. |
| Arhivsko ime | Izračunato istim izrazom `echo "$CUTOVER_ID"` / `tr -c`: **`immich_failed_20261115t150714z_`**. Siguran identifikator, ime slobodno. Završna donja crta odgovara dokumentu 41. |
| PGDATA/mountovi | `PGDATA=/var/lib/postgresql/data`; bind `/opt/stacks/data/immich-postgres/data` → PGDATA i `/opt/stacks/data/backups` → `/backups`; samo mreža `postgis`, bez objavljenog porta. |
| Stari dokazi i konfiguracija | Hashovi prethodnih dokaza i `.env`/Compose datoteka identični referentnoj snimci. |
| Funkcija i opseg | Hardened `steps.sh` hashom nepromijenjen; funkcija koristi samo prekid ciljnih veza, `ALTER DATABASE ... RENAME` i `CREATE DATABASE ... TEMPLATE template0`; nema DROP DATABASE, brisanja PGDATA, Docker lifecycle naredbi ili zapisa PREPARED. |

Snimljen je novi read-only snapshot cilja: **72 hasha tablica, 1.080.428 redaka ukupno**, potpuni metapodaci i sekvence. Snimljena je stroga sonda pisanja bez allow-liste. Sadržaj redaka i tajne nisu zapisivani, samo hashovi/brojači/metapodaci.

## 2. Izvršena operacija

U svježoj `/bin/bash --noprofile --norc` ljusci, uz `set -Eeuo pipefail`, provjerene identifikatore i EXIT trap. Odobrenje nije globalno izvoženo; jedini mutirajući poziv:

```bash
CUTOVER_APPROVED="$CUTOVER_ID" s_target_reset_after_rollback
```

Postavljeni zaključani argumenti: `CUTOVER_ID=20261115t150714z`, `PG_NEW=immich-db`, novi `$EV`, `PREV_EV=/opt/stacks/data/backups/immich-cutover-20261115t130331z`. Nema uvjetnog/eval wrappera oko poziva. Nije pozvan `s_prepare_target`.

Stvarni izlaz u **15:52:56 UTC**, trajanje cijelog drivera oko **0,29 s** (početak/kraj unutar iste sekunde):

```text
Immediate read-only guard PASS
RESET_START 2026-11-15T15:52:56Z
pg_terminate_backend: (0 rows)
ALTER DATABASE
CREATE DATABASE
target database renamed, empty immich created
RESET_RC=0
CUTOVER_APPROVED_ABSENT
RESET_END 2026-11-15T15:52:56Z
```

Nije bilo djelomične SQL greške, ponavljanja reseta ni alternativnog SQL-a. Nije prekinuta nijedna klijentska veza jer ih nije bilo. Nakon povratka funkcije potvrđena je odsutnost `CUTOVER_APPROVED`; trap ga također uklanja na izlazu.

## 3. Očuvanost arhive i prazna nova baza

| Provjera | Stvarni rezultat |
| --- | --- |
| Arhivsko ime | **`immich_failed_20261115t150714z_`** |
| Identitet arhive | Isti PostgreSQL database OID **16385** kao izvorna ciljna `immich`; izvršeno je preimenovanje, ne restore ili kopiranje redaka. |
| Podaci | **72 tablice, 57.627 asseta**; svih **72 hasha tablica**, potpuni metapodaci i sve sekvence **točno jednaki** snimci prije reseta. |
| Vlasnik i ACL arhive | Vlasnik `immich`; raw ACL **`{immich=CTc/immich,=Tc/immich}`**, identičan prije reseta; UTF8 i locale nepromijenjeni. |
| Ekstenzije arhive | Iste: plpgsql 1.0, cube 1.5, earthdistance 1.2, pg_trgm 1.6, unaccent 1.1, uuid-ossp 1.1, vector 0.8.2, vchord 1.1.1. |
| Nema pisanja u arhivu | Stroga sonda prije/poslije i kroz završni audit: **PASS C0–C5**, isti postmaster/reset statistike, isti skup tablica, nijedan insert/update/delete brojač ni sekvenca pomaknuti. |
| Nova baza | `immich`, novi OID **129819**, vlasnik `immich`, PG **16.16**, UTF8, collate/ctype **en_US.utf8**. |
| Praznina nove baze | **0 korisničkih tablica, 0 relacija u public**, samo `plpgsql 1.0` iz template0. Nema aplikacijskih tablica/podataka prvog pokušaja. |
| Rola `immich` | Isti OID i atributi prije/poslije; LOGIN, bez SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS. Nema CREATE/ALTER ROLE. |
| Pozitivni SCRAM | Mrežna prijava postojećom aplikacijskom lozinkom i `BEGIN READ ONLY; SELECT current_user; ROLLBACK`: **rc 0**, `immich`. |
| Negativni SCRAM | Pogrešna lozinka: **rc 2**, potvrđena poruka `password authentication failed`; nije samo proizvoljna Docker/mrežna greška. |

Lozinka je uzeta iz okoline postojećeg aplikacijskog kontejnera u memoriju i proslijeđena preko procesne okoline; nije ispisana ni spremljena u evidenciju.

## 4. Produkcija, backupovi i žurnali

Završni read-only audit u **15:55:18 UTC**:

- Svih **8 kontejnera** ostalo je istog Id/StartedAt/restart count/Running stanja, image/config hasha, mreža i sadržaja mountova. Server, bridge, media-operations, Redis i baze healthy; Traefik running.
- Immich i dalje **`postgis/immich`**; oba javna URL-a **HTTP 200**. Redis nije restartan. `postgis` i `immich-db` nisu restartani/recreateani.
- **130 zaštićenih datoteka** (stari dokazi i kopije, novi F0, konfiguracija i Traefik datoteke): hashovi prije/poslije jednaki.
- Prethodni žurnal: **ROLLED_BACK**, isti hash tip i 9 zapisa. Novi žurnal: **NONE**, nema `state`/`state.log` i **nije upisan PREPARED**.

Jedina promjena baze bila je odobreno preimenovanje i stvaranje prazne baze unutar `immich-db`. Nisu mijenjani produkcijski `.env`, Compose, Traefik ili Redis; nisu pokrenuti freeze, F2, restore, F4–F10, commit, push ili PR. Ništa nije obrisano i stari dumpovi nisu ponovno korišteni.

## 5. Zabilježeno odstupanje provjere — bez prikrivanja

Prva `postcheck.py` završila je s **rc 1** nakon **12 PASS i 1 FAIL** na složenoj tvrdnji `container unchanged postgis`. Do te točke već su prošle arhivske hash/metadata/sequence i write-probe provjere, praznina nove baze, očuvanost role i obje SCRAM kontrole. Ta skripta zato nije proglašena uspješnom i nema njezinog završnog `postcheck.json`.

Nakon HALT-a nije izvedena nijedna mutacija. Zasebna read-only dijagnostika pokazala je da Docker inspect povremeno mijenja **redoslijed** elemenata `Mounts`, bez promjene bilo kojeg mounta. Ista greška za `postgis` reproducirana je u **6 read-only očitanja**: jedino `mounts_raw` bilo je false; Id, start, restart count, running/health, konfiguracija, mreže i sortirani sadržaj mountova svi true. Pojava je potvrđena i na drugim kontejnerima.

Problem je u mojoj novoj pripremnoj provjeri koja je mountove usporedila kao uređenu listu. Originalna skripta, njezin rc 1 i FAIL ostaju sačuvani. Nisu mijenjani produkcijski mountovi niti izvršni `steps.sh`. Neovisni `final-read-audit.py` usporedio je isti **potpuni sadržaj** mountova kanonski, dovršio preostale provjere i završio **rc 0, 25/25 PASS**, uz status `PASS_WITH_RECORDED_VALIDATOR_DEVIATION` i izričitu evidenciju prvog neuspjeha.

## 6. Granica prije F2 i dokazi

**Nastavak F2 nije odobren.** Rola `immich` već postoji pa originalni `s_prepare_target` i dalje nije prikladan: bezuvjetno bi ponovio CREATE ROLE. Zaseban sljedeći korak mora pripremiti i verificirati F2 za postojeću rolu te tek nakon odobrenja zapisati novi PREPARED. Sam reset to nije učinio. Buduće provjere mountova moraju koristiti kanonsku usporedbu sadržaja. G14 još čeka nove dumpove i F6b; ovaj reset ne odobrava freeze, restore ili otvaranje.

Privatna evidencija: `/opt/stacks/data/backups/immich-cutover-20261115t150714z/target-reset-20261115t154945z` unutar novog `$EV`:

- `precheck.py`, `precheck.out`, `precheck.json`, `f0-verify.out`: 37 preduvjeta i F0 OK.
- `before-snapshot/`, `before-write-probe.json`: stanje cilja prije mutacije.
- `run-reset.sh`, `execution.out`: jedini poziv funkcije, SQL ackovi, rc 0 i uklonjen token.
- `archive-snapshot/`, `archive-write-probe.json`, `archive-write-proof.json`: očuvanost arhive.
- `postcheck.py`, `postcheck.out`, `postcheck-failed.json`: neuspjela prva validacija, sačuvana.
- `halt-container-diagnostic.json`, `mount-order-reproduction.json`, `postgis-mount-order-reproduction.json`: uzrok odstupanja provjere.
- `final-read-audit.py`, `.out`, `.json`, `archive-final-write-probe.json`: dovršena samo čitajuća validacija, rc 0.

**Stajem nakon target reseta i izvještaja. Novi žurnal ostaje NONE. F2 i zamrzavanje nisu pokrenuti.**
