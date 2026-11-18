# 22 — Immich: obavezna provjera lokalnih backupa u cutoveru (faza 7D)

Datum: 15. studenoga 2026. (Europe/Zagreb).
Status: **ugrađeno i testirano samo na izoliranom stacku; produkcija nije dirana; cutover nije odobren ni pokrenut.** Nadovezuje se na [17](17-immich-production-cutover.md), [20](20-immich-cutover-safety.md), [21](21-immich-local-backup-plan.md).

## 0. Sažetak

- `steps.sh` sada uključuje `local_backup.sh`. **`s_open` ne može proći bez `lb_gate_open` (uvjet G14)**; isto vrijedi za `s_manual_forward` (drugi put koji otvara promet).
- Vrata rade **prije svake promjene**: nema izmjene `.env`, nema radnje nad kontejnerima, nema upisa u žurnal stanja, izvorna baza se ne dira. Neuspjeh = **HALT, exit 6**, promet ostaje zatvoren, stanje ostaje `DARK_VERIFIED` (ili `HALT_MANUAL`).
- Rehearsal: 174 PASS od 176 zabilježenih; 2 FAIL-a su greške u testu (ispravljene i ponovljene), 0 otvorenih. Jedinični testovi vrata: 30/30 PASS.
- Produkcija ponovno provjerena: kontejneri, `.env`, Compose, ACL baze, 57.627 asseta, 14 backupova i odsutnost `immich-db` nepromijenjeni; `/home/immich-cutover-backups` **ne postoji** (nijedan produkcijski backup nije kopiran).
- G14 u produkciji **ostaje OTVOREN**: kod je spreman, kopije ne postoje. G6 (off-host) ostaje **neispunjen**.

## 1. Što `lb_gate_open` provjerava (sve mora biti PASS; UNKNOWN je FAIL)

| ID | Provjera |
| --- | --- |
| G1 | ime `$EV` = `immich-cutover-$CUTOVER_ID`; direktorij `/home/immich-cutover-backups/$CUTOVER_ID` postoji; markeri `cutover-id` (u `$EV`) i `CUTOVER_ID` (u kopiji) jednaki trenutnom ID-u |
| G2 | `lb_check`: svi `md*` raid1 `[UU]`, 2 aktivna uređaja, stanje clean/active, `mismatch_cnt` 0, `sync_action` idle, nema resynca/recoveryja u `/proc/mdstat`, NVMe `live` i < 70 °C, slobodan prostor na oba datotečna sustava |
| G3 | 4 manifesta (`app-backup.sha256`, `dumps.sha256` u `$EV`; `SHA256SUMS` u `app-backup/` i `dumps/` na `/home`) postoje, svaki redak je `<64 hex>␣␣<ime>`, točan broj redaka bez duplikata; oba manifesta dumpova navode `immich.full.dump` i `immich.no-postgis.dump`; marker `COPIES_DONE` |
| G4 | postoje i nisu prazni: oba dumpa u originalu i u kopiji; Immich backup u originalu i u kopiji |
| G5 | hash koji je zabilježio korak runbooka (`*.dump.sha256`) = hash u manifestu; `lb_verify`: originali i kopije ponovno hashirani prema svojim manifestima i međusobno |

Evidencija: `$EV/local-backup/gate.log` (jedino što gate piše), `BACKUP-GATE-HALT.txt` pri neuspjehu. `OPEN_BEGIN` u žurnalu bilježi hash `gate.log` kad vrata prođu. Simulirani `mdstat` (`LB_MDSTAT`) prihvaća se **samo** u test/rehearsal načinu; u produkciji se odbija. Ručna provjera bez posljedica: `s_backup_gate`.

## 2. Izmjene koda

| Datoteka | Izmjena |
| --- | --- |
| `local_backup.sh` | `lb_gate_open`, `_lb_manifest_ok`; markeri identiteta cutovera pri kopiranju; `lb_check` čita (po potrebi simulirani) mdstat uvijek i traži resync/recovery; način rehearsala (staze samo `/tmp/immich-apptest-*`); sve kritične naredbe izričito provjerene |
| `steps.sh` | `. local_backup.sh` (iza rehearsal `docker()` omotača); `s_open`: vrata odmah nakon provjere stanja, **prije** `trap`, `.env` kopije i prvog upisa u žurnal; `s_manual_forward`: vrata prije bilo koje radnje; novi `s_backup_gate` |
| `tests/local_backup_selftest.sh` | 14 → 30 provjera (vrata, degradirani RAID, resync, pogrešan ID, strani marker, nedostajuća kopija, oštećen dump, neispravan i netočan manifest, nedostajući `COPIES_DONE`, nedostajući dump, odbijanje `LB_MDSTAT` u produkciji); uključeno u `offline_selftest.sh` |
| `rehearsal/` | env: `LB_ROOT` (stand-in za `/home`), sintetički Immich backup; grupe `gG1`–`gG3b` |

## 3. Testirano (izolirani stack, `immich-apptest-*`)

### 3.1 Negativni testovi vrata (13 slučajeva × 2 provjere, grupa gG1)

Za svaki slučaj: `s_open` mora izaći s **6**, poruka `HALT (G14)`, padati mora očekivana provjera, a **ništa se ne smije promijeniti**: SHA-256 `.env`, kontejner servera (Id, `StartedAt`, label rute), bridge i `media-operations` (ostaju zaustavljeni), žurnal i stanje (`DARK_VERIFIED`), ACL i veze izvorne baze, nema `T_open*`/`immich.env.before`/`env.after`.

| Slučaj | Provjera koja pada | Rezultat |
| --- | --- | --- |
| nedostaje kopija dumpova na `/home` | G4 | PASS / PASS |
| nedostaje kopija app backupa | G4 | PASS / PASS |
| oštećen dump na `/home` (1 bajt) | G5b | PASS / PASS |
| oštećen **originalni** dump | G5 | PASS / PASS |
| neispravan redak u manifestu kopije | G3d | PASS / PASS |
| manifest originala s pogrešnim hashem | G5 | PASS / PASS |
| manifest originala nedostaje | G3b | PASS / PASS |
| nedostaje `COPIES_DONE` | G3f | PASS / PASS |
| nedostaje sanitizirani dump u `$EV` | G4 | PASS / PASS |
| marker kopije pripada drugom cutoveru | G1d | PASS / PASS |
| RAID1 degradiran `[U_]` (simulacija) | G2 | PASS / PASS |
| RAID1 resync u tijeku (simulacija) | G2 | PASS / PASS |
| pogrešan `CUTOVER_ID` | G1 | PASS / PASS |

Nakon 13 neuspješnih vrata strogu sondu pisanja izvorne baze (`write_probe.py`, bez allow-liste) prolazi: **nijedan zapis na izvoru**. Kad se sve vrati, `s_backup_gate` ponovno daje PASS.

### 3.2 Cijeli postupak s vratima

- **gG1 (61/61):** STOP-1 (istek pražnjenja) i R1 iz `FREEZING`; F0 `lb_check` + `lb_copy_app_backup` + `lb_verify`; zamrzavanje novim redoslijedom; dump; STOP-3/STOP-4; sanitizacija; F6b `lb_copy_cutover_dumps` + `lb_verify`; restore + validacija; dark launch; 13 negativnih testova; vrata PASS → kvar nakon rute (`ROUTE_LIVE`) → `s_open_abort` (E1–E7 PASS, `ABORT_VERIFIED`) → ponovni dark → **R1 iz `DARK_VERIFIED`** (izvor vraćen, API verify prema zamrznutom baselineu PASS); kopije još vrijede nakon rollbacka.
- **gG2 (33/33):** pravi upload na novu bazu → abort blokiran (E4/E5/E6) → `HALT_MANUAL` → **`s_manual_forward` s točnim tokenom blokiran vratima** kad nedostaje kopija dumpova i kad je RAID1 degradiran (exit 6, server ostaje zaustavljen, ništa promijenjeno) → ispravljeno → GO → `OPEN_CONFIRMED` → 4 odbijanja.
- **gG3 (36/36 + gG3b 1/1):** neispravan dump nije tražen; STOP-5 (izmijenjen snapshot izvora → usporedba pada); STOP-6 (pogrešna lozinka → dark launch pada, žurnal ostaje `VALIDATED`); `s_backup_gate` PASS → **`s_open` → `OPEN_CONFIRMED`**, puni lanac žurnala (`OPEN_BEGIN` nosi hash vrata), hash lanac valjan, 5 odbijanja nakon PONR-a, kopije i dalje verificirane, redovi prazni, API verify PASS, izvor nepromijenjen.
- **g0/g1:** `offline_selftest.sh` (uključuje 30 provjera vrata) PASS; produkcijski način bez `CUTOVER_APPROVED` odbija 17 mutirajućih funkcija (uključujući `lb_copy_app_backup` i `lb_copy_cutover_dumps`) bez poziva dockera; audit log od 3.370 naredbi bez produkcijskih resursa, staza `/home` ni `docker.sock`.

### 3.3 Vrata ne narušavaju `cutstate.py`, `s_open_abort` ni STOP uvjete

- Žurnal: vrata ne upisuju ništa prije prolaza; pri neuspjehu stanje ostaje `DARK_VERIFIED`, broj redaka žurnala nepromijenjen; hash lanac valjan nakon cijelog `gG3`.
- `s_open_abort`: u `DARK_VERIFIED` i dalje odbijen (5); nakon otvaranja koje je prošlo vrata i pada nakon rute daje E1–E7 PASS i `ABORT_VERIFIED`; nakon pravog uploada i dalje HALT (4).
- STOP-1 (R1 iz `FREEZING`), STOP-3 (veličina/ponavljanje dumpa), STOP-4 (skraćen dump: bridge pada, nema sanitiziranog dumpa), STOP-5, STOP-6 provjereni; STOP-8 je u dokumentu 17 preimenovan u HALT (G14).

### 3.4 Ograničenja (iskreno)

- **RAID1 degradacija je simulirana** datotekom `mdstat`; stvarna degradacija nije izazivana. Stvarni `lb_check` na hardveru ovog hosta (RAID1, NVMe, temperatura, prostor) je u rehearsalu prošao (samo čitanje).
- `/home` je u rehearsalu zamijenjen direktorijem `/tmp/immich-apptest-*/lb-home`; produkcijski `/home` nije korišten.
- STOP-3 je u ovoj fazi provjeren samo kao odbijanje ponovnog `s_dump_source` (granica veličine provjerena u fazi 6B); SMART podaci i dalje nisu dostupni (O17).
- Vrata dokazuju da kopije **postoje i da su jednake originalu**, ne da se iz njih može restaurirati; restore iz kopije nije dio ovog testa.

## 4. Ažurirana dokumentacija

Doc 17: napomena revizije 7D, F6b (STOP-8 sada tvrdo vrata), F10 (vrata prije svake promjene, exit 6), STOP tablica (HALT G14), G14, K18, tablica datoteka. Doc 21: G14 se sada provjerava kodom (vidi odjeljak 1).

## 5. Što ostaje za produkcijsko prebacivanje

1. **Odobrenje O16 i izvršenje kopiranja** (`lb_copy_app_backup`, `lb_copy_cutover_dumps`, `lb_verify`): bez toga vrata (G14) ne prolaze. Nijedna produkcijska kopija još ne postoji.
2. **Pisano prihvaćanje rizika lokalne RAID1 zaštite** (G6 ostaje neispunjen; doc 21, odjeljak 6).
3. Odluka O17 (instalacija `smartmontools`) prije prozora, ako se želi SMART baseline.
4. Iz doc 19/20: **G10** privremeni API ključevi i preflight s ključevima; **G2, G7, G8, G3, G11** (pragovi uz recall 0,90 za `face_index`, termin, retencija, izmjena `.env`/recreate, osoba za OIDC, obavijest korisnicima i monitoring); **O14/O15** (tko izdaje token nakon HALT-a; dodatni start servera u `s_freeze`).
5. Neprobano jer postoji samo u produkciji: Traefik, `media-operations` i bridge tijekom cutovera, OIDC, kanarski testovi, stvarni promet, stvarni kvar diska. Preporuka: odobrena "proba bez otvaranja" (`s_freeze` → … → `s_dark_launch` → `s_rollback_r1`) na produkciji.

## 6. Što je izvršeno

Samo izolirani stack (`immich-apptest-*`), uklonjen nakon testova; dokazi (privatni, 0700) u `/opt/stacks/data/backups/immich-rehearsal-20261115t110955z-eca24b`. Na produkciji samo čitanje (stanje kontejnera, datumi datoteka, ACL, broj asseta, popisi). Izmijenjene datoteke: `immich-cutover/local_backup.sh`, `steps.sh`, `tests/*`, `rehearsal/*`, dokumenti 17, 21 (napomena), 22. Nije kopiran nijedan produkcijski backup, nije stvoren `/home/immich-cutover-backups`, nije pokrenut `immich-db`, zaustavljen Immich, mijenjani baze, `.env`, Compose ili API ključevi; nijedan backup obrisan; cutover nije pokrenut.

**Stati ovdje. Produkcijska migracija nije odobrena.**
