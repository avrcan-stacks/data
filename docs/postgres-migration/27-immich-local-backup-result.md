# 27 — Immich: lokalni sigurnosni backup, rezultat (faza 8E)

Datum: 15. studenoga 2026. (Europe/Zagreb).
Status: **kopija NIJE napravljena: korak F0 je blokiran zaštitom `CUTOVER_APPROVED`, koju nisam zaobilazio.** Provjere prije kopiranja prošle su. Produkcija nije zaustavljena ni promijenjena.

## 0. Sažetak

| Pitanje | Odgovor |
| --- | --- |
| Je li kopija izrađena? | **Ne.** `/home/immich-cutover-backups` ne postoji. |
| Zašto? | `lb_copy_app_backup` u produkcijskom načinu traži `CUTOVER_APPROVED=$CUTOVER_ID`, a vi ste izričito zabranili zaobilaženje te zaštite i postavljanje `CUTOVER_APPROVED`; funkcija je odbila rad (poruka niže). |
| `lb_check` | **OK** |
| `lb_verify` | **nije izvršen** (nema kopije; provjera bi bez nje bila prazna) |
| G14 | **OTVOREN** (ni F0 ni F6b nisu gotovi) |
| Produkcija | nije zaustavljena ni promijenjena |

## 1. Provjere prije kopiranja (zadatak 1; sve prošle, pa je blokada samo odobrenje)

| Provjera | Nalaz |
| --- | --- |
| RAID1 | `md0`–`md3`: `clean` (`md2` `active`), `[UU]`, `mismatch_cnt` 0, `sync_action` idle, nema resynca |
| NVMe | `nvme0` i `nvme1` `live`, **41 °C** oba (prag 70) |
| Prostor | `/home` 1.454 GiB slobodno (prag 50), `/` 426 GiB |
| Drugi datotečni sustav | `/home` je na `md3`, glavni backupovi na `md2` (PASS) |
| SMART | nedostupan (`smartmontools` nije instaliran; O17), procjena samo po `md`/NVMe stanju i temperaturi |
| `lb_check` | **`lb_check OK`**, zapis: `$EV/local-backup/f0-lb_check.txt` |

## 2. Izvorni backup (zadatak 3, samo čitanje)

| Polje | Vrijednost |
| --- | --- |
| Datoteka | `/opt/stacks/immich/docker-data/library/backups/immich-db-backup-20261115T020000-v3.3.5-pg16.13.sql.gz` |
| Veličina / starost | 355.181.926 B (≈ 339 MiB) / 11 h (granica 26 h) |
| Provjera | `gzip -t` OK; potpuni Immich backup (14 datoteka u direktoriju, ova je najnovija) |
| **SHA-256** | `25b7780f666822c99bc8bcfc50d3e9c5851f203f29d7149b65d429821d73b0fd` |

Hash je izračunan samo čitanjem datoteke (privremeni zapis `f0-source-sha256-precheck.txt` u privatnoj evidenciji; to **nije** službeni manifest `app-backup.sha256` koji piše `lb_copy_app_backup`). Datoteka nije mijenjana, premještana ni brisana; direktorij i dalje ima 14 datoteka.

## 3. Blokada (zadatak 4)

`CUTOVER_ID` za ovaj pokušaj: `f0-20261115t124512z` (evidencija `/opt/stacks/data/backups/immich-cutover-f0-20261115t124512z`, 0700, bez tajni). Poziv `lb_copy_app_backup` bez `CUTOVER_APPROVED` vratio je:

> `production copy refused: export CUTOVER_APPROVED=f0-20261115t124512z only after the written approval (O16)`

Ništa nije stvoreno na `/home`. `CUTOVER_APPROVED` nisam postavljao, ni na `1` ni na `CUTOVER_ID`, jer je to ista zaštita koja u `steps.sh` otključava **sve** mutirajuće korake cutovera (`s_freeze`, `s_open`, …); postavljanje u istoj ljusci proširilo bi odobrenje preko onoga što ste odobrili (samo F0).

*(Faza 8F, [28](28-immich-backup-only-approval.md): prijedlog je implementiran.)*

## 4. Prijedlog: poseban "backup-only" način odobrenja (traži vašu potvrdu; nije implementirano)

Problem: postoji samo jedna oznaka odobrenja (`CUTOVER_APPROVED`) i ona otključava i kopiranje i cutover. Prijedlog za `local_backup.sh` (jedna mala izmjena i testovi):

- Nova varijabla **`LB_BACKUP_ONLY_APPROVED=F0:<CUTOVER_ID>`** (token mora sadržavati točan ID i oznaku koraka, npr. `F0:f0-20261115t124512z`). Prihvaća je **samo** `lb_copy_app_backup` (F0).
- **Ne otključava** `steps.sh`: `_gate` u `steps.sh` i dalje gleda isključivo `CUTOVER_APPROVED`, pa `s_freeze`/`s_open`/… ostaju zaključani. Nema zamjene za `CUTOVER_APPROVED`, ne smije biti `1`, token drugog ID-a ili drugog koraka odbija se.
- `lb_copy_cutover_dumps` (F6b) **ostaje** pod `CUTOVER_APPROVED` (dumpovi nastaju tek u prozoru).
- Dodati testove: bez tokena odbijeno; token za krivi ID odbijen; `LB_BACKUP_ONLY_APPROVED` ne otključava `s_freeze`/`lb_copy_cutover_dumps`; `1` odbijen; s točnim tokenom `lb_copy_app_backup` radi i ne dira izvor.

Ako je odobrite, izvršit ću izmjenu, testove, pa F0 s tokenom `F0:<novi CUTOVER_ID>` koji ćete vi potvrditi u poruci. Alternativa: vi sami u svojoj ljusci izvršite F0 s `CUTOVER_APPROVED` za jednu naredbu (`CUTOVER_APPROVED=<ID> bash -c 'source immich-cutover/local_backup.sh; lb_copy_app_backup && lb_verify'`), što ne širi odobrenje na moju sesiju.

## 5. G14 i preostalo

- **G14 OTVOREN.** Čak i kad F0 prođe, G14 nije zadovoljen dok ne postoje i kopije zamrznutih dumpova iz F6b te `lb_gate_open` PASS neposredno prije `s_open`. G6 (off-host) ostaje neispunjen; treba pisano prihvaćanje rizika lokalne RAID1 zaštite.
- Ostalo iz [26](26-immich-api-keys-ready.md): G2, G7, G8, G3, G11 (pragovi, termin, retencija, `.env`/recreate, OIDC osoba, obavijest korisnicima i monitoring), O14/O15, preporuke (brisanje kopija ključeva u VS Code povijesti, `chmod 600` na `.env`, jačanje `POSTGRES_PASSWORD`, `smartmontools`), neprobano samo-produkcijsko (Traefik, bridge i `media-operations`, OIDC, kanarski testovi).

## 6. Potvrda: produkcija nije zaustavljena ni promijenjena

Samo čitanje (`/proc/mdstat`, `mdadm --detail`, `/sys`, `df`, `stat`, `gzip -t` i `sha256sum` nad backupom) i jedan odbijeni poziv zaštićene funkcije. Nije zaustavljen ni restartan Immich, bridge, Redis ni PostgreSQL; nije pokrenut `immich-db`, `s_freeze`, `s_open` ni drugi korak cutovera; baze, `.env`, Compose i API ključevi nepromijenjeni; nijedan backup nije kopiran, premješten ni obrisan; nijedna tajna nije ispisana.

**Stati ovdje. Produkcijski cutover nije odobren.**
