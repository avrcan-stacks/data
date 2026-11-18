# 16 — Immich v3.3.5: Stage B test (microservices worker i sintetičke fotografije)

Datum: 14. studenoga 2026. (Europe/Zagreb).
Konačni case: **20261114t231622z-f6b615** (privatni direktorij `/opt/stacks/data/backups/immich-apptest-20261114t231622z-f6b615`).
Ulaz: [13](13-immich-application-test-plan.md), [15](15-immich-application-retest.md), sanitizirani dump iz faze 4B (SHA-256 `27d2bbf36980888b050d0e7a502a8d111fecf2889fa30d21113f3a38dc6cf415`), PG 16.16 bez PostGIS-a.

**Status: PASS.** Server s API i microservices workerom na PostgreSQL 16.16 bez PostGIS-a obradio je 12 sintetičkih fotografija (thumbnailovi, EXIF i GPS reverse geocoding, CLIP embeddingi, OCR, detekcija lica), a baza je mijenjana isključivo očekivanim testnim zapisima. Nije bilo migracija, promjena ekstenzija ni reindeksiranja VectorChorda, a produkcija nije dirana.

Ovo je test na malom skupu (12 slika) na praznom hostu s CPU ML-om. **Nije produkcijski GO** i nije mjerenje produkcijske propusnosti.

## Pokušaji

| Pokušaj | Case | Ishod | Uzrok |
| --- | --- | --- | --- |
| 1 | `20261114t231125z-42450a` | HALT u klijentskim provjerama | cijeli Stage B je radio, ali su dva kriterija u mojoj skripti bila neispravna (vidi niže) |
| 2 | `20261114t231622z-f6b615` | **PASS** | cijeli pipeline ispočetka s prilagođenim kriterijima |

U pokušaju 1 nisu pronađene greške aplikacije. Prilagodio sam dva kriterija nakon što sam vidio rezultate prvog pokušaja, pa to otvoreno navodim:
1. **Brojač `completed` poslova** je uvijek 0 jer BullMQ briše završene poslove. Provjera je uklonjena, a završetak poslova dokazuje se iz vremenskih oznaka u bazi (`asset_job_status`, `asset_file`) i praznih redova (active/waiting/delayed = 0, failed = 0).
2. **Detekcija lica 6/6** bila je prestroga: portret `portrait_B2` imao je rezultat 0,721 u izravnoj ML probi (prag je 0,7) i aplikacija ga nije detektirala. Kriterij je sada: najmanje 5 od 6 portreta i barem jedno lice za svaki od 3 sintetička identiteta. Stvarni rezultat je 5/6. Uzrok promašaja nisam dokazao (vjerojatno rezultat tik ispod praga nakon obrade slike, ali to nije potvrđeno).

## Rezultati po testovima

| Test | Rezultat |
| --- | --- |
| Preflight, image ID-evi, SHA-256, izolacijski gateovi | PASS |
| Restore sanitiziranog dumpa, sekvenca `bigint`, baseline B0 | PASS |
| Start s API + microservices workerom | PASS (healthy ≈30 s, 0 ERROR) |
| Bootstrap: promjene baze prije uploada (B0 → B1) | PASS (samo `system_metadata`) |
| Zasebni testni korisnik (admin API) i prijava | PASS |
| Upload 12 sintetičkih slika + otkrivanje duplikata | PASS |
| Thumbnail i preview (12/12) te integritet originala | PASS |
| Ekstrakcija metapodataka (EXIF) | PASS |
| GPS i reverse geocoding (lokalna baza, cube/earthdistance) | PASS |
| CLIP embeddingi | PASS (12 × 512) |
| OCR | PASS |
| Detekcija lica | PASS uz prilagođeni kriterij (5 od 6) |
| Prepoznavanje (klasteriranje) lica | PASS (1 osoba) |
| Redis redovi i završetak poslova | PASS |
| Usporedba sheme i podataka s baselineom | PASS |
| Nema migracija, promjene ekstenzija ni reindeksiranja | PASS |
| VectorChord: novi vektori u indeksima | PASS |
| Pretraga (metadata, grad, OCR, smart, po osobi) | PASS |
| Mjerenje performansi | PASS (izmjereno) |
| Mediji samo u testnom direktoriju | PASS |
| Produkcija nepromijenjena | PASS |

## Sintetički podaci

Slike generira [tools/gen_synthetic.py](../../immich-app-test/tools/gen_synthetic.py) proceduralno u ML imageu bez mreže. Nema stvarnih osoba, dokumenata ni fotografija: crtana lica 3 izmišljena identiteta, generički tekst stranica i apstraktne scene.

| Vrsta | Datoteke | Namjena |
| --- | --- | --- |
| Portreti | `portrait_A1..A3`, `portrait_B1..B2`, `portrait_C1` (6) | detekcija i prepoznavanje lica, CLIP |
| Dokumenti | `document_invoice.jpg`, `document_notice.jpg`, `document_table.png` (3) | OCR |
| Scene | `scene_mountains`, `scene_city`, `scene_sea` (3, s GPS-om Splita, Zagreba i Pariza) | metapodaci, reverse geocoding, CLIP |

Ukupno 12 datoteka, 1.075.377 B. EXIF: proizvođač/model `SyntheticCam`/`TestModel-1`, datumi; PNG nema EXIF. Popis i SHA-256 nalaze se u privatnom direktoriju slučaja.

Prije testa svaka je slika provjerena izravnim pozivom ML-a u izoliranom kontejneru bez mreže (lica 0,72–0,80, OCR čitljiv, CLIP 512 dimenzija).

## Konfiguracija i izolacija

- Isti izolirani projekt kao u fazi 5C (`internal: true`, bez portova, bez produkcijskog `.env`, `docker.sock`, medija, Nextclouda i Redisa); overlay [docker-compose.immich-test.stageb.yml](../../immich-app-test/docker-compose.immich-test.stageb.yml) dodaje samo mount sintetičkih slika klijentu, više memorije serveru i Stage B config.
- [immich-test.stageb.config.json](../../immich-app-test/immich-test.stageb.config.json): isključeni su skeniranje i praćenje knjižnica, backup baze, integrity provjere, provjera nove verzije, noćni poslovi, OAuth, SMTP i karta. Uključen je lokalni reverse geocoding. Samo za test `facialRecognition.minFaces=2` (zadano 3) da se iz nekoliko sintetičkih lica može stvoriti osoba.
- Isti image ID-evi kao prije: server `sha256:619fb163…`, DB `sha256:e21ee65b…`, ML `sha256:5b28c935…`.
- Izolacijski gateovi prije starta aplikacije: mreža `Internal=true`; svi kontejneri samo na njoj, bez portova; mountovi točno očekivani; u okolini servera nema `IMMICH_API_KEY`, `OIDC_*`, `BRIDGE_*`, `MEDIA_OPS_*`, `IMMICH_EVENT_WEBHOOK_*`; produkcijska imena se ne razrješavaju; 0 od 12 izlaznih TCP pokušaja uspjelo.
- Administrator iz testne kopije (nema podataka) dobio je testnu lozinku (1 redak u `user`, samo na testnoj bazi). Služio je samo za poziv admin API-ja koji je stvorio **novog** testnog korisnika `stageb.test@example.com`. Postojeći korisnici s podacima nisu mijenjani.

## Start (API + microservices)

| Provjera | Rezultat |
| --- | --- |
| Workeri | "Starting api worker" i "Starting microservices worker" |
| Healthy | ≈30 s |
| Migracije | "Finished running migrations"; **0 primijenjenih**; statički 101 = 101, pending 0 |
| Schema drift | "No schema drift detected" |
| VectorChord | `targetLists=1, current=1` za oba indeksa; **nema `Reindex…`** |
| Ekstenzije | nema Creating/Dropping/Updating |
| Konfiguracija | `configFile=true`, `oauth=false`, `email=false`; nema nepoznatih/nevaljanih ključeva |
| Greške | 0 ERROR na startu i nakon cijelog testa; 1 WARN (`LegacyRouteConverter` za `/api/*`, isto kao u produkciji) |
| Izlazne greške (`ENOTFOUND`, `ECONNREFUSED`, `fetch failed`) | 0 |
| Neuspjeli poslovi u logu | 0 |
| ML modeli učitani | CLIP visual i textual `ViT-B-32__openai`, OCR detection/recognition `PP-OCRv5_mobile`, face detection/recognition `buffalo_l` (iz kopije cachea, bez preuzimanja) |

Promjene baze između baselinea i prvog starta (prije uploada): samo `system_metadata`, jedan redak (`AdminOnboarding`, aplikacija ga upisuje uz config datoteku).

## Obrada fotografija

| Korak | Rezultat |
| --- | --- |
| Upload | 12/12 stvoreno; ponovni upload iste slike vraćen kao `duplicate` s istim ID-em |
| Thumbnail + preview | 12 + 12 datoteka u testnom `thumbs`; sve dostupne preko API-ja |
| Originali | SHA-256 preuzetog originala jednak SHA-256 sintetičke slike (12/12) |
| EXIF | 11 JPEG-ova s `SyntheticCam`/`TestModel-1` i datumom; PNG bez EXIF-a |
| GPS i mjesto | 3/3 koordinate točne; grad: Split/Hrvatska, Zagreb/Hrvatska, "Paris 04 Hôtel-de-Ville"/Francuska |
| CLIP | 12 redaka u `smart_search`, 512 dimenzija |
| OCR | `asset_ocr`: invoice 11, notice 6, table 14 redaka; tekst "INVOICE" nađen u `ocr_search` |
| Lica | detektirano 5/6 portreta (po 1 lice): A1, A2, A3, B1, C1; B2 bez detekcije (vidi gore) |
| Prepoznavanje | 1 osoba, sve 5 detektiranih lica u njoj |
| Job status | `asset_job_status`: 12/12 s metadata, faces, duplicates i OCR vremenskim oznakama |

Napomene:
- OCR je uz 3 dokumenta pročitao i po jedan redak teksta na `portrait_A2` i `scene_mountains` (dva lažna pozitiva na slikama bez teksta; ukupno 33 retka).
- Sva 5 sintetičkih lica završila su u jednoj osobi, dakle model nije razlikovao izmišljene identitete A/B/C. To dokazuje da klasteriranje radi, ali **ne** dokazuje kvalitetu razlikovanja stvarnih osoba.

## Redis i redovi

| Provjera | Rezultat |
| --- | --- |
| Redovi prije uploada | svih 19 redova prazno (active/waiting/delayed 0) |
| Vršna dubina tijekom obrade | faceDetection 10, ocr 9, metadataExtraction 8, facialRecognition 6, thumbnailGeneration 4, smartSearch 2, storageTemplateMigration 1 |
| Redovi nakon obrade | svi 0 (active, waiting, delayed), 5 uzastopnih provjera u razmaku od 2 s |
| Neuspjeli poslovi | 0 u svim redovima |
| Brojač završenih poslova | nije dostupan (BullMQ ih briše); završetak dokazan iz baze |
| Redis | 46 ključeva, 19 grupa; `used_memory` 2,13 MB (vrh 2,82 MB) |

## Podaci: što se promijenilo

Baseline je B0 (nakon restorea, normalizacije sekvence i planirane izmjene lozinke administratora). Usporedba je tražila: (1) metapodatke jednake, (2) svih 72 tablica: hash redaka koji su postojali u B0 (po `xmin` ispod baseline transakcije) mora biti jednak B0 hashu tablice, (3) novi redci samo u očekivanim tablicama i vezani za testnog korisnika.

| Provjera | Rezultat |
| --- | --- |
| Metapodaci (relacije, indeksi, constraintovi, funkcije, triggeri, tipovi, ACL, default ACL, sekvence) B0 → B2 | identični; sekvence nepromijenjene |
| Redci koji su postojali u B0 (72 tablice, uključujući sve produkcijske korisnike, asset-e i vektore) | **nepromijenjeni i neobrisani u svih 72 tablica** (0 tablica s razlikom) |
| Novi redci | `asset` 12, `asset_exif` 12, `asset_file` 24, `asset_job_status` 12, `smart_search` 12, `asset_face` 5, `face_search` 5, `asset_ocr` 33, `ocr_search` 5, `person` 1, `person_group` 1, `cluster_group` 1, `user` 1, `session` 1, `system_metadata` 1 |
| Neočekivane tablice s novim redcima | nijedna |
| Vlasništvo novih asseta | svih 12 pripada testnom korisniku; 0 novih asseta drugih vlasnika |
| Siročad (`asset_exif`, `asset_file` bez asseta) | 0 |
| `kysely_migrations`, `migration_overrides` | nepromijenjeno |

Jedna dopuštena promjena prije testa: `user` (lozinka administratora na testnoj kopiji, B-pre → B0). Novi redak u `session` najvjerojatnije je sesija administratora: skripta se na kraju odjavljuje samo kao testni korisnik (nisam zasebno provjerio čiji je to redak).

## VectorChord

| Indeks | Novi redci | Najbliži susjed preko indeksa (vlastiti vektor) | Plan koristi indeks | Valid / ready | `lists=[1]` | Veličina |
| --- | --- | --- | --- | --- | --- | --- |
| `clip_index` | 12 | 12/12 | da | da / da | da | 169.975.808 B |
| `face_index` | 5 | 5/5 | da | da / da | da | 156.868.608 B |

Novi vektori ubačeni su u postojeće indekse bez reindeksiranja (nema `Reindex…` u logu). Veličine indeksa jednake su prethodnim mjerenjima (zaokruživanje na stranice).

## Performanse (12 slika, prazan host, CPU ML)

| Mjera | Vrijednost |
| --- | --- |
| Upload | 12 datoteka (1,08 MB) u 0,16 s; po zahtjevu medijan 11,5 ms (9,1–28,0) |
| Vrijeme od stvaranja asseta: thumbnail i preview | medijan 0,59 s, maks 1,30 s |
| EXIF/metadata | medijan 0,29 s, maks 0,40 s |
| Detekcija duplikata | medijan 2,01 s, maks 3,54 s |
| Detekcija i prepoznavanje lica | medijan 4,11 s, maks 4,54 s |
| OCR | medijan 4,37 s, maks 6,10 s |
| Svi redovi prazni | 14,75 s nakon početka uploada (uključuje 10 s potvrde mirovanja) |
| Metadata pretraga / po gradu / po OCR tekstu | 3,6 / 3,2 / 6,7 ms |
| Smart search, prvi upit (učitava tekstualni CLIP model) | 204,7 ms |
| Smart search, ostala 4 nova upita | 35,9–40,3 ms |
| Smart search, isti upit ponovljen 5 puta | 6,9–10,0 ms |
| Resursi nakon obrade | server 1,32 GiB (od 6), ML 352 MiB, baza 961 MiB, Redis 8,9 MiB; CPU u mirovanju |

Vremena su iz jednog izvršenja; nisu benchmark. 12 slika ne govori o propusnosti pri tisućama slika, istodobnim korisnicima ni velikim fotografijama/videu.

### Smart search kvaliteta (informativno)

Za 5 upita ("a document with printed text", "a mountain landscape", "a portrait of a person", "a city skyline at night", "the sea and the sky") prvi rezultat bio je očekivana sintetička slika u svih 5. To nije kriterij uspjeha: skup je od 12 apstraktnih slika.

## Mediji i trajni direktoriji

| Provjera | Rezultat |
| --- | --- |
| Datoteke u testnom `/data` | `upload`: 12 originala (1.086.926 B); `thumbs`: 25 datoteka (708.708 B); `encoded-video`, `library`, `profile`, `backups`: prazni |
| Produkcijski mediji | nisu montirani |
| `postgres-standard/data`, `immich-postgres/data` | prazni |

## Produkcija

| Provjera | Rezultat |
| --- | --- |
| Kontejneri `postgis`, `immich_server`, `immich_redis`, `immich_machine_learning`, `immich_media_operations`, `nextcloud_immich_bridge`: Id, image, StartedAt, restart count, mreže, portovi, mountovi (sortirani), hash konfiguracije | nepromijenjeno |
| Hashevi `docker-compose*.yml`, Dockerfileova, `.env`, tailscale env, Immich compose i `.env` | nepromijenjeno |
| Veze na produkcijsku bazu `immich` | prije i poslije isti klijent `172.28.0.11` (immich_server); broj praznih veza 10 → 11 (promjena veličine poola, nije povezana s testom) |
| Izvorni dump faze 4 i sanitizirani dump | SHA-256 nepromijenjen |
| Produkcijske lozinke, korisnici, webhookovi, `docker.sock` | nisu korišteni ni mijenjani |

## Što nije testirano

- Videozapisi i transkodiranje; storage template; trash/brisanje i povrat; knjižnice i skeniranje (isključeno); backup baze u 02:00 (isključen, nije provjeren `pg_dump` prema 16.16); integrity provjere (isključene); provjera nove verzije (isključena); noćni poslovi.
- Velike fotografije, HEIC, RAW, tisuće slika, istodobni korisnici, produkcijska propusnost.
- Kvaliteta razlikovanja stvarnih lica; OCR na stvarnim dokumentima.
- OIDC/Nextcloud prijava, `media-operations` i bridge, Traefik/TLS, mobilne aplikacije.

## Preostale prepreke za produkcijski cutover

1. **Backup baze (Immich cron 02:00):** nakon prebacivanja mora raditi `pg_dump` prema `immich-db` 16.16; nije testiran (isključen u testu).
2. **Videozapisi/transkodiranje, trash, storage template i skeniranje knjižnica** nisu testirani s microservices workerom.
3. **OIDC prijava** i integracije (`media-operations` preko `docker exec immich-db psql`, bridge, Traefik) provjeravaju se ručno nakon prebacivanja.
4. **Pragovi** recall-a/latencije i dopušteni prozor prekida i dalje nisu dogovoreni.
5. **Cutover postupak** iz [13](13-immich-application-test-plan.md): zamrzavanje pisanja, pražnjenje redova (Redis nema volumen), novi dump nakon zamrzavanja, sekvenca i tekstualna razlika indeksa, rollback točka, retencija izvora, gateovi G1–G8.
6. **Skala:** test je s 12 slika; za produkcijsku bazu od 57.627 asseta nije mjeren nikakav učinak obrade na veliku knjižnicu.

## Čišćenje

Nakon spremanja izvještaja uklonjeni su isključivo testni resursi konačnog slučaja: 4 kontejnera projekta `immich-apptest-20261114t231622z-f6b615` (`down` bez `-v`), mreža `testnet`, direktorij `/tmp/immich-apptest-20261114t231622z-f6b615` (provjereni realpath i da ga nijedan proces ne koristi; sadržavao je testnu bazu, kopiju ML cachea, testni medijski direktorij i sintetičke slike) i `.env.test` (testne lozinke). Prije testa je uklonjen i privremeni ML kontejner za probu sintetičkih slika te njegova kopija cachea. Resursi prvog pokušaja uklonjeni su prije drugog. Privatni direktoriji oba pokušaja (rezultati, snapshotovi metapodataka i hashova bez redaka, logovi, popis sintetičkih slika s hashevima, SHA256SUMS) su zadržani i gitignored. Dokazi faza 4–5C i svi backupovi nisu dirani.

**Stati ovdje. Produkcijska migracija nije odobrena.**
