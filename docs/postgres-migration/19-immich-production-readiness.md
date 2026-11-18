# 19 — Immich: produkcijska spremnost (faza 7)

Datum: 15. studenoga 2026. (Europe/Zagreb).
Status: **pregled spremnosti; cutover nije odobren ni pokrenut.** Nad produkcijom izvršeno je samo čitanje. Nadovezuje se na [17](17-immich-production-cutover.md) i [18](18-immich-cutover-rehearsal.md).

## 0. Sažetak

- Produkcija je zdrava i identična stanju prije pripreme; `preflight.py` u produkciji: **0 FAIL, 1 WARN** (WARN = API provjere preskočene jer privremeni ključevi još ne postoje).
- `offline_selftest.sh`: 12/12 PASS.
- Svih 9 ispravaka iz rehearsala ugrađeno je u `steps.sh`, skripte i doc 17 (odjeljak 3).
- Pronađeno je **jedno tehničko ograničenje** (nema skriptiranog povratka ako `s_open` zakaže prije nego server postane dostupan, odjeljak 8) i jedna **ispravka dokumenta** (popis dozvola ključeva, odjeljak 5). Ostalo su odluke.
- **GO još nije moguć**: nema odredišta za off-host kopiju, privremeni ključevi nisu kreirani, pragovi, termin i osobe nisu odobreni.

## 1. Stanje produkcije (samo čitanje, 15.11.2026. 09:35)

| Provjera | Nalaz |
| --- | --- |
| Servisi Immich | `immich_server` (image `sha256:619fb163…`), `immich_media_operations`, `nextcloud_immich_bridge`, `immich_machine_learning`, `immich_redis`, `postgis`, `traefik`: svi `running`, zdravi, 0 restartova; `StartedAt` nepromijenjen (server 3.11., redis i postgis 26.6.) |
| PostgreSQL | `postgis` 16.13 (PostGIS 3.6.2), baza `immich` 1192 MB, 72 tablice, 57.627 asseta, 9 ekstenzija na validiranim verzijama, 101/101 migracija, 0 nevaljanih indeksa, rola `immich` bez ovlasti (nije superuser, pa `REVOKE CONNECT` stvarno štiti) |
| Veze na izvor | samo `immich_server` (172.28.0.11, 9–11 praznih veza `postgres.js`); nema drugog potrošača; nema `pg_cron` poslova ni cron zadataka koji diraju Immich bazu |
| ACL baze `immich` | `{=Tc/immich, immich=CTc/immich}` (ostalo kao prije; fence je još neaktivan) |
| Disk | `/` 2,0 TB, 77 %, **436 GiB slobodno** (prag 96 GiB), RAM 74 GiB slobodno |
| Immich backupovi | 14 datoteka u `/opt/stacks/immich/docker-data/library/backups`, najnoviji `immich-db-backup-20261115T020000-v3.3.5-pg16.13.sql.gz` (355,2 MB, star 7,6 h), `gzip -t` OK, pg_dump klijent 16.15 |
| Migracijski dokazi | privatni direktoriji u `/opt/stacks/data/backups/immich-*` (0700), plus `pre-immich-cutover/postgis-globals-…sql` (4.4.), svi sačuvani |
| `immich-db` | ne postoji; `immich-postgres/data` prazan; image `sha256:e21ee65b…` prisutan; mreža `postgis` slobodna (42 sudionika) |
| Config drift | Compose hash za `redis` jednak je pokrenutom; za `immich-server` i `media-operations` razlikuje se (oba su `build:` servisi, a `config --hash` ne vidi izgrađeni image), ali **env, labeli, mountovi, mreže i image ID su identični** onome što Compose renderira; dakle recreate bez builda mijenja samo ono što override zadaje |
| Napomena izvan opsega | `fiskal_otel_collector` se restarta, `farma_frontend` je `unhealthy`; nisu povezani s Immichom i nisu diran |

Dokaz preflighta (bez tajni): `/opt/stacks/data/backups/immich-cutover-readiness-20261115/preflight-20261115T083505.json` (jedini zapis ovog pregleda, 0700).

## 2. Selftest

`immich-cutover/tests/offline_selftest.sh`: **ALL OFFLINE CHECKS PASSED** (12/12: usporedba, 5 ručno pokvarenih kopija, `delta`, odbijanje `--execute`, odbijanje produkcijskih imena u rehearsal načinu, kompilacija skripti).

## 3. Devet ispravaka iz rehearsala u završnom runbooku

| # | Ispravak | Gdje je ugrađen (provjereno) |
| --- | --- | --- |
| 1 | lozinka iz okoline kontejnera, ne iz `.env` | `steps.sh:52` `getsecret.py "$SRV" DB_PASSWORD`; doc 17 §1.1 |
| 2 | prijava preko mrežne adrese + negativna kontrola | `steps.sh:58-62`, `validate_target.py` V6 |
| 3 | ACL baze izvora ne uspoređuje se, V4 uspoređuje sortirano | `db_snapshot.py:55`, `validate_target.py` V4, `steps.sh` (`source-db-acl.before`) |
| 4 | usporedba bridgea prije i poslije `DROP EXTENSION … RESTRICT` | `steps.sh:136-139` |
| 5 | `backgroundTask` se ne može pauzirati | `api_checks.py:23,108` (`UNPAUSABLE`, wait-drain, `held`) |
| 6 | dark launch samo s API workerom | `docker-compose.dark.yml` (`IMMICH_WORKERS_INCLUDE: api`), `steps.sh:206` (STOP-6 ako se pojavi "Starting microservices worker") |
| 7 | baseline nakon pražnjenja redova | `steps.sh:76` |
| 8 | V10 prema zamrznutom izvoru | `steps.sh:180` (`--source-snapshot`), `validate_target.py` V10 |
| 9 | strogi exit kodovi i vrata odobrenja | `steps.sh:8,40,46,68` (`set -Eeuo pipefail`, `CUTOVER_APPROVED`) |

Svih 9 ispravaka prisutno je i u tekstu doc 17.

## 4. Off-host kopija (G6), bez kopiranja

**Što postoji:** alati `rsync`, `ssh`, `scp`, `gpg`, `zstd`. **Ne postoji:** `rclone`, `restic`, `borg`, `age`; nema konfiguriranih SSH odredišta (samo `github.com`); nema crontab ni timer zadatka za off-host backup. Tailscale peerovi su većinom offline ili neprovjereni, pa nijedan ne smatram pouzdanim odredištem.

**Što nije off-host:** `/home` je zaseban datotečni sustav (`md3`, 1,5 TB, prazan), ali leži na istom paru NVMe diskova (RAID1) kao `/`, na istom hostu. Štiti od greške datotečnog sustava, ne od gubitka hosta ili diskova. Svi dnevni Immich backupovi također su na istom hostu.

**Prijedlog (traži odluku vlasnika):**
1. Odredište: **zaseban sustav izvan `dedicated-hel1`**, po prvenstvu: (a) Hetzner Storage Box (isti pružatelj, SSH/rsync na portu 23, podračun s vlastitim ključem), ili (b) vlasnikovo računalo preko Tailscalea koje je pouzdano uključeno u prozoru. Ništa od toga nisam provjeravao niti kontaktirao.
2. **Šifrirati prije slanja** (`gpg` je dostupan): dump sadrži OIDC `clientSecret` u `system_metadata`, hashirane API ključeve, sesije, GPS i embeddinge lica. Ključ čuvati izvan hosta.
3. Što slati: najnoviji Immich backup (`…pg16.13.sql.gz`, 355 MB) prije prozora (G6), a nakon dumpa u prozoru i `immich.full.dump` (354 MB) uz SHA-256; provjera hasha na odredištu.
4. Pristup: poseban SSH ključ samo za taj cilj, bez prava na ostale direktorije; `rsync --partial`, nikad `--delete`.
5. Napomena: DB backup ne pokriva medije (`/data/upload`, `encoded-video`, `thumbs`); njihov off-host status nije u opsegu ovog plana, ali ga treba svjesno potvrditi.

## 5. Privremeni API ključevi (G10)

**Trenutno stanje:** u tablici `api_key` postoji jedan redak, `nextcloud-immich-bridge`, s dozvolama `adminUser.create/read/update`, `library.create/read/update/delete/statistics`. Ne smije se prenamjenjivati. Nema `queue.*`, `job.*`, `asset.read`, `album.read`, `person.read`, `server.*`.

**Kako se stvaraju:** ključ se stvara u Immich UI-ju (Account Settings → API Keys) kao prijavljeni korisnik; API `POST /api-keys` traži `apiKey.create` i sesiju, što bridge ključ nema, pa to ne radi nikakva skripta. Tajna se prikaže jednom i unosi se u ljusku s `read -rs`. Operacija je **jedan INSERT u produkcijsku bazu** (O2): radi se **prije** zamrzavanja da retci uđu u dump (V10 uspoređuje broj ključeva sa zamrznutim izvorom), reverzibilno brisanjem ključa u UI-ju.

**Najmanji potreban skup** (dozvole provjerene u kodu image-a, `Permission.*` po kontroleru, i prema stvarnim pozivima `api_checks.py`):

| Ključ | Vlasnik | Dozvole | Zašto |
| --- | --- | --- | --- |
| admin | administrator | `queue.read`, `queue.update`, `job.create`, `server.about`, `server.statistics`, `library.read`, `library.statistics` | `GET /queues`, `PUT /queues/{naziv}` (pauza), `POST /jobs` (backup), `GET /server/about`, `GET /server/statistics`, `GET /libraries`, `GET /libraries/{id}/statistics` (svi `admin: true`, pa vlasnik mora biti admin) |
| korisnik | korisnik s podacima (npr. vlasnik biblioteke) | `asset.read`, `album.read`, `person.read` | `POST /search/smart`, `GET /albums`, `GET /people` |

**Ispravak doc 17 (izvršen):** F0 je navodio i `job.read`, `apiKey.read` i `server.about` za korisnika, koje nijedan poziv ne koristi; uklonjeno radi najmanjih ovlasti. Ako se želi ručni `library.update` (ručno skeniranje), dodaje se zasebno uz odobrenje O12. Revokacija: brisanje ključeva u UI-ju nakon završetka retencije (ili ranije, odmah nakon F11 ako se ne trebaju za 24 h provjere).

## 6. Redoslijed zaustavljanja, zamrzavanja i zaštite izvora

Potvrđeno prema `steps.sh` (`s_freeze`, `s_fence_inner`):

1. T0 i zapis ACL-a izvora (`source-db-acl.before`).
2. `queues pause --execute` (svi redovi osim `backgroundTask`), `wait-drain` do `active == 0` (STOP-1 pri isteku; još ništa nije zaustavljeno).
3. `api_checks.py baseline` → `api-baseline.json` (zamrznuto stanje).
4. `docker stop -t 60`: `nextcloud_immich_bridge`, `immich_media_operations`, `immich_server` (u tom redoslijedu).
5. Provjera: 0 veza na bazu `immich` (STOP-2).
6. Zaštita: `REVOKE CONNECT … FROM PUBLIC`, `FROM immich`, `pg_terminate_backend`.
7. Dump, bridge, restore, validacija, dark launch (F5–F8).

Zaštita je učinkovita jer rola `immich` nije superuser; Redis nije dotaknut.

**Rizik koji redoslijed ostavlja:** između koraka 3 (baseline) i 4 (zaustavljanje servera) korisnik može uploadati (sekunde); redovi su pauzirani, ali zapis ide u bazu. To je već u K9: razlika se objašnjava usporedbom baza (`compare` PASS), ne API-jem. **Prijedlog (odluka D1):** zaustaviti `nextcloud_immich_bridge` i `immich_media_operations` *prije* pauze redova (oni su skriptirani pisci koji generiraju najviše posla u prozoru), a server zadnji. Zahtijeva izmjenu `steps.sh` i ponovni rehearsal `gStop`; nisam mijenjao skripte. Ako se ne prihvati, ostaje trenutni redoslijed uz objašnjenje K9.

## 7. Redis tijekom cijelog prebacivanja

Potvrđeno da ostaje aktivan i netaknut:
- `steps.sh` ne sadrži nijednu naredbu prema `immich_redis`; svi `compose up` pozivi imaju `--no-deps --no-build --pull never` i imenuju samo `immich-server` ili `media-operations`; `docker stop` ide samo na bridge, `media-operations` i server. Skripte ne rade `FLUSH*`.
- Compose hash Redisa jednak je pokrenutom (čak ni obični `up` ga ne bi mijenjao), ali nikada se ne koristi obični `up`.
- Stanje: Valkey 9.0.3, 62 ključa, 9,5 MB, `maxmemory-policy noeviction` (ispravno za BullMQ), `appendonly no`, RDB `save` pravila, **bez volumena**: restart ili recreate gubi redove i pauzu. Gubitak Redisa ne bi pokvario bazu, ali bi izgubio zadržane poslove (miniaturе, embeddinge) koje bi trebalo pokrenuti kao "missing" poslove.
- U dark fazi 81 klijentska veza (server, workeri) se prekine zaustavljanjem servera i ponovno uspostavi pri startu; Redis ostaje.
- **Odluka D2 (neobvezno):** prije T0 spremiti kopiju RDB-a (npr. `valkey-cli --rdb` u `$EV`) kao osiguranje; to je dodatno čitanje Redisa i traži odobrenje; nije u skriptama.

## 8. Rollback i točka bez povratka

- **PONR = T_open**: `s_open` zapisuje `T_open`, mijenja samo `DB_HOSTNAME` u `.env` i recreateira server bez dark override-a. Do tada izvor je netaknut i `s_rollback_r1` vraća stanje (probano u rehearsalu, RPO 0, ≈10 min). `s_rollback_r1` odbija rad ako postoji `T_open` (exit 3).
- Nakon T_open nema skriptiranog rollbacka (R2: A gubitak podataka od T_open, B povratna migracija neprobana, C ispravak unaprijed); izvor se čuva ≥ 7 dana za forenziku, ne kao praktičan rollback.
- **Pronađeno ograničenje (preporučeno zatvoriti prije GO):** `T_open` se zapisuje *prije* izmjene `.env` i recreatea. Ako `s_open` zakaže ranije (diff `.env`, `compose up`, zdravlje), promet još nije stigao do nove baze, ali `s_rollback_r1` odbija rad zbog `T_open`, a skripta za siguran povratak (vratiti `.env` iz `immich.env.before`, ukloniti `T_open`, pokrenuti R1) ne postoji. Preporuka: korak `s_open_abort` koji je dopušten samo ako server nikad nije bio healthy bez dark labela; probati ga u rehearsalu. Do tada bi takav kvar zahtijevao ručnu odluku (O14).
- `nextcloud_immich_bridge` i `immich_media_operations` ponovno se pokreću na novoj bazi tek u `s_open`; `media-operations` zahtijeva da kontejner baze ima točno ime `immich-db` (ima ga).

## 9. GO/NO-GO checklist

### 9.1 Spremnost (prije zakazivanja prozora)

| ID | Uvjet | Status 15.11. |
| --- | --- | --- |
| G1 | Stage A/B testovi | ispunjen |
| G2 | pragovi i prozor | **OTVOREN** |
| G3 | osoba za OIDC provjeru | **OTVOREN** |
| G4 | image, mreža, ime `immich-db` | ispunjen (potvrđeno preflightom T1, T2, N1, I1) |
| G5 | disk ≥ 96 GiB | ispunjen (436 GiB) |
| G6 | off-host kopija | **OTVOREN** (nema odredišta, odjeljak 4) |
| G7 | rollback i retencija | **OTVOREN** (R1 probano na kopiji; retencija nije odobrena) |
| G8 | odobrenje promjene `.env`, recreatea, zaštite | **OTVOREN** |
| G9 | rehearsal | ispunjen |
| G10 | privremeni ključevi | **OTVOREN** (nisu kreirani; odjeljak 5) |
| G11 | obavijest korisnicima, utišan Uptime Kuma | **OTVOREN** |
| G12 (novo) | `s_open_abort` ili izričito prihvaćanje ručnog oporavka | **OTVOREN** (odjeljak 8) |
| G13 (novo) | odluka o redoslijedu zaustavljanja (D1) i Redis kopiji (D2) | **OTVOREN** |

### 9.2 Na dan prozora (prijedlozi pragova, nisu odobreni; detalji u doc 17 §9)

| Faza | Kriterij | Prijedlog |
| --- | --- | --- |
| Preflight | `preflight.py` s ključevima | 0 FAIL, WARN pročitan; A0 se tek tada pokreće (danas preskočen) |
| Termin | izvan 23:40–04:15, radni dan | npr. 05:00–09:00 ili 20:00–22:00 |
| Pražnjenje | `active == 0` | ≤ 10 min, inače STOP-1 |
| Dump | veličina, prazan log, TOC | 200–500 MB, 0 B loga, > 1000 stavki |
| Bridge | usporedba prije/poslije `DROP EXTENSION` | PASS, TOC bez PostGIS-a |
| Cilj | `compare` + `validate_target` | 72/72 hasha, 0 FAIL, recall@10 prosjek ≥ 0,95, **minimum ≥ 0,90 (na granici za `face_index`, mora se svjesno odobriti)**, amcheck 0 |
| Dark | zdravlje, log | ≤ 180 s, 0 migracija, 0 reindeksiranja, 0 ERROR, nijedan worker |
| API | `verify` prema baselineu nakon pražnjenja | identično; razlika samo uz `compare` PASS |
| Smart search | preklapanje top-20, latencija | ≥ 0,90; topli p95 ≤ max(250 ms, 2×baseline); hladni ≤ 5 s |
| Trajanje | T0 → T_open | cilj ≤ 30 min, najviše 45; pri 60 min obavezan R1 |
| Nakon otvaranja (60 min) | redovi, backup, OIDC, ERROR | idle, `failed` 0, ručni backup `pg16.16` ±10 %, DDL bez PostGIS-a (0), 7 `CREATE EXTENSION`, OIDC uspješan |
| 24 h / 7 d | 02:00 backup, integrity (baseline 8033), resursi | bez neočekivanih razlika |

### 9.3 Operacije koje traže vaše pisano odobrenje

O1 termin, pragovi, osobe; O2 kreiranje dva ključa (INSERT u produkcijsku bazu); O3 pokretanje `immich-db` i stvaranje role/baze; O4 pauza redova i zaustavljanje bridgea, `media-operations`, servera (**prekid usluge**); O5 `REVOKE CONNECT` na izvoru; O6 dump, bridge, sanitizirani dump; O7 restore i `ANALYZE`; O8 dark launch; O9 izmjena `/opt/stacks/immich/.env` i recreate (**točka bez povratka**); O10 nastavak redova, bridge, ručni backup; O11 odredište i način off-host kopije (uključujući šifriranje i čuvanje ključa); O12 kanarski testovi (pišu u produkciju); O13 čuvanje izvora 7 dana i zabrana zamjene `postgis`; O14 tko odlučuje u R2 i pri kvaru unutar `s_open`; **novo:** O15 izmjena `steps.sh` (D1, `s_open_abort`) uz ponovni rehearsal; O16 neobvezna RDB kopija Redisa (D2).

## 10. Preostale odluke i blokeri

**Blokeri GO-a**
1. **G6:** nema odredišta off-host kopije; odlučiti odredište i ključ za šifriranje (odjeljak 4).
2. **G10:** kreirati dva privremena ključa s dozvolama iz odjeljka 5 (O2), pa ponoviti preflight s ključevima (A0).
3. **G2/G8/G7/G3/G11:** odobriti pragove (osobito minimalni recall 0,90 za `face_index`), termin, retenciju 7 dana, osobu za rollback i OIDC, obavijest korisnicima i utišan monitoring.
4. **G12:** zatvoriti prazninu u `s_open` (skripta `s_open_abort` + rehearsal) ili izričito prihvatiti ručni oporavak.

**Odluke koje nisu blokeri**
- D1: redoslijed zaustavljanja (bridge i `media-operations` prije pauze).
- D2: RDB kopija Redisa prije T0.
- Potvrda off-host statusa medija (`/data/upload`, `thumbs`, `encoded-video`), što je izvan DB backupa.

**Ostaje neprobano jer postoji samo u produkciji:** stvarni Traefik (samo label i statička konfiguracija), `media-operations` i bridge tijekom cutovera, OIDC prijava, kanarski testovi (video, trash/restore, storage template, skeniranje), stvarni promet i veličina redova.

## 11. Što je izvršeno u ovoj fazi

Samo čitanje: `docker ps/inspect`, `docker compose config` (parsiranje, bez ispisa tajni, privremena datoteka u scratchpadu uklonjena), read-only SQL nad `postgis`, popis i `gzip -t` nad backupovima (preflight), `valkey-cli INFO/CONFIG GET/DBSIZE`, popis kontrolera u imageu, `preflight.py --skip-api` (piše samo u privatni dokaz 0700), `offline_selftest.sh`. Jedina izmjena datoteka: ispravak popisa dozvola u doc 17 i ovaj dokument.

Nije izvršeno: pokretanje `immich-db`, promjena `.env`/Composea/baze/ključeva, zaustavljanje kontejnera ili redova, novi dump ili restore, kopiranje backupova izvan hosta, cutover. Nakon pregleda provjereno: `StartedAt` svih Immich kontejnera, datumi `.env`/Composea i ACL baze `immich` nepromijenjeni.

**Stati ovdje. Produkcijska migracija nije odobrena.**
