# 29 — Immich: F0, produkcijska lokalna kopija backupa (faza 8G)

Datum: 15. studenoga 2026. (Europe/Zagreb).
Status: **F0 izvršen i potvrđen.** Odobreno je isključivo F0 (O16); **produkcijski cutover nije odobren ni pokrenut.** Korišten je samo token `LB_BACKUP_ONLY_APPROVED=F0:<CUTOVER_ID>` (doc 28); `CUTOVER_APPROVED` nije postavljan.

## 0. Sažetak

| Stavka | Vrijednost |
| --- | --- |
| **`CUTOVER_ID`** (koristi se i u kasnijem cutoveru) | **`20261115t130331z`** |
| Evidencijski direktorij `$EV` | `/opt/stacks/data/backups/immich-cutover-20261115t130331z` (0700) |
| Izvorna datoteka | `/opt/stacks/immich/docker-data/library/backups/immich-db-backup-20261115T020000-v3.3.5-pg16.13.sql.gz` (355.181.926 B, 15.11.2026. 02:00) |
| Odredišna datoteka | `/home/immich-cutover-backups/20261115t130331z/app-backup/immich-db-backup-20261115T020000-v3.3.5-pg16.13.sql.gz` |
| **SHA-256 (izvor = kopija)** | `25b7780f666822c99bc8bcfc50d3e9c5851f203f29d7149b65d429821d73b0fd` |
| `lb_check` | **OK** (prije kopiranja) |
| `lb_verify` | **OK** |
| G14 | **OTVOREN** (djelomično: F0 gotov; nedostaju kopije dumpova F6b i `lb_gate_open` PASS) |

## 1. Provjera prije kopiranja (`lb_check`)

RAID1 `md0`–`md3`: `clean` (`md2` `active`), `[UU]`, `mismatch_cnt` 0, `sync_action` idle; `nvme0` i `nvme1` `live`, 41 °C (prag 70); slobodan prostor `/home` 1.454 GiB, `/` 425 GiB (prag 50); `/home` na drugom datotečnom sustavu od glavnih backupa. Rezultat `lb_check OK`. SMART brojači nisu čitljivi (`smartmontools` nije instaliran, O17).

## 2. Izvršeni koraci

1. `CUTOVER_ID=20261115t130331z`, `EV` kreiran (0700) prema runbooku.
2. `export LB_BACKUP_ONLY_APPROVED=F0:20261115t130331z` (samo to).
3. `lb_copy_app_backup`: `lb_check` OK, `gzip -t` izvora, kopija s `cp -p`, hash prije i poslije, izvor nepromijenjen tijekom kopiranja → `lb_copy_app_backup OK`.
4. `lb_verify` → `lb_verify OK` (originalni backup, `/home` kopija i međusobna jednakost).
5. `unset LB_BACKUP_ONLY_APPROVED`: potvrđeno da token i `CUTOVER_APPROVED` nisu u okolini.
6. `CUTOVER_ID` zapisan u `$EV/CUTOVER_ID` (0600) za nastavak.

## 3. Neovisne provjere nakon kopiranja

| Provjera | Rezultat |
| --- | --- |
| SHA-256 izvora prije kopiranja = poslije = kopije | **jednaki** (`25b7780f…73b0fd`) |
| `cmp` izvor ↔ kopija | bajt-za-bajt identično |
| `gzip -t` kopije | OK |
| Manifest kopije `app-backup/SHA256SUMS` = manifest originala `$EV/local-backup/app-backup.sha256` | identični, jedan redak, ime i hash ispravni |
| Marker identiteta | `/home/…/20261115t130331z/CUTOVER_ID` i `$EV/local-backup/cutover-id` = `20261115t130331z` |
| Izvor nepromijenjen | veličina 355.181.926 B, `mtime` isti, vlasnik/prava (`0644`) isti; u direktoriju i dalje **14** backupova, ništa premješteno ni obrisano |

### Prava pristupa

| Putanja | Prava | Vlasnik |
| --- | --- | --- |
| `/home/immich-cutover-backups` | 0700 | root:root |
| `…/20261115t130331z`, `…/app-backup` | 0700 | root:root |
| kopija `.sql.gz`, `SHA256SUMS` | **0400** | root:root |
| `…/20261115t130331z/CUTOVER_ID` | 0600 | root:root |
| `$EV`, `$EV/local-backup` | 0700 | root:root |
| `$EV/local-backup/app-backup.sha256`, `cutover-id` | 0600 | root:root |

## 4. G14

F0 je gotov (`lb_verify OK`), ali **G14 NIJE zadovoljen**: (a) nedostaju kopije zamrznutih dumpova (`lb_copy_cutover_dumps`, F6b, tek u prozoru nakon `s_freeze`/F5/F6 i uz `CUTOVER_APPROVED`); (b) `lb_gate_open` mora proći neposredno prije `s_open`. G6 (off-host) ostaje neispunjen; treba pisano prihvaćanje rizika lokalne RAID1 zaštite. Ova kopija jednostavno pripada ovom `CUTOVER_ID`; ako se cutover pokrene s drugim ID-om, gate će HALT-ati (marker). Kopija ne zamjenjuje svježi dump zamrznute baze.

## 5. Produkcija nepromijenjena

`immich_server`, `immich_media_operations`, `nextcloud_immich_bridge`, `immich_machine_learning`, `immich_redis`, `postgis`: `running`, `healthy`, 0 restartova, `StartedAt` isti kao prije (server 3.11., ostali kao ranije). `traefik` radi. `immich-db` ne postoji. `postgis/immich`: ACL baze `{=Tc/immich, immich=CTc/immich}`, 3 API ključa, 57.627 asseta (isto). `.env` (13.16, 3.11.) i Compose (13.21, 3.11.) nepromijenjeni. RAID1 i dalje `[UU]`. Nijedan kontejner nije zaustavljen ni restartan; nije pokrenut nijedan korak cutovera (`s_freeze`, `s_open`, …); nisu dirani PostgreSQL, Redis, `.env`, Compose ni API ključevi; nije kopiran nijedan dump iz aktivne baze; nijedan backup nije obrisan ni premješten; nijedna tajna nije ispisana.

## 6. Preostali uvjeti (kratko, prema [26](26-immich-api-keys-ready.md) i [27](27-immich-local-backup-result.md))

G14 do kraja (F6b + `lb_gate_open`), G6 pisano prihvaćanje rizika, G2/G7/G8/G3/G11 (pragovi, termin, retencija, `.env`/recreate, OIDC osoba, obavijest korisnicima i monitoring), O14/O15, preporuke (kopije ključeva u VS Code povijesti, `chmod 600` na `.env`, jačanje `POSTGRES_PASSWORD`, `smartmontools`), neprobano samo-produkcijsko (Traefik, bridge i `media-operations`, OIDC, kanarski testovi).

**Stati ovdje. Produkcijski cutover nije odobren.**
