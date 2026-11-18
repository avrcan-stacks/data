# 39 — Immich: R1 uspješno završen

Datum: 15. studenoga 2026. · `CUTOVER_ID=20261115t130331z`.

**Immich je vraćen na `postgis/immich` i javno dostupan (HTTP 200).** Dokumentirani `s_rollback_r1` završio je s **rc 0** u **14:26:50 UTC**; žurnal je **`ROLLED_BACK`**, hash lanac valjan. Završne provjere prošle su u **14:27:05 UTC**. Ovaj rezultat zamjenjuje trenutačni HALT iz dokumenta [38](38-immich-cutover-rollback-r1.md), uz očuvanu povijest prvog pokušaja.

## Vrijeme i opseg

| Događaj | UTC | Od T0=13:33:40Z |
| --- | --- | --- |
| Prvi `date -u` nakon novog odobrenja | 14:24:20 | 50 min 40 s |
| Aktualni precheck | 14:25:40 | 52 min |
| Početak R1 | 14:25:58 | 52 min 18 s |
| Završetak R1 / API PASS / `ROLLED_BACK` | 14:26:50 | 53 min 10 s |
| Završne provjere dostupnosti i očuvanosti | 14:27:05 | 53 min 25 s |

Sam R1 trajao je **52 s**. Završio je prije praga obveznog R1 **14:33:40 UTC**. Sva vremena su UTC (Europe/Zagreb: UTC+1).

Izvršen je samo postojeći postupak R1: zaustavljanje dark servera, dokumentirani `s_unfence` i točna usporedba ACL-a, recreate servera iz baznog Composea bez ovisnosti/builda/pulla, start pomoćnih kontejnera, nastavak redova, API baseline i zapis završnog stanja. F9/F10 i novi pokušaj migracije nisu pokrenuti. Nisu mijenjani `.env`, CUTOVER_ID ili podaci alternativnim SQL postupkom; Redis nije restartan. Nema brisanja baza, dumpova ili backupova.

## Ispravak i zaštita izvršenja

U privatnom `$EV/r1-precheck.py` upit sada koristi:

```sql
SELECT to_json(has_database_privilege('immich','immich','CONNECT'));
```

Parser poziva `json.loads` i zahtijeva `type(value) is bool`; uvjet za zaštićeni izvor je isključivo `value is False`. `true` je valjan odgovor, ali ne prolazi provjeru zaštite izvora. Prazan odgovor, neispravan JSON, `null`, broj, string i lista odbijaju se iznimkom. SQL se izvršava postojećim `cutlib.psql` u READ ONLY transakciji uz `ON_ERROR_STOP=1` i provjeru povratnog koda; SQL pogreška ne postaje PASS.

**8/8 parser testova PASS**: `true`, `false`, prazan odgovor, `invalid`, `null`, `0`, `"false"`, `[]`. Testovi su izolirano izveli istu parser funkciju iz stvarne skripte, bez pristupa bazama. Prethodna inačica skripte je sačuvana.

Prema zahtjevu za izričitom provjerom povratnih kodova, postojeći R1 u `steps.sh` dodatno je zaštićen: obavezni stop/inspect, odmrzavanje i usporedba ACL-a, recreate, healthcheck, labela rute, DB hostname, start svakog pomoćnog kontejnera, nastavak redova, API baseline i zapis `ROLLED_BACK` prekidaju korak s nenultim kodom pri grešci. `s_unfence` izričito provjerava rezultat SQL-a i usporedbe ACL-a. Redoslijed operacija i SQL ostali su dokumentirani R1, bez alternativnog rollbacka. `bash -n` i četiri izolirana testa grešaka stopa/ACL-a/recreatea/healthchecka prolaze.

Poziv je izvršen samostalno u novom `/bin/bash --noprofile --norc` procesu s `set -Eeuo pipefail` i ERR trapom; nema uvjetnog ili `eval` wrappera oko poziva. `CUTOVER_APPROVED` nije globalno izvožen, nego postavljen samo uz:

```bash
CUTOVER_APPROVED="$CUTOVER_ID" s_rollback_r1
```

Oba API ključa učitana su postojećim `keys_env.sh` / `keys_load`, bez ispisa vrijednosti. `R1_SKIP_VERIFY` i `CUTOVER_REHEARSAL` nisu korišteni.

## Aktualne provjere prije R1

Sve su prošle prije prve produkcijske mutacije:

| Provjera | Rezultat |
| --- | --- |
| Žurnal i dopuštenost R1 | `DARK_VERIFIED`, 8 zapisa, valjan lanac, stanje u `ROLLBACK_OK`. |
| `T_open`, `.env` | `T_open` ne postoji; jedan `DB_HOSTNAME=postgis`. |
| Dark server | Healthy, `immich-db`, API-only, `traefik.enable=false`; pomoćni servisi zaustavljeni. |
| Javna ruta | Nema uključene Docker/static Immich rute; origin GET ping vraća 404. |
| Izvor | 0 drugih klijenata; CONNECT za `immich` = JSON `false`. |
| Izvor nepromijenjen | Živa sonda prema frozen A: bez restarta, reseta, promjene skupa tablica, brojača ili sekvenci; svih 72 aktualna hasha tablica jednaka frozen snapshotu `src`. |
| Cilj bez novih zapisa | Živa sonda prema dark baselineu: nema promjena izvan startup allow-liste ni pomaka sekvenci; svih 72 aktualna hasha tablica jednaka `dst2`. |
| Mediji | Nema datoteka korisničkog uploada s `ctime` poslije T0; oznaka `.immich` izuzeta kao u službenom postupku. |
| Ključevi i dokazi | Oba ključa učitana; frozen API baseline i ACL dokaz postoje. |
| Redis | Izvorni `StartedAt=2026-06-26T21:46:10.698303676Z`, 0 restartova. |
| Dumpovi | Oba dumpa postoje, zabilježeni SHA-256. |

## Potvrda uspjeha

| Uvjet | Stvarni rezultat |
| --- | --- |
| Žurnal | **`ROLLED_BACK`**, seq 9, `cutstate.py verify` PASS. |
| Server | Healthy; `DB_HOSTNAME=postgis`; standardni workeri iz baznog Composea. Novi `StartedAt=14:26:00.473278425Z`. |
| Javna dostupnost | **HTTP 200** za `/` i `/api/server/ping`, i preko javnog DNS-a i preko lokalnog Traefik origin-a s `--resolve`. |
| API baseline | **PASS, 0 FAIL / 0 WARN**; Q1–Q10 prolaze, statistike, 8 knjižnica, albumi i 792 osobe identični baselineu. Smart search overlap 1,00, warm p95 289 ms, cold max 447 ms. |
| Redovi | Resume svih 19 redova: svaki HTTP 200; Q5 potvrđuje da nijedan nije ostao pauziran. Failed jobs ne rastu; poznati `facialRecognition=1`. |
| Bridge i media-operations | Oba **running, healthy**. |
| Redis | Nije restartan: isti `StartedAt`, restart count 0. |
| Izvorni podaci | 72 hasha prije R1 identična frozen snapshotu; nakon R1 API sadržaj identičan baselineu, izvor ima **57.627 asseta**. |
| ACL i `.env` | ACL bajt-u-bajt jednak `source-db-acl.before`; `.env` SHA-256 ostaje `20ef9f32a7e618fa837f4fa64254c77816b99c2940798fd6221f2956fc966579`. |
| Nova baza | `immich-db` sačuvan, radi; isti `StartedAt=13:19:51.520224608Z`, **57.627 asseta**. |
| Dumpovi i backupovi | Oba dumpa nepromijenjena. SHA-256 provjeren za originale i `/home` kopije oba dumpa te F0 aplikacijskog backupa; sve PASS. |

Sačuvani dumpovi:

- `immich.full.dump`: 354.261.789 B; SHA-256 `243e383091cbe1281aae163850f6688b04ab354469f36b90de5f79990bad5018`.
- `immich.no-postgis.dump`: 354.050.055 B; SHA-256 `3a85087152e0344b5e405975a8e3366aade5da315246307972dac5eba45061dd`.

## Evidencija

Privatni direktorij: `/opt/stacks/data/backups/immich-cutover-20261115t130331z/`.

- `r1-parser-tests.json`: svih 8 parser testova.
- `r1-precheck.before-parser-fix.py`: prethodna inačica pripremne skripte.
- `r1-precheck.py`, `r1-run.sh`, `r1-precheck.json`: stvarni kod i svi rezultati prechecka.
- `r1-retry-execution.out`: točne izvršene operacije i izlazi, `R1_START`, API PASS, `s_rollback_r1 OK`, `R1_END`, `ROLLED_BACK`; povratni kod procesa **0**.
- `api-verify-20261115T142650.json`: API dokaz iz samog R1.
- `r1-postcheck.py`, `r1-postcheck.out`, `r1-postcheck.json`: samo čitajuće završne provjere; proces **rc 0**, ukupno **PASS** u 14:27:05Z.
- `state.log`, `state`, `source-db-acl.after`: valjan završni žurnal i vraćeni ACL.

Ključne naredbe:

```bash
date -u '+%FT%TZ'
bash -n immich-cutover/steps.sh
/bin/bash --noprofile --norc /opt/stacks/data/backups/immich-cutover-20261115t130331z/r1-run.sh \
  > /opt/stacks/data/backups/immich-cutover-20261115t130331z/r1-retry-execution.out 2>&1
PYTHONDONTWRITEBYTECODE=1 python3 -B backups/immich-cutover-20261115t130331z/r1-postcheck.py \
  > backups/immich-cutover-20261115t130331z/r1-postcheck.out 2>&1
python3 -I immich-cutover/cutstate.py verify backups/immich-cutover-20261115t130331z
```

**R1 završen. Immich dostupan. Stajem bez nastavka migracije.**
