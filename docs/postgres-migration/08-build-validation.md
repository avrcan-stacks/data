# 08 — Phase 2: build i izolirana validacija

Datum: 14. studenoga 2026. (Europe/Zagreb).

**Build oba imagea uspješan.** Standardni funkcionalni testovi prolaze. VectorChord aktivacija i izrada indeksa prolaze; pretraživanje prolazi uz eksplicitni session parametar **vchordrq.probes=1**. Test s praznom zadanom vrijednošću reproducirao je grešku opisanu niže. Produkcijske konfiguracije nisu mijenjane radi otklanjanja te greške.

Migracija nije započeta. Trajni servisi postgres i immich-db nisu pokrenuti. Izvršeni su odobreni build i privremeni testovi; testni kontejneri i njihove data putanje uklonjeni su.

## Build i identitet artefakata

Korišten je isključivo zaseban Compose iz [faze 1](07-phase1-infrastructure.md):

~~~bash
docker compose -f docker-compose.postgres-new.yml config --quiet
docker compose -f docker-compose.postgres-new.yml build --progress plain postgres immich-db
~~~

Obje naredbe završile su exit kodom **0**. Compose je upozorio da je --progress globalni parametar; build je svejedno uspješno izvršen. Za budući poziv preferirati:

~~~bash
docker compose --progress plain -f docker-compose.postgres-new.yml build postgres immich-db
~~~

Završni izlaz:

~~~text
Image postgres-standard-local:16.16-bookworm-vector0.8.2-cron1.6.7 Built
Image immich-db-local:16.16-bookworm-vector0.8.2-vchord1.1.1 Built
~~~

Nisu mijenjani Dockerfileovi, verzije, pinovi ni Compose konfiguracija. Build je potvrdio dostupnost pinanih server-dev/libpq-dev paketa, SHA-256 izvora, kompajliranje dodataka, contrib control datoteke, odsutnost neželjenih ekstenzija i prolaz ldd provjera. Nema PostGIS-a u novim imageovima; standardni nema vchord, a Immich nema pg_cron.

| Artefakt | Image referenca | Docker inspect Image identifikator |
| --- | --- | --- |
| Standardni | postgres-standard-local:16.16-bookworm-vector0.8.2-cron1.6.7 | sha256:2f9d2f25e8960e9cea97454611f3761802ebfbd8e1685a9704c6436bd26e1bb2 |
| Immich | immich-db-local:16.16-bookworm-vector0.8.2-vchord1.1.1 | sha256:e21ee65b5a53580b8f1e85b21ba0bf16f19c43d4dcc2ad49c4ce68a864a7cf51 |

Oba runtimea prijavljuju:

~~~text
PostgreSQL 16.16 (Debian 16.16-1.pgdg12+1) on x86_64-pc-linux-gnu, compiled by gcc (Debian 12.2.0-14+deb12u1) 12.2.0, 64-bit
~~~

Upstream pg_cron izgrađen je iz v1.6.7 izvora; njegova SQL extension verzija jest **1.6**. Pgvector je **0.8.2**, VectorChord **1.1.1**, u skladu s planom. Izgrađeni imageovi ostaju na hostu kao rezultat ove faze. Nisu uklanjani zajednički build cacheovi ni drugi imageovi.

## Izolacija

Svaki test koristio je novi kontejner i data direktorij pod /tmp/postgres-phase2-*, odvojeno od produkcijskog i budućih migracijskih direktorija:

- --network none, bez produkcijskih mreža, aliasa ili objavljenih portova;
- točno jedan bind mount: vlastiti privremeni direktorij → /var/lib/postgresql/data;
- bez /backups, /srv/qubit/backups, aplikacijskih mountova ili init skripti;
- bez produkcijske .env datoteke i njezinih lozinki; trust autentikacija samo u mrežno izoliranom testnom kontejneru;
- memory 2 GiB, CPU limit 2, shm 512 MiB, shared_buffers 128 MiB, max_connections 20;
- samo sintetički podaci, bez produkcijskih dumpova i kopiranja baza.

Privremena baza phase2_validation osnovana je samo u testnim clusterima. Pg_cron je aktiviran u njihovoj privremenoj ugrađenoj bazi postgres, sukladno bootstrap konfiguraciji i uz cron.launch_active_jobs=off.

Testni kontejneri:

- pg-phase2-standard-ib0jk04p
- pg-phase2-immich-ib0jk04p
- pg-phase2-immich-vs0xw1io (prvi uspješni probes retest)
- pg-phase2-immich-5h55ey8a (ponovljeni probes retest sa završnim dokazima)

Svi su uklonjeni, zajedno sa svojim data putanjama. Za testove je korišten docker run nad upravo izgrađenim imageovima, uz docker exec/psql. Nije korišten docker compose up, create ili run nad postojećim ili budućim trajnim stackom.

Reprezentativni poziv testnog kontejnera (NAME, DATA i IMAGE odgovaraju njegovim gore navedenim vrijednostima):

~~~bash
docker run -d --name NAME --network none --restart no \
  --memory 2g --cpus 2 --shm-size 512m \
  --mount type=bind,src=DATA,dst=/var/lib/postgresql/data \
  -e POSTGRES_HOST_AUTH_METHOD=trust \
  -e POSTGRES_USER=postgres -e POSTGRES_DB=postgres \
  -e 'POSTGRES_INITDB_ARGS=--encoding=UTF8 --locale=en_US.utf8' \
  IMAGE postgres -c shared_buffers=128MB -c max_connections=20 \
  -c TimeZone=Europe/Zagreb
~~~

Standardni test dodao je preload pg_cron,pg_stat_statements i cron.database_name=postgres, cron.timezone=GMT, cron.launch_active_jobs=off; Immich test dodao je preload vchord. Ti su parametri provjereni i u runtimeu.

## Aktivirane ekstenzije

Uspješno aktivirane SQL naredbom CREATE EXTENSION na privremenim bazama. Plpgsql je automatski prisutan.

| Image | Privremena baza | Ekstenzija | Verzija |
| --- | --- | --- | --- |
| standard | phase2_validation | fuzzystrmatch | 1.2 |
| standard | phase2_validation | pageinspect | 1.12 |
| standard | phase2_validation | pg_stat_statements | 1.10 |
| standard | phase2_validation | pg_trgm | 1.6 |
| standard | phase2_validation | pgcrypto | 1.3 |
| standard | phase2_validation | plpgsql | 1.0 |
| standard | phase2_validation | uuid-ossp | 1.1 |
| standard | phase2_validation | vector | 0.8.2 |
| standard | postgres (testni cluster) | pg_cron | 1.6 |
| immich | phase2_validation | cube | 1.5 |
| immich | phase2_validation | earthdistance | 1.2 |
| immich | phase2_validation | pg_trgm | 1.6 |
| immich | phase2_validation | plpgsql | 1.0 |
| immich | phase2_validation | unaccent | 1.1 |
| immich | phase2_validation | uuid-ossp | 1.1 |
| immich | phase2_validation | vchord | 1.1.1 |
| immich | phase2_validation | vector | 0.8.2 |

Standardni smoke upiti izvršili su digest, trigram similarity i levenshtein; similarity istih stringova je 1, levenshtein 0. Immich je dodatno izvršio trigram similarity i unaccent. Ostalim navedenim contrib dodacima provjerena je aktivacija, ne puni regresijski suite.

## pgvector: izrada i uporaba IVFFlat indeksa

Standardni test upisao je **2048 sintetičkih vektora**, svaki vector(512):

~~~sql
CREATE TABLE vectors(id integer PRIMARY KEY, embedding vector(512));
INSERT INTO vectors
SELECT g, ARRAY(
  SELECT sin((g*j)::double precision) FROM generate_series(1,512) j
)::vector
FROM generate_series(1,2048) g;

CREATE INDEX phase2_ivfflat ON vectors
USING ivfflat(embedding vector_cosine_ops) WITH(lists=4);
ANALYZE vectors;
~~~

Uz enable_seqscan=off izvršen je EXPLAIN ANALYZE i stvarni top-10 upit. Plan sadrži **Index Scan using phase2_ivfflat**; indisvalid i indisready su true. Vraćeno je 10 redaka, a identični vektor id=1 prvi je rezultat.

Ovo potvrđuje izradu i korištenje indeksa; nije benchmark niti dokaz ANN recall kvalitete za stvarne aplikacijske podatke. Forsiranje index plana služi provjeri mogućnosti korištenja, ne dokazuje da bi ga planner uvijek sam odabrao.

## VectorChord: problem i uspješna provjera

Aktivacije vector i vchord prolaze. Nad zasebnih 2048 sintetičkih vector(512) redaka uspješno je izrađen indeks:

~~~sql
CREATE INDEX phase2_vchordrq ON vectors
USING vchordrq(embedding vector_cosine_ops)
WITH(options='
residual_quantization = false
[build.internal]
lists = [1]
spherical_centroids = true
build_threads = 2
sampling_factor = 1024
');
~~~

### Negativni test zadane postavke

Prvi EXPLAIN ANALYZE koji je stvarno izvršavao pretraživanje pao je, psql exit 3:

~~~text
ERROR: need 1 probes, but 0 probes provided
~~~

U čistoj bazi zadani vchordrq.probes je **prazan string** (prazna lista), a indeks ima jedan nivo lists=[1]. Izrada indeksa nije pala; pri pretraživanju nedostaje parametar odgovarajućeg oblika.

### Korekcija samo testne sesije

U novom izoliranom testu, bez promjene imagea ili Composea:

~~~sql
SET vchordrq.probes=1;
SET enable_seqscan=off;

EXPLAIN (ANALYZE, FORMAT JSON)
SELECT id FROM vectors
ORDER BY embedding <=> (SELECT embedding FROM vectors WHERE id=1)
LIMIT 10;
~~~

**PASS**: Index Scan nad phase2_vchordrq; valid/ready true; 2048 spremljenih redaka; vraćeno 10 redaka i id=1 kao prvi rezultat.

| Provjera | Rezultat |
| --- | --- |
| indisvalid | true |
| indisready | true |
| Top-10 ID | 1, 711, 1421, 376, 1086, 1796, 1042, 332, 1752, 290 |
| EXPLAIN execution time, jedan sintetički test | 2.019 ms |

**Predloženi ispravak za kasniju integraciju:** osigurati odgovarajući vchordrq.probes za stvarne indekse preko aplikacijskih sesija/DB postavki ili odobrenog index-level fallbacka. Za sadašnje jednonivovske lists=[1] strukture testirana vrijednost jest 1. Ne postaviti univerzalno 1 za indekse drukčije dubine: oblik probes mora odgovarati hijerarhiji lists. [VectorChord indexing dokumentacija](https://vchord.pgsty.com/docs/vchord/usage/indexing/), [index fallback parametri](https://vchord.pgsty.com/docs/vchord/usage/fallback-parameters/).

Ništa od toga nije primijenjeno na produkciju niti na budući trajni Compose. Prije migracije provjeriti stvarne Immich v3.3.5 session parametre i aplikacijski smoke u zasebno odobrenoj fazi. To ostaje eksplicitni migracijski gate.

## pg_cron: zabrana izvršavanja

U testnom standardnom serveru potvrđeno:

~~~text
shared_preload_libraries = pg_cron,pg_stat_statements
cron.database_name = postgres
cron.timezone = GMT
cron.launch_active_jobs = off
cron.log_run = on
~~~

U privremenoj ugrađenoj bazi postgres aktiviran je pg_cron 1.6 i kreiran bezopasan sintetički posao:

~~~sql
CREATE TABLE phase2_cron_probe(executed_at timestamptz DEFAULT now());
SELECT cron.schedule(
  'phase2-disabled-probe', '1 second',
  'INSERT INTO phase2_cron_probe DEFAULT VALUES'
);
~~~

Nakon 5 sekundi:

~~~json
{
  "active_jobs": 1,
  "probe_rows": 0,
  "run_details": 0
}
~~~

Posao je bio aktivno zakazan, ali nijedan redak nije upisan i nijedno izvršavanje nije evidentirano. Potom je unschedulean i testni cluster uklonjen. **Nije pokrenut nijedan produkcijski cron zadatak**, prune/export funkcija ili aplikacijski worker.

Dokaz vrijedi za ovu konfiguraciju i promatrani interval, ne za buduću konfiguraciju s promijenjenim gateom. Trajni postgres servis nije startan; njegovu zabranu potvrđuju Compose model i izolirani test istog imagea s istim parametrom.

## Puni inventar dostupnih ekstenzija

Ovo je pg_available_extensions inventar control datoteka. Dostupnost nije aktivacija. Stvarno aktivirane verzije navedene su gore; nije izvršen puni PostgreSQL contrib regresijski suite.

| Ekstenzija | Standardni default_version | Immich default_version |
| --- | --- | --- |
| adminpack | 2.1 | 2.1 |
| amcheck | 1.3 | 1.3 |
| autoinc | 1.0 | 1.0 |
| bloom | 1.0 | 1.0 |
| btree_gin | 1.3 | 1.3 |
| btree_gist | 1.7 | 1.7 |
| citext | 1.6 | 1.6 |
| cube | 1.5 | 1.5 |
| dblink | 1.2 | 1.2 |
| dict_int | 1.0 | 1.0 |
| dict_xsyn | 1.0 | 1.0 |
| earthdistance | 1.2 | 1.2 |
| file_fdw | 1.0 | 1.0 |
| fuzzystrmatch | 1.2 | 1.2 |
| hstore | 1.8 | 1.8 |
| insert_username | 1.0 | 1.0 |
| intagg | 1.1 | 1.1 |
| intarray | 1.5 | 1.5 |
| isn | 1.2 | 1.2 |
| lo | 1.1 | 1.1 |
| ltree | 1.2 | 1.2 |
| moddatetime | 1.0 | 1.0 |
| old_snapshot | 1.0 | 1.0 |
| pageinspect | 1.12 | 1.12 |
| pg_buffercache | 1.4 | 1.4 |
| pg_cron | 1.6 | nije dostupna |
| pg_freespacemap | 1.2 | 1.2 |
| pg_prewarm | 1.2 | 1.2 |
| pg_stat_statements | 1.10 | 1.10 |
| pg_surgery | 1.0 | 1.0 |
| pg_trgm | 1.6 | 1.6 |
| pg_visibility | 1.2 | 1.2 |
| pg_walinspect | 1.1 | 1.1 |
| pgcrypto | 1.3 | 1.3 |
| pgrowlocks | 1.2 | 1.2 |
| pgstattuple | 1.5 | 1.5 |
| plpgsql | 1.0 | 1.0 |
| postgres_fdw | 1.1 | 1.1 |
| refint | 1.0 | 1.0 |
| seg | 1.4 | 1.4 |
| sslinfo | 1.2 | 1.2 |
| tablefunc | 1.0 | 1.0 |
| tcn | 1.0 | 1.0 |
| tsm_system_rows | 1.0 | 1.0 |
| tsm_system_time | 1.0 | 1.0 |
| unaccent | 1.1 | 1.1 |
| uuid-ossp | 1.1 | 1.1 |
| vchord | nije dostupna | 1.1.1 |
| vector | 0.8.2 | 0.8.2 |
| xml2 | 1.1 | 1.1 |

## Produkcija i cleanup

Usporedba protected-file hashova i Docker metapodataka prije/poslije:

| Provjera | Rezultat |
| --- | --- |
| docker-compose.yml, docker-compose.local.yml, Dockerfile.postgis | nepromijenjeni |
| .env, .env.example, postgis-tailscale.env | nepromijenjeni; vrijednosti nisu ispisane |
| Novi Compose i oba Dockerfilea | nepromijenjeni tijekom faze 2 |
| postgis ID / image / mountovi / mreže | nepromijenjeni |
| postgis StartedAt i status | bez restarta; running |
| postgres-standard/data i immich-postgres/data | ostali prazni |
| Testni mountovi | samo /tmp; bez produkcijskog PGDATA i backup mountova |
| Backup direktoriji | nisu mijenjani našim naredbama |
| Testni kontejneri i data direktoriji | uklonjeni; završna provjera bez ostataka |
| Produkcijski dump/restore/CREATE DATABASE/migrate | nije izvršeno |
| Aplikacijski endpointi i credentials | nisu mijenjani |

Privremeno uklanjanje kontejnera na početnim prolazima neko je vrijeme pokazivalo Docker status removing/Dead; završilo je uspješno bez intervencije u Docker daemon ili produkciju. Završni ponovljeni test zaustavljen je graceful stopom i uklonjen. Naknadni pokušaj slanja SIGINT starom testnom imenu dobio je No such container jer je cleanup već bio dovršen; druge kontejnere nije dirao.

Cleanup se odnosio samo na poznata testna imena i vlastite putanje. Nije korišten docker system/volume prune niti brisanje produkcijskih ili budućih data direktorija. Privremene skripte i logovi uklonjeni su nakon prijenosa dokaza u ovaj dokument.

Završna sigurnosna provjera: **PASS**. Provjereno je i da nijedan testni kontejner ili data direktorij više ne postoji. Build je koristio Dockerfile-specifične ignore datoteke koje isključuju produkcijski data, backupove i secrets iz konteksta.

## Granica faze

Oba imagea izgrađena su i provjereni su PG16.16, potrebne ekstenzije, sintetički indeksi i isključen cron scheduler. VectorChord pretraživanje ima gore dokumentiran uvjet probes konfiguracije.

Nisu testirani restore produkcijskih arhiva, aplikacijske migracije, stvarni Immich/Chatwoot promet, mediji, dugoročno opterećenje ili poslovni cutover. Nijedan novi trajni servis nije pokrenut.

**Ovdje se staje. Migracija i preusmjeravanje aplikacija zahtijevaju novo izričito odobrenje.**
