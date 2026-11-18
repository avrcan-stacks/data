# 13 — Immich v3.3.5: plan izoliranog aplikacijskog testa i produkcijskog prebacivanja

Datum analize: 14. studenoga 2026. (Europe/Zagreb).
Status: **samo analiza, plan i priprema datoteka. Nijedan testni kontejner, mreža, restore, dump, migracija ni aplikacija nisu pokrenuti.**

Nadovezuje se na [plan](09-immich-restore-plan.md), [faze 4](10-immich-restore-results.md), [4B](11-immich-restore-retest.md) i [4C](12-immich-index-validation.md). Za izvođenje bilo čega iz odjeljaka 7 i 12 potrebno je novo izričito odobrenje. **Produkcijska migracija nije odobrena.**

## 0. Sažetak odgovora

**Može li se aplikacijski test sigurno provesti?** Da, u ograničenom obliku. Izolirana mreža bez izlaza (`internal: true`), vlastiti PostgreSQL 16.16, Redis i ML, konfiguracija iz datoteke (`IMMICH_CONFIG_FILE`) i prazan medijski direktorij omogućuju sigurno testiranje startupa, migracija, drift provjere, logina, albuma, pretrage (uključujući CLIP preko ML-a) i postojećih podataka o licima. **Ne može se** u izolaciji provjeriti OIDC/Nextcloud prijava, Traefik/TLS, mobilne aplikacije, `media-operations` i `nextcloud-immich-bridge` te prikaz stvarnih slika. To ostaje za provjeru poslije cutovera. Ova pripremna analiza dokazuje da je plan izvediv; sam test još nije izveden.

**Preostali rizici (sažeto, detalji u odjeljku 13):**
1. Produkcijska konfiguracija je u bazi (OAuth uključen), test koristi config datoteku. OIDC putanja ostaje neprovjerena do cutovera.
2. `immich_media_operations` pristupa bazi preko `docker exec <DB_HOSTNAME> psql`, pa novi kontejner mora imati točno ime iz `DB_HOSTNAME`; njegovi SQL upiti nisu testirani na 16.16.
3. Normalizacija sekvence i tekstualna razlika indeksa (iznimka iz [12](12-immich-index-validation.md)) moraju se ponoviti na cutoveru.
4. Redis nema volumen: stanje redova se gubi pri recreateu pa red treba isprazniti prije zamrzavanja.
5. Rollback nakon prvog pisanja na novu bazu znači gubitak tih zapisa ili ručnu povratnu sinkronizaciju.
6. Prag recall-a/latencije i dopušteni prozor prekida nisu dogovoreni.

**Što treba odobriti za sljedeću fazu (5B):** vidi odjeljak 14.

**Očekivani postupak produkcijskog prebacivanja:** priprema `immich-db` bez prekida; zamrzavanje pisanja (pauza i pražnjenje redova, zaustavljanje `immich_server`, `immich_media_operations`, `nextcloud_immich_bridge`, zaštita izvorne baze); novi konzistentni dump; bridge sanitizacija bez PostGIS-a; restore u `immich-db`; normalizacija sekvence i validacija; promjena `DB_HOSTNAME`; recreate servera i `media-operations`; provjera i otvaranje pisanja; izvor ostaje netaknut radi rollbacka. Mjerena DB faza traje oko 3 min, planirani prozor 30–45 min (odjeljak 12).

## 1. Stvarna produkcijska konfiguracija (bez tajni)

| Stavka | Nalaz |
| --- | --- |
| Stack | `/opt/stacks/immich`, Compose projekt `immich`; servisi `immich-server`, `immich-machine-learning`, `redis`, `nextcloud-immich-bridge`, `media-operations` |
| Server image | lokalno izgrađen `immich-immich-server`, ID `sha256:619fb163d959f4ee2f35f222ef23b2390ccba5e307ade748548834ad77aef463`, baza `ghcr.io/immich-app/immich-server:v3.3.5` plus `patch-server.js`; server radi od 2026-11-03T13:29:21Z, 0 restarta |
| ML image | `ghcr.io/immich-app/immich-machine-learning:v3.3.5` (CPU), ID `sha256:5b28c9352c8374b8a1ed96fbdd8d6755fea6e43510ec43fdf6538aa02ea40f56`; model cache volume `immich_model-cache` 2,1 GB |
| Redis | `docker.io/valkey/valkey:9@sha256:3eeb09785cd61ec8e3be35f8804c8892080f3ca21934d628abc24ee4ed1698f6`, **bez ikakvog volumena** (stanje redova je u memoriji) |
| Mreže servera | `immich_default`, `postgis`, `proxy` (Traefik) |
| Mountovi servera | `/opt/stacks/immich/docker-data/library` → `/data` (rw); Nextcloud data → `/external-libraries/nextcloud-data` (ro) |
| DB veza | `DB_HOSTNAME=postgis`, korisnik i baza `immich`; jedan klijent (IP servera), 11 praznih veza, `max_connections=100` |
| Ostali kontejneri sa `.env` | `nextcloud_immich_bridge` (docker.sock, Nextcloud data ro), `immich_media_operations` (docker.sock, Nextcloud data rw) |
| Ključevi u `.env` (vrijednosti nisu čitane) | DB_*, IMMICH_API_KEY, IMMICH_EVENT_WEBHOOK_URL/SECRET, MEDIA_OPS_*, BRIDGE_*, OIDC_NEXTCLOUD_* (uključujući client secret) |
| Veličina medija | thumbs 15 GB, encoded-video 5,9 GB, profile 48 KB (izvorne datoteke su u Nextcloudu) |
| Sadržaj baze | 8 korisnika (1 admin, 5 s OAuth vezom, svi imaju lozinku), 8 knjižnica, 1 API ključ, 57.627 asseta: 56.260 u `/external-libraries`, 1.253 u `/data/upload`, 114 u `/data/encoded-video` |
| Konfiguracija u bazi | `system-config` sadrži samo `oauth.*` (uključen OAuth, mobile override); sve ostalo su zadane vrijednosti; `passwordLogin` zadano uključen |
| Migracije | 101 primijenjena u `kysely_migrations`, 101 datoteka u imageu, najnovija `1792213725597-AddAssetFaceAssetState`: **nema nepromijenjenih (pending)** |

### Patchirani build

`patch-server.js` mijenja ponašanje u tri bitna smjera:
- ispravlja migraciju `AlbumOwnerDeleteTrigger` (zato test mora koristiti **isti image po ID-u**, ne službeni `ghcr.io` image i ne ponovni build);
- šalje HTTP webhookove (asset trash/restore/delete, metadata extracted, faces recognized) samo ako su postavljeni **oba** `IMMICH_EVENT_WEBHOOK_URL` i `IMMICH_EVENT_WEBHOOK_SECRET`;
- proxira `/utilities/exif*fix/api` na `MEDIA_OPS_INTERNAL_URL` (zadano `http://media-operations:8091`).

Test ne postavlja te varijable pa su webhookovi i proxy bez učinka; internal mreža dodatno sprječava izlaz.

## 2. Što se izvršava pri pokretanju servera

Izvor: stvarni kod v3.3.5 u pokrenutom kontejneru (`dist/services/*`) i stvarni produkcijski startup log od 2026-11-03 (read-only).

| Aktivnost | Worker | Kad | Učinak na bazu/medije | Kontrola u testu |
| --- | --- | --- | --- | --- |
| Provjera verzije PostgreSQL (≥14) i vector ekstenzije (vchord `>=0.3 <2`, vector `>=0.5 <1`) | oba | bootstrap | read; **može** `CREATE`/`ALTER EXTENSION UPDATE` ako ekstenzije nema ili je dostupna novija; `DROP` ostalih vector ekstenzija osim `vector` uz vchord | verzije su jednake (vchord 1.1.1, vector 0.8.2); PASS = nijedna ekstenzijska izmjena u logu i katalogu |
| `reindexVectorsIfNeeded` za clip_index i face_index | oba | bootstrap | **ponovna izgradnja indeksa** ako `lists` ne odgovara broju redaka; prod log: `targetLists=1, current=1` | PASS = nema reindexa; definicije indeksa jednake |
| `runMigrations` (Kysely) | oba | bootstrap | primjenjuje nove migracije, zatim `VACUUM ANALYZE` samo ako je primijenjena barem jedna | statički: nema pending migracija; PASS = nula `Migration "…" succeeded` |
| `checkSchemaDrift` | oba | bootstrap | read; upozorenja o odstupanju sheme | prod: "No schema drift detected"; PASS = isto na 16.16 bez PostGIS-a |
| Prewarm vchord indeksa | oba | bootstrap | read | očekivano |
| Provjera mount foldera (`.immich` u 6 mapa) | oba | bootstrap | **piše** (`overwriteFile` `.immich`) u `/data/*`; uz `mountChecks` već true čita postojeće markere | test koristi skeleton medijski direktorij s markerima (odjeljak 5) |
| Provjera `MediaLocation` | oba | bootstrap | može masovno prepisati putanje u bazi ako se mount točka razlikuje | test montira točno na `/data` (kao produkcija) |
| ConfigInit: učitavanje konfiguracije | oba | bootstrap | uz `IMMICH_CONFIG_FILE` baza se ne čita za konfiguraciju; `ServerService` upisuje `AdminOnboarding` u `system_metadata` | očekivana razlika u `system_metadata` |
| Cron noćnih poslova (`nightlyTasks`, 00:00) | api (zaključava lock) | konfiguracija | ulančava poslove: cleanup, memories, quota, missing thumbnails, cluster faces | isključeno u config datoteci |
| Cron skeniranja knjižnica, praćenje datoteka | microservices | konfiguracija | skeniranje može **označiti assete offline/trash** u bazi | isključeno; stage A nema microservices |
| Backup baze (02:00, `pg_dump` u `/data/backups`) | microservices | konfiguracija | piše dump u medijski direktorij | isključeno |
| Integrity provjere (03:00) | microservices | konfiguracija | čitanje/checksum datoteka | isključeno |
| Provjera nove verzije (GitHub) | microservices | bootstrap + satno | izlazni HTTP | isključeno; internal mreža ionako blokira |
| Pokretanje worker-a poslova (thumbnail, metadata, face, smart search, OCR, transcoding) | microservices | bootstrap | obrada medija, ML pozivi | stage A **nema** microservices (`IMMICH_WORKERS_INCLUDE=api`) |
| Sinkronizacija workflow pluginova | microservices | bootstrap | piše `plugin`/`plugin_method` ako je hash različit (prod: "up to date") | samo u opcionalnom stageu B |
| Zapis u `version_history` pri promjeni verzije | microservices | bootstrap | upis samo ako se verzija razlikuje (ista v3.3.5) | samo u stageu B |
| Provjera dostupnosti ML-a | oba | bootstrap/30 s | HTTP prema ML URL-u | ML URL ide na testni `ml` |

Posljedica: **API-only start** (`IMMICH_WORKERS_INCLUDE=api`) izvodi migracije, drift provjeru, mount provjeru i servira API, ali **ne pokreće** obradu medija, skeniranje, backup, version check ni integrity cron. Time stage A pokriva ono što je rizično za bazu bez dodirivanja medija.

## 3. Arhitektura izoliranog testa

Sve u jednom Compose projektu `immich-apptest-$CASE_ID` (datoteka [docker-compose.immich-test.yml](../../immich-app-test/docker-compose.immich-test.yml)):

~~~text
 host (bez objavljenih portova)
   │ docker exec / docker compose run
   ▼
 ┌──────────────────── testnet (internal: true) ────────────────────┐
 │ client ──HTTP──► server (immich v3.3.5, api worker)               │
 │                    ├──► db     (PG 16.16, vchord/vector, bez PostGIS)
 │                    ├──► redis  (valkey, bez persistencije)         │
 │                    └──► ml     (CPU, offline, kopija model cachea) │
 └───────────────────────────────────────────────────────────────────┘
 Nema: produkcijskih mreža, portova, docker.sock, Nextclouda, produkcijskog /data i .env
~~~

### Kontrole izolacije

| Kontrola | Mjera |
| --- | --- |
| Mreža | jedina mreža `testnet` je `internal: true` (nema gatewaya, nema izlaza prema internetu ni hostu); nijedna vanjska ili produkcijska mreža nije deklarirana |
| Portovi | nema `ports:`; test klijent radi unutar iste mreže, pa host ne treba port |
| Imena | nema `container_name`; imena su prefiksirana projektom i ne mogu zamijeniti produkcijska |
| Secrets | nema `env_file`; produkcijski `.env` se ne čita. Test koristi nasumične lozinke iz `.env.test` (generate-env.sh, 0600, izvan gita) |
| Produkcijski servisi | nema DNS imena `postgis`, `immich_redis`, `immich-server`, `media-operations`, `traefik` |
| Medij | zaseban `${TEST_ROOT}/media`; Nextcloud data i produkcijski `/data` se ne montiraju |
| Image | `pull_policy: never`, svi image ID-evi zaključani; bez `latest`, bez builda |
| Webhook/OIDC/bridge | odgovarajuće env varijable se ne postavljaju |
| Konfiguracija | [immich-test.config.json](../../immich-app-test/immich-test.config.json): OAuth, SMTP, version check, map, backup, integrity, library scan/watch, noćni poslovi isključeni; ML URL na testni servis |
| Resursi | ograničenja memorije, CPU-a i PID-ova po servisu |

### Provjere izolacije koje su obavezni gate prije prvog logina

1. `docker network inspect` testne mreže: `Internal=true`, točno 5 spojenih kontejnera (ili 4 bez klijenta u stanju mirovanja).
2. `docker inspect` svakog kontejnera: samo mreža `testnet`; `PortBindings` prazno; mountovi točno očekivani (nijedan pod `/opt/stacks/immich`, `/opt/stacks/nextcloud`, `/opt/stacks/data/postgres`, nijedan `docker.sock`).
3. Imena (bez vrijednosti) env varijabli servera ne sadrže `IMMICH_API_KEY`, `OIDC_*`, `BRIDGE_*`, `MEDIA_OPS_*`, `IMMICH_EVENT_WEBHOOK_*`.
4. Iz `client` kontejnera sljedeće mora **ne uspjeti**: razrješavanje `postgis`, `immich_redis`, `immich_server`, `traefik`, `example.org`; TCP prema `1.1.1.1:443` i prema produkcijskoj adresi servera. Uspjeti mora samo `server`, `db`, `redis`, `ml`.
5. Produkcija: broj veza na bazu `immich` jednak prije/poslije i bez veza s testnih adresa; hashevi produkcijskog Composea/`.env` i podaci `docker inspect postgis` nepromijenjeni (isti protokol kao u fazama 4–4C).

## 4. Redis i ML

- **Redis:** zasebna instanca iz istog pinanog imagea, `--save "" --appendonly no`, tmpfs. Ne dijeli ništa s produkcijskim `immich_redis`.
- **ML:** isti image, ali s **kopijom** cachea (`cp -a` iz volumena, 2,1 GB, čitanje produkcijskog volumena je jedina radnja na produkciji) i `HF_HUB_OFFLINE=1`. Produkcijski volumen se ne montira jer ML može pisati lockove u cache. Prije testa potvrditi da su modeli `ViT-B-32__openai`, `buffalo_l`, `PP-OCRv5_mobile` u kopiji; ako nedostaju, test smart searcha je **blokiran**, a ne rješava se vanjskim preuzimanjem.

## 5. Mediji

Immich u produkciji ima 15 GB thumbnailova i izvornike u Nextcloudu. Produkcijski mediji se **ne montiraju** u test, ni samo za čitanje: `verifyWriteAccess` piše `.immich` u svaku mapu pa bi read-only mount srušio startup, a rw bi ugrozio produkciju.

| Opcija | Opis | Pokriva | Rizik | Preporuka |
| --- | --- | --- | --- | --- |
| A. Prazan skeleton | `upload,library,thumbs,encoded-video,profile,backups` s novim `.immich` markerima | startup, migracije, login, albumi, pretraga, popis osoba/lica iz baze | slike se ne prikazuju (očekivano 404) | **stage A (zadano)** |
| B. Sintetički mediji | nekoliko generiranih ili javno dostupnih slika s licima, nova testna knjižnica/korisnik, uključen microservices worker | thumbnail, metadata, detekcija i prepoznavanje novih lica, CLIP embedding, OCR | microservices aktivira obradu; zasebno odobrenje | stage B (opcionalno) |
| C. Uzorak stvarnih thumbnailova | kopija ≤200 derivata iz `/data/thumbs` u test direktorij | vizualni prikaz | kopiranje korisničkih fotografija (derivata) unutar hosta | samo uz izričito odobrenje |

Skeleton marker: nova datoteka `.immich` sa sadržajem `date +%s%3N` u svakoj od šest mapa (sadržaj nije bitan, kod ga samo čita i prepisuje). Kopija produkcijskih markera nije potrebna. Mount na `/data` osigurava da se `MediaLocation` ne mijenja.

## 6. Funkcionalni testovi

Skripta [client/smoke_test.py](../../immich-app-test/client/smoke_test.py) (samo standardna biblioteka; piše samo brojeve, statuse i vremena u `/results/smoke.json`):

| Test | Endpoint | Očekivanje |
| --- | --- | --- |
| Ping, verzija, značajke | `GET /api/server/ping`, `/about`, `/features` | verzija v3.3.5; `configFile=true`, `oauth=false`, `passwordLogin=true`, `email=false` |
| Login | `POST /api/auth/login` | token za testnog administratora |
| Albumi | `GET /api/albums`, `/albums/{id}` | broj albuma i asseta jednak očekivanju iz baseline baze |
| Pretraga metapodataka | `POST /api/search/metadata` | rezultati > 0 |
| Pametna pretraga | `POST /api/search/smart` | rezultati > 0 (traži testni ML) |
| Popis osoba, statistika | `GET /api/people`, `/people/{id}/statistics` | broj osoba jednak bazi |
| Pretraga po osobi, lica na assetu | `POST /api/search/metadata` (`personIds`), `GET /api/faces?id=` | rezultati i lica > 0 |

Napomene:
- **Login:** stvarne lozinke nisu poznate. Na **testnoj kopiji baze** (nikad na produkciji) postavlja se `user.password` odabranog administratora na bcrypt hash nasumične testne lozinke. Hash se generira istim `bcrypt` modulom iz imagea u jednokratnom kontejneru s `--network none`. Ta izmjena se izvodi prije baseline snapshota B0 i evidentira kao jedina planirana razlika naspram izvora.
- **Prepoznavanje lica:** u stageu A testira se postojeće prepoznavanje (osobe, lica, pretraga po osobi) iz baze. Detekcija i prepoznavanje **novih** lica traži microservices worker i medij (stage B sa sintetičkim slikama).
- Izravni DB `SELECT`ovi `media-operations` ne spadaju u aplikacijski test servera. Njihova kompatibilnost provjerava se odvojeno, read-only, na testnoj bazi (odjeljak 7, stage A4).

## 7. Runbook testa (nije izvršen)

Datoteke: [immich-app-test/](../../immich-app-test/) (`docker-compose.immich-test.yml`, `immich-test.config.json`, `env.test.example`, `generate-env.sh`, `client/smoke_test.py`, `tools/compare_db.py`, `sql/schema-manifest.sql`). Compose je statički validiran (`docker compose config`), nije pokretan.

Okvir: `CASE_ID` iz `generate-env.sh`; `dc() { docker compose -p immich-apptest-$CASE_ID --env-file .env.test -f docker-compose.immich-test.yml "$@"; }`. Svaki korak se zaustavlja na prvoj neočekivanoj razlici.

### Stage 0 — gateovi (bez ikakvih kontejnera)
1. Provjeriti slobodan prostor (≥ 96 GiB), memoriju (budžet kontejnera ukupno ≈ 14,5 GiB: db 4, ml 6, server 4, redis 0,5) i da ne postoje resursi imena `immich-apptest-*`.
2. SHA-256 sanitiziranog dumpa `27d2bbf36980888b050d0e7a502a8d111fecf2889fa30d21113f3a38dc6cf415` i SHA256SUMS faza 4/4B.
3. Postojanje svih pinanih imagea (`docker image inspect`).
4. Zabilježiti produkcijski protection baseline (kao u fazama 4–4C).
5. `./generate-env.sh`; stvoriti `$TEST_ROOT` (0700) s `db-data` (vlasnik 999:999), `ml-cache`, `media` (skeleton), `results`.

### Stage A1 — baza
1. `dc up -d db`; čekati healthy; potvrditi PG 16.16 i da PostGIS nije dostupan.
2. Kreirati rolu `immich` (nesuperuser, `LOGIN`, test lozinka) i bazu `immich` iz `template0` (UTF8, `en_US.utf8`, owner immich).
3. `pg_restore --exit-on-error --jobs=2 /sanitized.dump` (bez `--clean/--create`); log mora biti prazan.
4. Primijeniti DB ACL kao u izvoru. **Normalizirati sekvencu** `ALTER SEQUENCE public.naturalearth_countries_tmp_id_seq1 AS bigint MINVALUE 1 MAXVALUE 2147483647 START WITH 1 INCREMENT BY 1 CACHE 1 NO CYCLE;` i provjeriti tip, last_value 4274, is_called true.
5. Statička provjera migracija: popis `dist/schema/migrations` iz imagea (`docker run --rm --network none --entrypoint ls $TEST_SERVER_IMAGE …`, ne pokreće Immich) mora odgovarati `kysely_migrations`; očekivano 101 = 101, pending = 0. Svaka razlika je **HOLD** prije starta.
6. Postaviti test lozinku administratora (jedina planirana izmjena podataka) i odrediti e-mail u `.env.test`.
7. **Snapshot B0:** `python3 -I tools/compare_db.py snapshot --container <db> --out $TEST_ROOT/results/B0`.

### Stage A2 — poslužitelj i migracije
1. `dc up -d redis ml`, potom `dc up -d server` s `TEST_WORKERS=api`, `TEST_DB_SKIP_MIGRATIONS=false`.
2. Provjere izolacije iz odjeljka 3 (gate).
3. Pregled loga: vidi PASS kriterije (odjeljak 9).
4. Zaustaviti server, **snapshot B1**, `compare_db.py diff --before B0 --after B1 --allow session,system_metadata` (stroga usporedba metapodataka, 72 hasha, sekvence informativno).
5. Ponovni start (idempotentnost), snapshot B2, `diff B1 B2 --allow session,system_metadata`.

### Stage A3 — funkcionalni testovi
1. `dc up -d server`; `dc run --rm client python -I /tests/smoke_test.py` s očekivanim brojevima (`EXPECT_ALBUMS`, `EXPECT_PEOPLE_TOTAL`) iz B0 baze.
2. Vremena i rezultati u `results/smoke.json`; `docker logs` sanitizirati (bez e-mailova/imena) prije spremanja.
3. Snapshot B3 i diff naspram B2 uz isti allow-list.

### Stage A4 — usporedba upita
Upiti `media-operations` (SQL iz `server.js`, tri putanje `runPostgresRowsQuery`) izvode se **read-only** na testnoj bazi (`BEGIN READ ONLY`) i uspoređuju s rezultatima iz sanitiziranog restorea na 16.13 (faza 4C obnavlja isti dump); cilj je potvrditi da ne zahtijevaju PostGIS ni 16.13 ponašanje.

### Stage B (opcionalno, zasebno odobrenje)
`TEST_WORKERS=api,microservices`, sintetički mediji i testni korisnik, uz isti compose i config. Dodatni allow-list: tablice `asset*`, `person*`, `smart_search`, `face_search`, `notification`, `plugin*`, `version_history` isključivo za retke sintetičkog korisnika; svi redci produkcijskih korisnika moraju ostati hash-identični. Očekivano: thumbnail, metadata, detekcija i prepoznavanje lica te CLIP embedding za sintetičke slike, uz ML bez interneta.

### Stage C — čišćenje
Vidi odjeljak 10.

## 8. Provjera automatskih migracija sheme

| Provjera | Metoda | PASS |
| --- | --- | --- |
| Pending migracije prije starta | popis iz imagea naspram `kysely_migrations` | 0 |
| Što je server izvršio | log: redci `Running migrations`, `Finished running migrations`, `Migration "…" succeeded` | nijedan `succeeded`; `kysely_migrations` jednak B0 |
| Drift | log `No schema drift detected` | da; svako upozorenje analizirati, ne popravljati automatski |
| Ekstenzije | katalog prije/poslije; log bez `Updating … extension` i bez `DROP EXTENSION` | verzije i popis jednaki |
| VectorChord indeksi | log `targetLists=1, current=1`; definicije u katalogu | nema reindexa; indeksi valid/ready |
| Katalog sheme | `compare_db.py diff` (relacije, indeksi, constraintovi, funkcije, triggeri, tipovi, ACL, default ACL, sekvence) | metadata B1 jednak B0 (bez iznimki) |
| Podaci | 72 hasha | razlike samo u `session`, `system_metadata` |
| Sekvence | `last_value` | informativno; ne smiju pasti ispod najvećeg ključa |
| Idempotentnost | drugi start (B2) | bez novih razlika |

## 9. Kriteriji PASS / FAIL

**PASS za stage A** samo ako su istodobno zadovoljeni:
1. Svi gateovi izolacije (odjeljak 3) prošli; produkcijski protection baseline nepromijenjen.
2. Restore sanitiziranog dumpa exit 0, prazan log; normalizacija sekvence prošla; B0 jednak izvoru osim planirane promjene lozinke.
3. Server dosegne healthy bez `ImmichStartupError`, bez izmjene ekstenzija, bez reindexa i bez migracija.
4. `No schema drift detected` i mount provjere uspješne.
5. B1 i B2 metadata jednaki B0; promijenjene tablice ⊆ {`session`, `system_metadata`}.
6. Svi testovi iz odjeljka 6 prošli, a brojevi albuma i osoba jednaki bazi.
7. Nijedan izlazni pokušaj prema internetu ili produkciji (probe iz odjeljka 3 i logovi).

**FAIL / HOLD** pri bilo kojem od: neočekivana razlika metapodataka ili podataka, migracija ili reindex koji se ne očekuje, upozorenje o driftu bez objašnjenja, pogreška pri startu, test koji ne prolazi, nepoznata mrežna veza, promjena produkcijskog stanja. Nema popravljanja "u hodu"; test se zaustavlja, dokumentira i traži odluku.

Napomena: odluku o pragovima recall-a/latencije i dalje nitko nije donio. Rezultati ML-a i pretrage se mjere i evidentiraju, ali bez dogovorenog praga ne postoji produkcijski GO.

## 10. Čišćenje

1. Spremiti rezultate i sanitizirane logove u privatni direktorij `/opt/stacks/data/backups/immich-apptest-$CASE_ID` (0700, gitignored): `results.json`, `smoke.json`, snapshotovi B0–B3 (metapodaci i hashevi, bez redaka), SHA256SUMS. Izvještaj se sprema **prije** čišćenja.
2. `dc down` (s `-p`; bez `-v`, nema imenovanih volumena).
3. Provjeriti `realpath "$TEST_ROOT"` pod `/tmp/immich-apptest-`, label i da nijedan proces ne koristi putanju; tek tada `rm -rf "$TEST_ROOT"` i brisanje `.env.test` (nasumične testne lozinke).
4. Potvrditi: nema kontejnera/mreža `immich-apptest-*`; produkcijski protection baseline isti.
5. Zabranjeno: `docker system prune`, `docker volume prune`, `docker compose down` bez `-p`, brisanje postojećih backupova, sanitiziranog dumpa i privatnih arhiva faza 4–4C.

## 11. Uvjeti za budući produkcijski cutover (gate)

| Gate | Uvjet |
| --- | --- |
| G1 | Aplikacijski test (stage A) PASS; opcionalni stage B PASS ili izričito izostavljen odlukom |
| G2 | Dogovoreni pragovi recall-a i latencije te prihvaćen prozor prekida (RPO/RTO) |
| G3 | Odobren dokumentirani postupak za OIDC (ručna provjera prijave nakon prebacivanja) |
| G4 | `immich-db` image, mreža i ime kontejnera `immich-db` potvrđeni (zbog `media-operations`); `media-operations` upiti provjereni (A4) |
| G5 | Slobodan prostor ≥ 96 GiB; novi dump i bridge ne ugrožavaju rezervu od 80 GiB |
| G6 | Off-host kopija pune produkcijske baze prije prozora |
| G7 | Provjeren rollback (dolje) i odobrena retencija izvorne baze |
| G8 | Izričito odobrenje za promjenu produkcijskog `.env`/recreate i za fence izvorne baze |

## 12. Predloženi postupak produkcijskog prebacivanja (nije odobren)

### Mjereni okvir (faze 4–4C, host u mirovanju)
Puni dump 40,7 s; bridge restore 17,9 s; hash 72 tablice 21 s po strani; `DROP EXTENSION postgis RESTRICT` oko 1 s; sanitizirani dump 40,3 s; restore na PG 16.16 17,9 s. Zbroj DB koraka s jednim usporednim hashiranjem oko 3 min. To je izmjereno na testnim kopijama bez opterećenja; **nije SLA**. Planirani prozor: 30 min uz budžet do 45 min (uključuje pražnjenje redova, zaustavljanje/pokretanje servisa, validaciju i odluku).

### P0 — prije prozora (bez prekida)
1. Odobrenja G1–G8. Off-host kopija postojeće baze.
2. Podići trajni `immich-db` iz `docker-compose.postgres-new.yml` (samo taj servis; prazan `/opt/stacks/data/immich-postgres/data`); provjeriti PG 16.16, ekstenzije dostupne, PostGIS nedostupan.
3. Kreirati rolu `immich` s produkcijskom lozinkom (iz `DB_PASSWORD`, bez ispisa u logove) i praznu bazu `immich` (owner immich, `template0`, UTF8, `en_US.utf8`) te DB ACL.
4. Pripremiti (ne primijeniti) izmjenu `/opt/stacks/immich/.env`: `DB_HOSTNAME=immich-db`; sigurnosna kopija `.env` (0600).

Preporuka: **bez probnog restorea u trajni `immich-db`**; rehearsal je već izveden u izoliranim kontejnerima, a trajni data direktorij bi nakon probe trebao brisanje (zahtijeva odobrenje).

### P1 — zamrzavanje pisanja (T0)
1. Obavijest korisnicima. Pauzirati sve Immich redove poslova (API) i pričekati `active=0` (najviše 10 min). Ako se ne isprazne, dokumentirati i prihvatiti ponovni pokušaj zaglavljenih poslova.
2. Zaustaviti redom: `nextcloud_immich_bridge`, `immich_media_operations`, `immich_server`. ML i Redis ostaju (nemaju DB).
3. Potvrditi 0 veza na bazu `immich` na izvoru (`pg_stat_activity`). Zaštititi izvor od slučajnog restarta: `REVOKE CONNECT ON DATABASE immich FROM PUBLIC, immich` (reverzibilno `GRANT`).

### P2 — konačni dump (nakon zamrzavanja nema pisanja pa dodatni snapshot nije potreban)
`pg_dump -Fc --compress=gzip:6` u novi privatni direktorij `/opt/stacks/data/backups/immich-cutover-$ID` (0700), SHA-256, read-only hash 72 tablice izvora.

### P3 — sanitizacija
Bridge iz originalnog imagea (network none): restore, normalizacija sekvence, usporedba s izvorom, `DROP EXTENSION postgis RESTRICT`, sanitizirani dump, provjera TOC-a (bez PostGIS).

### P4 — restore u immich-db
`pg_restore --exit-on-error --jobs=2` u `immich`; normalizacija sekvence; DB ACL; `ANALYZE`; usporedba metapodataka (jedina dopuštena iznimka: tekst `pg_get_indexdef` za `asset_localDateTime_month_idx`, vidi [12](12-immich-index-validation.md)), 72 hasha, indeksi valid/ready, sekvence ≥ najveći ključ.

### P5 — prebacivanje aplikacije
1. Primijeniti `DB_HOSTNAME=immich-db` u `/opt/stacks/immich/.env`. Taj `.env` čitaju server i `media-operations`; `media-operations` pristupa bazi preko `docker exec immich-db psql`, pa ime kontejnera mora biti točno `immich-db`.
2. Recreate samo `immich-server` i `media-operations` iz postojećeg imagea (**bez `--build`**, da image ID ostane `619fb163…`); server je već na mreži `postgis` na kojoj je `immich-db`.
3. Log mora pokazati: 0 migracija, "No schema drift detected", `targetLists=1`, mount provjere uspješne.

### P6 — validacija prije otvaranja
Read-only API pozivi uz postojeći API ključ (albumi, pretraga, osobe, smart search), pregled `pg_stat_activity` na `immich-db`, ručna provjera OIDC prijave koju obavlja vlasnik. Odluka GO/NO-GO; zabilježiti T_write.

### P7 — otvaranje i praćenje
Pokrenuti `nextcloud_immich_bridge`, nastaviti redove, pratiti greške, veze, latenciju pretrage, noćni backup (02:00) i integrity provjere najmanje jedan puni dan. Izvorna baza ostaje netaknuta i zaštićena; njezino brisanje je zaseban zahvat s izričitim odobrenjem.

### Rollback
- **Prije prvog pisanja na `immich-db`:** vratiti `DB_HOSTNAME=postgis`, ukloniti fence (`GRANT CONNECT`), recreate servera i `media-operations`. Izvor nije mijenjan, pa nema gubitka podataka.
- **Nakon pisanja:** novi zapisi postoje samo na `immich-db`. Povratak znači `pg_dump` iz `immich-db` i restore u novu bazu na `postgis`, uz zasebnu odluku o gubitku. Zato prije P7 treba odrediti točku bez povratka i njezino trajanje.

### Što "završna sinkronizacija" znači za Immich
Nema inkrementalne sinkronizacije: jedina promjena je baza. Datoteke (`/data`, Nextcloud) ostaju na istim putanjama i ne kopiraju se. Konzistentnost osigurava zamrzavanje pisanja i dump nakon njega. Redis stanje se ne migrira (prazni se prije zamrzavanja).

## 13. Preostali rizici

| Rizik | Kontrola / otvoreno |
| --- | --- |
| Test koristi config datoteku, produkcija bazu s OAuth-om | OIDC se ne može testirati u izolaciji; ručna provjera nakon prebacivanja; rollback prije T_write |
| `media-operations` koristi `docker exec <DB_HOSTNAME> psql` i docker.sock | kontejner mora imati ime `immich-db`; A4 provjera upita; nikad se ne uključuje u test |
| Drift/izmjena sheme zbog sekvence (`integer`→`bigint`) ili indeksne tekstualne razlike | test se izvodi s normaliziranom sekvencom i na 16.16; svako upozorenje analizirati |
| Patchirani image i migracija | isti image po ID-u; nikad službeni image ni rebuild tijekom prebacivanja |
| Gubitak redova poslova (Redis bez volumena) | pauza i pražnjenje prije zamrzavanja; nakon recreatea provjeriti i po potrebi pokrenuti "missing" poslove |
| Webhookovi i integracije prema produkciji | test ne postavlja tražene varijable; internal mreža |
| Neposredno pisanje u produkcijski `/data` | test ga ne montira |
| Modeli ML-a ne postoje u kopiji cachea | test smart searcha tada je blokiran; bez preuzimanja s interneta |
| Reindex vchord indeksa pri startu | `targetLists=1`; svaka promjena broja redaka preko praga ponovno se izračunava prije cutovera |
| Pragovi recall-a/latencije, prozor prekida i retencija izvora nisu odobreni | blokiraju produkcijski GO |
| Sirovi dump i test baza sadrže osobne podatke i hasheve lozinki | privatni 0700/0600, bez gita, brisanje nakon testa |
| Test nije jednak produkciji (stage A bez medija i microservicesa) | prepoznato; stage B i post-cutover provjera |

## 14. Što treba odobriti za sljedeću fazu (5B)

1. Izvođenje stagea 0, A1–A4: stvaranje `/tmp/immich-apptest-$CASE_ID`, kopija model cachea (čitanje produkcijskog volumena), jedan restore sanitiziranog dumpa u testni PG 16.16, pokretanje 4 testna kontejnera + klijenta na internal mreži, izmjena lozinke administratora **samo na testnoj kopiji**.
2. Odabir opcije medija (A / A+B / C) i odobrenje stagea B (microservices worker i sintetičke slike) ako se želi test detekcije novih lica.
3. Potvrda da se test izvodi bez produkcijskog `.env`, `docker.sock` i produkcijskih mreža (dokumentirano gore).
4. Pragovi recall-a/latencije i dopušteni prozor prekida (ne blokira 5B, blokira cutover).
5. Pravilo čišćenja: brisanje testnih kontejnera i `/tmp` direktorija nakon spremanja izvještaja; zadržavanje privatnih rezultata.

## 15. Izvršene naredbe i što nije izvršeno

Izvršeno (isključivo čitanje i lokalne datoteke):
- čitanje dokumentacije faza 1–4C, `/opt/stacks/immich` Composea, `.env` samo kao popis ključeva (vrijednosti zacrnjene), `patch-server.js`, `docker-compose.postgres-new.yml`, `Dockerfile.immich-db`;
- `docker inspect` (image, env ključevi bez vrijednosti, mountovi, mreže, `RestartCount`) i `docker network inspect` produkcijskih kontejnera;
- čitanje izvornog koda v3.3.5 u pokrenutom kontejneru (`docker exec … sed/grep`) i produkcijskog startup loga od 2026-11-03;
- read-only SQL (`BEGIN READ ONLY`, kratak timeout) nad `postgis/immich`: broj migracija, ključevi `system_metadata`, struktura `system-config` s vrijednostima samo za boolean/broj, brojevi korisnika/knjižnica/asseta, `pg_stat_activity` bez izmjena;
- `du`, `df`, `free`;
- `docker compose config` nad testnim Composeom (parsiranje, bez pokretanja), `py_compile` i `bash -n` nad novim skriptama;
- izrada datoteka u `immich-app-test/` i ovog dokumenta.

**Nije izvršeno:** nijedan kontejner, mreža ni volumen; nikakav dump ni restore; nikakva migracija ni pozadinski posao; nikakva promjena produkcijskog Composea, `.env`, tajni, mreža, baza ili podataka; nikakvo brisanje backupova i privatnih arhiva.

**Stati ovdje. Aplikacijski test, kontejneri i migracija ne pokreću se bez novog odobrenja. Produkcijska migracija nije odobrena.**
