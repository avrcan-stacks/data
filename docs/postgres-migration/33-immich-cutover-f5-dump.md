# 33 — Immich produkcijski cutover: F5 (dump zamrznutog izvora)

Datum: 15. studenoga 2026. (izvedba 13:42 UTC).
**`CUTOVER_ID=20261115t130331z`** · evidencija `/opt/stacks/data/backups/immich-cutover-20261115t130331z` (`f5-dump.out`, `immich.full.dump`, `.sha256`, `.toc-lines`, `.log`, `spatial_ref_sys.source.csv`, `write-probe-frozen-B.json`, `freeze-gap-proof.json`, `src/`).
Odobreno: samo F5. **F6 i kasniji koraci nisu pokrenuti.** Produkcijski Immich je i dalje **nedostupan** (zamrznut).

## 1. Sažetak

| Stavka | Rezultat |
| --- | --- |
| `s_dump_source` | **`s_dump_source OK`, exit 0** (HALT/STOP nije bilo) |
| Dump | `/opt/stacks/data/backups/immich-cutover-20261115t130331z/immich.full.dump` |
| Veličina | **354.261.789 B** (≈338 MiB; raspon 200–500 MB: OK) |
| SHA-256 | `243e383091cbe1281aae163850f6688b04ab354469f36b90de5f79990bad5018` (sidecar i ponovni izračun identični) |
| TOC (`pg_restore --list`) | **1740** stavki (> 1000) |
| Log `pg_dump` | prazan (0 B) |
| Snapshot izvora | 72 tablice, 1.080.428 redaka (`src/`) |
| Sonda B vs. A | **identične** (SHA-256 prefiks `ac01b764cecd56e3` obje) |
| `freeze-gap-proof` | **PASS** (C0–C5, strogo, bez allow-liste) |
| Žurnal | **`DUMPED`** (seq 4, `FROZEN` → `DUMPED`, note „dump sha 243e383091cbe128"), hash lanac valjan |
| Izvor još zamrznut? | **Da** |
| Sigurno na F6? | **Tehnički da**; čeka novu uputu |

## 2. Prethodne provjere (prije dumpa)

Pročitani: dokument 32 (cijeli), relevantni dijelovi dokumenta 17 (F4/F5, STOP-3, redoslijed) i izvor `s_dump_source` u `steps.sh`. Dokument 20 nisam pročitao u cijelosti; sigurnosni uvjeti za F5 uzeti su iz dokumenta 17 i iz samih provjera funkcije. Rezultat:

- `CUTOVER_ID` datoteka i `$EV` odgovaraju; žurnal `FROZEN`, `cutstate.py verify` OK.
- `immich_server` (Exited 143), `immich_media_operations` i `nextcloud_immich_bridge` (Exited 137) zaustavljeni.
- `postgis` i `immich_redis` rade, `StartedAt` 26.6.2026., 0 restartova.
- ACL izvorne baze `{=T/immich,immich=CT/immich}` (bez CONNECT), 0 veza za `immich`.
- `.env` zadnja izmjena 3.11.2026. (prije cutovera), `DB_HOSTNAME=postgis`; nepromijenjeno.
- Sonda A postoji (`ac01b764cecd56e3…`, kao u dokumentu 32).
- Dump još nije postojao; 426 GiB slobodno.

## 3. Izvršenje

`( source immich-cutover/steps.sh; CUTOVER_APPROVED=$CUTOVER_ID s_dump_source )`; `CUTOVER_APPROVED` postavljen samo prefiksom (provjereno: nije postavljen u ljusci poslije). Izlaz u `f5-dump.out`.

Slijed: snapshot izvora → sonda B → `freeze-gap-proof` (C0 čitljive sonde, C1 postmaster nije restartan, C2 statistike nisu resetirane, C3 isti skup tablica, C4 nijedan insert/update/delete, C5 nijedna sekvenca pomaknuta: svi **PASS**) → `pg_dump -Fc --compress=gzip:6` u `.partial` → prazan log, veličina, TOC → preimenovanje u `immich.full.dump` → SHA-256 → CSV `spatial_ref_sys` (7.088.002 B) → žurnal `DUMPED`.

## 4. Status kontejnera i izvora nakon F5

| Kontejner | Stanje |
| --- | --- |
| `immich_server` | zaustavljen (Exited 143) |
| `immich_media_operations` | zaustavljen (Exited 137) |
| `nextcloud_immich_bridge` | zaustavljen (Exited 137) |
| `immich_machine_learning` | radi, healthy |
| `postgis` | radi, healthy, `StartedAt` 26.6. nepromijenjen, 0 restartova |
| `immich_redis` | radi, healthy, `StartedAt` 26.6. nepromijenjen, 0 restartova |
| `immich-db` | radi, healthy (prazan, nije dirana) |

Izvor je i dalje zamrznut: ACL bez CONNECT, 0 veza, žurnal `DUMPED` (ne `FROZEN` — to je očekivani sljedeći korak, izvor se ne odmrzava).

## 5. Što nije dirano

F4 nije ponovno pokrenut; izvor nije odmrznut; Immich server, bridge i media-operations nisu pokrenuti; Redis nije restartan; `.env`, Compose i Traefik nisu mijenjani; nema F6/F6b/F7/F10, restorea ni brisanja; postojeći dumpovi i F0 backup nisu dirani.

## 6. Je li sigurno nastaviti na F6?

**Tehnički da**: dump je potpun, provjeren i dokazano bez zapisa između zamrzavanja i dumpa; stanje `DUMPED` je preduvjet za `s_bridge_sanitize`. Napomena: prije F7 treba izvesti F6b (druga kopija dumpa na `/home`, `lb_copy_cutover_dumps && lb_verify`). **Stajem nakon F5; F6 ne pokrećem bez nove upute.** Odustajanje: `s_rollback_r1` prema runbooku (stanje `DUMPED` treba provjeriti u `steps.sh`; nije izvršeno).
