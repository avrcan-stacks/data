# 21 — Immich: plan lokalne backup zaštite (faza 7C)

Datum: 15. studenoga 2026. (Europe/Zagreb).
Status: **priprema; na produkciji nije ništa kopirano ni mijenjano; cutover nije pokrenut.** *(Faza 7D, [22](22-immich-backup-gate.md): uvjet G14 je sada tvrdo vrata u `s_open` i `s_manual_forward`.)* Nadovezuje se na [17](17-immich-production-cutover.md), [19](19-immich-production-readiness.md), [20](20-immich-cutover-safety.md).

## 0. Odluka i sažetak

Vlasnik je odlučio: migracija se izvodi na postojećem serveru s RAID1 diskovima, **bez off-host backupa**. Zato:

- **G6 (off-host kopija) ostaje NEISPUNJEN.** Ne označava se ispunjenim; off-host kopija ne postoji i ne planira se.
- G6 se u GO/NO-GO uvjetima **zamjenjuje izričito prihvaćenim rizikom** lokalne RAID1 zaštite (odjeljak 6) i novim uvjetom **G14**: zdrav RAID1 + druga kopija na `/home` s jednakim SHA-256 prije T0 i prije otvaranja prometa.
- Pripremljeni su `immich-cutover/local_backup.sh` (kopiranje i provjera) i `tests/local_backup_selftest.sh` (14/14 PASS, samo na sintetičkim datotekama u `/tmp`). **Ništa nije kopirano s produkcije.**

## 1. RAID1 i diskovi (samo čitanje, 15.11.2026.)

| Provjera | Nalaz |
| --- | --- |
| Polja | `md0` (swap 4 GiB), `md1` (`/boot` 1 GiB), `md2` (`/` 2,0 TB), `md3` (`/home` 1,5 TB): svi `raid1`, `[2/2] [UU]`, 2 aktivna uređaja, 0 neispravnih, 0 rezervnih; sva polja na istom paru `nvme0n1` + `nvme1n1` |
| Stanje | `md0`, `md1`, `md3` `clean`; `md2` `active` (normalno, na njemu se piše); `sync_action` = `idle` na svima, nema resynca ni oporavka |
| Konzistentnost | `mismatch_cnt` = 0 (`md2`, `md3`); zadnji `data-check` svih polja 3.–4.11.2026., sljedeći planira `mdcheck_start.timer` 3.12.2026. |
| Diskovi | 2 × Samsung MZQL23T8HCLS (3,5 TB NVMe), isti firmware `GDC5A02Q`; kontroler `live`; temperatura 41 °C oba (maks. 79, kritično 82) |
| Kernel log (30 dana) | bez NVMe grešaka/timeouta, bez `degraded`/`Disk failure`, bez I/O ili EXT4 grešaka (jedine poruke `memory limit failcnt` su cgroup, nepovezane) |
| Datotečni sustavi | `/` i `/home`: `clean`, ext4 |
| **Ograničenje** | `smartctl` i `nvme-cli` **nisu instalirani**: SMART brojači (istrošenost, media errors, unsafe shutdowns) nisu čitljivi. Zdravlje je procijenjeno samo prema `md` stanju, stanju kontrolera, temperaturi i logovima. Instalacija `smartmontools` mijenja pakete hosta, pa nije izvršena (odluka O17, preporučeno prije prozora) |

Zaključak: RAID1 je zdrav i potpuno sinkroniziran; stvarno zdravlje NAND-a nije potvrđeno SMART-om.

## 2. Prostor

| Datotečni sustav | Slobodno | Potrebno za plan |
| --- | --- | --- |
| `/` (`/opt/stacks/data`, Immich backupovi, `immich-postgres`) | 427 GiB (78 % zauzeto; 11 % inodea) | dumpovi u `$EV` ≈ 0,7 GiB + `immich-db` + bridge + rezerva: ≥ 96 GiB (doc 17, H1) |
| `/home` (`md3`) | 1.454 GiB (1 % zauzeto; 102 M inodea) | druga kopija ≈ 1,1 GiB (355 MB Immich backup + 354 MB `immich.full.dump` + ≈ 350 MB `immich.no-postgis.dump`); skripta traži ≥ 50 GiB slobodno na oba |
| `/opt/stacks/data/backups` | 6,1 GB (uključuje ranije privatne dokaze, sačuvani) | nepromijenjeno |
| Immich backupovi | 14 datoteka, 4,9 GB, najnoviji `…20261115T020000…pg16.13.sql.gz` (355 MB) | ostaju na mjestu; kopiraju se, ne premještaju |

`/home` je prazan osim `parkschloss` (36 KB) i `ubuntu`; koristi se novi direktorij `/home/immich-cutover-backups/<CUTOVER_ID>/` (0700, root).

## 3. Plan kopija

| Kopija | Što | Gdje | Kada |
| --- | --- | --- | --- |
| **Glavna** (postojeća) | Immich 02:00 backupi (14 dana); `immich.full.dump` i `immich.no-postgis.dump` u `$EV` | `/opt/stacks/immich/docker-data/library/backups`, `/opt/stacks/data/backups/immich-cutover-<ID>` | nastaje redovno / u F5, F6 |
| **Druga (`/home`)**, L0 | najnoviji Immich backup (`.sql.gz`) | `/home/immich-cutover-backups/<ID>/app-backup/` | F0 (T-1 d), bez prekida |
| **Druga (`/home`)**, L1 | `immich.full.dump` (dump zamrznutog izvora) + `immich.no-postgis.dump` | `/home/immich-cutover-backups/<ID>/dumps/` | F6b, odmah nakon sanitizacije, prije restorea |

Baza `postgis/immich` je izvor i **nikad se ne dira**: kopije se rade s datoteka (backup i dumpovi), a ne iz baze. Dump u F5 već je postojeći korak runbooka (`pg_dump` samo čita).

Svojstva `local_backup.sh`: novi direktorij po cutoveru (postojeći se odbija, nema prepisivanja, `noclobber`); samo `cp -p`, nikad `mv`/`rm`; izvorna datoteka se hashira prije i poslije kopiranja (nije se promijenila); `gzip -t` izvornika i kopije; dump se kopira tek ako je jednak hashu koji je zabilježio korak runbooka; TOC (`pg_restore --list`, preko kontejnera `postgis`, bez pristupa bazi) kopije jednak je TOC-u originala; kopije `0400`, direktorij `0700`; neobvezni `chattr +i` (`LB_IMMUTABLE=1`); u produkcijskom načinu traži `CUTOVER_APPROVED=$CUTOVER_ID`.

## 4. SHA-256 provjera integriteta obiju kopija

- **Manifesti:** originali: `$EV/local-backup/app-backup.sha256`, `dumps.sha256` (izvan backup direktorija, da se on ne mijenja); kopije: `SHA256SUMS` uz same datoteke u `/home`.
- **`lb_verify`** (samo čitanje): svaka datoteka obje strane ponovno se hashira prema svom manifestu i **međusobno** (original == kopija). Izlaz `lb_verify OK` ili `FAILED` (exit 1).
- **Kada:** nakon L0 i L1, neposredno prije F10, T+24 h, tjedno do dana 7, te prije bilo kakve odluke o brisanju izvora. Svaki FAIL = STOP; ne ponavlja se kopiranje preko postojećeg, nego se istražuje (nova kopija ide u novi direktorij uz odobrenje).
- **Testirano (sintetički podaci, 14/14 PASS):** ispravna kopija, odbijanje prepisivanja (backup i dumpovi), otkrivanje izmijenjene kopije, otkrivanje izmijenjenog originala, odbijanje dumpa koji se razlikuje od zabilježenog hasha, odbijanje pri nedovoljno prostora, odbijanje oštećenog gzipa, odbijanje starijeg backupa od 26 h, odbijanje bez `CUTOVER_APPROVED`, odbijanje `LB_TEST` izvan `/tmp`, izvor nepromijenjen. Test je pronašao da se na `errexit` u tom kontekstu ne može osloniti, pa su svi kritični koraci zaštićeni izričitim provjerama.
- Provjera stvarnog hardvera `lb_check` izvršena je samo čitanjem i prolazi (RAID1 `[UU]`, `mismatch_cnt` 0, `idle`, NVMe `live`, 41 °C, prostor).

## 5. Izmjene runbooka (u doc 17, već upisane; ništa se ne izvršava dok nema odobrenja)

F0 točka 4 (off-host zamijenjen s `lb_check` + `lb_copy_app_backup` + `lb_verify`); novi korak **F6b** (`lb_copy_cutover_dumps && lb_verify`) uz **STOP-8**; G6 neispunjen + novi **G14**; **K1** uključuje `lb_check`; novi **K18** (obje kopije verificirane, RAID1 bez degradacije tijekom prozora); **O11** ukinut kao off-host, novi **O16** (kopija na `/home`); odjeljak 7 (retencija) koristi drugu kopiju umjesto off-host. `s_open` nije mijenjan; provjera `COPIES_DONE` i `lb_verify OK` je stavka kontrolne liste F9 (ako se želi tvrdo vrata u `s_open`, to je izmjena koda koja traži novi rehearsal).

## 6. Prihvaćeni rizik (izričito)

Lokalna RAID1 zaštita i druga kopija na `/home` štite od: kvara jednog diska, greške ili oštećenja datotečnog sustava `/` ili glavnog backup direktorija, slučajnog brisanja ili prepisivanja jedne kopije, grešaka u cutoveru koje se vide odmah (R1, ponovni restore iz dumpa).

**Ne štite od** (vlasnik ih prihvaća odlukom o izostanku off-host backupa):
1. gubitka cijelog hosta ili oba NVMe diska istodobno (oba polja `md2` i `md3` leže na istom paru fizičkih diskova, pa je `/home` odvojen samo datotečnim sustavom, ne hardverom): **svi backupovi, izvor i nova baza nestaju zajedno**;
2. požara, krađe, pogreške pružatelja, ransomwarea ili kompromitacije hosta (root vidi sve kopije);
3. logičke pogreške koja se RAID1 zrcali na oba diska (RAID1 nije backup);
4. tihog oštećenja koje se otkrije kasnije od 14 dana (rotacija Immich backupa), osim ako se prije toga ne sačuva kopija;
5. nedostupnosti SMART podataka (odjeljak 1): rano upozorenje na istrošenost diska ne postoji dok se ne instalira alat.

Posljedica: u slučaju katastrofalnog gubitka hosta Immich baza ne može se vratiti iz backupa; mogu se ponovno stvoriti samo ako postoje mediji i migracija od početka (metapodaci, albumi, osobe, embeddingi i postavke bi se izgubili). Mediji (`/data/upload`, `thumbs`, `encoded-video`) nisu pokriveni ovim DB planom.

Ublažavanja unutar odluke (preporuke, nisu obvezne): instalirati `smartmontools` i zabilježiti SMART stanje prije i poslije prozora (O17); ne planirati prozor dok traje `mdcheck`; `LB_IMMUTABLE=1`; zadržati drugu kopiju najmanje 30 dana (ne samo 7); ne mijenjati disk konfiguraciju u prozoru.

## 7. GO/NO-GO: što se mijenja

| ID | Prije | Sada |
| --- | --- | --- |
| G6 | off-host kopija prije prozora, OTVOREN | **NIJE ISPUNJEN** i neće biti; zamijenjen G14 + izričito prihvaćen rizik iz odjeljka 6 (zahtijeva pisano prihvaćanje vlasnika u zapisniku GO odluke) |
| G14 (novo) | — | `lb_check` OK; `lb_copy_app_backup` i `lb_verify` OK prije T0; `lb_copy_cutover_dumps` i `lb_verify` OK prije F8/F10; **OTVOREN (pripremljeno)** |
| K1 | disk, backup < 26 h | + `lb_check` OK |
| K18 (novo) | — | obje kopije verificirane, TOC kopije = original, RAID1 bez degradacije u prozoru |
| O11 | odredište off-host | ukinuto odlukom vlasnika |
| O16 (novo) | — | kopiranje na `/home` (~1,1 GiB, novi direktorij) i neobvezni `chattr +i` |
| O17 (novo, preporuka) | — | instalacija `smartmontools` radi SMART baselinea prije i poslije prozora |

## 8. Preostali blokeri za produkcijski GO

1. **G14 nije izvršen**: kopije na `/home` još ne postoje (traži O16).
2. Pisano prihvaćanje rizika iz odjeljka 6 u zapisniku GO odluke (G6 ostaje neispunjen).
3. Nepromijenjeno iz doc 19/20: **G10** privremeni ključevi, **G2/G7/G8/G3/G11** (pragovi uz recall 0,90, termin, retencija, `.env`/recreate, OIDC osoba, obavijest i monitoring), **O14/O15** (tko izdaje token nakon HALT-a; dodatni start servera u `s_freeze`).
4. Neprobano jer postoji samo u produkciji (Traefik, `media-operations` i bridge u cutoveru, OIDC, kanarski testovi, stvarni promet).

## 9. Što je izvršeno

Samo čitanje: `/proc/mdstat`, `mdadm --detail`, `/sys/block/md*/md`, `/sys/class/nvme`, `dmesg`/`journalctl`, `tune2fs -l`, `df`, popisi direktorija; `lb_check` (čita stanje). Nova datoteka `local_backup.sh` i testovi izvršeni su isključivo na sintetičkim podacima u `/tmp` (scratchpad). Izmijenjeni dokumenti: 17 i ovaj. Nije kopirana nijedna produkcijska datoteka, nije kreiran `/home/immich-cutover-backups`, nije dirana baza `postgis/immich`, backupovi, kontejneri, `.env`, Compose, ključevi; nije instaliran nijedan paket; cutover nije pokrenut.

**Stati ovdje. Produkcijska migracija nije odobrena.**
