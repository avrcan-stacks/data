# 35 — Immich produkcijski cutover: F6b (druga kopija dumpova na /home)

Datum: 15. studenoga 2026. (izvedba 13:56–13:57 UTC).
**`CUTOVER_ID=20261115t130331z`** · evidencija `/opt/stacks/data/backups/immich-cutover-20261115t130331z` (`f6b-copy.out`, `f6b-bridge-cleanup.out`, `local-backup/dumps.sha256`, `local-backup/COPIES_DONE`).
Odobreno: samo F6b (`lb_copy_cutover_dumps` + `lb_verify`) i dokumentirani `s_bridge_cleanup`. **F7, F8, F10 nisu pokrenuti.** Produkcijski Immich je i dalje **nedostupan** (zamrznut).

## 1. Sažetak

| Stavka | Rezultat |
| --- | --- |
| `lb_copy_cutover_dumps` | **`lb_copy_cutover_dumps OK`**, exit 0 (uključuje `lb_check OK` i usporedbu TOC-a kopija) |
| `lb_verify` | **`lb_verify OK`** (8 PASS: app backup original + kopija + jednakost; oba dumpa original + kopija + jednakost) |
| Marker `COPIES_DONE` | postoji (`$EV/local-backup/COPIES_DONE`) |
| Žurnal | **`SANITIZED`** (seq 5, nepromijenjen), `cutstate.py verify` OK |
| Privremeni bridge | **uklonjen** (`s_bridge_cleanup`, vidi odjeljak 5) |
| Sigurno na F7? | **Da, tehnički** (vidi odjeljak 9); čeka novu uputu |

## 2. Status i SHA-256 oba dumpa

| Dump | Veličina (B) | SHA-256 original | SHA-256 kopija na `/home` | Očekivano |
| --- | --- | --- | --- | --- |
| `immich.full.dump` | 354.261.789 | `243e383091cbe1281aae163850f6688b04ab354469f36b90de5f79990bad5018` | isti | isti |
| `immich.no-postgis.dump` | 354.050.055 | `3a85087152e0344b5e405975a8e3366aade5da315246307972dac5eba45061dd` | isti | isti |

Dodatno neovisno (izvan `lb_verify`): `sha256sum` originala i kopija ručno, `cmp` original ↔ kopija bajt-za-bajt (oba dumpa identična), `sha256sum -c SHA256SUMS` u odredištu OK; manifest originala (`$EV/local-backup/dumps.sha256`) i manifest kopije (`dumps/SHA256SUMS`) imaju identičan sadržaj (2 retka, oblik `<64 hex>␣␣<ime>`). Veličine i `mtime` originala (13:42:49 i 13:50:33) nepromijenjeni; `cp -p` sačuvao `mtime` u kopijama.

## 3. Odredište i prava pristupa

`/home/immich-cutover-backups/20261115t130331z/dumps/`

| Putanja | Prava | Vlasnik |
| --- | --- | --- |
| `…/20261115t130331z`, `…/dumps` | 0700 | root:root |
| `immich.full.dump`, `immich.no-postgis.dump`, `SHA256SUMS` | **0400** | root:root |
| `$EV/local-backup/dumps.sha256`, `COPIES_DONE` | 0600 | root:root |

Marker `CUTOVER_ID` u kopiji i `$EV/local-backup/cutover-id` odgovaraju (`20261115t130331z`). `chattr +i` nije postavljen (neobvezno, `LB_IMMUTABLE` nije uključen).

## 4. F0 backup i G14

F0 nije dirao: `app-backup/immich-db-backup-20261115T020000-v3.3.5-pg16.13.sql.gz` (0400), SHA-256 `25b7780f…73b0fd` jednak izvorniku u `/opt/stacks/immich/docker-data/library/backups/` (veličina 355.181.926 B nepromijenjena; u direktoriju i dalje 14 backupova); `lb_verify` ga je ponovno potvrdio.

**G14: kopije su sada potpune** (app backup + oba dumpa, hashevi jednaki, manifesti i `COPIES_DONE` na mjestu, `lb_check OK`). Formalni prolaz **`lb_gate_open` nije pokretan** (nije bio tražen); on se izvršava u `s_open`/`s_backup_gate` neposredno prije F10, uz ponovni `lb_check`. G6 (off-host) i dalje je neispunjen uz prihvaćeni rizik (doc 21).

## 5. Privremeni bridge

Prema runbooku (doc 17, F6: `s_bridge_sanitize && s_bridge_cleanup`; F12: „Bridge se već uklanja u F6") cleanup je izričito predviđen, a F6b je uspio. Prije izvršenja provjereno: label `immich.cutover=20261115t130331z` odgovara; bridge je bio `--network none`; njegov `$EV` mount je **read-only**; radni direktorij `/tmp/immich-cutover-20261115t130331z` sadržavao je samo `bridge-data` (PGDATA bridgea) i prolazi `realpath` provjeru funkcije. Svi artefakti koji trebaju F7 (dumpovi, snapshotovi `bridge-before/after`, usporedbe, TOC, logovi) već su u `$EV`, a ne u bridgeu. Izvršeno: `BR=immich-cutover-bridge-20261115t130331z WB=/tmp/immich-cutover-20261115t130331z CUTOVER_APPROVED=$CUTOVER_ID s_bridge_cleanup` → **`bridge removed`**, exit 0. Nakon toga: kontejner više ne postoji, `/tmp/immich-cutover-*` ne postoji; hashevi oba originala i kopija nepromijenjeni. Izvor, ciljna baza i dumpovi nisu dirani. Napomena: `BR`/`WB` nisu zadani u `steps.sh` (traže se iz okoline), pa su postavljeni prema konvenciji imenovanja iz F6 (potvrđeno labelom i `docker inspect` mountom).

## 6. Cutover žurnal

`SANITIZED` (seq 5, 13:50:34Z), hash lanac valjan. F6b ne piše u žurnal; stanje nije mijenjano.

## 7. Status produkcijskih kontejnera

| Kontejner | Stanje |
| --- | --- |
| `postgis` | running, healthy, `StartedAt` 2026-06-26, 0 restartova |
| `immich_redis` | running, healthy, `StartedAt` 2026-06-26, 0 restartova |
| `immich-db` | running, healthy, `StartedAt` 15.11. 13:19:51 (F2), 0 restartova, nema restorea |
| `immich_server` | zaustavljen (Exited 143) |
| `immich_media_operations`, `nextcloud_immich_bridge` | zaustavljeni (Exited 137) |
| Izvor `postgis/immich` | ACL `{=T/immich,immich=CT/immich}` (bez CONNECT), 0 veza uloge `immich` |

`.env` (`/opt/stacks/immich/.env`, 3.11.), Compose i Traefik nisu mijenjani. `CUTOVER_APPROVED` postavljan samo prefiksom/podljuskom po pozivu; nakon izvršenja nije u okolini.

## 8. Vrijeme

T0 = 13:33:40Z. F6b počeo 13:56:30Z, završio 13:56:44Z (14 s); cleanup 13:57:17Z. **Proteklo od T0 ≈ 23 min 37 s.**
- Planirano T0 → `OPEN_CONFIRMED` ≤ 30 min (K11): ostalo **≈ 6 min 23 s**; F7–F10 realno traju dulje, pa se **planirani cilj od 30 min vjerojatno neće postići** (F9 odluka je planirana na T0 + ≤ 25 min).
- Maksimum 45 min (T0 + 45 = 14:18:40Z): nije prekoračen. Obavezni rollback R1 pri 60 min (14:33:40Z): nije prekoračen.
- G2 (pragovi/prozor prekida) i K11 u doc 17 vode se kao „OTVOREN" (prijedlozi); prema prijedlogu nije prekoračen obvezni prag, pa HALT po vremenu nije bio potreban.

## 9. Je li sigurno nastaviti na F7?

**Tehnički da:** stanje `SANITIZED` je preduvjet, obje kopije su bajt-za-bajt jednake originalima, G14 kopije su na mjestu, izvor je zaštićen, pisci su zaustavljeni, `postgis`/Redis nisu restartani. Odluku o nastavku treba donijeti vlasnik s obzirom na vrijeme: **do praga od 45 min preostaje ≈ 21 min, do obaveznog R1 ≈ 36 min**, a F7–F10 s validacijom i dark launchem u rehearsalu traju znatno više od 6 min do planiranih 30 min. Ako se vrijeme približi 45 min, runbook traži odluku; pri 60 min rollback R1 (`s_rollback_r1`, dopušten iz `SANITIZED`).

**Stajem nakon F6b. F7 ne pokrećem bez nove upute.**
