# 15 — Immich v3.3.5: ponovljeni izolirani aplikacijski test (faza 5C)

Datum: 14. studenoga 2026. (Europe/Zagreb).
Konačni case: **20261114t225542z-b30ca6** (privatni direktorij `/opt/stacks/data/backups/immich-apptest-20261114t225542z-b30ca6`).
Ulaz: [14](14-immich-application-test-results.md), runbook Stage A iz [13](13-immich-application-test-plan.md), sanitizirana arhiva iz faze 4B (SHA-256 `27d2bbf36980888b050d0e7a502a8d111fecf2889fa30d21113f3a38dc6cf415`).

**Status: PASS.** Stage 0 i A1–A4 prošli su u trećem pokušaju bez ijedne neočekivane migracije, promjene sheme, reindeksiranja ili pristupa produkciji. Prva dva pokušaja zaustavila su se zbog grešaka u mom test harnessu (ne aplikacije), vidi niže.

Rezultat vrijedi za SQL i API razinu s API workerom, praznim medijskim direktorijem i konfiguracijom iz datoteke. **Nije produkcijski GO.** Stage B (microservices), mediji, OIDC i integracije nisu testirani.

## Pokušaji

| Pokušaj | Case | Ishod | Uzrok |
| --- | --- | --- | --- |
| 1 | `20261114t224554z-764bc4` | HALT na `album_detail` | harness: u v3.3.5 `GET /albums/{id}` ne vraća asset-e (`withAssets: false`), samo `assetCount`; potvrđeno čitanjem koda. Provjera sada uspoređuje `assetCount` i asset-e dohvaća kroz `POST /search/metadata` s `albumIds` |
| 2 | `20261114t225118z-596784` | A1–A3 PASS, HALT u novoj provjeri VectorChorda nakon aplikacije | harness: egzaktni upit nije postavio `vchordrq.probes` (u fazi 4C postavljen u svim načinima) |
| 3 | `20261114t225542z-b30ca6` | **PASS** | cijeli pipeline ispočetka, s oba ispravka |

Svaki pokušaj ponavlja cijeli pipeline iz iste sanitizirane arhive na svježem testnom clusteru. Ni u jednom pokušaju nije uočena greška aplikacije. Testni resursi neuspjelih pokušaja uklonjeni su prije sljedećeg, a njihovi privatni dokazi su zadržani.

## Rezultati po testovima

| Test | Rezultat |
| --- | --- |
| Stage 0: preflight (prostor, image ID-evi, SHA-256, modeli, ML kopija) | PASS |
| Izolacijski gateovi (prije starta aplikacije) | PASS |
| A1: restore sanitiziranog dumpa u PG 16.16 | PASS (18,6 s, exit 0, prazan log) |
| A1: normalizacija sekvence na `bigint` | PASS |
| A1: usporedba s izvorom (72 tablice, metapodaci) | PASS |
| A1: statička provjera pending migracija | PASS (101 = 101, pending 0) |
| A1: odabir korisnika i testna lozinka (samo test kopija) | PASS |
| A2: tri pokretanja s API workerom (start, restart, start) | PASS |
| A2: usporedba baze B1 i B2 | PASS |
| A3: login | PASS |
| A3: `/server/about` s tokenom | PASS |
| A3: popis albuma i očekivani broj | PASS (6 = 6) |
| A3: detalj albuma i broj asseta | PASS (20.311 = 20.311) |
| A3: asseti albuma (pretraga po `albumIds`) | PASS |
| A3: metadata search | PASS |
| A3: smart search (CLIP preko ML-a) | PASS |
| A3: popis osoba | PASS |
| A3: statistika osobe i pretraga po osobi | PASS |
| A3: lica na assetu | PASS |
| A3: usporedba baze B3 | PASS |
| VectorChord nakon aplikacije | PASS |
| A4: read-only SQL upiti `media-operations` | PASS (10 upita) |
| Ispravljena provjera produkcijskih veza | PASS |
| Sortirani Docker mountovi, produkcijsko stanje | PASS |

## Odabir testnog korisnika

Kriteriji su se izvodili na restoreanoj testnoj kopiji; korisnik se ne imenuje i e-mail se ne bilježi. Korisnik mora imati: asset-e (slike), barem jedan vlastiti neprazni album, barem jednu imenovanu vidljivu osobu, smart-search embeddinge i lica.

| Stavka | Vrijednost |
| --- | --- |
| Korisnika u bazi / zadovoljava sve kriterije | 8 / 2 |
| Odabran | prvi po broju asseta (rang 1 od 2) |
| Vrsta računa | neadministrator, ima OAuth vezu (lozinka se u testu koristi preko config datoteke s isključenim OAuthom) |
| Asseti / slike | 40.378 / 40.378 |
| Albumi (svi / vlastiti neprazni) | 6 / 4 |
| Osobe u bazi (imenovane vidljive / skrivene) | 894 (6 / 0) |
| Smart-search embeddingi / lica | 40.373 / 40.559 |

Račun je prikladan za sva tri testa (albumi, pretraga, osobe i lica). Administrator iz faze 5B nije imao nijedan podatak i zato nije mogao poslužiti.

### Planirana izmjena testnog korisnika (dopuštena razlika)

U testnoj bazi postavljena je `user.password` tog jednog korisnika na bcrypt hash nasumične testne lozinke (hash je izračunat jednokratnim kontejnerom bez mreže iz lozinke preko stdin-a). Izmjena je zahvatila točno 1 redak. U usporedbi je dopuštena isključivo tablica `user` u koraku B-pre → B0 (stvarno promijenjena: samo `user`). Produkcijski korisnici i lozinke nisu mijenjani.

## Izolacija

| Provjera | Rezultat |
| --- | --- |
| Mreža `testnet` | `Internal=true`; spojeni samo kontejneri testnog projekta |
| Kontejneri (db, redis, ml, server) | svaki samo na `testnet`; bez objavljenih portova; mountovi točno očekivani; nema `docker.sock`, produkcijskog `.env`, Nextclouda ni produkcijskog `/data`; u okolini servera nema `IMMICH_API_KEY`, `OIDC_*`, `BRIDGE_*`, `MEDIA_OPS_*`, `IMMICH_EVENT_WEBHOOK_*` |
| DNS iz testne mreže | testna imena razrješavaju; `postgis`, `immich_redis`, `immich_server`, `immich-server`, `media-operations`, `immich-db`, `traefik`, `example.org`, `github.com` ne razrješavaju |
| TCP iz testne mreže | 12 izlaznih pokušaja (produkcijski postgis, server i Redis, `172.17.0.1`, `1.1.1.1:443`, `8.8.8.8:53`): **0 uspjelih**; `db:5432` i `redis:6379` uspjeli; `ml:3003` još nije slušao u trenutku probe |
| Greške izlazne veze u logu servera nakon smokea | 0 |
| Image ID-evi | server `sha256:619fb163…` (isti kao produkcijski), db `sha256:e21ee65b…`, ml `sha256:5b28c935…`, Redis isti digest kao produkcija |
| ML | kopija cachea (75 datoteka, 2,2 GB), `HF_HUB_OFFLINE=1`; ML log potvrđuje "Loading textual model 'ViT-B-32__openai'" u trenutku smart searcha |

## A1: baza

| Stavka | Rezultat |
| --- | --- |
| Restore | exit 0, prazan log, 18,6 s |
| Sekvenca `naturalearth_countries_tmp_id_seq1` | `integer` → `bigint`; min 1, max 2147483647, inkrement 1, cache 1, bez cikliranja; owner immich; ACL nepromijenjen; last_value 4274, is_called true; identity dependency očuvan; max(id) 4274 |
| Izvor → B-pre | 72/72 hasha jednaka (1.080.420 redaka); metapodaci jednaki izvoru bez PostGIS članova; jedina iznimka: tekst `pg_get_indexdef` indeksa `asset_localDateTime_month_idx` ([12](12-immich-index-validation.md)); ekstenzije točno: cube 1.5, earthdistance 1.2, pg_trgm 1.6, plpgsql 1.0, unaccent 1.1, uuid-ossp 1.1, vchord 1.1.1, vector 0.8.2 |
| Migracije (statički) | 101 datoteka u imageu = 101 primijenjena, pending 0, nema primijenjenih koje image ne poznaje |

## A2: startup (API worker)

Tri pokretanja istog kontejnera, analiza loga svakog:

| Provjera | Rezultat u sva tri |
| --- | --- |
| Samo API worker | da; nema microservices workera |
| Healthy | na prvoj healthcheck provjeri (≈30 s) |
| Migracije | "Running migrations" i "Finished running migrations"; **0 primijenjenih migracija** |
| Schema drift | "No schema drift detected" |
| Mount provjere | uspješne |
| VectorChord | `targetLists=1, current=1` za `clip_index` i `face_index`; **nema reindeksiranja** |
| Ekstenzije | nema Creating/Dropping/Updating |
| Konfiguracija | `configFile=true`, `oauth=false`, `passwordLogin=true`, `email=false`; nema nepoznatih ni nevaljanih ključeva |
| ERROR/FATAL | 0 |
| WARN | `LegacyRouteConverter` za `/api/*` (postoji i u produkcijskom logu); u startu 3 još "No microservices worker is connected" (očekivano uz samo API worker) |

## Usporedba baze nakon pokretanja aplikacije

| Usporedba | Metapodaci | Promijenjene tablice | Sekvence |
| --- | --- | --- | --- |
| izvor → B-pre | jednaki (osim dopuštene tekstualne iznimke indeksa) | 0 | — |
| B-pre → B0 | jednaki | `user` (1 redak, planirana lozinka) | nepromijenjene |
| B0 → B1 (nakon prvog starta) | jednaki | `system_metadata` | nepromijenjene |
| B1 → B2 (nakon restarta) | jednaki | nijedna | nepromijenjene |
| B2 → B3 (nakon smokea) | jednaki | nijedna | nepromijenjene |
| B0 → B3 (ukupno) | jednaki | samo `system_metadata` | nepromijenjene |

Dopušteno je bilo samo `system_metadata` i `session` (dopuštene razlike za aplikaciju) te `user` za planiranu izmjenu lozinke. Jedina stvarna promjena podataka tijekom rada aplikacije je jedan redak u `system_metadata` (`AdminOnboarding`, aplikacija ga upisuje kad je aktivna config datoteka). Sesija nastala prijavom obrisana je odjavom, pa u `session` nema neto promjene. Hashevi svih 72 tablice nakon pokretanja jednaki su stanju prije, osim spomenutog retka. Katalog (relacije, indeksi, constraintovi, funkcije, triggeri, tipovi, ACL, default ACL, sekvence) je identičan.

## A3: smoke test (korisnik s podacima)

| Provjera | Rezultat | Vrijeme / vrijednosti |
| --- | --- | --- |
| Ping | PASS | |
| Značajke | PASS | configFile true, oauth false, passwordLogin true, email false, smartSearch true, facialRecognition true |
| Login | PASS | HTTP 201, 78,5 ms |
| `GET /server/about` s tokenom | PASS | v3.3.5 |
| Popis albuma | PASS | 6, jednako očekivanju iz baze (6) |
| Detalj albuma | PASS | `assetCount` 20.311, jednako popisu i bazi (20.311) |
| Asseti albuma (`albumIds`) | PASS | 20 vraćeno, 52,6 ms |
| Metadata search | PASS | 20 vraćeno, 8,5 ms |
| Smart search | PASS | 20 vraćeno, 347 ms (prvi poziv uključuje učitavanje CLIP modela) |
| Popis osoba | PASS | 500 na stranici, `total` 792, 56,3 ms |
| Statistika osobe | PASS | 8.517 asseta |
| Pretraga po osobi | PASS | 20 vraćeno, 25,1 ms |
| Lica na assetu | PASS | 4 |

Napomene:
- `total` 792 je manji od 894 osoba u bazi. Kod `getAllForUser` uključuje samo osobe koje imaju ime ili barem minimalan broj lica, pa razlika nije kvar.
- Smart search je tražio rezultate za jedan fiksni upit; kvalitetu rezultata nisam ocjenjivao.
- Vremena su iz jednog izvršenja u izoliranom kontejneru; nisu benchmark.

## VectorChord nakon pokretanja aplikacije

Isti postupak kao u 4C, 5 determinističkih uzoraka po tablici, `probes=1`, egzaktno naspram ANN.

| Indeks | Valid / ready | Veličina | Definicija (`lists=[1]`) | Index korišten u ANN planu | Recall@10 prosjek / min | ANN maks (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| `clip_index` | da / da | 169.975.808 B (jednaka kao u 4C) | da | 5/5 | 1,00 / 1,00 | 7,9 |
| `face_index` | da / da | 156.868.608 B (jednaka kao u 4C) | da | 5/5 | 1,00 / 1,00 | 7,6 |

Ovo je mali uzorak s vlastitim vektorima, ne mjerenje produkcijske kvalitete pretrage. Aplikacija je pri startu prewarmala indekse, ali ih nije reindeksirala.

## A4: SQL upiti media-operations

Mehanizam kao u produkciji: `docker exec` psql kao rola `immich` s lozinkom iz okoline, uz `default_transaction_read_only=on` (pokušaj pisanja odbijen). Izvršeno 10 upita iz `server.js` na testnoj bazi, kao testni korisnik s jednom knjižnicom:

| Upit | Izlaz | Redaka |
| --- | --- | --- |
| popis za EXIF utility (datum) | exit 0 | 39.680 |
| zapis jednog asseta (datum) | exit 0 | 1 |
| popis za GPS utility | exit 0 | 32.741 |
| zapis jednog asseta (GPS) | exit 0 | 1 |
| susjed po grupi imena | exit 0 | 0 |
| susjed po smjeru (prethodni) | exit 0 | 1 |
| broj lica na assetu | exit 0 | 1 |
| članstvo u smart albumima | exit 0 | 0 |
| vlastiti album po imenu | exit 0 | 0 |
| asset za događaj | exit 0 | 1 |

Svi upiti izvršeni su bez greške na PG 16.16 bez PostGIS-a i ne sadrže ST_/geometry/geography izraze. Ograničenja: redci 0 za tri upita ne znače kvar (ovise o parametrima; imena smart albuma `Documents`, `Screenshots`, `WhatsApp` i `Documents` postavljena su kao primjer jer stvarna imena nisu izvučena); rezultati nisu uspoređeni s PG 16.13 ni produkcijskom bazom.

## Produkcija

| Provjera | Rezultat |
| --- | --- |
| Kontejneri `postgis`, `immich_server`, `immich_redis`, `immich_machine_learning`, `immich_media_operations`, `nextcloud_immich_bridge`: Id, image, StartedAt, restart count, mreže, portovi, mountovi (sortirani), hash konfiguracije | nepromijenjeno |
| Hashevi `docker-compose*.yml`, Dockerfileova, `.env`, `.env.example`, tailscale env, Immich compose i `.env` | nepromijenjeno |
| Veze na produkcijsku bazu `immich` (ispravljeni upit) | prije i poslije: `172.28.0.11|immich|11`, samo immich_server; upit vraća podatke (provjera više nije prazna) |
| Data direktoriji budućih servisa | prazni |
| Izvorni dump faze 4 i sanitizirani dump | SHA-256 nepromijenjen |
| Produkcijske lozinke i korisnici | nisu mijenjani |

Ispravci harnessa (zadatak 7): upit za veze više nema agregat u `GROUP BY`, prazan rezultat je HALT, a mountovi se uspoređuju sortirano. Oba ispravka rade.

## Preostale prepreke za produkcijski cutover

1. **Stage B nije testiran** (nije odobren): microservices worker, obrada novih medija (thumbnail, metadata, detekcija i prepoznavanje novih lica, OCR), cron zadaci, backup baze u 02:00 (`pg_dump` prema 16.16), integrity provjere, provjera nove verzije i skeniranje knjižnica. Test je sve to namjerno isključio.
2. **Mediji i prikaz slika** nisu testirani (prazan skeleton direktorij).
3. **OIDC/Nextcloud prijava**: produkcijska konfiguracija je u bazi (OAuth uključen), test koristi config datoteku. Ručna provjera nakon prebacivanja.
4. **Integracije:** `media-operations` (pristup preko `docker exec immich-db psql`, kontejner mora imati ime `immich-db`) i `nextcloud_immich_bridge` nisu pokretani; testirani su samo SQL upiti. Traefik/TLS i mobilne aplikacije također nisu.
5. **Cutover postupak:** sekvenca se mora ponovno normalizirati, a tekstualna razlika indeksa ponovno dopustiti; zamrzavanje pisanja, pražnjenje Redisa i rollback točka kako su opisani u [13](13-immich-application-test-plan.md).
6. **Odluke koje još nisu donesene:** pragovi recall-a/latencije, dopušteni prozor prekida i retencija izvorne baze.
7. Svi gateovi G1–G8 iz [13](13-immich-application-test-plan.md) ostaju na snazi.
8. Podaci u testu su snapshot od 14. studenoga; živi izvor se mijenja pa konačni dump mora biti nakon zamrzavanja.

## Čišćenje

Nakon spremanja izvještaja uklonjeni su isključivo testni resursi konačnog slučaja: 4 kontejnera projekta `immich-apptest-20261114t225542z-b30ca6` (`down` bez `-v`), njegova mreža `testnet`, direktorij `/tmp/immich-apptest-20261114t225542z-b30ca6` (provjereni realpath i da ga nijedan proces ne koristi) i `.env.test` (testne lozinke i adresa testnog korisnika). Potvrđeno: nema kontejnera ni mreža `immich-apptest-*`, nema testnog `/tmp` direktorija. Resursi prvog i drugog pokušaja uklonjeni su prije sljedećeg pokušaja. Privatni direktoriji sva tri pokušaja (rezultati, snapshotovi metapodataka i hashova bez redaka, logovi, SHA256SUMS) su zadržani i gitignored. Dokazi faza 4–5B i svi backupovi nisu dirani.

**Stati ovdje. Produkcijska migracija nije odobrena. Stage B nije pokrenut.**
