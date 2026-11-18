# 42 — Immich drugi pokušaj: F0 završen

Datum: 15. studenoga 2026., UTC. **Izvršen je samo odobreni F0. F2, reset cilja i produkcijska migracija nisu pokrenuti.**

Pročitani dokumenti [21](21-immich-local-backup-plan.md), [22](22-immich-backup-gate.md), [28](28-immich-backup-only-approval.md), [29](29-immich-f0-production-backup.md) i [41](41-immich-second-attempt-readiness.md). Korišten je postojeći, neizmijenjeni `immich-cutover/local_backup.sh`.

## Identitet, izvor i kopija

| Stavka | Rezultat |
| --- | --- |
| Novi CUTOVER_ID | **`20261115t150714z`** |
| Novi `$EV` | `/opt/stacks/data/backups/immich-cutover-20261115t150714z` |
| Nova backup lokacija | `/home/immich-cutover-backups/20261115t150714z/` |
| Izvor | `/opt/stacks/immich/docker-data/library/backups/immich-db-backup-20261115T020000-v3.3.5-pg16.13.sql.gz` |
| Kopija | `/home/immich-cutover-backups/20261115t150714z/app-backup/immich-db-backup-20261115T020000-v3.3.5-pg16.13.sql.gz` |
| Veličina, obje datoteke | **355.181.926 B** |
| SHA-256, izvor prije/poslije i kopija | **`25b7780f666822c99bc8bcfc50d3e9c5851f203f29d7149b65d429821d73b0fd`** |
| Starost pri prechecku | **14,39 h**, manje od 26 h; najnoviji odgovarajući v3.3.5/PG16 aplikacijski backup po mtime. |
| gzip / usporedba | `gzip -t` izvora i kopije PASS; neovisni `cmp --silent` rc 0, bajt-za-bajt jednako. |

Obje nove putanje prije rada nisu postojale, uključujući provjeru symlinkova. Prethodni žurnal bio je valjan `ROLLED_BACK`, server healthy na `postgis/immich`, javni ping HTTP 200. Prethodni dokazi i konfiguracija provjereni su prije kopiranja. Backup je odabran iz aplikacijskog direktorija; dumpovi i `/home` kopija prvog pokušaja nisu korišteni kao izvor.

## Izvršenje i provjere

Prvi `date -u`: **15:23:45Z**. Kopiranje i `lb_verify`: **15:25:02–15:25:16Z**, oko **14 s**. Neovisne završne provjere prošle su u **15:26:07Z**.

- `lb_check`: **rc 0 / OK** prije kopiranja i ponovno unutar `lb_copy_app_backup`. RAID1 `md0`–`md3` prošli provjere aktivnih uređaja, stanja, `mismatch_cnt=0`, `sync_action=idle` i odsutnosti degradacije/resynca. Oba NVMe uređaja `live`, temperatura **41,85 °C** (prag 70 °C). Slobodno približno **422 GiB na /** i **1453 GiB na /home** (prag 50 GiB); različiti filesystemi. SMART brojači i dalje nisu dostupni, kao dokumentirano u 21.
- `lb_copy_app_backup`: **rc 0 / OK**. Samo novi F0 token `LB_BACKUP_ONLY_APPROVED=F0:20261115t150714z`; `CUTOVER_APPROVED` nije postavljen.
- `lb_verify`: **rc 0 / OK**. Original, kopija i oba manifesta nose isti hash. Izlaz `INFO no dump manifest yet` očekivan je za F0 i nije potvrda F6b.
- Oba operativna tokena potvrđeno odsutna nakon `unset LB_BACKUP_ONLY_APPROVED`. EXIT trap uklanja uski token i pri grešci. Izvršni proces završio je **rc 0**.
- Neovisni postcheck: **157/157 PASS, rc 0**. Potvrđeni sadržaj, veličina, gzip, manifesti, markeri, prava, svi postojeći aplikacijski backupovi, prethodni dokazi, kontejneri i HTTP dostupnost.

Manifest `$EV/local-backup/app-backup.sha256` i `app-backup/SHA256SUMS` uz kopiju identični su, s jednim retkom točnog hasha i imena. `$EV/CUTOVER_ID`, `$EV/local-backup/cutover-id` i marker `/home/.../CUTOVER_ID` sadrže točno novi ID.

| Putanja / objekt | Prava i vlasnik |
| --- | --- |
| `/home/immich-cutover-backups`, novi ID direktorij, `app-backup` | **0700, root:root** |
| Kopija `.sql.gz` i njezin `SHA256SUMS` | **0400, root:root** |
| Novi `$EV` i `$EV/local-backup` | **0700, root:root** |
| Markeri identiteta i manifest originala | **0600, root:root** |
| Nova privatna evidencija | **0600, root:root** |

## Očuvanost produkcije i prvog pokušaja

Izvorni aplikacijski direktorij i dalje ima **14 backupova**. Za sve su prije/poslije jednaki skup imena, SHA-256, veličina, mtime, vlasnik i prava. Ništa nije premješteno, prepisano ili obrisano.

Svih **107 prethodno popisanih datoteka** prvog pokušaja, njegovih `/home` kopija i konfiguracije ostalo je hashom identično. Žurnal `20261115t130331z`: **ROLLED_BACK**, 9 zapisa, isti tip lanca `c25c344676e5145e9b9cf23a5f74ed40410a5d695adc43a68593e29b3ccb85da`.

Osam pregledanih produkcijskih kontejnera zadržalo je isti Id, StartedAt, restart count i Running stanje. Immich je healthy na **`postgis`**, javni ping **HTTP 200**. Redis nije restartan; postojeći `immich-db` nije resetiran niti mijenjan. Izvršene su samo datotečne F0 operacije i read-only očitanja. Nije izvršen SQL, mutirajući API, stop/restart/recreate, F2, freeze, target reset, F9/F10 ni promjena `.env`, Composea ili Traefika. Produkcijski podaci ostaju dostupni normalnim korisničkim operacijama; ova provjera ne tvrdi da je aktivna aplikacija zamrznuta.

## G14 i završno stanje

**F0 je završen. G14 ostaje PENDING:** za novi ID još ne postoje `dumps/`, manifest dumpova ni `COPIES_DONE`; F6b nije izvršen. Potrebni su novi frozen dumpovi F5/F6, njihove nove kopije F6b i zasebni G14 PASS prije F10. Stari dumpovi ne prenose se u novi pokušaj. G6 (off-host backup) ostaje neispunjen prema postojećoj odluci.

Novi migracijski žurnal nije inicijaliziran: nema `state` ni `state.log`, `cutstate.load` daje `NONE`, ne `PREPARED`. Markeri novog F0 ne označavaju pripremljenu ciljnu bazu.

Privatni dokazi nalaze se u novom `$EV`: `f0-precheck.json`, `f0-execution.out`, `f0-lb-check.out`, `f0-nvme.json`, `f0-postcheck.json`, `f0-postcheck.out`, `f0-run.sh` i `f0-postcheck.py`. Izvorna evidencija pripreme izvršenja: `/opt/stacks/data/backups/immich-f0-audit-20261115t150714z-152430`.

Ključne izvršene operacije: `date -u`, `docker inspect`, GET javnog pinga, provjera hash lanca postojećim `cutstate.load`, `gzip -t`, SHA-256, `lb_check`, **`lb_copy_app_backup`**, **`lb_verify`**, `unset LB_BACKUP_ONLY_APPROVED`, `cmp --silent` i neovisne provjere datoteka/prava. Nisu korišteni API ključevi niti ispisane tajne.

**Stajem nakon F0. F2 i reset ciljne baze nisu izvršeni niti odobreni ovim F0 nalogom.**
