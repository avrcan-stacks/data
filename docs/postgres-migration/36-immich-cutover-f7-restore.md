# 36 — Immich produkcijski cutover: F7 (restore i validacija ciljne baze `immich-db`)

Datum: 15. studenoga 2026. (izvedba 14:03:03–14:04:01 UTC).
**`CUTOVER_ID=20261115t130331z`** · evidencija `/opt/stacks/data/backups/immich-cutover-20261115t130331z` (`f7-restore-validate.out`, `f7-start.txt`, `target.restore.log`, `dst/`, `compare.json`, `validate-target-20261115T140358.json`).
Odobreno: samo F7 (`s_restore_and_validate`). **F8, F9, F10 nisu pokrenuti.** Promet nije otvoren; produkcijski Immich je i dalje **nedostupan** (zamrznut).

## 1. Sažetak

| Stavka | Rezultat |
| --- | --- |
| `s_restore_target` | **OK**, exit 0; `pg_restore --exit-on-error --jobs=2`, `target.restore.log` = **0 B** |
| `s_validate_target` | **OK**; `validate_target.py` **RESULT: PASS (0 FAIL, 0 WARN)** (V1–V12, W1–W4 za oba indeksa, X1–X2) |
| Usporedba izvor ↔ cilj | **PASS** — 72 tablice, 1.080.428 redaka, 0 problema (`compare.json`, hashevi tablica) |
| Žurnal | **`VALIDATED`** (seq 7, `RESTORED` → `VALIDATED`, „validate_target PASS"), `cutstate.py verify` OK |
| Sigurno na F8? | **Tehnički da**, ali samo uz novu uputu i odluku vlasnika o vremenu (odjeljak 6) |

Funkcija je pozvana nepromijenjena, bez improviziranog SQL-a: `( source steps.sh; CUTOVER_APPROVED=$CUTOVER_ID s_restore_and_validate )`. `CUTOVER_APPROVED` postavljen samo prefiksom podljuske za taj poziv.

## 2. Vremenska provjera (G2/K11)

Prije izvršenja: UTC sat servera 14:02:32Z → od T0 (13:33:40Z) proteklo **28,9 min** (< 45), pa je nastavak procijenjen kao siguran (očekivano trajanje F7 ≈ 4 min). Vremenska granica nije dosegnuta tijekom F7.

## 3. Provjere prije restorea (sve prošle)

- Žurnal `SANITIZED` (seq 5), hash lanac valjan; `CUTOVER_ID` datoteka i `local-backup/cutover-id` odgovaraju.
- `lb_verify OK` (re-run prije F7).
- SHA-256 (ponovno izračunat, jednak `.sha256` datotekama i dokumentu 35): `immich.full.dump` `243e383091cbe1281aae163850f6688b04ab354469f36b90de5f79990bad5018`; `immich.no-postgis.dump` `3a85087152e0344b5e405975a8e3366aade5da315246307972dac5eba45061dd`. Funkcija je dodatno provjerila hash sanitiziranog dumpa unutar ciljnog kontejnera.
- `immich-db`: healthy, 0 tablica korisničkih shema, 0 veza uloge `immich`, samo `plpgsql`.
- Izvor `postgis/immich`: ACL `{=T/immich,immich=CT/immich}` (bez CONNECT), 0 veza.
- `immich_server` (Exited 143), `immich_media_operations`, `nextcloud_immich_bridge` (Exited 137) zaustavljeni.
- `immich_redis` i `postgis`: `StartedAt` 2026-06-26, 0 restartova.

## 4. Rezultati validacije

| Provjera | Rezultat |
| --- | --- |
| Verzija | PostgreSQL 16.16 (V1) |
| Ekstenzije | točno 8: `plpgsql 1.0, cube 1.5, earthdistance 1.2, pg_trgm 1.6, unaccent 1.1, uuid-ossp 1.1, vector 0.8.2, vchord 1.1.1`; **PostGIS nije dostupan** (V2, V3) |
| Vlasnik/ACL/uloga `immich` | jednaki izvoru; prijava preko mreže s produkcijskom tajnom OK, pogrešna lozinka odbijena (V4–V6) |
| Ovlasti | SELECT/INSERT/UPDATE/DELETE na 72 tablice, sve funkcije izvršive (V7) |
| Indeksi | 254 ukupno, 0 neispravnih, 2 `vchordrq` (V8) |
| Sekvenca identity | `bigint`, last 4274, nije ispod izvora (V9) |
| Brojevi redaka / `kysely_migrations` / system-config | jednaki zamrznutom izvoru; 101 migracija, ista zadnja; JSON byte-identičan (V10–V12) |
| **`clip_index`** | vektori 512-dim, 0 NULL; planer koristi indeks; recall@10 **prosjek 1,000, min 1,00**; ANN topli max **9,4 ms** (hladni prvi 9,0 ms) |
| **`face_index`** | vektori 512-dim, 0 NULL; planer koristi indeks; recall@10 **prosjek 0,995, min 0,90**; ANN topli max **7,8 ms** (hladni prvi 6,8 ms) |
| `amcheck` | 243 btree indeksa, **0** grešaka heapa; ekstenzija nije ostala instalirana (X1, X2) |
| `ANALYZE` | izvršen |

Napomena: `face_index` minimum recall je **točno na granici 0,90** (prag ≥ 0,90 zadovoljen; isto kao u rehearsalu, doc 30 G2 — svjesno prihvaćeno). Prag je i dalje označen kao PROPOSED u validatoru.

## 5. Stanje nakon F7

| Komponenta | Stanje |
| --- | --- |
| `immich-db` | healthy, `StartedAt` 13:19:51 (F2), 0 restartova, 0 veza uloge `immich`; sadrži restorean podatak (72 tablice) |
| Izvor `postgis/immich` | nepromijenjen: ACL bez CONNECT, 0 veza, PostGIS i dalje u izvoru; **nije odmrznut** |
| `postgis`, `immich_redis` | healthy, `StartedAt` 2026-06-26, 0 restartova |
| `immich_server`, `immich_media_operations`, `nextcloud_immich_bridge` | zaustavljeni |
| `.env` (`/opt/stacks/immich/.env`, 3.11.), `DB_HOSTNAME`, Compose, Traefik | nisu mijenjani |
| Dumpovi i backupovi | netaknuti (SHA-256 oba dumpa nakon F7 jednak) |

## 6. Vrijeme i odluka o nastavku

- Aktualno vrijeme nakon F7 (provjera): **14:04:06Z**; F7 trajao **58 s** (14:03:03–14:04:01Z).
- **Ukupno trajanje od T0: ≈ 30 min 26 s** (T0 = 13:33:40Z).
- K11: planirani cilj T0 → `OPEN_CONFIRMED` ≤ 30 min je **već prekoračen** (F8–F10 tek slijede). Prag od 45 min: **14:18:40Z** (preostaje ≈ 14 min 34 s od 14:04:06Z). Obavezni R1 pri 60 min: **14:33:40Z** (preostaje ≈ 29 min 34 s).
- **Je li dopušteno nastaviti prema F8?** Tehnički da (stanje `VALIDATED` je preduvjet F8, svi uvjeti ispunjeni). F8 (dark launch ≈ 5 min), F9 odluka (planirana T0 + ≤ 25 min, već prošla) i F10 realno ne stanu u planiranih 30 min; ostaje ≈ 14,5 min do 45-minutnog praga, nakon kojeg runbook traži novu odluku vlasnika. **Preporuka: prije F8 vlasnik treba izričito odlučiti** hoće li se prihvatiti prekoračenje cilja od 30 min i radi li se do 45 min ili do 60 min; F8 ne pokretati bez nove upute.
- **Je li R1 još sigurno moguć?** **Da.** Dopušten iz stanja `VALIDATED` (runbook: `FREEZING … DARK_VERIFIED`); izvor je netaknut (ACL bez CONNECT, nema veza, `.env` pokazuje na izvor, `T_open` ne postoji), cilj nije primio aplikacijski promet (0 veza uloge `immich`). Obavezan na 60 min (14:33:40Z), a RTO R1 ≈ 10 min.

**Stajem nakon F7. F8 ne pokrećem bez nove upute.**
