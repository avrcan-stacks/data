# 28 — Immich: zasebno odobrenje za lokalni backup (faza 8F)

Datum: 15. studenoga 2026. (Europe/Zagreb).
Status: **implementirano i testirano samo u izoliranom okruženju (/tmp, sintetički podaci). F0 NIJE izvršen na produkciji, produkcijski backup nije kopiran, `CUTOVER_APPROVED` nije postavljan.** Nadovezuje se na [27](27-immich-local-backup-result.md).

## 0. Potvrda

**Novi token `LB_BACKUP_ONLY_APPROVED=F0:<CUTOVER_ID>` omogućuje isključivo `lb_copy_app_backup` (F0). Sve ostale produkcijske operacije ostaju zaključane iza nepromijenjenog `CUTOVER_APPROVED`.**

## 1. Izmjena (jedna datoteka: `immich-cutover/local_backup.sh`)

- `_lb_gate [F0]`: u produkcijskom načinu `lb_copy_app_backup` (jedini koji prosljeđuje argument `F0`) prihvaća `LB_BACKUP_ONLY_APPROVED` ako je **točno** `F0:$CUTOVER_ID` i `CUTOVER_ID` ima najmanje 6 znakova. Inače odbija (token `1`, drugi ID, drugi korak npr. `F6b:<id>`, goli ID, prazan ili prekratak ID).
- Ako token nije postavljen, vrijedi staro ponašanje: traži se `CUTOVER_APPROVED=$CUTOVER_ID` (logika nepromijenjena; poruka greške sada dodatno spominje token za F0).
- `lb_copy_cutover_dumps` (F6b) poziva `_lb_gate` **bez** argumenta, pa token ignorira. `lb_verify`, `lb_check`, `lb_gate_open` su samo čitanje i ne trebaju odobrenje.
- **`steps.sh` nije mijenjan** (provjereno: jedine izmijenjene datoteke su `local_backup.sh` i njegov test); njegov `_gate` i dalje gleda isključivo `CUTOVER_APPROVED`.

## 2. Testovi (`tests/local_backup_selftest.sh`, +16 provjera, ukupno 46 PASS; `offline_selftest.sh` PASS)

Svi u produkcijskom načinu zaštite (bez `LB_TEST`), ali s izoliranim stazama u `/tmp` (test odbija rad ako staza nije u `/tmp`); `docker` i `python3` zamijenjeni su stubovima koji bilježe svaki poziv.

| Test | Rezultat |
| --- | --- |
| nema tokena → odbijeno, ništa stvoreno | PASS |
| token za drugi `CUTOVER_ID` → odbijeno | PASS |
| token `1` → odbijeno | PASS |
| token za drugi korak (`F6b:<id>`) → odbijeno | PASS |
| goli ID bez prefiksa `F0:` → odbijeno | PASS |
| prekratak ID (< 6) uz odgovarajući token → odbijeno | PASS |
| **F0 token ne otključava `lb_copy_cutover_dumps` (F6b)**, zahtijeva `CUTOVER_APPROVED` | PASS |
| **samo s F0 tokenom svih 16 mutirajućih funkcija odbijeno** (`s_prepare_target`, `s_freeze`, `s_dump_source`, `s_bridge_sanitize`, `s_bridge_cleanup`, `s_restore_target`, `s_validate_target`, `s_dark_launch`, `s_open`, `s_open_abort`, `s_manual_forward`, `s_manual_rollback_accept_loss`, `s_rollback_r1`, `s_unfence`, `s_target_reset_after_rollback`, `lb_copy_cutover_dumps`); nijedan poziv dockera ni pythona | PASS |
| pogrešan `CUTOVER_APPROVED` i dalje odbijen (logika nepromijenjena) | PASS |
| **uspjeh s tokenom** (izolirano): kopija izrađena | PASS |
| SHA-256 kopije = izvor | PASS |
| oba manifesta (`$EV/local-backup/app-backup.sha256`, `SHA256SUMS` uz kopiju) valjana i nose hash izvora | PASS |
| prava: datoteka `0400`, direktoriji `0700`, marker `CUTOVER_ID` | PASS |
| izvor nepromijenjen i ništa drugo nije stvoreno/uklonjeno u njegovom direktoriju | PASS |
| `lb_verify` nakon kopije (bez odobrenja) | PASS |
| ponovni F0 u isti ID odbijen (nema prepisivanja) | PASS |

Napomena: uspješni test izvodi pravi `lb_check` (samo čitanje stanja ovog hosta: RAID1, NVMe, prostor); kopiranje ide samo između sintetičkih `/tmp` direktorija.

## 3. Kako se koristi (kad vlasnik izda odobrenje za F0)

```bash
cd /opt/stacks/data/immich-cutover
export CUTOVER_ID="$(date -u +%Y%m%dt%H%M%Sz)"            # jedinstven, ≥ 6 znakova
export EV=/opt/stacks/data/backups/immich-cutover-$CUTOVER_ID; umask 077; mkdir -p -m 700 "$EV"
source ./local_backup.sh
lb_check                                                    # bez odobrenja
export LB_BACKUP_ONLY_APPROVED=F0:$CUTOVER_ID              # vrijedi samo za F0; NE postavljati CUTOVER_APPROVED
lb_copy_app_backup && lb_verify
unset LB_BACKUP_ONLY_APPROVED
```
Isti `CUTOVER_ID` mora se koristiti u cijelom cutoveru (G14 provjerava marker); token vrijedi samo za taj ID.

## 4. Status

- G14 ostaje **OTVOREN** (nema ni F0 ni F6b); G6 neispunjen; ostalo kao u [26](26-immich-api-keys-ready.md) i [27](27-immich-local-backup-result.md).
- Sljedeći korak je izričita izjava vlasnika da se izvrši F0 s ovim tokenom (jedan `CUTOVER_ID`).

## 5. Što je izvršeno

Izmijenjeno: `immich-cutover/local_backup.sh`, `tests/local_backup_selftest.sh`, oznaka u `tests/offline_selftest.sh`, dokumenti 17, 27, 28. Testovi su pisali samo u privremeni direktorij u `/tmp` (obrisan). Nije: izvršen F0 na produkciji, kopiran backup, postavljen `CUTOVER_APPROVED` ili token (u mojoj ljusci su neodređeni), zaustavljen ni restartan kontejner, dirnuta baza, `.env`, Compose ili API ključ, pokrenut `immich-db` ni cutover. `/home/immich-cutover-backups` ne postoji.

**Stati ovdje. Produkcijski cutover nije odobren.**
