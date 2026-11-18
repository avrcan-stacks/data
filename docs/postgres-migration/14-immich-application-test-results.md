# 14 — Immich v3.3.5: rezultati aplikacijskog testa (faza 5B, Stage 0 i A1–A4)

Datum: 14. studenoga 2026. (Europe/Zagreb).
Case: **20261114t223106z-8b8687** (privatni direktorij `/opt/stacks/data/backups/immich-apptest-20261114t223106z-8b8687`).
Plan: [13](13-immich-application-test-plan.md). Ulaz: sanitizirana arhiva iz faze 4B, SHA-256 `27d2bbf36980888b050d0e7a502a8d111fecf2889fa30d21113f3a38dc6cf415`.

**Status: HALT na Stageu A3 (smoke test). Stage 0, A1 i A2 su PASS. A3 nije prošao, a A4 nije izvršen.**

Zaustavljanje nije pokazalo grešku aplikacije ili baze: login, ML veza, migracije, drift provjera i usporedbe baze prošli su. Test je pao jer je testni administrator račun bez ikakvih podataka (0 asseta, 0 albuma, 0 osoba), a jedna provjera u mojoj test skripti nije slala token. Zato **albumi, pretraga i lica nisu stvarno provjereni na podacima**. To nije PASS i nije dokaz kvara.

## Rezultat po koracima

| Korak | Rezultat | Napomena |
| --- | --- | --- |
| Stage 0: preflight | PASS | disk 438,1 GiB slobodno, RAM 75,1 GiB, svi image ID-evi, SHA256SUMS faza 4 i 4B, sanitizirani dump, modeli u kopiji cachea |
| A1: restore sanitiziranog dumpa | PASS | PG 16.16, `pg_restore` exit 0, prazan log, 18,8 s |
| A1: normalizacija sekvence | PASS | `integer` → `bigint`, 4274, `is_called` true |
| A1: usporedba s izvorom (B-pre) | PASS | metapodaci jednaki izvoru bez PostGIS članova, 72/72 hasha, 1.080.420 redaka |
| A1: pending migracije (statički) | PASS | 101 u imageu = 101 u bazi, pending 0 |
| A1: testna lozinka administratora | PASS | 1 redak u tablici `user`, samo na testnoj kopiji |
| A1: baseline B0 | PASS | B-pre → B0: promijenjena samo tablica `user` |
| Izolacijski gateovi | PASS | prije pokretanja aplikacije, vidi dolje |
| A2: start 1, restart, start 3 (API worker) | PASS | 0 migracija, bez driftа, bez reindexa, bez promjene ekstenzija, 0 ERROR |
| A2: B1 vs B0, B2 vs B1 | PASS | vidi dolje |
| A3: smoke test | **FAIL / HALT** | 4 od 8 provjera nisu prošle; uzrok dolje |
| A3: B3 vs B2, B3 vs B0 | PASS | snimljeno nakon zaustavljanja, samo `system_metadata` |
| A4: SQL upiti `media-operations` | **NIJE IZVRŠENO** | zaustavljeno prije A4 prema pravilu zaustavljanja |
| Produkcija nepromijenjena | PASS | vidi dolje |

## Stage 0 i izolacija

| Provjera | Rezultat |
| --- | --- |
| Mreža `immich-apptest-…_testnet` | `Internal=true`; spojena samo 3 kontejnera prije starta servera (db, redis, ml), kasnije i server |
| Kontejneri (db, redis, ml, server) | svaki samo na `testnet`; bez objavljenih portova; mountovi točno očekivani (db: PGDATA i read-only dump; ml: kopija cachea; server: skeleton `/data` i config; redis: tmpfs) |
| Zabranjeno | nijedan mount pod `/opt/stacks/immich`, `/opt/stacks/nextcloud`, `/opt/stacks/data/postgres`, nijedan `docker.sock`; u okolini servera nema `IMMICH_API_KEY`, `OIDC_*`, `BRIDGE_*`, `MEDIA_OPS_*`, `IMMICH_EVENT_WEBHOOK_*` |
| Image ID-evi | server `sha256:619fb163…` (isti kao produkcijski), db `sha256:e21ee65b…`, ml `sha256:5b28c935…`, redis isti digest kao produkcija |
| DNS iz testne mreže | `db`, `redis`, `ml` razrješavaju; **ne razrješavaju** `postgis`, `immich_redis`, `immich_server`, `immich-server`, `media-operations`, `immich-db`, `traefik`, `example.org`, `github.com` |
| TCP iz testne mreže | `db:5432` i `redis:6379` uspješni; **0 od 12** izlaznih pokušaja uspjelo (adrese produkcijskog postgisa, servera i Redisa, `172.17.0.1`, `1.1.1.1:443`, `8.8.8.8:53`) |
| Greške izlazne veze u logu servera nakon smokea | 0 (`ENOTFOUND`, `EAI_AGAIN`, `ECONNREFUSED`, `fetch failed`) |
| Model cache | kopija 75 datoteka, 2,2 GB; `ViT-B-32__openai`, `buffalo_l`, `PP-OCRv5_mobile` prisutni |

Napomena: u trenutku probe `ml:3003` još nije slušao (ML se pokretao), pa taj internal TCP nije potvrđen u probi. Server je kasnije zabilježio "Machine learning server became healthy (http://ml:3003)".

## A2: startup, migracije, drift, VectorChord

Tri pokretanja istog kontejnera (start 1, restart, start 3), obrada loga svakog:

| Provjera | Rezultat u sva tri pokretanja |
| --- | --- |
| Samo API worker | "Starting api worker"; nema "Starting microservices worker" |
| Healthy | nakon prve healthcheck provjere (≈30 s) |
| Migracije | "Running migrations" i "Finished running migrations"; **0 redaka `Migration "…" succeeded`** |
| Schema drift | "No schema drift detected" |
| Mount provjere | "Successfully verified system mount folder checks" |
| VectorChord | `targetLists=1, current=1` za `clip_index` i `face_index`; **nema `Reindex…`** |
| Ekstenzije | nema `Creating/Dropping/Updating … extension` |
| Konfiguracija | `configFile=true`, `oauth=false`, `passwordLogin=true`, `email=false`; nema "Unknown keys" ni "Invalid system config" |
| Greške | 0 ERROR/FATAL |
| Upozorenja | 1 WARN: `LegacyRouteConverter` za rutu `/api/*`; isto upozorenje postoji i u produkcijskom logu. Kasnije "No microservices worker is connected" (očekivano uz samo API worker) |

### Usporedba baze

| Usporedba | Metapodaci | Promijenjene tablice | Sekvence |
| --- | --- | --- | --- |
| izvor → B-pre | jednaki (jedina iznimka: tekst `pg_get_indexdef` za `asset_localDateTime_month_idx`, vidi [12](12-immich-index-validation.md)) | 0 od 72 | — |
| B-pre → B0 | jednaki | `user` (planirana izmjena lozinke) | nepromijenjene |
| B0 → B1 (nakon prvog starta) | jednaki | samo `system_metadata` | nepromijenjene |
| B1 → B2 (nakon restarta) | jednaki | nijedna | nepromijenjene |
| B2 → B3 (nakon smokea) | jednaki | nijedna | nepromijenjene |
| B0 → B3 (ukupno) | jednaki | samo `system_metadata` | nepromijenjene |

Jedina promjena podataka je jedan novi redak u `system_metadata` (ukupno 1.080.420 → 1.080.421 redaka). To je `AdminOnboarding` koji `ServerService` upisuje kad je aktivna config datoteka; to je očekivano u testnom načinu, a produkcija koristi konfiguraciju iz baze. Sesija nastala prijavom obrisana je odjavom na kraju smokea (nema neto promjene u `session`). Katalog (relacije, indeksi, constraintovi, funkcije, triggeri, tipovi, ACL, default ACL, sekvence) je neizmijenjen, uključujući definicije `clip_index` i `face_index`.

## A3: smoke test

| Provjera | Rezultat | Napomena |
| --- | --- | --- |
| `GET /server/ping` | PASS | |
| `GET /server/about` | **FAIL** (HTTP 401) | greška u mojoj skripti: endpoint traži prijavu, a poziv je išao bez tokena |
| `GET /server/features` | PASS | konfiguracija iz datoteke, OAuth isključen, lozinka uključena |
| `POST /auth/login` | PASS | HTTP 201, 84 ms |
| `GET /albums` | PASS (0 albuma) | očekivano za ovog korisnika |
| `POST /search/metadata` | **FAIL** (HTTP 200, 0 rezultata) | korisnik nema asseta |
| `POST /search/smart` | **FAIL** (HTTP 200, 0 rezultata, 1,13 s) | zahtjev je izvršen, ali korisnik nema asseta pa nema što vratiti; trajanje odgovara pozivu ML-a, što nisam zasebno potvrdio |
| `GET /people` | **FAIL** (HTTP 200, 0 osoba) | korisnik nema osoba |

### Uzrok

Testna kopija ima 8 korisnika, od kojih je točno 1 administrator. Taj administrator ima **0 asseta, 0 albuma i 0 osoba** (provjereno read-only upitom). Podatke posjeduje 7 drugih korisnika (najveći ima 40.378 asseta, a najviše osoba ima 894). Odobrenje je obuhvaćalo nasumičnu testnu lozinku administratora pa smo mogli provjeriti samo prazan račun. Provjere albuma, metapodataka, smart searcha i postojećih lica **nisu izvedene na stvarnim podacima**. Smatram to nezavršenim, a ne uspjelim testom.

## A4: SQL upiti media-operations

**Nije izvršeno.** Prema pravilu zaustavljanja test je stao nakon neuspjelog smokea. Statički pregled iz [13](13-immich-application-test-plan.md): upiti čitaju tablice `asset`, `asset_exif`, `asset_face`, `album`, `album_user`, `album_asset`, a ne koriste PostGIS funkcije ni tipove. To je pregled koda, ne izvršenje na PG 16.16.

## Produkcija

| Provjera | Rezultat |
| --- | --- |
| Kontejneri `postgis`, `immich_server`, `immich_redis`, `immich_machine_learning`, `immich_media_operations`, `nextcloud_immich_bridge`: Id, image, StartedAt, restart count, mreže, portovi, hash konfiguracije | nepromijenjeno (mountovi su isti, samo je redoslijed u `docker inspect` drukčiji među pozivima; usporedba je ponovljena sortirano) |
| Hashevi `docker-compose*.yml`, Dockerfileova, `.env`, `.env.example`, tailscale env, Immich compose i `.env` | nepromijenjeno |
| Veze na produkcijsku bazu `immich` | jedini klijent je `172.28.0.11` (immich_server), 11 praznih veza; nijedna s testne podmreže `192.168.144.0/20` |
| `postgres-standard/data`, `immich-postgres/data` | prazni |
| Izvorni dump faze 4 i sanitizirani dump | SHA-256 nepromijenjen |

Napomene o mojoj skripti: automatska usporedba produkcijskih veza imala je neispravan SQL (agregat u `GROUP BY`) pa nije dala podatke, a automatska usporedba produkcijskog stanja lažno je javila razliku zbog redoslijeda mountova. Obje provjere ponovio sam ručno (gore). Zato pouzdanost "bez promjene" počiva na ručnoj provjeri nakon testa i na izolaciji mreže.

## Odstupanja i greške test harnessa

1. `/server/about` u smoke skripti zahtijeva token; treba ga slati.
2. Smoke test treba račun s podacima. Prema odobrenju lozinka je postavljena samo administratoru koji nema podataka.
3. Automatska provjera produkcijskih veza: neispravan upit.
4. Usporedba `docker inspect` mountova: treba sortirati.
5. Skripta nije poduzela nikakvu radnju na produkciji; sva je čitanje.

## Preostali uvjeti za produkcijsko prebacivanje

- **Zatvoriti A3 i A4** na računu s podacima (potrebno odobrenje, vidi dolje) i s ispravljenim harnessom.
- Pragovi recall-a/latencije i dopušteni prozor prekida još nisu dogovoreni.
- OIDC prijava i `media-operations`/bridge integracija ne mogu se provjeriti u izolaciji; ručna provjera nakon prebacivanja.
- Stage B (microservices, ML detekcija novih lica) nije pokrenut niti odobren.
- Svi uvjeti G1–G8 iz [13](13-immich-application-test-plan.md) ostaju na snazi.

## Što treba odobriti za ponavljanje A3 i A4

Predloženo: ponoviti pipeline (≈5 min, isti dump i skripta) s ispravljenim smoke testom i **testnom lozinkom jednog korisnika koji posjeduje podatke** (npr. onog s najviše asseta), isključivo na testnoj kopiji baze, uz isti A4. To je izmjena izvan trenutnog odobrenja, koje navodi samo administratora, pa nije izvršena.

## Čišćenje

Nakon spremanja izvještaja uklonjeni su isključivo testni resursi: 4 kontejnera projekta `immich-apptest-20261114t223106z-8b8687` (`down` bez `-v`), njihova mreža `testnet`, direktorij `/tmp/immich-apptest-20261114t223106z-8b8687` (provjereni realpath i da ga nijedan proces ne koristi) i `.env.test` (testne lozinke i adresa testnog korisnika). Potvrđeno: nema kontejnera ni mreža `immich-apptest-*`, nema testnog `/tmp` direktorija. Zadržan je privatni direktorij slučaja (0700, gitignored, oko 3,6 MB sa snapshotovima metapodataka i hashova bez redaka, logovima i `results.json`, uz SHA256SUMS). Dokazi faza 4–4C i svi backupovi nisu dirani.

**Stati ovdje. Produkcijska migracija nije odobrena. Stage B nije pokrenut.**
