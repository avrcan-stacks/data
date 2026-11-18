# 09 — Immich: plan izoliranog restore testa stvarne baze

Datum analize: 14. studenoga 2026. (Europe/Zagreb).
Status: **priprema završena; produkcijski dump, restore, pokretanje testnih/novih servisa i promjene ekstenzija nisu izvršeni**.

Plan nadopunjuje [inventar](01-inventory.md), [arhitekturu](02-target-architecture.md), [runbook](04-migration-runbook.md), [validaciju i rollback](05-validation-rollback.md) te [rezultate faze 2](08-build-validation.md). Za izvođenje opisanih naredbi potrebno je novo izričito odobrenje, uključujući uklanjanje PostGIS-a **samo na privremenoj obnovljenoj kopiji**.

## 1. Potvrđeno stanje i prostor

Izvor je baza **immich u postojećem kontejneru postgis**, ne stari database servis opisan u zastarjelom Immich AGENTS.md. Aktualni task eksplicitno određuje izvor; runtime endpoint potvrđuje postgis/immich.

| Stavka | Nalaz |
| --- | --- |
| PostgreSQL izvora / pg_dump | 16.13 (Debian 16.13-1.pgdg12+1) |
| Vlasnik / encoding | immich / UTF8 |
| Locale / kolacija | en_US.utf8; zabilježena i stvarna glibc kolacija 2.36 |
| pg_database_size | 1249680407 bajtova = 1,164 GiB |
| Tablice uključujući TOAST | 595550208 bajtova = 0,555 GiB |
| Indeksi | 640860160 bajtova = 0,597 GiB |
| clip_index + face_index | 386.793.472 bajta = 0,360 GiB |
| Aplikacijske public tablice | 72 |
| Large objects / foreign tables / RLS policies | 0 / 0 / nema |
| Tablespaceovi aplikacijskih objekata | samo pg_default |
| Nevalidirani constraintovi / nevaljani ili nespremni indeksi | 0 / 0 |
| Event triggeri | nema |
| Slobodan prostor filesystema | 471.532.003.328 bajtova = 439,15 GiB; zauzeće 77% |

Veličine tablica i indeksa odnose se na public r/m relacije, pa njihov zbroj nije točno jednak cijeloj bazi. Broj redaka u katalogu reltuples bio je zastario za neke tablice; niže su stvarni COUNT rezultati iz jedne kratke read-only transakcije.

| Tablica | Trenutačni COUNT |
| --- | --- |
| public.asset | 57627 |
| public.asset_file | 123512 |
| public.smart_search | 57502 |
| public.face_search | 53059 |
| public.asset_face | 53063 |
| public.album | 11 |
| public."user" | 8 |

Ovi brojevi **nisu budući dump baseline** jer izvor ostaje živ. Dump i manifest moraju dijeliti snapshot u sljedećoj fazi.

Najnoviji pronađeni Immich backup: /opt/stacks/immich/docker-data/library/backups/immich-db-backup-20261114T020000-v3.3.5-pg16.13.sql.gz, **355.180.212 bajtova**. Faza 1/analiza potvrdila je gzip integritet, ali nije stvarni restore test. Njega ne prepisivati. Za ovu probu predlaže se novi custom-format dump s manifestom i snapshotom.

### Budžet prije odobrenog testa

| Dodatna alokacija | Planski limit |
| --- | --- |
| Puni custom dump + SRS sidecar | 2 GiB |
| Sanitizirani custom dump | 2 GiB |
| Bridge cluster PGDATA, uključujući njegov WAL | 4 GiB |
| Novi target PGDATA, uključujući njegov WAL | 4 GiB |
| Sort/index build temp prostor | 3 GiB |
| Manifesti, shema, logovi i rezerva testa | 1 GiB |
| Ukupni dodatni budžet | 16 GiB |

Ovo je konzervativni operativni budžet, ne izmjerena komprimirana veličina. Indeksi se u logičkom dumpu ne prenose kao fizički blokovi, nego se ponovno grade. Kompresija nije unaprijed zajamčena.

Zadržati ranije predloženi globalni slobodni reserve od 80 GiB. Za ovu jednu probu gate je **barem 96 GiB slobodno**, uz projekciju rasta ostalih stackova; trenutačno prolazi s velikom rezervom. /tmp i /opt/stacks/data dijele isti filesystem i nisu neovisni kapaciteti. Provjeru ponoviti prije dumpa i restorea. Ako test premaši 16 GiB ili ugrožava 80 GiB slobodne rezerve, zaustaviti samo test i dopuniti proračun. Ne oslobađati prostor brisanjem produkcijskih podataka.

## 2. Ekstenzije i njihove ovisnosti

| Ekstenzija | Verzija | Vlasnik | Schema | Odluka |
| --- | --- | --- | --- | --- |
| cube | 1.5 | postgres | public | sačuvati |
| earthdistance | 1.2 | postgres | public | sačuvati |
| pg_trgm | 1.6 | postgres | public | sačuvati |
| plpgsql | 1.0 | postgres | pg_catalog | sačuvati |
| postgis | 3.6.2 | postgres | public | zadržati u punoj arhivi; ukloniti samo iz testne kopije i sanitiziranog dumpa |
| unaccent | 1.1 | postgres | public | sačuvati |
| uuid-ossp | 1.1 | postgres | public | sačuvati |
| vchord | 1.1.1 | postgres | public | sačuvati |
| vector | 0.8.2 | postgres | public | sačuvati |

Izravne dependency veze ekstenzija: **earthdistance → cube**, **vchord → vector**. Nijedna od zadržanih ekstenzija ne zahtijeva PostGIS. U novom imageu svi zadržani binarni dodaci i njihove verzije već su provjereni u fazi 2.

Ponovljena klasifikacija PostGIS ovisnosti bez LIMIT-a:

- 894 izravna člana PostGIS ekstenzije;
- 1135 internih dependency bridova i 4 brida preko parent objekata;
- **0 preostalih aplikacijskih kandidata**;
- **0 aplikacijskih geometry/geography/raster stupaca**;
- tekstualno pronađeni geography_columns i geometry_columns su extension pogledi;
- nema security labela ni event triggera u bazi.

Provjera ne dokazuje odsutnost svakog dinamičkog SQL-a. Međutim, pregledane stvarne Immich search putanje ne pozivaju PostGIS; koriste vector, cube/earthdistance i unaccent.

### Prostorni nazivi koji se moraju sačuvati

**Ne uklanjati GiST indekse ni geodata/naturalearth tablice po nazivu ili metodi.**

~~~sql
CREATE INDEX "IDX_geodata_gist_earthcoord"
ON public.geodata_places USING gist (ll_to_earth_public(latitude, longitude));

CREATE INDEX "IDX_asset_exif_gist_earthcoord"
ON public.asset_exif USING gist (ll_to_earth_public(latitude, longitude));
~~~

ll_to_earth_public vraća earth, izrađen iz cube i earthdistance funkcija; f_unaccent koristi unaccent rječnik. To nisu PostGIS ovisnosti. Obje funkcije, oba GiST indeksa, geodata_places i naturalearth_countries pripadaju sadržaju koji treba očuvati.

## 3. Točno uklanjanje PostGIS-a iz migracijskog sadržaja

### Zašto nije dovoljan jednostavan TOC filter

PostGIS ima extconfig samo za public.spatial_ref_sys (trenutačni OID **232185**), a njegova extension OID vrijednost je **231866**. spatial_ref_sys ima **8500 redaka**; primjenom stvarnog extcondition predikata dobiveno je **0 konfiguracijskih redaka za pg_dump**.

To nije prazna tablica niti dokaz da nijedan standardni SRS zapis nije ručno mijenjan. Zato puni sadržaj SRS tablice treba zasebno arhivirati kao sidecar istog snapshota, prije bilo kakvog uklanjanja na testnoj kopiji.

Važan nalaz: **svih 776 PostGIS funkcija ima proacl različit od pg_init_privs.initprivs**. Prostorna config tablica također ima dodatni grant immich roli. U arhivi zato mogu postojati mnoge zasebne ACL stavke za extension članove, uz EXTENSION/COMMENT i TABLE DATA.

Uklanjanje samo CREATE EXTENSION postgis ostavilo bi GRANT/REVOKE naredbe za nepostojeće funkcije/tipove. Nisu prihvatljivi grep -v postgis, preskakanje svih ACL stavki, --no-acl ili --no-owner. Mnogi extension objekti u nazivu uopće nemaju riječ postgis. Puni TOC buduće arhive još ne postoji i njegov točan broj takvih stavki nije potvrđen.

### Odabrani postupak: izolirani bridge i RESTRICT

1. Napraviti **puni, nefiltrirani** custom dump izvora. Sačuvati ga neizmijenjenog, uz SHA-256, manifest rola/ACL i puni SRS sidecar.
2. Pokrenuti novi, privremeni bridge kontejner iz **istog postojećeg image ID-a** koji koristi produkcijski postgis:
   **sha256:33e372cc42ccaa91156d5072e48836abb2e532063dfdc79aa30e17df333a3bf0**.
   To nije pokretanje, build, retagiranje ili izmjena produkcijskog kontejnera.
3. Bridge ima vlastiti prazan data direktorij, --network none, bez portova i bez .env, backup ili aplikacijskih mountova. Uključiti samo preload vchord; pg_cron se ne učitava i nema njegovih SQL objekata/jobova.
4. U bridgeu obnoviti punu arhivu u **immich_restore_stage**, uz role postgres i immich i očuvane vlasnike/ACL. Provjeriti sve verzije, naročito PostGIS **3.6.2** — bez upgradea ili downgradea.
5. Usporediti bridge aplikacijski manifest s istim source snapshotom. Prije uklanjanja ekstenzije svi aplikacijski redci, definicije, vlasnici i prava moraju odgovarati.
6. **Samo na bridge bazi** izvršiti:
   ~~~sql
   DROP EXTENSION postgis RESTRICT;
   ~~~
   Nikad CASCADE, nikad prema kontejneru postgis. Ako RESTRICT odbije uklanjanje, **HOLD**: zapisati dependente, ne siliti uklanjanje.
7. Ponovno usporediti sve aplikacijske tablice, funkcije, indekse, sekvence, vlasništvo i ACL prije/poslije. Dopuštena razlika isključivo su PostGIS članovi, njihove interne strukture i pripadajuće privilegije/8500 SRS redaka; SRS je arhiviran odvojeno. Očekuje se svih **72 aplikacijskih tablica bez promjene podataka**.
8. Iz bridgea, sada bez PostGIS-a, napraviti drugi custom dump. On zadržava ostale ekstenzije i aplikacijske objekte te predstavlja **sanitizirani migracijski dump**.
9. pg_restore --list i schema-only render sanitizirane arhive moraju potvrditi odsutnost PostGIS ekstenzije i njezinih bivših objekata/ACL. Uspoređivati po prethodno spremljenim identitetima članova, ne samo po prefiksu imena.
10. Sanitizirani dump obnoviti u drugom izoliranom kontejneru na **novom PG16.16 imageu**. Time se istodobno provjeravaju potpunost logičkog sadržaja i stvarna odsutnost binarne PostGIS ovisnosti.

Ovaj postupak prepušta PostgreSQL-u uklanjanje extension objekata i njihovih ACL-a. Ne prepravlja SQL retke niti arhivu ručno. **Izvorni puni dump, source ekstenzija, source SRS i aplikacijski podaci ostaju sačuvani.**

Prethodni prijedlog TOC filtriranja ovdje je zamijenjen bridge pristupom zbog stvarno pronađenih ACL razlika. Ručni/automatizirani TOC filter ostaje alternativa samo uz zasebno odobren, potpuno pregledan object manifest; nije zadani put ove probe.

## 4. VectorChord kompatibilnost i stvarni probes parametar

| Indeks | Tablica/stupac | Tip | Metoda | Veličina MiB | Valid/ready |
| --- | --- | --- | --- | --- | --- |
| face_index | public.face_search.embedding | vector(512) | vchordrq | 166.13 | true/true |
| clip_index | public.smart_search.embedding | vector(512) | vchordrq | 202.74 | true/true |

Oba indeksa koriste vector_cosine_ops, residual_quantization=false, lists=[1], spherical_centroids=true, build_threads=4, sampling_factor=1024. Njihove definicije treba sačuvati; u fazi 2 sintetički build koristio je dva threada radi ograničenja testa. Identitet fizičkih indeksnih blokova neće se očuvati jer ih restore ponovno gradi.

Novi target image:
**immich-db-local:16.16-bookworm-vector0.8.2-vchord1.1.1**,
Docker image ID **sha256:e21ee65b5a53580b8f1e85b21ba0bf16f19c43d4dcc2ad49c4ce68a864a7cf51**.
Iste vector/vchord verzije već su funkcionalno testirane. To nije dokaz stvarnog restorea niti produkcijskog recall/performance ponašanja.

### Runtime dokaz Immich v3.3.5

Potvrđena verzija servera: v3.3.5, revision 8303cb117e197c700332b33b61b45314c9cc5bb4.

Pročitane su datoteke unutar **stvarnog pokrenutog** immich_server kontejnera:

- /usr/src/app/server/dist/repositories/database.repository.js:50–52: početni probes Clip=1, Face=1;
- isti file:301–308: targetListCount vraća 1 za count <128000, targetProbeCount = ceil(lists/8);
- isti file:145–170: pri provjeri postojećih indeksa izračunava probes po indeksu i može tražiti rebuild ako lists ne odgovara;
- /usr/src/app/server/dist/repositories/search.repository.js:66–71: searchSmart otvara transakciju, postavlja SET LOCAL vchordrq.probes pa izvodi cosine upit;
- isti file:86–87: searchFaces također postavlja parametar lokalno u transakciji;
- isti file:234–240: searchSmartV3 radi isto.

Za sadašnjih **57502 smart_search i 53059 face_search redaka**, lists=[1] i probes=1 odgovaraju toj logici. Nema DB/role-level settinga za immich, a inspekcijska sesija također vidi prazan zadani probes. Zato prazna default vrijednost iz faze 2 **nije dokaz kvara postojeće aplikacije**: aplikacija pretraživanje konfigurira transakcijski.

[Izvor točne verzije: DatabaseRepository](https://raw.githubusercontent.com/immich-app/immich/v3.3.5/server/src/repositories/database.repository.ts), [SearchRepository](https://raw.githubusercontent.com/immich-app/immich/v3.3.5/server/src/repositories/search.repository.ts).

Restore SQL test treba reproducirati **SET LOCAL**, uz novu vezu/transakciju za svaku putanju. Ne dodavati globalni probes=1 u Compose i ne mijenjati source bazu. Ako se do buduće migracije promijene broj redaka, lists ili aplikacijska verzija, ponovno izračunati očekivanje; ne pretpostaviti da 1 ostaje trajno točno.

## 5. Role, vlasništvo i privilegije

Baza je u vlasništvu immich, ali brojni postojeći aplikacijski objekti su u vlasništvu postgres. Na primjer asset, smart_search i face_search imaju vlasnika postgres i eksplicitna prava immich. Novije tablice poput geodata_places i naturalearth_countries imaju vlasnika immich. **Ne prepisivati sve objekte na immich.**

| Područje | Očuvati |
| --- | --- |
| Role | postgres kao bootstrap administrator; immich bez SUPERUSER/CREATEDB/CREATEROLE/REPLICATION/BYPASSRLS, INHERIT |
| Role membership | nema članstava immich role |
| Database ACL | PUBLIC CONNECT,TEMPORARY; immich CREATE,CONNECT,TEMPORARY; owner immich |
| Public schema | owner pg_database_owner; PUBLIC USAGE; immich USAGE,CREATE |
| Default table prava vlasnika postgres u public | immich: arwdDxt |
| Default sequence prava vlasnika postgres u public | immich: rwU |
| Default function prava vlasnika postgres u public | immich: EXECUTE |
| Kolonski ACL / RLS | trenutačno nema |
| Sekvenca | public.naturalearth_countries_tmp_id_seq1; owner immich; increment 1; trenutačni last_value 4274 |

Za izolirani restore **ne uvoziti produkcijske role password hashove ni sve globalne role clustera**. Prema sadašnjem inventaru potrebne su postgres, immich, PUBLIC i builtin pg_database_owner. Baza/objekti imaju samo ta imena granteea; manifest ponoviti s budućim dump snapshotom i stati ako se pojavi nepoznata rola.

Na bridge i target testu bootstrap postgres postoji. Testnu rolu immich stvoriti kao **NOLOGIN**, uz ostale zabilježene nesuperuser atribute; restore kao postgres očuvat će stvarne vlasnike/ACL, a SET ROLE immich omogućuje provjeru efektivnih prava bez produkcijske lozinke. NOLOGIN je namjerna razlika testne autentikacije, ne migracijska odluka. Stvarni login, SCRAM/HBA i credential prijenos nisu predmet ove probe.

Bazu osnovati iz čistog template0, owner immich, UTF8, en_US.utf8. Budući restore ne koristi --create, DB ACL i DB komentare/postavke treba primijeniti zasebno na **testno ime**. Trenutačno nema immich DB/role GUC postavki; ponoviti provjeru uz snapshot. Dumpovi i restore zadržavaju owner i ACL naredbe; ne koristiti --no-owner, --no-acl ili globalni --role immich.

## 6. Precizan postupak za sljedeće odobrenje

**Sve naredbe u ovom odjeljku su plan, nisu izvršene.** Prije izvedbe imenovati jedan jedinstveni CASE_ID, manifest datoteku i dva container imena. Ako bilo koja putanja/ime već postoji, stati umjesto ponovne uporabe.

Predložene lokacije:

- IMMICH_ARTIFACTS=/opt/stacks/data/backups/immich-restore-test-CASE_ID — privatni 0700 direktorij; artefakti 0600;
- IMMICH_WORK=/tmp/immich-restore-test-CASE_ID — samo novi bridge-data i target-data direktoriji, vlasnik 999:999, mode 0700;
- IMMICH_BRIDGE=immich-restore-bridge-CASE_ID;
- IMMICH_TARGET=immich-restore-target-CASE_ID.

CASE_ID mora odgovarati dozvoljenim Docker znakovima. Provjeriti realpath i da se nijedna nova putanja ne preklapa s /opt/stacks/data/postgres/data, postgres-standard/data ili immich-postgres/data. Ne montirati te direktorije u testove.

### A. Konzistentan source snapshot i puni dump

1. Ponoviti role/extensions/dependency/ACL/veličina/SRS inspekciju. Potvrditi pinane image ID-eve i disk gate. Dogovoriti da nema schema deploya tijekom snapshota; aplikacijske write transakcije nastavljaju normalno.
2. U zasebnoj trajno otvorenoj source vezi na postgis/immich:
   ~~~sql
   BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
   SELECT pg_export_snapshot();
   ~~~
   Session drži snapshot otvorenim do kraja pg_dumpa i baseline manifest čitanja. Ne koristiti jednokratni psql -c koji odmah zatvori exporter.
3. Validirani token prenijeti pg_dumpu i read-only baseline vezama. Svaka baseline veza: BEGIN REPEATABLE READ READ ONLY; SET TRANSACTION SNAPSHOT 'TOKEN'; tek zatim SELECT upiti.
4. Sačuvati 72-tablični object/data manifest, row countove, deterministične hashove, owners/ACL/default ACL, index definicije, constraints, funkcije/triggere, extension member identitete i sve SRS retke iz tog snapshota. Ne zapisivati sadržaj fotografija, embeddinge, emailove, API ključeve ili korisničke retke u javni izvještaj.
5. Izvorni full dump:
   ~~~bash
   docker exec postgis pg_dump -U postgres -d immich \
     --format=custom --compress=gzip:6 --snapshot="$IMMICH_SNAPSHOT" \
     --lock-wait-timeout=5s \
     > "$IMMICH_ARTIFACTS/immich.full.dump.partial" \
     2> "$IMMICH_ARTIFACTS/immich.full.dump.log"
   ~~~
   Pokretati serijski, bez parallel dumpa. Provjeriti exit 0 i upozorenja prije atomskog preimenovanja .partial u immich.full.dump. Ne prepisivati postojeću arhivu. Zabilježiti SHA-256 i veličinu.
6. Nakon pg_dumpa i baseline čitanja završiti exporter transakciju. Operativni limit trajanja source snapshota: 15 minuta; pri prekoračenju prekinuti samo dump/read klijente, arhivu označiti nepotpunom i ponoviti plan. Dugi snapshot može zadržavati MVCC mrtve retke; ne držati ga tijekom višeminutnih target restoreova.
7. Sačuvati i manifest stabilnosti sekvenci prije/poslije dumpa. PostgreSQL sekvence nisu MVCC snapshot: ako se zabilježene vrijednosti promijene, ne uspoređivati ih kao da imaju isti snapshot. Nakon restorea moraju biti barem iznad najvećeg postojećeg ključa i ne smiju biti umanjene. Za sada postoji jedna navedena sekvenca.
8. Archive/manifest klijentski podaci su osjetljivi čak i bez DB role lozinki. Bez objave arhive u git/logove; eventualnu off-host kopiju šifrirati.

Budući dump 16.13 čita isti PG16.13 source. Obnavlja se pomoću alata iz konkretnog bridge imagea, potom novog PG16.16 imagea; ne koristiti slučajni host psql/pg_restore druge glavne verzije.

### B. Izolirani bridge restore

Pokretati samostalnim docker run, ne postojećim Compose stackom:

~~~bash
docker run -d --name "$IMMICH_BRIDGE" --network none --restart no \
  --memory 4g --cpus 2 --shm-size 1g \
  --mount "type=bind,src=$IMMICH_WORK/bridge-data,dst=/var/lib/postgresql/data" \
  --mount "type=bind,src=$IMMICH_ARTIFACTS,dst=/restore,readonly" \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  -e POSTGRES_USER=postgres -e POSTGRES_DB=postgres \
  -e 'POSTGRES_INITDB_ARGS=--encoding=UTF8 --locale=en_US.utf8' \
  sha256:33e372cc42ccaa91156d5072e48836abb2e532063dfdc79aa30e17df333a3bf0 \
  postgres -c shared_preload_libraries=vchord \
  -c shared_buffers=256MB -c max_connections=20 -c TimeZone=Europe/Zagreb
~~~

Potvrditi da je PID1 stvarni postgres nakon završetka entrypoint init faze, network=none, bez portova i samo dva očekivana mounta. Ne koristiti --env-file.

Samo u bridgeu:

~~~sql
CREATE ROLE immich NOLOGIN INHERIT NOSUPERUSER NOCREATEDB
  NOCREATEROLE NOREPLICATION NOBYPASSRLS;
CREATE DATABASE immich_restore_stage WITH OWNER immich
  TEMPLATE template0 ENCODING 'UTF8'
  LC_COLLATE 'en_US.utf8' LC_CTYPE 'en_US.utf8';
~~~

Role atribute i nazive ponovno uskladiti s manifestom; ovaj SQL je točan za sadašnji nalaz. Puni restore:

~~~bash
docker exec "$IMMICH_BRIDGE" pg_restore -U postgres \
  --dbname=immich_restore_stage --exit-on-error --jobs=2 \
  /restore/immich.full.dump
~~~

Ne kombinirati --jobs i --single-transaction. Ne koristiti --clean, --disable-triggers ili --create. Postojeća bootstrap baza postgres ne smije biti restore odredište.

Postaviti DB ACL prema izvornom manifestu na testno ime, bez promjene ownera aplikacijskih objekata. Primjer za sadašnji DB ACL, u testnoj vezi kao postgres:

~~~sql
SET ROLE immich;
REVOKE ALL ON DATABASE immich_restore_stage FROM PUBLIC;
GRANT CONNECT, TEMPORARY ON DATABASE immich_restore_stage TO PUBLIC;
GRANT CREATE, CONNECT, TEMPORARY ON DATABASE immich_restore_stage TO immich;
RESET ROLE;
~~~

Provjeriti extension verzije prije usporedbe s baselineom. Puni dump sam aktivira potrebne ekstenzije kao postgres; ako verzija ne odgovara manifestu, HOLD, bez upgradea. Schema-only dump ili pg_get_* manifest koristi se za usporedbu, ne kao opravdanje za ignoriranje restore grešaka.

### C. Uklanjanje PostGIS-a samo na bridge kopiji i drugi dump

Tek nakon početne validacije:

~~~bash
docker exec "$IMMICH_BRIDGE" psql -X -U postgres \
  -d immich_restore_stage -v ON_ERROR_STOP=1 \
  -c 'DROP EXTENSION postgis RESTRICT;'
~~~

Provjeriti sve aplikacijske podatke/ACL prije-poslije i da nema PostGIS extension članova ni C funkcija koje referenciraju postgis library. Ako ostane ikakav orphan objekt, HOLD, ne brisati ga po nazivu.

Sanitizirana arhiva nastaje logičkim dumpom kopije:

~~~bash
docker exec "$IMMICH_BRIDGE" pg_dump -U postgres -d immich_restore_stage \
  --format=custom --compress=gzip:6 \
  > "$IMMICH_ARTIFACTS/immich.no-postgis.dump.partial" \
  2> "$IMMICH_ARTIFACTS/immich.no-postgis.dump.log"
~~~

Exit 0, hash, pregled TOC-a i schema-only render prethode preimenovanju u immich.no-postgis.dump. Bridge nema drugih writera pa mu novi eksportirani snapshot nije nužan. Izvorna i sanitizirana arhiva namjerno nemaju isti binarni hash; aplikacijski redci i njihovi sadržajni hashovi moraju se podudarati.

Čitanje TOC-a, bez SQL izvršavanja:

~~~bash
docker exec "$IMMICH_BRIDGE" pg_restore --list /restore/immich.no-postgis.dump
~~~

Bind je read-only, ali nove datoteke koje host zapisuje u artifact direktorij postaju dostupne kontejneru za čitanje. Za zapis arhiva koristiti stdout redirekciju na hostu; ne tražiti da bridge piše u /restore.

### D. Restore na novi PG16.16 image

Drugi samostalni testni kontejner, vlastiti target-data, isti read-only /restore mount, --network none, bez portova/produkcijskog env-a, memory 4g, CPU 2, shm 1g. Koristiti **točan image ID iz faze 2**, ne rebuild ili latest:

~~~text
sha256:e21ee65b5a53580b8f1e85b21ba0bf16f19c43d4dcc2ad49c4ce68a864a7cf51
~~~

PostgreSQL parametri isti kao bridge: preload vchord, shared_buffers=256MB, max_connections=20, TimeZone=Europe/Zagreb. Ne uključivati pg_cron. Provjeriti runtime 16.16 i očekivane mountove prije bilo kakvog restorea.

Kreirati istu testnu NOLOGIN rolu immich te bazu **immich_restore_test** iz template0, owner immich, UTF8 i isti locale. Sanitizirani dump:

~~~bash
docker exec "$IMMICH_TARGET" pg_restore -U postgres \
  --dbname=immich_restore_test --exit-on-error --jobs=2 \
  /restore/immich.no-postgis.dump
~~~

Nema --create, pa izvorno ime immich_restore_stage ne postaje target DB. Primijeniti isti source DB ACL na ime immich_restore_test i provjeriti svih osam preostalih ekstenzija uključujući plpgsql. ANALYZE izvršiti samo na ovoj testnoj bazi prije query plan testova.

Nema pokretanja Immich servera, njegovih migracija, Redis queueova, weba, ML-a ili media helpera. Restore test dokazuje SQL sadržaj i upite; eventualni puni aplikacijski startup zaseban je zahvat jer može mijenjati shemu i automatski reindeksirati.

## 7. Testovi integriteta i kriteriji uspjeha

### Obavezne usporedbe

| Točka usporedbe | Uvjet za PASS |
| --- | --- |
| Izvorni snapshot → bridge prije uklanjanja | isti svi aplikacijski redci, tablice, definicije, owners, ACL, default ACL i očekivane extension verzije |
| Bridge prije → poslije RESTRICT | nula promjena u aplikacijskim objektima/podacima; uklonjeni samo dokazani PostGIS objekti i pripadajući metapodaci |
| Bridge bez PostGIS-a → PG16.16 target | isti aplikacijski manifest i sadržaj; točne preostale extension verzije; nema PostGIS SQL/binarne ovisnosti |
| Svih 72 aplikacijskih tablica | COUNT i deterministični sadržajni hash isti; broj iz future manifest snapshot-a ima prednost pred sadašnjim brojem |
| Funkcije, triggeri, constraints, sekvence | sve očekivane definicije i prava; nijedan neočekivani gubitak; source sequence race zasebno evidentiran |
| clip_index, face_index i oba geografska GiST indeksa | definicije/metode/opclass/options očuvani, indisvalid/indisready true |
| Podaci o vektorima | vector(512); isti hashovi, NULL countovi i raspodjele dimenzije; nema izgubljenih embeddinga |
| Efektivna prava | SET ROLE immich može čitati sve app tablice i izvršavati potrebne funkcije; nema slučajnog proširenja privilegija |
| Obnova / logovi | exit 0; nula neočekivanih SQL grešaka; nema duplicate object grešaka koje su proglašene bezazlenima |
| Izolacija i kapacitet | bez prod mountova/mreža/portova/creds; poštovan reserve; izvor nije restartan niti modificiran |

Hash manifest: streamati kanonski JSONB prikaz reda, u PK redoslijedu; za tablice bez PK sortirati kanonski tekst s COLLATE "C" i očuvati multiplicitet duplikata. Fiksirati UTF8, TimeZone=UTC, DateStyle=ISO i extra_float_digits=3. Koristiti host SHA-256 nad streamom, ne veliki string_agg u RAM-u. Privatno sačuvati samo hash/count manifest; stvarne retke ne ispisivati u izvještaj.

Source baseline koristi isti eksportirani snapshot kao dump. Target/bridge su bez writera. Fizička veličina i binarni indeksni hash nisu kriterij jednakosti.

### Upiti za oba VectorChord indeksa

Izabrati determinističan privatni uzorak do 10 ne-NULL, ne-nultih vektora po tablici iz tog snapshota; zabilježiti ID-eve samo u privatnom manifestu. Na targetu ponoviti kroz nove read-only transakcije, uključujući prava immich:

~~~sql
BEGIN READ ONLY;
SET LOCAL ROLE immich;
SET LOCAL vchordrq.probes=1;
SET LOCAL enable_seqscan=off;

EXPLAIN (ANALYZE, FORMAT JSON)
SELECT "assetId"
FROM public.smart_search
ORDER BY embedding <=> (
  SELECT embedding FROM public.smart_search
  WHERE "assetId" = :'sample_asset_id'
)
LIMIT 10;
ROLLBACK;
~~~

Isti obrazac za face_search i faceId. Za parametre koristiti psql quoted-value mehanizam ili bind parametre; nikad tekstualno interpolirati embeddinge ili korisničke podatke u shell. U izvještaju zapisati index ime, broj rezultata, vremena i udaljenosti bez biometrijskih embeddinga.

PASS: stvarni Index Scan nad clip_index/face_index, valid/ready true, uspješno izvršenje bez probes greške i na uzorku povrat barem jednog zero-distance kandidata za upit vlastitim postojećim vektorom. Kod duplikata nije nužno baš isti ID prvi.

Za svaki uzorak na targetu napraviti i exact baseline s index/index-only/bitmap scanovima isključenima, pa usporediti ANN top-k s exact rezultatima i izračunati recall. ANN redoslijed i svi top-k ID-evi ne moraju biti bit-identični nakon rebuilda. Produkcijski prag recall-a i dopuštena latencija nisu dogovoreni: rezultat se mjeri i evidentira, a bez prihvaćenog praga **ne izdavati produkcijski GO**. SQL restore/integrity PASS može postojati odvojeno od tog aplikacijskog gatea.

Ponoviti i bez enable_seqscan=off te evidentirati plannerov stvarni odabir. Forsirani plan dokazuje sposobnost uporabe indeksa, ne prirodni odabir u svim aplikacijskim filterima.

### Testovi ACL i write putanje samo na kopiji

Prvo čist read-only SET ROLE test. Za dokaz efektivnih INSERT/UPDATE prava na targetu koristiti provjeru has_table_privilege i has_function_privilege. Ne dodavati stvarne nove foto/face korisničke retke radi smokea. Ako se naknadno traži stvarni DML test, zasebno odrediti sandbox redak i rollback; rollback transakcije ne vraća potrošene sekvence.

DB autentikacija, HBA/SCRAM, medijske datoteke, Nextcloud mountovi, ML modeli, stvarni HTTP upiti i background poslovi **nisu obuhvaćeni ovom SQL restore probom**.

## 8. Rollback i čišćenje

Nema produkcijskog cutovera, pa rollback ne znači promjenu DATABASE_URL-a ili povrat izvornog DB-a. **Izvor je cijelo vrijeme jedini authoritative servis i nastavlja raditi.**

Ako bilo što padne:

1. Zaustaviti samo dump/test klijente i dva testna kontejnera; zatvoriti source snapshot ako je otvoren.
2. Arhivu .partial ne proglasiti valjanom. Sačuvati privatne logove/hash manifest; izvorne i sanitizirane dokaze ne prepisivati novim pokušajem.
3. Ako RESTRICT odbije, pokazati dependente. Bez CASCADE, bez uklanjanja source objekata, bez improvizirane promjene app sheme.
4. Ako nakon RESTRICT nestane aplikacijski objekt ili se hash razlikuje, označiti FAIL; kopiju ne koristiti kao migracijski izvor. Sljedeća proba počinje iz neizmijenjene full arhive u novom privatnom direktoriju.
5. Privremene testne kontejnere i data direktorije ukloniti tek nakon prikupljanja dokaza i u okviru odobrenog cleanup opsega. Prije brisanja provjeriti test label/ime, mount realpath i da nijedan proces više ne koristi putanju.
6. Puni backup, SRS sidecar i manifesti ostaju privatni; retenciju/brisanju arhiva odrediti zasebno. Ne brisati postojeće backupove, izvornu produkciju ili buduće migracijske direktorije.

Ne koristiti docker system/volume prune, docker compose down nad postojećim stackovima, izvorni pg_restore --clean niti reset PGDATA. Ne mijenjati Docker daemon radi čišćenja eventualno sporog removing statusa.

## 9. Rizici i odluke prije izvedbe

| Rizik | Kontrola / otvorena odluka |
| --- | --- |
| 776 PostGIS function ACL razlika | bridge RESTRICT i ponovno logičko dumpanje; nema grubog TOC tekstualnog filtera |
| SRS tablica nije prazna; config_dump_rows=0 ne dokazuje neizmijenjene standardne retke | arhivirati cijelu tablicu u sidecar istog source snapshota; namjerno izostaviti samo iz non-PostGIS kopije |
| Bridge koristi postojeći kompleksni image | pinned image ID, vlastiti PGDATA, network none, samo vchord preload; nema produkcijskog container/image retagiranja |
| Dinamički SQL nije potpuno vidljiv u katalozima | statički pregled stvarnih search putanja; target SQL smoke; puna app integracija ostaje budući gate |
| Pomiješani postgres/immich vlasnici | restore kao postgres bez no-owner/no-acl; oba vlasnika i default grants očuvati |
| Live izvor se mijenja | eksportirani snapshot za dump i content manifest; sekvence tretirati odvojeno; bez write-freezea i tvrdnje o finalnom RPO=0 |
| probes ovisi o indeksu i runtime verziji | SET LOCAL kao stvarna aplikacija; aktualni lists/count ponovno provjeriti prije probe |
| Startup Immicha može migrirati/reindeksirati | u ovoj restore probi ne pokretati aplikaciju |
| Dump sadrži osobne podatke, tokene i biometrijske embeddinge | privatni 0700/0600 artefakti, bez produkcijskih mreža i logiranja redaka |
| Kapacitet i izvorno opterećenje | 16 GiB budžet + 80 GiB reserve; serijski source dump; ograničeni test CPU/RAM; stop pri prekoračenju |
| Auth, mediji, recall SLA i downtime nisu potvrđeni | izvan SQL restore PASS-a; posebno odobrenje/pragovi prije migracije |

## 10. Izvršene naredbe i što nije izvršeno

U ovoj fazi izvršene su samo:

- cat/sed/grep nad migracijskom dokumentacijom i runtime JS izvorima;
- docker inspect nad postojećim kontejnerima, uz ispis samo verzija/identiteta i DB host/name, bez tajni;
- docker image inspect nad već izgrađenim novim imageom;
- docker exec postgis pg_dump --version (isključivo verzija, **nije dump**);
- psql transakcije **BEGIN READ ONLY**, s lokalnim statement_timeout=20s i SELECT upitima nad katalozima, veličinama i navedenim COUNT agregatima;
- df -B1 i git status;
- provjera službene PostgreSQL dokumentacije i izvora točne Immich verzije.

Jedan početni grep uključio je nepostojeću smart-info.repository.js putanju pa je vratio exit 2; svi relevantni nalazi potom su potvrđeni čitanjem postojećih database.repository.js/search.repository.js datoteka. To nije baza ili aplikacijska greška.

Nisu izvršeni pg_dump bez --version, pg_restore, export snapshot, CREATE/DROP/ALTER, promjene ekstenzija, pokretanje novih kontejnera ili stvaranje data direktorija. Ovaj dokument jedina je nova datoteka faze. Završna provjera linkova, code fenceova i tajni prošla je; postgis je isti, running i bez restarta, a budući migracijski data direktoriji ostali su prazni.

[PostgreSQL pg_dump dokumentacija](https://www.postgresql.org/docs/16/app-pgdump.html) potvrđuje custom archive i snapshot mehanizam; [pg_restore dokumentacija](https://www.postgresql.org/docs/16/app-pgrestore.html) opisuje restore iz arhive. Ponuđeni bridge postupak projektna je odluka izvedena iz stvarno izmjerenih ACL/dependency nalaza.

**Stati nakon pregleda plana. Novo izričito odobrenje potrebno je za full dump, dva izolirana restore clustera, RESTRICT uklanjanje na bridge kopiji, drugi dump i testove. Nema odobrenja za migraciju ni promjenu aplikacijskih konekcija.**
