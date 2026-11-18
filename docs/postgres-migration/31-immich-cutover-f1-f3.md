# 31 — Immich produkcijski cutover: F1–F3

Datum: 15. studenoga 2026. (izvedba oko 14:19–14:25 po vremenu hosta).
**`CUTOVER_ID=20261115t130331z`** · evidencija `/opt/stacks/data/backups/immich-cutover-20261115t130331z` · kopija `/home/immich-cutover-backups/20261115t130331z/`.
Odobreno: samo F1–F3. **F4 (`s_freeze`) nije pokrenut.** Immich je cijelo vrijeme dostupan.

## 1. Sažetak

| Korak | Status |
| --- | --- |
| Identitet, manifesti, `lb_verify` | **PASS** |
| **F1** završni produkcijski preflight (oba ključa) | **PASS**, 0 FAIL / 0 WARN |
| **F2** `s_prepare_target` (`immich-db`) | **PASS** |
| **F3** preflight `target-ready`, proba alata | **PASS**, 0 FAIL / 0 WARN |
| `immich-db` | radi, `healthy`, PostgreSQL 16.16, prazna baza `immich`, spojen samo na mrežu `postgis` |
| Postojeći Immich, Redis, `postgis` | **nepromijenjeni**, dostupni (javni rub 200), isto `StartedAt`, 0 restartova |
| Monitoring | **nema nijednog Immich monitora**; nema što utišavati; ništa nije mijenjano |
| Žurnal cutovera | `PREPARED` (1 zapis: "target role+db ready"), lanac valjan |
| Sigurno prijeći na F4? | **Tehnički da** (odjeljak 8); čeka sljedeću operativnu uputu |

## 2. Identitet i backup

Markeri `CUTOVER_ID`: u `/home/…/20261115t130331z/CUTOVER_ID`, `$EV/CUTOVER_ID`, `$EV/local-backup/cutover-id` svi `20261115t130331z`; ime `$EV` odgovara. `lb_check OK`. `lb_verify OK` (original i kopija `immich-db-backup-20261115T020000-v3.3.5-pg16.13.sql.gz`, SHA-256 `25b7780f…73b0fd`, manifesti jednaki; "no dump manifest yet" je očekivano do F6b). Nepodudaranja nema.

## 3. Monitoring (Uptime Kuma, samo čitanje)

- Kontejner `kuma` (`louislam/uptime-kuma:1`), `healthy`, podaci `/opt/stacks/kuma/data`. Konfiguracija pročitana `sqlite3 -readonly` unutar kontejnera (bez ispisa vjerodajnica).
- **17 monitora, svi aktivni.** Pretraga po `immich`, `media` (domena Immicha je `media.finestar.hr`), `photo`, `postgis`, `postgres`, `nextcloud`: **0 pogodaka**. Monitori su Fiscal Platform, Qubit, Headscale, DERP, EMQX, RoamKit i tri generička ulazna `port` monitora (HTTPS 443, HTTP 80, STUN 3478 na zajedničkoj IP adresi); **oni nisu Immich-specifični i ne smiju se utišavati** (pokrivaju sve usluge na hostu).
- Prozori održavanja: 0 postojećih.
- **Zaključak:** prekid Immicha ne aktivira nijedan monitor, pa nema što utišavati ni ponovno uključivati. **Plan povrata:** ništa se ne mijenja, pa nema što vraćati. Ako vlasnik ipak želi, moguć je zaseban prozor održavanja u Kumi (Maintenance → Add, bez pridruženih monitora) koji se nakon `OPEN_CONFIRMED` jednostavno obriše; to nije potrebno i nije izvedeno.
- Obavijesti korisnicima: izričito izostavljene odlukom vlasnika.

## 4. F1 — završni preflight (`preflight.py --phase before-target`, bez `--ignore-window`)

`exit=0`, **RESULT: PASS (0 FAIL, 0 WARN)**, 46 PASS. Zapis `$EV/f1-preflight.out`. Među ostalim: H1 disk (426 GiB), H2 RAM, H3 vrijeme izvan cron sudara; svi kontejneri zdravi; image servera `619fb163…`; `DB_HOSTNAME=postgis`; `media-operations` `DB_HOSTNAME=postgis` (M1); Traefik TR1 nema statičkih ruta i TR2 `traefik.enable=true`; T1 `immich-db` nije postojao, T2 direktorij podataka prazan, N1 mreža `postgis`; S1–S10 izvor 16.13, 9 ekstenzija, 72 tablice, 101/101 migracija, 0 nevaljanih indeksa, rola `immich` bez ovlasti, samo `immich_server` na bazi; B1–B5 backup 12,3 h, `gzip -t` OK; A1–A7 oba API ključa rade (admin čita redove, statistike i 8 knjižnica; korisnik čita albume). RAID1 `[UU]`, NVMe `live` 41 °C (lb_check). Redis `healthy`, `PONG`, bez restartova, `unless-stopped`, nema volumena (RD1: ne dirati), nijedan korak ga ne dira.

Ključevi: `keys_verify_meta` 3 × PASS (7 admin dozvola, 3 korisničke, nema `all`).

## 5. F2 — priprema `immich-db` (`s_prepare_target`)

`CUTOVER_APPROVED=$CUTOVER_ID` postavljen **samo prefiksom za taj jedan poziv** (nakon poziva u ljusci nije postavljen); nije postavljen ni na `1` ni za F4.

| Provjera | Rezultat |
| --- | --- |
| Kontejner | `immich-db`, `running`, `healthy`, 0 restartova, image `sha256:e21ee65b…` (validirani), mreža samo `postgis` (172.28.0.44), **nijedan objavljen port** |
| PostgreSQL | **16.16** (Debian 16.16-1.pgdg12+1); `shared_preload_libraries=vchord`; `password_encryption=scram-sha-256`; `shared_buffers` 1GB, `max_connections` 100, vremenska zona Europe/Zagreb |
| Ekstenzije dostupne | `vector 0.8.2`, `vchord 1.1.1`, `cube`, `earthdistance`, `pg_trgm`, `unaccent`, `uuid-ossp`, `plpgsql`; **PostGIS nije dostupan (0)**; instalirano samo `plpgsql` (ostale dolaze restoreom u F7) |
| Rola `immich` | LOGIN, bez SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS; lozinka u SCRAM-SHA-256 obliku (iz okoline aplikacijskog kontejnera, `getsecret.py`) |
| Baza `immich` | vlasnik `immich`, UTF8, `en_US.utf8`, prazna (0 tablica); ACL se postavlja u F7 |
| SCRAM, pozitivno | prijava `immich` s mrežne adrese (i iz kontejnera `postgis`, kao što će aplikacija) uspješna |
| Negativne kontrole | pogrešna lozinka → `password authentication failed`; bez lozinke → `no password supplied`; nepostojeći korisnik → odbijen; `immich` u `-d postgres` s ispravnom lozinkom dopušteno kao u produkciji (nije privilegija) |
| `pg_hba` | lokalno `trust` samo za unix socket i `127.0.0.1`/`::1` unutar kontejnera (zadano u imageu); sve ostalo `host all all all scram-sha-256` |

Napomena (nije mijenjano, bez improvizacije): superuser `postgres` u `immich-db` koristi `POSTGRES_PASSWORD` iz `/opt/stacks/data/.env`, **isti slabi 8-znamenkasti kao postojeći `postgis`** (compose `env_file`). Baza nije izložena izvan mreže `postgis` (43 kontejnera), ali je preporuka jačanje lozinke nakon cutovera (zaseban zadatak).

## 6. F3 — `preflight --phase target-ready` i proba alata

`exit=0`, **PASS (0 FAIL, 0 WARN)**: I1–I3 (image ID-evi), T1 `immich-db` healthy, T3 image validiran, T4 samo mreža `postgis` bez porta, T5 samo dva mounta (`/var/lib/postgresql/data`, `/backups`), N1, T6, B1–B5, A1–A7. `api_checks.py baseline` (proba alata, `api-baseline-pre.json`, 55.535 fotografija, 1.306 videa): zapisan, **nije** baseline za usporedbu (pravi se uzima u `s_freeze`). `queues status`: 19 redova, nijedan aktivan ni pauziran, **`facialRecognition failed = 1`** (baseline), ostali 0. Zapisi: `f3-preflight.out`, `f3-queues.txt`.

## 7. Stanje produkcije nakon F1–F3

| Provjera | Nalaz |
| --- | --- |
| Početci rada (`StartedAt`) | `immich_server` 3.11., `immich_media_operations` 3.11., `nextcloud_immich_bridge` 3.11., `postgis` i `immich_redis` 26.6.: **identični** snimci prije (`f2-before-containers.txt`) i poslije; 0 restartova; sve `healthy` (`immich_machine_learning` i `traefik` rade) |
| Dostupnost Immicha | `GET https://media.finestar.hr/api/server/ping` → **200** (10 ms); label `traefik.enable=true` |
| `.env` / Compose | `DB_HOSTNAME=postgis`; `.env` 3.11. 13:16, Compose 3.11. 13:21 (nepromijenjeni) |
| Izvorna baza | ACL `{=Tc/immich, immich=CTc/immich}` (nije zaštićena, nema `REVOKE`), 57.627 asseta, 3 API ključa, 12 veza (`immich_server`) |
| Redis | `PONG`, nije diran (broj ključeva varira zbog efemernih BullMQ ključeva: 68, 59; nebitno) |
| Backupovi | 14 u Immich direktoriju, nepromijenjeni; `lb_verify OK` i nakon F3 |
| Resursi | `immich-db` 0,02 % CPU, 80 MiB; `/` 426 GiB slobodno |
| Okolina | `CUTOVER_APPROVED` i `LB_BACKUP_ONLY_APPROVED` nisu postavljeni |

## 8. Žurnal i spremnost za F4

- `cutstate.py get`: **`PREPARED`**; `state.log`: `1 PREPARED — target role+db ready`; lanac valjan. `s_freeze` zahtijeva `NONE` ili `PREPARED` i vodi u `FREEZING`.
- **Je li sigurno prijeći na F4? Tehnički da:** F1–F3 sve PASS, `immich-db` pripravan i prazan, kopija backupa i identitet potvrđeni, ključevi ispravni, redovi mirni (jedini `failed` je poznati baseline), RAID1 i prostor u redu.
- Što F4 donosi (podsjetnik, nije izvršeno): prekid usluge (bridge i `media-operations` stop, pauza i pražnjenje redova, stop servera), dodatni kratki API-only start servera na izvornoj bazi radi baselinea (O15), `REVOKE CONNECT` na izvoru. Za F4 i sve kasnije korake treba novo, zasebno `CUTOVER_APPROVED=20261115t130331z` (nije dano u ovom koraku).

## 9. Što je izvršeno

Čitanje: identitet, `lb_check`, `lb_verify`, Uptime Kuma konfiguracija (`sqlite3 -readonly`), stanje kontejnera/mreža/Redisa, API (GET, plus `POST /search/smart` u baselineu), upiti `postgis`. Pisanje/mutacija: **jedino `s_prepare_target`**: stvoren kontejner `immich-db` (podaci u `/opt/stacks/data/immich-postgres/data`), rola `immich` i baza `immich` u njemu; zapisi u evidenciji (`f1-preflight.out`, `f2-prepare-target.out`, `f2-before-containers.txt`, `f3-*.out`, `api-baseline-pre.json`, `state`/`state.log`). Nije: pokrenut `s_freeze`/`s_open`, zaustavljen ili restartan ikoji kontejner, dirnut Redis, mijenjan `DB_HOSTNAME`, `.env`, Compose, mreže ili Traefik, izvršen `REVOKE CONNECT`, dump ili restore, kopirani podaci, obrisan backup ili podatak, mijenjan monitoring.

**Stajem nakon F3. F4 se ne pokreće bez sljedeće operativne upute.**
