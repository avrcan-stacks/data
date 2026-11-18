# 30 — Immich: završni GO/NO-GO (faza 8H)

Datum: 15. studenoga 2026. (Europe/Zagreb), provjere u 14:09.
**Ovaj dokument nije odobrenje migracije.** Nastao je isključivo čitanjem produkcije; ništa nije zamrznuto, zaustavljeno, kopirano niti promijenjeno. `CUTOVER_APPROVED` nije postavljan.
Zaključani identifikatori: **`CUTOVER_ID=20261115t130331z`**, evidencija `/opt/stacks/data/backups/immich-cutover-20261115t130331z`, lokalna kopija `/home/immich-cutover-backups/20261115t130331z/`.

## 1. Izvršni sažetak

- **Tehnički je sve što se moglo provjeriti prije prozora zeleno:** produkcija zdrava i nepromijenjena, preflight s oba ključa 0 FAIL / 0 WARN, ključevi ispravni (točni skupovi dozvola, nema `all`), API baseline identičan prošlom (10/10), RAID1 i NVMe zdravi, F0 kopija backupa jednaka originalu (`lb_verify OK`).
- **Odluka ipak nije GO.** Preostaju odluke koje smije donijeti samo vlasnik (skupina A, odjeljak 5): pisano prihvaćanje rizika bez off-host kopije (G6), pragovi (G2), termin/retencija/odobrenje operacija (G7/G8), OIDC osoba (G3), obavijest i monitoring (G11), tko izdaje token nakon HALT-a (O14), dodatni start servera u `s_freeze` (O15), `smartmontools` (O17).
- **Status: NO-GO dok se skupina A ne zatvori i vlasnik izričito ne odobri početak.** Skupina B (tijekom cutovera) označena je PENDING, ne neuspjelom.
- **RAID1 i kopija na `/home` nalaze se na istom fizičkom serveru (isti par NVMe diskova). To nije neovisni off-host backup.**

## 2. Dokazano završene faze (17–29)

| Faza | Što je dokazano | Dokument |
| --- | --- | --- |
| Runbook i skripte | izvršivi koraci u `steps.sh`, STOP uvjeti, kriteriji K1–K18 | 17 |
| Rehearsal na izoliranom stacku | 124 testa, 9 ispravaka runbooka | 18 |
| Spremnost produkcije | pregled servisa, baza, diska, backupa; selftest; 9 ispravaka ugrađeno | 19 |
| Sigurnost otvaranja i rollbacka | stanja cutovera (hash lanac), `s_open_abort` E1–E7, `HALT_MANUAL`, novi redoslijed zamrzavanja; 229 PASS / 234, 0 otvorenih | 20 |
| Lokalni backup | RAID1/NVMe/prostor, `local_backup.sh`, SHA-256 | 21 |
| Backup gate G14 | `lb_gate_open` ispred `s_open` i `s_manual_forward`; 13 negativnih slučajeva, HALT bez promjena; 174 PASS / 176 | 22 |
| API sigurnost i ključevi | kompromitirani ključ `all` opozvan od vlasnika; 7+3 dozvole; baseline | 23–26 |
| Backup-only odobrenje | `LB_BACKUP_ONLY_APPROVED=F0:<ID>` otključava samo F0; 46 PASS | 28 |
| **F0 na produkciji** | kopija backupa izrađena i verificirana | 27, 29 |

Ništa od navedenog nije izvedeno nad pravim cutoverom: skripte su probane na izoliranoj kopiji (`immich-apptest-*`), a ne na produkciji.

## 3. Trenutačno stanje produkcije (samo čitanje, 14:09)

| Područje | Nalaz | Razlika od zadnjeg izvještaja |
| --- | --- | --- |
| Kontejneri | `immich_server`, `immich_media_operations`, `nextcloud_immich_bridge`, `immich_machine_learning`, `immich_redis`, `postgis`: `running`, `healthy`, 0 restartova; `traefik` radi. `StartedAt`: server 3.11. 13:29, media-ops 3.11. 13:25, bridge 3.11. 13:27, ML 3.11. 13:24, redis i postgis 26.6., traefik 25.9. | **nema** |
| `immich-db` | ne postoji; direktorij podataka prazan | nema |
| Baza `postgis/immich` | PostgreSQL 16.13 (PostGIS 3.6.2); 72 aplikacijske tablice; 101/101 migracija; 0 nevaljanih indeksa; ACL `{=Tc/immich, immich=CTc/immich}`; veličina 1192 MB; rola `immich` bez ovlasti | nema |
| Podaci | 57.627 asseta ukupno (56.956 nije obrisano), 8 korisnika, 11 albuma (svi računi; 6 na računu Carolina), 1.197 osoba (svi računi) | broj asseta isti; 56.956/11/1.197 nisu ranije izvještavani (različiti presjeci), ukupni brojevi nepromijenjeni |
| Veze na bazu | samo `immich_server` (11–12 veza; jedna dodatna je ova provjera) | nema |
| `.env` / Compose | `/opt/stacks/immich/.env` 3.11. 13:16, `docker-compose.yml` 3.11. 13:21; `DB_HOSTNAME=postgis` | nema |
| Redis | 63 ključa, `aof_enabled:0`, bez volumena (ne dirati) | nema |
| Redovi poslova | 19 redova, `active`/`waiting`/`delayed` = 0, nijedan pauziran; **`facialRecognition failed = 1`** (poznati stari posao iz 4.4.2026., baseline; svi ostali 0) | nema |
| RAID1 | `md0`–`md3` `[UU]`, `mismatch_cnt` 0, `sync_action` idle | nema |
| NVMe / prostor | `nvme0`, `nvme1` `live`, 41 °C; `/` 426 GiB slobodno (78 %), `/home` 1.454 GiB (339 MB zauzeto F0 kopijom) | `/home` +339 MB (očekivano, F0) |
| SMART | nedostupan (`smartmontools` nije instaliran) | nema |
| Preflight (s oba ključa) | **0 FAIL, 0 WARN** (A1–A7, H1–H3, S1–S10, B1–B5, T1/T2/T6, TR1/TR2, I1–I3, N1) | nema |
| API baseline vs 8D baseline | **10/10 PASS** (Q1–Q10): identične fotografije (55.535), videi (1.306), korištenje, 8 knjižnica, 6 albuma, 792 osobe, preklapanje pametnog pretraživanja 1,00; topli p95 272 ms (baseline 314 ms), hladni 258 ms | p95 252 → 272 ms: unutar praga, šum mjerenja |

Napomena o jednoj vlastitoj grešci: prvi poziv preflighta u ovoj fazi bio je pokrenut bez učitanih ključeva (učitavanje sam pokrenuo kroz cijev, pa nije ušlo u ljusku) i u evidenciji `$EV` ostao je zapis `A0 FAIL` s tom pogreškom. Ponavljanje s ispravno učitanim ključevima: PASS. To nije stanje produkcije.

### Ključevi

| Ključ | Vlasnik | Dozvole | Status |
| --- | --- | --- | --- |
| `cutover-admin-temp` | Immich Admin | točno 7: `queue.read queue.update job.create server.about server.statistics library.read library.statistics` | ispravan |
| `cutover-user-temp-carolina` | Carolina Plaza (običan korisnik) | točno 3: `asset.read album.read person.read` | ispravan |
| `nextcloud-immich-bridge` | Immich Admin | `adminUser.*` (3), `library.*` (5), nepromijenjen od 4.4. | nepromijenjen |
| ključ s dozvolom `all` | — | — | **ne postoji** |

`keys_verify_meta`: 3 × PASS. Vrijednosti ključeva nisu ispisane.

## 4. Status F0 i G14

| Stavka | Dokaz | Status |
| --- | --- | --- |
| `CUTOVER_ID` | markeri u `/home/…/20261115t130331z/CUTOVER_ID`, `$EV/CUTOVER_ID`, `$EV/local-backup/cutover-id`: svi `20261115t130331z` | **odgovara** |
| Izvor | `/opt/stacks/immich/docker-data/library/backups/immich-db-backup-20261115T020000-v3.3.5-pg16.13.sql.gz`, 355.181.926 B, postoji; u direktoriju 14 backupova | postoji, nepromijenjen |
| SHA-256 izvora i kopije | **`25b7780f666822c99bc8bcfc50d3e9c5851f203f29d7149b65d429821d73b0fd`** (oba, ponovno izračunati danas) | jednaki |
| Manifesti | `$EV/local-backup/app-backup.sha256` = `/home/…/app-backup/SHA256SUMS` | jednaki |
| `lb_check` / `lb_verify` | OK / **`lb_verify OK`** (original, kopija, međusobna jednakost); “no dump manifest yet” je očekivano | PASS |
| **F0** | izvršen 29 | **GOTOV** |
| **G14** | traži još: F6b (kopije oba dumpa na `/home`), `lb_verify` nakon F6b, `lb_gate_open` PASS neposredno prije `s_open` | **OTVOREN, PENDING — DURING CUTOVER** |

Kopija je kopija **postojećeg 02:00 backupa**, ne svježeg dumpa zamrznute baze (njega nema do prozora). RAID1 štiti od kvara jednog diska, a `/home` od oštećenja datotečnog sustava `/` i slučajnog brisanja jedne kopije; **ne štite** od gubitka hosta ili oba diska, požara, krađe, ransomwarea ni logičke pogreške. Strategija backupa nije mijenjana niti predlažem promjenu.

## 5. Skupina A — obavezno prije početka produkcijskog prozora

Odluke donosi vlasnik; ja nijednu nisam donio. “Ako nije ispunjeno” znači stanje GO/NO-GO.

| ID | Točna definicija (doc 17/21) | Trenutačno stanje | Odlučuje | Ako nije ispunjeno |
| --- | --- | --- | --- | --- |
| **G6** | Off-host kopija pune baze prije prozora; zamijenjena **izričito prihvaćenim rizikom** lokalne RAID1 zaštite + G14 (doc 21 §6: gubitak hosta ili oba diska = gubitak svih kopija, izvora i nove baze; mediji nisu pokriveni DB planom) | **NIJE ISPUNJEN; off-host kopije nema**; pisano prihvaćanje rizika **nije zabilježeno** (usmena odluka vlasnika postoji, ali nije zapisana u zapisniku GO odluke) | vlasnik | **NO-GO** |
| **G2** | Pragovi validacije i prozor prekida (K1–K17): K7 recall@10 prosjek ≥ 0,95 i **minimum ≥ 0,90** (`face_index` u rehearsalu: prosjek 0,995, minimum 0,90, dakle na granici, svjesno odobriti), ANN topli ≤ 250 ms, amcheck 0; K10 preklapanje ≥ 0,90, p95 topli ≤ max(250 ms, 2×baseline), hladni ≤ 5 s; K11 T0 → `OPEN_CONFIRMED` ≤ 30 min (maks. 45, pri 60 obavezan R1) | pragovi su **prijedlozi**, neodobreni | vlasnik | **NO-GO** |
| **G7** | Provjeren rollback i odobrena retencija: R1 dokumentiran i probano u rehearsalu (ne na produkciji); retencija izvorne baze **≥ 7 dana** (doc 17 §7) | R1 i `s_open_abort` probani na izolaciji; **retencija nije odobrena** | vlasnik | **NO-GO** |
| **G8** | Odobrenje promjene `/opt/stacks/immich/.env` (`DB_HOSTNAME`) i recreatea `immich-server`/`media-operations` bez builda te zaštite izvora (`REVOKE CONNECT`) (O4, O5, O9) | nije odobreno | vlasnik | **NO-GO** |
| **G3** | Postupak OIDC: vlasnik se prijavljuje preko Nextclouda (web i mobilna), prijava lozinkom kao rezerva; **treba imenovati osobu** | osoba nije imenovana; OIDC je u Immichu uključen, račun `immich-admin@finestar.hr` nije povezan s OIDC-om | vlasnik | **NO-GO** (G3 se ne može provjeriti nakon otvaranja) |
| **G11** | Obavijest korisnicima (8 računa) i utišan monitoring (Uptime Kuma) | nije učinjeno | vlasnik | **NO-GO** |
| **Termin (K2/O1)** | izvan 23:40–04:15 (cron sudari), radni dan; preflight prijedlog 04:30–22:00; planirano ≤ 30 min prekida | **termin nije odabran** | vlasnik | **NO-GO** |
| **O14** | tko smije izdati token `FORWARD:<ID>` / `ROLLBACK_ACCEPT_LOSS:<ID>` nakon `HALT_MANUAL` (i tko odlučuje u R2) | **osoba nije imenovana** | vlasnik | **NO-GO** (bez nje HALT nema tko razriješiti) |
| **O15** | kratki API-only start `immich-server` na izvornoj bazi u `s_freeze` radi baselinea (`docker-compose.frozen.yml`); dodatni recreate servera, reverzibilno | nije odobreno | vlasnik | **NO-GO** (`s_freeze` ne smije se izvesti bez toga u predviđenom obliku) |
| **O17** | instalacija `smartmontools` radi SMART baselinea prije i poslije prozora (preporuka; runbook ne propisuje drukčije, nije uvjet) | nije odlučeno; SMART nedostupan | vlasnik | **ne blokira**; rizik lošeg zdravlja NAND-a ostaje neprovjeren |
| O12 | kanarski testovi nakon otvaranja (privremeni korisnik, video, trash/restore, ručno skeniranje) pišu u produkciju | nije odobreno | vlasnik | ne blokira otvaranje; ostaje neprobano iz skupine C |
| O13 | čuvanje izvora ≥ 7 dana i zabrana zamjene/nadogradnje `postgis` u tom razdoblju | nije odobreno | vlasnik | **NO-GO** (dio G7) |
| Operacije O3–O10 | popis iz doc 17 §10 (pokretanje `immich-db`, pauza redova, zaustavljanje bridgea/`media-operations`/servera, fence izvora, dump, restore, dark launch, izmjena `.env`) | nije odobreno | vlasnik | **NO-GO** |
| G10 | privremeni API ključevi | **ispunjen** (odjeljak 3) | — | — |
| G1, G4, G5, G9 | rehearsal, image/mreža, prostor ≥ 96 GiB (426 GiB), skripte probane | **ispunjeni** | — | — |

## 6. Skupina B — uvjeti koji se mogu ispuniti tek tijekom cutovera

**Svi su PENDING — DURING CUTOVER** (nisu neuspjeli). Redoslijed i kriteriji iz doc 17/20/22.

| Korak (runbook) | Uvjet / kriterij | Status |
| --- | --- | --- |
| F1 `preflight.py --phase before-target` (T-60 min), F2 `s_prepare_target` | 0 FAIL; `immich-db` 16.16 healthy, scram login i negativna kontrola | PENDING — DURING CUTOVER |
| F3 proba alata, `preflight --phase target-ready` | 0 FAIL | PENDING — DURING CUTOVER |
| F4 `s_freeze` — **zamrzavanje svih izvora pisanja** | redoslijed: bridge i `media-operations` → pauza i pražnjenje redova (`active == 0` ≤ 10 min, K3) → stop servera → baseline iz API-only instance → fence izvora → sonda A; `freeze-order.log` točan (K16) | PENDING — DURING CUTOVER |
| F5 `s_dump_source` — **svjež dump zamrznute baze** | exit 0, prazan log, 200–500 MB, TOC > 1000 stavki, SHA-256; sonda B = sonda A (`freeze-gap-proof` PASS) (K4, K16) | PENDING — DURING CUTOVER |
| F6 `s_bridge_sanitize` — **sanitizacija bez PostGIS-a** | restore bez greške, usporedba izvor↔bridge prije i poslije `DROP EXTENSION postgis RESTRICT`, TOC bez PostGIS-a (K5) | PENDING — DURING CUTOVER |
| **F6b `lb_copy_cutover_dumps` + `lb_verify`** | oba dumpa na `/home/immich-cutover-backups/20261115t130331z/dumps`, SHA-256 original = kopija, TOC kopije jednak; traži `CUTOVER_APPROVED` (F0 token ovdje ne vrijedi) (K18) | PENDING — DURING CUTOVER |
| F7 `s_restore_and_validate` — **validacija ciljne baze** | `compare` 72/72, `validate_target` 0 FAIL (22 provjere, recall, latencija, amcheck) (K6, K7) | PENDING — DURING CUTOVER |
| F8 `s_dark_launch` — **dark launch i API provjere** | healthy ≤ 180 s, 0 migracija, "No schema drift", API-only, `verify --allow-paused` prema `api-baseline.json` iz zamrznutog stanja, `delta` samo dopuštene tablice (K8, K9, K10) | PENDING — DURING CUTOVER |
| F9 odluka GO/NO-GO (T0 + ≤ 25 min) | imenovana osoba; K15 (žurnal), K9 (bez razlike) | PENDING — DURING CUTOVER |
| **`lb_gate_open` / G14 neposredno prije `s_open`** | PASS (identitet `20261115t130331z`, RAID1 `[UU]` bez resynca, oba dumpa i app backup u originalu i kopiji, manifesti, hashevi, `COPIES_DONE`); inače HALT exit 6 bez promjena (K18) | PENDING — DURING CUTOVER |
| F10 `s_open` | stanja do `OPEN_CONFIRMED`; T0 → `OPEN_CONFIRMED` ≤ 30 min (K11) | PENDING — DURING CUTOVER |

## 7. Skupina C — kontrole nakon otvaranja (kriteriji iz doc 17 §8, K13, K14)

| Kontrola | Postupak i kriterij (iz runbooka) |
| --- | --- |
| API i redovi | `api_checks.py queues status` i `verify` prema `api-baseline.json`: redovi mirni, `failed` **ne više od baselinea (`facialRecognition` = 1)**, svi ostali 0; Q1–Q10 PASS (K13) |
| OIDC | vlasnik se prijavljuje preko Nextclouda (web i mobilna), prijava lozinkom kao rezerva; uspješna prijava **istog računa, bez duplikata korisnika** (G3) |
| Upload i čitanje fotografija | kanarski testovi O12: sintetički HEVC klip + slika kao privremeni korisnik; u `/data/encoded-video/<korisnik>` nastaje H.264 inačica, 0 neuspjelih poslova; trash/restore stanja u UI-ju i API-ju odgovaraju; čišćenje kanara uz odobrenje (broj korisnika i asseta vraćen) |
| Pametno pretraživanje | `verify` Q8–Q10: preklapanje top-20 ≥ 0,90 za 10 upita, topli p95 ≤ max(250 ms, 2×baseline), hladni ≤ 5 s |
| Albumi, osobe, lica | Q6, Q7 identični baselineu (6 albuma, 792 osobe); lica/embeddingi kroz `validate_target` i Q8 |
| Redovi poslova | svi `active/waiting/delayed` 0 nakon obrade; 0 novih neuspjelih |
| `immich_media_operations` | `docker logs` bez grešaka veze na bazu (bez `Postgres lookup failed`); jedna read-only akcija utility sučelja |
| `nextcloud_immich_bridge` | jedan ciklus (300 s) bez greške u logu |
| Traefik pristup | ruta aktivna samo nakon `ROUTE_LIVE` (label `traefik.enable=true`); neobvezno read-only `GET /api/server/ping` 404 u dark fazi i 200 nakon otvaranja; nema promjene Traefika |
| Backup | ručni `backup-database`: datoteka `…-pg16.16.sql.gz`, `gzip -t`, ±10 % prethodnog, 7 `CREATE EXTENSION`, 0 PostGIS DDL; sljedeće jutro 02:00 "Database Backup Success" |
| Skeniranje knjižnica, storage template, integrity | noćno skeniranje 00:00 bez neočekivanih promjena; storage template ostaje isključen; integrity 03:00 bez skoka (baseline 8033) |
| Logovi 24 h | 0 neočekivanih ERROR; veze, disk i resursi stabilni; 0 restarta (K14) |
| Monitoring i obavijesti | Uptime Kuma ponovno uključen nakon `OPEN_CONFIRMED`; korisnici obaviješteni o završetku (G11) |
| Zaštita izvora i retencija | `postgis/immich` nepromijenjen i zaštićen (`REVOKE CONNECT`), ≥ **7 dana**; tjedna provjera `db_snapshot` source↔`$EV/src` PASS; `postgis` se ne zamjenjuje ni nadograđuje; dan 7: zasebna odluka o brisanju (brisanje nije dio plana) |
| Lokalne kopije | `lb_verify OK` nakon otvaranja, T+24 h i tjedno; kopije se ne brišu bez odobrenja |

## 8. Točka bez povratka i pravila rollbacka

1. **Kada je dopušten automatski rollback R1:** samo u stanjima `FREEZING, FROZEN, DUMPED, SANITIZED, RESTORED, VALIDATED, DARK_VERIFIED` i `ABORT_VERIFIED`, uz žive unakrsne provjere (`.env` upućuje na izvor, `T_open` ne postoji, aplikacija ne služi novu bazu s rutom). Neslaganje = HALT (exit 4), ne rollback.
2. **Dokaz da nova baza nije primila zapis** daje `s_open_abort` kad open zakaže u stanjima `OPEN_BEGIN … AUX_STARTED`: prvo se zaustave svi pisci, zatim moraju svi PASS: E1 pisci zaustavljeni, E2 žurnal valjan, E3 nijedna veza uloge `immich` na novu bazu, E4 sonda pisanja (brojači `n_tup_ins/upd/del` izvan `system_metadata, version_history, plugin, plugin_method` i **sve sekvence** nepromijenjene, nema restarta ni reseta statistike), E5 72 hasha tablica i metapodaci jednaki snapshotu nakon dark launcha, E6 nijedna datoteka u `upload` s `ctime` poslije T0, E7 `.env` točno zabilježeni sadržaj. Tek tada `.env` se vraća bajt-u-bajt, server ostaje zaustavljen, stanje `ABORT_VERIFIED` pa R1.
3. **`HALT_MANUAL` nastaje** kad bilo koji dokaz E1–E7 padne ili se ne može dokazati (UNKNOWN), kad je žurnal oštećen (tada bez ikakve radnje), ili kad `.env` nije zabilježeni sadržaj. Server ostaje zaustavljen, nastaje `HALT-REPORT.txt`, automatski rollback je zabranjen. Jedini izlazi su ručne odluke s tokenom: GO `FORWARD:<ID>` (`s_manual_forward`, i on prolazi G14) ili NO-GO `ROLLBACK_ACCEPT_LOSS:<ID>` (`s_manual_rollback_accept_loss`, uz izričito prihvaćanje gubitka; nova baza se **ne briše**).
4. **Zašto nakon potvrđenog pisanja u novu bazu nema automatskog povratka:** povratak na staru bazu bi odbacio sve što su korisnici i poslovi zapisali od `ROUTE_LIVE` (uploadi, sesije, albumi, rezultati obrade). Skripta ne može razlikovati što je vrijedno zadržati, pa takva odluka pripada imenovanoj osobi (O14). Od `RESUMING` (workeri nastavljaju zadržane redove na novoj bazi) više se ništa ne može dokazati i sve skripte odbijaju povratak (exit 3/5).
5. **Čuvanje stare baze 7 dana nije isto što i povratak bez gubitka:** izvor je zamrznut u T0 i zaštićen; svaki zapis nakon `ROUTE_LIVE` postoji samo u novoj bazi. Povratak na izvor znači gubitak svega od otvaranja, a izvor zastarijeva svakim danom. Služi za forenziku, usporedbu i hitni povratak uz prihvaćen gubitak (R2 opcija A); stvarna zaštita nove baze su 02:00 backupi (RPO ≤ 24 h) i ručni backup odmah nakon otvaranja.
6. U ovom dokumentu nije izveden nikakav rollback.

## 9. Operativna kontrolna lista

Tri moguće odluke: **GO** (svi uvjeti zadovoljeni **i** vlasnik izričito odobrio početak), **NO-GO** (nedostaje obavezno odobrenje ili sigurnosni uvjet), **HALT** (tijekom provedbe kvar ili odstupanje).

### 9.1 Prije prozora (GO samo ako je sve DA)

| # | Uvjet | Dokaz | Status danas |
| --- | --- | --- | --- |
| 1 | Pisano prihvaćanje rizika bez off-host kopije (G6) | zapisnik odluke | **NE** |
| 2 | Pragovi odobreni, uključujući recall minimum ≥ 0,90 (G2) | zapisnik | **NE** |
| 3 | Termin odabran (izvan 23:40–04:15) | zapisnik | **NE** |
| 4 | Retencija izvora ≥ 7 dana i zabrana zamjene `postgis` (G7/O13) | zapisnik | **NE** |
| 5 | Odobrene operacije O3–O10, izmjena `.env` i recreate (G8), O15 | zapisnik | **NE** |
| 6 | OIDC osoba imenovana (G3) | zapisnik | **NE** |
| 7 | Obavijest korisnicima poslana, Uptime Kuma utišan (G11) | potvrda | **NE** |
| 8 | Osoba za token nakon HALT-a (O14) | zapisnik | **NE** |
| 9 | Preflight 0 FAIL s oba ključa, ključevi 7+3 i bez `all` | danas izvršeno | DA |
| 10 | RAID1 `[UU]`, NVMe `live`, prostor ≥ 96 GiB | danas izvršeno | DA |
| 11 | F0: kopija backupa, SHA-256 `25b7780f…73b0fd`, `lb_verify OK` | danas izvršeno | DA |
| 12 | Rehearsal 17–29 PASS, bez otvorenih FAIL | doc 18, 20, 22 | DA |
| 13 | Vlasnik izričito objavi: "počinje produkcijski cutover `20261115t130331z`" | poruka vlasnika | **NE** |

**Trenutna odluka: NO-GO** (uvjeti 1–8 i 13). Tehnički uvjeti 9–12 ne mogu sami proglasiti GO.

### 9.2 Tijekom prozora (svako odstupanje = HALT)

| Korak | Dokaz | HALT ako |
| --- | --- | --- |
| Preflight (F1, F3) | 0 FAIL | bilo koji FAIL |
| `s_freeze` | `freeze-order.log`, `queues` `active == 0`, 0 veza, fence | STOP-1/2: redovi se ne isprazne u 10 min, veze ≠ 0 |
| `s_dump_source` | veličina 200–500 MB, `freeze-gap-proof` PASS | STOP-3 |
| `s_bridge_sanitize` | usporedbe PASS, TOC bez PostGIS-a | STOP-4 |
| F6b `lb_copy_cutover_dumps` + `lb_verify` | `lb_verify OK` | STOP-8 (bez druge kopije se ne ide dalje) |
| `s_restore_and_validate` | 22 provjere, recall ≥ 0,90 | STOP-5 |
| `s_dark_launch` | healthy, log, `verify`, `delta` | STOP-6 → R1 |
| `lb_gate_open` | PASS | exit 6 → ništa se ne mijenja, ispraviti uzrok |
| `s_open` | `OPEN_CONFIRMED` ≤ 30 min | kvar → samo `s_open_abort`; dokaz ili `HALT_MANUAL` |
| Vremenski limit | 45 min maksimum | 60 min → obavezan R1 (ako je u dopuštenom stanju) |

### 9.3 Nakon otvaranja

Provedba skupine C (odjeljak 7); odstupanje bez dokaza = HALT i ručna odluka imenovane osobe.

## 10. Odluke koje vlasnik još mora potvrditi

1. **G6:** pisano prihvaćanje rizika lokalne RAID1 zaštite bez off-host kopije.
2. **G2:** prag recall (minimum ≥ 0,90 za `face_index`), latencije, prozor prekida (K1–K17).
3. **G7/O13:** retencija izvora ≥ 7 dana i zabrana zamjene `postgis`.
4. **G8:** izmjena `.env` (`DB_HOSTNAME`), recreate `immich-server` i `media-operations`, `REVOKE CONNECT` na izvoru (O4, O5, O9).
5. **G3:** imenovana osoba za OIDC provjeru.
6. **G11:** obavijest korisnicima, utišan Uptime Kuma, vrijeme uključivanja.
7. **Termin** prozora (K2).
8. **O14:** tko izdaje token nakon HALT-a (GO ili NO-GO s gubitkom).
9. **O15:** kratki API-only start servera u `s_freeze`.
10. **O12:** kanarski testovi nakon otvaranja (nije uvjet otvaranja).
11. **O17:** `smartmontools` (preporuka, odluka vlasnika).
12. Preporuke bez blokade: obrisati kopije ključeva u VS Code povijesti (`/root/.vscode-server/…/History/`), `chmod 600` na `.env` datotekama (sada 0644), jačanje `POSTGRES_PASSWORD` (8 znakova); nakon cutovera i retencije obrisati privremene API ključeve.

Neprobano jer postoji samo u produkciji: stvarni Traefik, `media-operations` i bridge tijekom cutovera, OIDC prijava, kanarski testovi, stvarni promet i mobilni klijenti, stvarni kvar diska; ostaje i rizik iz doc 19 (korisnik koji uploada u sekundama prije zaustavljanja servera, pokriven usporedbom baza).

## 11. Jedna preporučena sljedeća radnja

**Vlasnik u jednoj pisanoj poruci potvrđuje odluke iz odjeljka 10 (točke 1–9: G6 prihvaćanje rizika, pragovi G2, retencija G7/O13, odobrenje operacija G8 i O15, OIDC osoba, obavijest i monitoring, termin, osoba za token nakon HALT-a).**

## 12. Što je izvršeno

Samo čitanje: stanje kontejnera, upiti nad `postgis/immich` (brojevi, ACL, metapodaci ključeva bez stupca `key`), `/proc/mdstat`, `mdadm`, `/sys`, `df`, `sha256sum`, `lb_check`, `lb_verify`, `preflight.py` i `api_checks.py` (samo GET plus `POST /search/smart` koji ne mijenja podatke), `keys_verify_meta`. Pisano: evidencija `api-baseline-8h.json` i `api-verify-8h.json` (0600) u `$EV`, preflight evidencija i ovaj dokument. Nije: postavljen `CUTOVER_APPROVED` ni token, izvršen `s_freeze`/`s_open`/`s_manual_forward`/rollback, pokrenut `immich-db`, zaustavljen ni restartan kontejner, mijenjani PostgreSQL, Redis, Compose, `.env`, mreže, Traefik, OIDC, korisnici ili ključevi, izvršen mutirajući API poziv, kopiran novi dump ili obrisan backup; nijedna tajna nije ispisana.

**PRODUCTION CUTOVER: NOT AUTHORIZED.**
