# 58 — Pre-launch audit standardnog servisa `postgres`

Datum audita: 18.11.2026. Način: **isključivo čitanje** (Docker metapodaci, `docker compose config`, read-only upiti u PostgreSQL katalog, provjera datotečnog sustava, čitanje dokumentacije). Nijedan kontejner nije kreiran ni pokrenut, ništa nije građeno, povučeno ni mijenjano. Tajne (lozinke iz `.env`) nisu ispisivane ni zapisane.

Pročitani dokumenti: 01, 02, 03, 04, 05, 06 (dodatno), 07, 08 (dodatno), 56, 57 — svi postoje. Dokument 01 (108 KB) pročitan je samo kroz sažetke u 03/06/57; nije čitan u cijelosti.

## 0. Odluka

# **NO-GO** (formalno, prema kriterijima iz zadatka §9)

Tehnički je kandidat spreman (image postoji i odgovara dokumentu 08, konfiguracija je valjana, nema kolizije mreža/portova/aliasa, resursi su dovoljni). Ne mogu napisati GO jer tri kriterija nisu potvrđena:

| # | Nepotvrđeni kriterij | Razlog |
|---|---|---|
| B1 | „Ima definiranu strategiju backupa” (§5) | Za novi servis ne postoji backup job, restore-testirana kopija ni off-host kopija (R03 iz dok. 06 još je otvoren; `/opt/stacks/data/backups` ne sadrži svježe dumpove 25 ciljnih baza, najnoviji generički dumpovi su iz veljače 2026.). Za *prazan* cluster to nije tehnička prepreka, ali nužna je izričita vlasnikova odluka da se start odobrava uz tu činjenicu. |
| B2 | „Jasno definirano kako će se pokretati bez recreatea ostalih servisa” (§9) | Definirano je u §9 ovog dokumenta, ali **Compose config-hash za `immich-db` ne odgovara hashu u labeli živog kontejnera** (vidi §8). Nenavedeni `up` bi vjerojatno recreateao `immich-db`. Postupak je siguran samo uz točnu naredbu iz §9; treba ga odobriti. |
| B3 | „Siguran plan inicijalizacije i provjere” (§9) | Plan je predložen u §9.3, ali nije odobren. Uz to postoje odluke koje se nakon prvog starta ne mogu jeftino promijeniti (`data-checksums`, §5.5). |

Sve tri su otklonjive jednim vlasnikovim odobrenjem + odlukom o checksums (vidi §11). Nijedna ne zahtijeva izmjenu datoteka.

## 1. Aktualno stanje sva tri servisa (provjereno ponovno 18.11.2026.)

| Servis | Stanje | Image | PG | Mreže | Port | PGDATA (host) | Mem. | Memorija/CPU u trenutku mjerenja |
|---|---|---|---|---|---|---|---|---|
| `postgis` | running, **healthy**, od 26.06.2026., projekt `data` | `postgis-local:16-bookworm-postgis3-cron-vchord1.1.1` | 16.13 (Debian 16.13-1.pgdg12+1) | backend, data_default, hetzner_net, postgis | `127.0.0.1:5432` | `/opt/stacks/data/postgres/data` (42 GB) | bez limita, shm 64 MB | 13,46 GiB, 6,5 % CPU, 51 PID |
| `immich-db` | running, **healthy**, od 15.11.2026., projekt `data-postgres-next` | `immich-db-local:16.16-bookworm-vector0.8.2-vchord1.1.1` (`sha256:e21ee65b…`) | 16.16 (Debian 16.16-1.pgdg12+1) | postgis (172.28.0.44) | nema | `/opt/stacks/data/immich-postgres/data` (2,8 GB) | limit 4 GiB, shm 1 GiB | 1,18 GiB, 0 % CPU, 25 PID |
| `postgres` | **ne postoji** (`docker ps -a` nema ni zaustavljenog kontejnera) | image **već postoji lokalno**: `postgres-standard-local:16.16-bookworm-vector0.8.2-cron1.6.7`, `sha256:2f9d2f25e896…` (izgrađen 14.11.2026. 14:50 UTC) | — | — | — | `/opt/stacks/data/postgres-standard/data` (prazan) | — | — |

Napomena: dokument 57 ne spominje da je image `postgres` već izgrađen; izgrađen je u fazi 2 (dok. 08), ID se točno podudara s dokumentom 08. **Za pokretanje nije potreban build ni pull.**

Ostalo: u `postgis` je u trenutku mjerenja 45 klijentskih veza (upit je uključivao i vlastitu sesiju), u `immich-db` 20. Postgis postavke: `max_connections=100`, `shared_buffers=128 MB` (16384 × 8 kB), `wal_level=replica`, `data_checksums=off`, `password_encryption=scram-sha-256`, `shared_preload_libraries=vchord,pg_cron`, TimeZone `Europe/Zagreb`.

## 2. Pregled Compose i Dockerfile konfiguracije

Datoteke: `docker-compose.postgres-new.yml` i `Dockerfile.postgres`, obje nepromijenjene od 14.11.2026. 14:29 (mtime), prije builda imagea (14:50) — dakle image odgovara trenutnom Dockerfileu. `docker compose -f docker-compose.postgres-new.yml config --quiet` → **exit 0**. `config --services` → `immich-db`, `postgres`.

| # | Stavka | Nalaz |
|---|---|---|
| 1 | Naziv servisa | `postgres`; `container_name: postgres`; Compose projekt `data-postgres-next` (isti projekt kao već živi `immich-db`) |
| 2 | Verzija/image | PostgreSQL **16.16** (Debian bookworm), `postgres-standard-local:16.16-bookworm-vector0.8.2-cron1.6.7`, `linux/amd64`, bazni image pinan po digestu `sha256:f45d631d…`. Env imagea: `PG_MAJOR=16`, `PG_VERSION=16.16-1.pgdg12+1`, `LANG=en_US.utf8`, `PGDATA` zadan |
| 3 | Build | context `.` (`/opt/stacks/data`), `Dockerfile.postgres`; multi-stage (pgvector 0.8.2 + pg_cron 1.6.7 iz izvora uz SHA-256 provjeru). Build ovdje **nije** potreban niti smije biti izveden |
| 4 | Volumeni | `/opt/stacks/data/postgres-standard/data` → `/var/lib/postgresql/data` (`PGDATA` isti); `/opt/stacks/data/backups` → `/backups`; `/srv/qubit/backups` → `/srv/qubit/backups`. Svi bind, `create_host_path: false` (nepostojeća putanja ⇒ greška, ne tiho stvaranje). Svi su **rw** |
| 5 | Mreže/DNS | external: `postgis`, `backend`, `hetzner_net`. Alias je implicitno `postgres` (+ ime kontejnera) na sve tri mreže |
| 6 | Healthcheck | `pg_isready -U postgres -d postgres`, interval 10 s, timeout 5 s, 10 pokušaja, start_period 30 s |
| 7 | Environment | iz `.env`: `TZ`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (vrijednosti nisu ispisane). `environment:` ima prednost: `POSTGRES_USER=postgres`, `POSTGRES_DB=postgres`; `POSTGRES_INITDB_ARGS=--encoding=UTF8 --locale=en_US.utf8`; `POSTGRES_HOST_AUTH_METHOD=scram-sha-256`; `PGDATA=/var/lib/postgresql/data`. Lozinka je **ista administratorska kao u postojećim clusterima** (po dizajnu, dok. 07) |
| 8 | Ovisnosti | `depends_on` nema; nema `links`, `volumes_from`, `network_mode: service:`. Servis je samostalan |
| 9 | Restart | `unless-stopped` |
| 10 | Portovi | **nema `ports:`** — ništa objavljeno na hostu. Host `ss` pokazuje 5432 samo za postojeće (127.0.0.1 docker-proxy za postgis, tailscaled na 100.64.0.6/fd7a…); 5433/5434 slobodni |
| 11 | Prava | PGDATA `/opt/stacks/data/postgres-standard/data` mode **0700**, vlasnik numerički 999:999 (host ga prikazuje kao `lxd:docker`); isto kao `immich-db` data direktorij, koji radi s istim baznim imageom |
| 12 | Kolizije | vidi §7 i §8 — nema kolizije imena, aliasa, portova ni mountova |

Ostalo iz compose-a: `mem_limit 12g`, `shm_size 1g`, bez CPU limita. Pokretanje: `command` postavlja `shared_preload_libraries=pg_cron,pg_stat_statements`, `cron.database_name=postgres`, `cron.timezone=GMT`, `cron.launch_active_jobs=off`, `shared_buffers=3GB`, `max_connections=100`, `work_mem=4MB`, `TimeZone=Europe/Zagreb`.

Opaska uz Dockerfile: sve `RUN` provjere (verzija 16.16, control datoteke, `ldd` bez „not found”, odsutnost `postgis.control` i `vchord.control`) izvršene su pri buildu 14.11.; to potvrđuje dokument 08, a ID imagea je isti. Image nisam pokretao niti raspakiravao, pa sadržaj imagea **nisam ponovno provjerio izravno** — oslanjam se na podudaranje ID-a s dok. 08.

## 3. Verificirana PostgreSQL verzija

- Image (metapodaci): `PG_VERSION=16.16-1.pgdg12+1`, `PG_MAJOR=16` — **potvrđeno** iz `docker image inspect`.
- Dok. 08 (izvršeni test na istom imageu): `PostgreSQL 16.16 (Debian 16.16-1.pgdg12+1) on x86_64-pc-linux-gnu, compiled by gcc 12.2.0`.
- Izvori: `postgis` 16.13 (Debian 12), `immich-db` 16.16 (Debian 12). Ista glavna verzija 16 i ista Debian generacija; novi je s `immich-db` u istoj minor verziji. Dump/restore 16.13 → 16.16 unutar iste glavne verzije je podržan. **Kompatibilno.**

## 4. Ekstenzije i ovisnosti

Stvarna potreba 25 baza koje su PENDING (dok. 03/57), nasuprot sadržaju imagea (dok. 08, aktivirane na probnom clusteru):

| Ekstenzija | Treba | U imageu (prema dok. 08) | Status |
|---|---|---|---|
| `pgcrypto` 1.3 | chatwoot, fiskal_f1_pts_smoke | da (contrib) | ✔ |
| `pg_trgm` 1.6 | chatwoot | da | ✔ |
| `uuid-ossp` 1.1 | headscale | da | ✔ |
| `pg_stat_statements` 1.10 | chatwoot (instaliran, ali dosad bez preloada) | da, **preload uključen** | ✔ (novost: statistika upita će postati stvarna) |
| `pageinspect` 1.12 | stay_platform_db | da | ✔ |
| `pg_cron` 1.6 | qubit_user | da (v1.6.7, SQL 1.6), preload uključen | ✔ uz uvjet: `cron.database_name` mora postati `qubit_user` prije restorea (restart samo `postgres`); **do tada ne postoji ekstenzija ni jobovi** (`launch_active_jobs=off`) |
| `vector` 0.8.2 | chatwoot (3 IVFFlat indeksa) | da | ✔ |
| `fuzzystrmatch` 1.2 | baza `postgres` (Uzorita) | da | ✔ |
| `pg_cron` ponašanje u praznoj `postgres` bazi bez `CREATE EXTENSION` | — | nije testirano (dok. 08 je ekstenziju kreirao u probnoj bazi) | **NOT VERIFIED**; provjeriti `docker logs` nakon starta (§9.3) |
| **`postgis`, `postgis_topology`, `postgis_tiger_geocoder`** | `postgres` (Uzorita: postgis+topology+tiger+fuzzystrmatch), finestar_erp_db, fiskal, mozzart_db, predix, superclean_db (instaliran u svih) | **namjerno NIJE u imageu** | ⚠ **blokada migracije tih baza**, ne starta servisa: dok. 03 gate D / dok. 06 D08, R07 — bez PostGIS-a ne smiju se prebaciti (ili se ekstenzija mora kontrolirano izostaviti uz test Django GIS backenda). Prazan servis nije time ugrožen |
| `vchord` 1.1.1 | samo immich | namjerno nije u imageu | ✔ ispravno (Immich je na `immich-db`) |
| `cube`, `earthdistance`, `unaccent` | samo immich | contrib je dostupan | nije potrebno |

Zaključak: za **pokretanje praznog servisa** nema blokade vezane uz ekstenzije; za **migraciju** 5–6 baza s PostGIS-om ostaje otvoren gate D (nije riješen ovim dokumentom).

## 5. Image: locale, WAL, memorija, autentikacija

1. **Locale/encoding.** Izvorne baze: `UTF8`, `en_US.utf8`/`en_US.utf8`, provider `c` (libc); jedina razlika u pisanju je `headscale` (`en_US.UTF-8`, isto značenje). Novi: `LANG=en_US.utf8` u imageu + `--encoding=UTF8 --locale=en_US.utf8` → **podudara se**. Već poznati nesklad verzije kolacije (glibc 2.31 → 2.36) na 8 baza i `template_postgis` (dok. 06 R05) ostaje otvoren uvjet za restore (REINDEX prije REFRESH VERSION), ne za start.
2. **Timezone.** `TimeZone=Europe/Zagreb` (isto kao oba živa servisa); `TZ` iz `.env`; `cron.timezone=GMT` (konzervativno, dok. 07).
3. **Autentikacija.** `scram-sha-256` za mrežne veze (`POSTGRES_HOST_AUTH_METHOD`); `password_encryption` u PG16 zadano scram. **Lokalni (unix socket) pristup u službenom imageu ostaje `trust`** — isto kao na postojećim servisima (R12); to nije regresija. Administratorska lozinka dijeli se između sva tri clustera (nova lozinka nije generirana).
4. **WAL/shm/konekcije.** `shm_size 1g` uz `shared_buffers 3GB`: **3 GB je veće od 1 GB shm, ali PostgreSQL 16 koristi `mmap`/anon shared memory za glavni segment (`shared_memory_type=mmap`), a `/dev/shm` služi samo za dinamičke segmente (paralelni upiti)**; isto rješenje je na `immich-db` (1 GB uz 1 GB buffers) i dokument 08 ga nije testirao s 3 GB. *Provjeriti pri prvom startu da server ne javlja grešku o shared memory* (§9.3). `max_connections=100` — za usporedbu: `postgis` trenutno ima 45 klijentskih veza za sve baze; ciljnih 25 baza imalo je ~40 veza. WAL parametri **nisu podešeni** (default: `max_wal_size=1GB`, `wal_level=replica`, `archive_mode=off`, `maintenance_work_mem=64MB`). Za restore CrowdSeca (≈39 GB) treba odluka o privremenom povećanju (`max_wal_size`, `maintenance_work_mem`) prije vala H; nije potrebno za prazan start.
5. **Odluka prije prvog starta: `data-checksums`.** Postojeći clusteri imaju `data_checksums=off`, a novi cluster po defaultu isto bit će `off`. Checksums se mogu uključiti **samo pri `initdb`** (kroz `POSTGRES_INITDB_ARGS=--data-checksums`) ili naknadno offline alatom `pg_checksums` na zaustavljenom clusteru. Ako ih vlasnik želi, to je izmjena Compose datoteke i mora biti odobrena *prije* starta. Ne preporučujem samo-inicijativnu promjenu; ostavljam kao odluku.
6. **Backup strategija.** **Nije definirana za novi servis** (B1). Dokumenti 04/05 opisuju per-DB `pg_dump -Fc`, globals, SHA-256, off-host kopiju i restore probu, ali ništa od toga još ne postoji za ciljne baze, a dnevni backupovi postoje samo za chatwoot (`backups/chatwoot`, zadnji 17.11.) i Immich. Isti mount `/backups` bit će dostupan novom servisu.

## 6. PGDATA, filesystem i resursi

| Provjera | Rezultat |
|---|---|
| `/opt/stacks/data/postgres-standard/data` | postoji, **prazan**, mode `0700`, vlasnik 999:999 (`lxd:docker`); roditelj `postgres-standard/` `root:root 755` |
| Filesystem | `/dev/md2`, **ext4**, `/` (isti filesystem kao `postgres/data`, `immich-postgres/data` i `backups` — nema odvojene particije) |
| RAID | `md2` raid1 `[UU]` (nvme0n1p3 + nvme1n1p3), 2/2 aktivna; md0, md1, md3 isto `[UU]` |
| Slobodan prostor | **414 GB** od 2,0 TB (78 % popunjeno). Dok. 06 računao je 179 GiB; sad je više |
| Proračun za migraciju (dok. 04) | ≈ **219,5 GiB** dodatnog prostora u najgorem slučaju (puna kopija + obnovljeni target + dump + WAL/temp + 80 GiB rezerve); 414 − 219,5 ≈ 195 GiB ostaje ⇒ **zadovoljeno**, ali samo uz serijske valove |
| Backup lokacije | `/opt/stacks/data/backups` (15 GB, `root:root 755`; nijedna datoteka nije u vlasništvu 999 ni world-writable) i `/srv/qubit/backups` (`lxd:docker`, podmape headscale/nginx/user). **Isti disk kao PGDATA** — nema off-host kopije |
| Drugi procesi na ciljnoj putanji | `lsof +D` i `fuser` bez rezultata; nijedan kontejner ne montira tu putanju |
| Memorija hosta | 125 GiB ukupno, 47 GiB iskorišteno, **74 GiB „available”**; novi servis: cap 12 GiB (+1 GiB shm unutar limita). **Swap 4/4 GiB popunjen** (stanje je već postojeće), `vmstat`: si/so = 0, iowait 0–1 %, nema trenutnog swapanja |
| CPU | 32 jezgre; kontejner nema CPU limit. Trenutno ~90 % idle |
| Docker logovi | `/etc/docker/daemon.json` ne postoji ⇒ `json-file` **bez rotacije** (zadano). `postgres` s `log_*` defaultom malo piše; za restore s greškama, logovi mogu rasti — opaska, ne blokada |
| Očekivana potrošnja | prazan cluster: ~50–100 MB RAM, CPU zanemariv; nakon migracije 25 baza ≈ 42 GB na disku (većina CrowdSec 38,9 GiB) i do cap-a 12 GiB RAM-a. Izračun je procjena, ne mjerenje |

## 7. Mreže i sigurnost

| Provjera | Nalaz |
|---|---|
| Javni port | **Ne otvara se**: nema `ports:`; `listen_addresses='*'` samo unutar Docker mreža. Za razliku od `postgis`, nema ni `127.0.0.1` bindinga ni Tailscale dosega |
| Mreže | `backend` (172.20.0.0/16, 10 članova: emqx, headscale, powerdns, qubit…), `postgis` (172.28.0.0/16, 43 člana), `hetzner_net` (192.168.16.0/20, 40 članova); sve `bridge`, `internal=false`, `attachable=false`, postoje. `data_default` **ne koristi** novi servis i ne sadrži ništa osim `postgis` |
| Alias `postgres` | **Pretraga svih 144+ kontejnera (uključujući zaustavljene): nijedan ne drži alias ni DNS ime `postgres`** na ikojoj mreži; nijedan `*_HOST/_HOSTNAME/_SERVER/_ADDR` env niti `*_URL/_URI/_DSN` s hostom `postgres` ne postoji. Ograničenje: pregledan je samo env; konfiguracijske datoteke unutar kontejnera/hosta (npr. headscale, powerdns) nisu parsirane ⇒ **NOT VERIFIED** da nijedna aplikacija ne razrješava ime `postgres` iz konfiguracije |
| Utjecaj na DNS `postgis` | Nema: novi kontejner dobiva samo svoje aliase (`postgres`, ime kontejnera, ID). Aliasi `postgis` na tim mrežama ostaju kod postojećeg kontejnera. Docker nema round-robin za različita imena |
| Pristup zaštićenoj Immich bazi | Novi servis je na mreži `postgis` gdje je i `immich-db` (172.28.0.44) ⇒ **mrežno dohvatljiv**, i dijeli administratorsku lozinku (`.env`). To nije opravdanje „bez razloga”: mreža `postgis` je potrebna jer na njoj već žive svi klijenti koji će se preseliti (dok. 02), a `immich-db` ne može se maknuti s nje. Zaštita je u autentikaciji; ne dodaje se nova izloženost, ali ni izolacija. Opcija (ne preduvjet): kasnije segmentirati `immich-db` na zasebnu mrežu |
| Višak mreža | `backend` i `hetzner_net` potrebne su tek kad se potrošači s tih mreža presele (npr. qubit/headscale/powerdns na `backend`; ERP/Stay/Tablio na `hetzner_net`). Za *prazan* start dovoljna bi bila samo `postgis`; smanjenje je izmjena Compose-a pa ga ne radim |
| Tajne | `.env` i `postgis-tailscale.env` su **mode 644 `root:root`** (čitljivi svima na hostu) — nalaz za vlasnika, nije izmijenjeno. `.env`/`postgis-tailscale.env`/`postgres-standard/`/`backups/` u `.gitignore` (provjereno `git check-ignore`). Lozinka nije u Compose datoteci kao literal; `docker compose config` ispisuje je u cijelosti ⇒ **ne pokretati `config` bez filtra u zajedničkim logovima** (u ovom auditu ispis je redigiran) |
| `/backups` kao rw | Montiran je `rw` s cijelim `backups/` (uključujući zaštićene Immich backupe), no proces je uid 999, a `backups/` je `root:root 755` bez world-writable stavki ⇒ praktično samo za čitanje. Preporuka (izmjena Compose-a, ne radi se): `read_only: true` za `/backups`, dok se ne odobri ispis dumpova iz kontejnera |

## 8. Rizici za postojeći `immich-db` i `postgis`

**Zaključak: ciljani `up` samo servisa `postgres` ne dira `immich-db` ni `postgis`; necilјani `up` (cijeli projekt) vjerojatno recreatea `immich-db`.**

Dokazi:

1. **Hash nesklad.** `docker compose -f docker-compose.postgres-new.yml config --hash '*'`:
   - `immich-db` → `29c4c18d508d…`
   - živa labela `com.docker.compose.config-hash` na `immich-db` → `ef618662fc11…`
   - **Razlikuju se.** Uzrok nije utvrđen (moguće: drukčiji Compose/env u času izrade 15.11., izmjena datoteke nakon kreiranja kontejnera, ili razlika u izračunu hasha) — **NOT VERIFIED**. Posljedica: `docker compose up -d` bez imena servisa (ili s `immich-db`) smatrao bi `immich-db` „promijenjenim” i recreateao bi ga ⇒ prekid Immicha (19 aktivnih veza, `immich_server`, `immich_media_operations`).
2. Compose projekt `data-postgres-next` trenutno ima samo `immich-db` (`docker compose ps -a`). `docker compose up -d postgres` bez `depends_on` ne dotiče `immich-db`; dodatni `--no-deps` je zaštitni pojas.
3. **Zabranjeno**: `docker compose -f docker-compose.postgres-new.yml up -d` (bez servisa), `up ... immich-db`, `down`, `--force-recreate`, `--remove-orphans`, `restart`, `build`, kao i `up --build`.
4. **Pozor — zamka u AGENTS.md.** Naredba iz „Production” sekcije AGENTS.md (`docker compose up -d --build` u `/opt/stacks/data`) koristi zadanu datoteku `docker-compose.yml` (projekt `data`) i odnosi se na `postgis`; **ne smije se koristiti za novi servis**, a bez `-f` ne bi ni pokrenula `postgres`. Dok. 07 izričito: nikad ne kombinirati novi Compose s `docker-compose.yml`.
5. `postgis` je u projektu `data` s datotekom `docker-compose.yml`; naredba s `-f docker-compose.postgres-new.yml` ne dotiče ga (različito ime projekta, nema zajedničkih servisa). `.env` ne sadrži `COMPOSE_FILE`/`COMPOSE_PROJECT_NAME` (ključevi: TZ, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB), pa nema skrivenog nadjačavanja.
6. Resursna konkurencija: nakon starta novi servis djeluje na isti disk i RAM (cap 12 GiB; dostupno 74 GiB), a `postgis` ne gubi memoriju zbog limita. Rizik na IO nastupa tek tijekom restorea (R17), ne tijekom starta praznog clustera.
7. Recreate za `immich-db` ostaje i dalje moguć nenamjerno kasnije (npr. neki budući `up` bez servisa) dok se hash ne uskladi; usklađivanje hasha je zasebna odobrena radnja i ovdje se ne radi.

## 9. Buduća naredba za pokretanje (NE IZVRŠAVATI)

### 9.1 Preduvjeti neposredno prije starta (read-only provjere)

```bash
cd /opt/stacks/data
# 0. Evidentirati stanje koje se ne smije promijeniti
docker inspect immich-db postgis --format '{{.Name}} id={{.Id}} started={{.State.StartedAt}} image={{.Image}}' | tee /tmp/prelaunch-before.txt
# 1. Cilj prazan, kontejner ne postoji, image na mjestu
test -z "$(ls -A /opt/stacks/data/postgres-standard/data)" && echo EMPTY
docker ps -a --format '{{.Names}}' | grep -x postgres || echo NO_CONTAINER
docker image inspect postgres-standard-local:16.16-bookworm-vector0.8.2-cron1.6.7 --format '{{.Id}}'   # očekivano sha256:2f9d2f25e896…
# 2. Konfiguracija valjana (BEZ ispisa — izlaz u /dev/null)
docker compose -f docker-compose.postgres-new.yml config --quiet
```

### 9.2 Naredba (isključivo servis `postgres`)

```bash
cd /opt/stacks/data
docker compose -f docker-compose.postgres-new.yml up -d --no-deps --no-build --pull never postgres
```

Objašnjenje zastavica: `postgres` ograničava akciju na jedan servis; `--no-deps` nikad ne pokreće/ne mijenja ništa drugo; `--no-build` i `--pull never` jamče da se ne gradi niti povlači (image već postoji lokalno); **nema** `--force-recreate`, `--remove-orphans`, `--build`. Ne treba `-p`: ime projekta (`data-postgres-next`) je u datoteci.

Opcionalno, tek uz zasebno odobrenje (nije dio ovog audita, jer je tehnički `up`): isti poziv s `--dry-run` prije pravog starta radi potvrde da popis akcija sadrži samo `postgres`.

### 9.3 Provjere nakon starta (read-only)

```bash
docker inspect immich-db postgis --format '{{.Name}} id={{.Id}} started={{.State.StartedAt}} image={{.Image}}' \
  | diff - /tmp/prelaunch-before.txt && echo "IMMICH-DB I POSTGIS NEPROMIJENJENI"
docker ps --filter name='^postgres$' --format '{{.Names}} {{.Status}} {{.Ports}}'   # očekivano: bez portova
docker logs postgres 2>&1 | grep -iE 'database system is ready|error|fatal|shared memory|pg_cron|checksum'   # ne ispisivati cijeli log
docker exec postgres psql -U postgres -d postgres -Atc 'select version(); show shared_preload_libraries; show data_checksums; show cron.database_name; show TimeZone;'
docker exec postgres psql -U postgres -d postgres -Atc "select name, default_version from pg_available_extensions where name in ('vector','pg_cron','pgcrypto','pg_trgm','uuid-ossp','pg_stat_statements','pageinspect','fuzzystrmatch','postgis','vchord') order by 1;"   # očekivano: postgis i vchord ODSUTNI
docker exec postgres psql -U postgres -Atc 'select datname from pg_database order by 1;'   # samo postgres, template0, template1
docker network inspect postgis backend hetzner_net --format '{{.Name}}: {{range .Containers}}{{.Name}} {{end}}' | grep -c postgres   # alias/DNS razrješenje iz drugog kontejnera tek uz odobrenje
```

Granica: nakon ove provjere **stati**. Restore, kreiranje baza/rola, `CREATE EXTENSION`, promjena `cron.database_name`, preusmjeravanje aplikacija i backup zahtijevaju zasebna odobrenja.

### 9.4 Rollback starta praznog clustera (samo uz odobrenje)

Zaustavljanje i uklanjanje samo kontejnera `postgres` (`docker compose -f docker-compose.postgres-new.yml stop postgres && docker compose -f docker-compose.postgres-new.yml rm -f postgres`) ne dotiče `immich-db`. Pražnjenje `postgres-standard/data` je brisanje podataka i traži izričitu uputu (AGENTS.md: „Never delete … unless explicitly instructed”) — u prazan cluster taj korak nije nužan za sigurnost produkcije.

## 10. GO / NO-GO — kriterij po kriterij

| Kriterij | Status | Opaska |
|---|---|---|
| Ispravna Compose konfiguracija | ✔ | `config --quiet` exit 0; image postoji, ID = dok. 08 |
| Sigurni mountovi i izolirani PGDATA | ✔ | prazan, 0700, 999:999, nije montiran drugdje, ne preklapa se s izvornim PGDATA; `create_host_path:false` |
| Nema kolizije mreža, portova, aliasa | ✔ (uz NOT VERIFIED za konfiguracijske datoteke aplikacija) | nijedan alias/DNS `postgres`; nema objavljenih portova |
| Nema rizika za `immich-db` i `postgis` | ⚠ **uvjetno** | samo uz naredbu iz §9.2; config-hash `immich-db` ne odgovara živoj labeli (§8) |
| Potrebne ekstenzije dostupne | ✔ za start; ⚠ za migraciju | PostGIS-ovisne baze čekaju gate D (§4) |
| Dovoljno prostora i resursa | ✔ | 414 GB slobodno, RAID1 [UU], 74 GiB RAM-a dostupno; swap pun (postojeće stanje) |
| Siguran plan inicijalizacije i provjere | ⚠ predložen, neodobren | §9; odluka o `data-checksums` (§5.5) |
| Definirano pokretanje bez recreatea ostalih | ⚠ definirano, neodobreno | §9.2 |
| Backup strategija | ✘ nije definirana | B1 |

**Odluka: NO-GO** dok vlasnik ne zatvori B1–B3 (vidi §11).

## 11. Popis blokada i uvjeta prije pokretanja

**Blokade (zatvaraju se odobrenjem/odlukom, ne izmjenom datoteka):**

1. **B1 — Backup strategija:** vlasnik izričito prihvaća start praznog clustera bez backupa novog servisa, **i** određuje da se prije prvog restorea definira/izvede: svježi `pg_dump -Fc` za svaku ciljnu bazu, `pg_dumpall --globals-only`, SHA-256, off-host kopija i restore proba (dok. 04/05, R03).
2. **B2 — Pokretanje bez recreatea:** odobriti isključivo naredbu iz §9.2 (uz zabrane iz §8.3) i potvrditi da se ne koristi `up` bez navedenog servisa dok se hash-nesklad `immich-db` ne razriješi.
3. **B3 — Plan inicijalizacije i provjere:** odobriti §9.1 i §9.3 te odlučiti o `data-checksums` (§5.5) prije prvog starta (poslije se mijenja samo offline).

**Uvjeti/otvorene stavke koje ne blokiraju start praznog clustera, ali moraju biti riješene prije migracije:**

4. Gate D (PostGIS za `postgres`/Uzorita, finestar_erp_db, fiskal, mozzart_db, predix, superclean_db) — odluka i test Django GIS backenda (dok. 03, R07, R08).
5. `qubit_user`: promjena `cron.database_name` u `qubit_user` i restart **samo** `postgres` prije restorea te baze (dok. 07).
6. Nesklad kolacije (R05), tuning WAL/`maintenance_work_mem` za restore velikih baza (CrowdSec), serijski valovi radi IO/swapa (R17).
7. Provjera da nijedna aplikacija ne razrješava host `postgres` iz konfiguracije (§7, NOT VERIFIED).
8. Opcionalna ojačanja (zasebna odobrenja): `.env` 644 → 600; `/backups` `read_only`; rotacija Docker logova; smanjenje mreža na potrebne; razlikovati administratorsku lozinku po clusteru.
9. Razjasniti uzrok hash nesklada `immich-db` (§8.1).
10. `nextcloud_immich_bridge` i `immich_machine_learning` i dalje imaju `DB_HOSTNAME=postgis` (nasljeđeno iz dok. 57, nije dio ovog audita).

## 12. Potvrda da produkcija nije mijenjana

Izvršeno isključivo:

- čitanje datoteka i dokumentacije (`cat`, `sed`, `ls`, `stat`, `grep`, `find`, `du`, `df`, `lsof`, `fuser`, `ss`, `vmstat`, `sysctl`, `free`, `/proc/mdstat`);
- Docker samo za čitanje: `ps -a`, `inspect`, `image ls/inspect`, `network ls/inspect`, `stats --no-stream`, `info`, `compose config`/`config --hash`/`config --services`/`ps -a`;
- `docker exec` s `psql` u `BEGIN READ ONLY … ROLLBACK` nad `postgis` i `immich-db` (verzije, `pg_database`, `pg_settings`, `pg_stat_activity` count, `pg_roles`);
- jedan privremeni Python (`-I`) prolaz kroz `docker inspect` JSON za pretragu aliasa/hostova (bez ispisa vrijednosti env-a osim imena kontejnera i varijable);
- pisanje ovog dokumenta (jedina izmjena datotečnog sustava).

Nije izvršeno: `docker compose up/build/create/start/pull/run`, `docker run`, `initdb`, `mkdir/chown/chmod`, izmjena Compose/Dockerfile/`.env`, izmjena rola, mreža i portova, backup/restore, migracija, restart/recreate kontejnera, promjene Redisa/Immicha, izmjene migracijskih žurnala, git commit/push/PR. `git status` prije i nakon: samo neprađeni dokumenti 57 i 58.

Usputna opaska (nije uzrokovana ovim auditom): tijekom `docker ps` primijećeni su kontejneri koji nisu povezani s ovim radom — `gha-tablio-*` runneri tek pokrenuti (5–22 s), `fiskal_otel_collector` u petlji restarta, `paddle-ocr-fastapi` izašao s kodom 132. Nisu dirani.

## Završna oznaka

`POSTGRES_STANDARD_PRELAUNCH_NO_GO_PENDING_OWNER_APPROVAL`

Stajem ovdje. Čekam zasebno odobrenje prije pokretanja servisa `postgres`.
