# 38 — Immich produkcijski cutover: R1 zaustavljen prije izvršenja

Datum: 15. studenoga 2026. · `CUTOVER_ID=20261115t130331z`.

**Naknadni rezultat:** nakon novog odobrenja vlasnika parser je ispravljen i R1 je uspješno završen u 14:26:50 UTC. Žurnal je `ROLLED_BACK`, Immich javno vraća HTTP 200. Vidi [39 — konačni rezultat](39-immich-r1-result.md). Tekst ispod čuva prvi, zaustavljeni pokušaj.

**Ishod: HALT u pripremnoj provjeri. `s_rollback_r1` nije pozvan. Immich nije vraćen na izvor; javni promet ostaje zatvoren.** Žurnal nije mijenjan i ostaje `DARK_VERIFIED`, što nije završno rollback stanje `ROLLED_BACK`.

## Odobrenje i postupak

Vlasnik je odobrio isključivo dokumentirani R1 iz dokumenata 17 (§6) i 20 (§1.1), koji su ponovno pročitani. F9/F10, novo pokretanje migracije, brisanje baze ili backupova i restart Redisa nisu odobreni niti izvršeni.

Pregled `_r1_core` otkrio je ignoriranje greške zaustavljanja servera (`docker stop … || true`). U `immich-cutover/steps.sh` uklonjeno je ignoriranje greške i dodana obavezna provjera `.State.Running=false` prije `s_unfence`. Drugih promjena rollback postupka, SQL-a ili Compose naredbi nema. `bash -n` prolazi. Četiri izolirana testa s nadomještenim funkcijama potvrdila su prekid kod greške stopa (rc 9), odmrzavanja (rc 8), recreatea (rc 7) i healthchecka (rc 1), prije kasnijih operacija. Testovi nisu pristupali produkciji.

Pripremljen je zaseban `/bin/bash --noprofile --norc` proces s `set -Eeuo pipefail` i ERR trapom. Poziv R1 nije u `&&`, `||`, `if` ili `eval` kontekstu. `CUTOVER_APPROVED` bio bi postavljen samo kao privremena dodjela uz `s_rollback_r1`, na točan ID; zbog ranijeg HALT-a ta naredba nije dosegnuta.

## Vrijeme

- Prvi `date -u`: **14:19:52Z**, T0 + **46 min 12 s**.
- Početak pripremne provjere: **14:21:19Z**, T0 + **47 min 39 s**.
- Proces je stao s **rc 1**, nakon približno **0,41 s**. Oznaka `R1_START` nije dosegnuta; trajanje samog rollbacka: nije izvršen.
- Završna provjera stvarnog stanja: **14:21:53Z**, T0 + **48 min 13 s**.
- Sve oznake vremena su UTC; lokalno Europe/Zagreb je UTC+1.

## Provjere i stanje prije/poslije pokušaja

| Provjera | Rezultat |
| --- | --- |
| Hash lanac i stanje | PASS: 8 zapisa, `DARK_VERIFIED`; ponovno `cutstate.py verify` nakon HALT-a potvrđuje isto stanje. |
| Dopuštenost R1 | PASS prema `ROLLBACK_OK` postojećeg `cutstate.py`; stanje `DARK_VERIFIED`. R1 nije izvršen. |
| `T_open` | PASS: ne postoji prije ni poslije. |
| `.env` | PASS: jedan `DB_HOSTNAME=postgis`; SHA-256 `20ef9f32a7e618fa837f4fa64254c77816b99c2940798fd6221f2956fc966579`, jednak prethodnom preuzimanju migracije. |
| Server | Healthy, API-only, `DB_HOSTNAME=immich-db`, `IMMICH_WORKERS_INCLUDE=api`, `traefik.enable=false`; nepromijenjen `StartedAt=14:07:55Z`. |
| Javna ruta | PASS za zatvoren promet: nema uključene Docker rute ni statičke Immich rute; GET `https://media.finestar.hr/api/server/ping` uz `--resolve media.finestar.hr:443:127.0.0.1` vraća **404**. HTTP 200 nakon rollbacka nije ostvaren. |
| Veze na izvor | PASS: 0 drugih veza na `postgis/immich` prije pokušaja. |
| CONNECT na izvoru | Pripremni program pao pri parsiranju rezultata. Naknadna samo čitajuća dijagnostika s ispravnim JSON rezultatom potvrđuje `false`: izvor i dalje zaštićen. Nije nastavljen rollback. |
| Izvor nepromijenjen | Naknadna živa sonda prema `write-probe-frozen-A.json`: isti postmaster, reset statistike, skup tablica i sekvence; nema promjena brojača ni jedne tablice. **57.627 asseta**. |
| Korisnički zapisi na cilju | Naknadna živa sonda prema `write-probe-dark.json`: isti postmaster, reset statistike, tablice i sekvence; nema promjena izvan dopuštenih `system_metadata,version_history,plugin,plugin_method`. **57.627 asseta**. Planirana nova provjera 72 hasha nije dosegnuta. |
| API ključevi | PASS: oba učitana postojećim `keys_env.sh` / `keys_load`; vrijednosti nisu ispisane. |
| API baseline nakon R1 | Nije izvršen: R1 nije započeo. Prethodni F8 dokaz u `f8-api-verify.out` ostaje povijesni PASS, ne dokaz rollbacka. |
| Bridge i media-operations | I dalje zaustavljeni (`exited`); nisu pokrenuti. |
| Redis | Healthy, 0 restartova, `StartedAt=2026-06-26T21:46:10.698303676Z`, nepromijenjen. |
| Ciljni PostgreSQL | `immich-db` healthy, 0 restartova, `StartedAt=2026-11-15T13:19:51.520224608Z`; sačuvan. |
| Dumpovi | Oba postoje, ponovno izračunati SHA-256; ništa nije obrisano. |
| Završno rollback stanje | **Nije postignuto**: žurnal ostaje `DARK_VERIFIED`, a ne `ROLLED_BACK`. |

## Točan uzrok HALT-a

Pogreška je u novom pripremnom programu, ne u dokazu da je produkcijski sigurnosni uvjet prekršen:

```text
check('source fenced', not pj('postgis',
    "SELECT has_database_privilege('immich','immich','CONNECT');"))
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
HALT rc=1 line=11 function=main
```

`pj()` očekuje JSON, a `psql` za taj boolean upit vraća `f`. Naknadna dijagnostika koristila je `SELECT to_json(has_database_privilege('immich','immich','CONNECT'));` i dobila JSON `false`. To nije korišteno za ponovni pokušaj R1. Po vlasnikovoj uputi nakon neuspjele provjere postupak je zaustavljen; nije izvedena nijedna mutirajuća SQL ili Docker operacija.

## Evidencija i naredbe

Privatna evidencija: `/opt/stacks/data/backups/immich-cutover-20261115t130331z/`:

- `r1-precheck.py`, `r1-run.sh`: točno pripremljeni program i driver; bez tajni.
- `r1-execution.out`: izlaz provjera i potpuna pogreška, rc procesa **1**.
- `r1-precheck-failed.json`: dovršene provjere i pogreška.
- `r1-halt-state.json`: naknadno očitano stanje, sonde, veličine i SHA-256 dumpova.

Ključne izvršene naredbe:

```bash
date -u '+%FT%TZ'
bash -n immich-cutover/steps.sh
/bin/bash --noprofile --norc /opt/stacks/data/backups/immich-cutover-20261115t130331z/r1-run.sh \
  > /opt/stacks/data/backups/immich-cutover-20261115t130331z/r1-execution.out 2>&1
python3 -I immich-cutover/cutstate.py verify backups/immich-cutover-20261115t130331z
```

Unutar drivera dosegnuti su `keys_load` i samo čitajuća pripremna provjera; `source steps.sh` i `CUTOVER_APPROVED="$CUTOVER_ID" s_rollback_r1` nisu dosegnuti. Naknadni SQL upiti izvršeni su postojećim `cutlib.pj` u READ ONLY transakcijama; `docker inspect`, GET javnog ruba i čitanje/hashiranje datoteka ne mijenjaju produkciju.

**Stajem u HALT-u. Potrebna je nova uputa za ispravak pripremnog parsera i ponovni pokušaj dokumentiranog R1.** Prag 60 minuta iz runbooka je 14:33:40Z; ovim HALT-om nije ukinut, ali ne nadjačava vlasnikovu zabranu nastavka nakon neuspjele provjere.
