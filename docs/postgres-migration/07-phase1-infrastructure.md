# 07 — Phase 1: priprema novih PostgreSQL servisa

Datum: 14.11.2026. Status: **konfiguracije pripremljene i validirane; build, create i up nisu pokrenuti**.

Odobren je plan migracije i samo priprema infrastrukture. Pokretanje, inicijalizacija, aktivacija ekstenzija i migracija podataka zahtijevaju novo izričito odobrenje.

## Izrađene i izmijenjene datoteke

| Datoteka | Sadržaj |
| --- | --- |
| ../../Dockerfile.postgres | PG16.16 Bookworm, vector 0.8.2, pg_cron upstream 1.6.7 / SQL 1.6; contrib iz osnovnog imagea |
| ../../Dockerfile.immich-db | PG16.16 Bookworm, vector 0.8.2, vchord 1.1.1 za PG16 |
| ../../docker-compose.postgres-new.yml | zaseban Compose projekt data-postgres-next; samo dva nova servisa |
| ../../Dockerfile.postgres.dockerignore | isključuje sve osim vlastitog Dockerfilea i ignore datoteke |
| ../../Dockerfile.immich-db.dockerignore | ista zaštita build konteksta za Immich |
| ../../.gitignore | dodani postgres-standard/ i immich-postgres/ |
| 07-phase1-infrastructure.md | ovaj zapis, finalni konfiguracijski sadržaj i rezultati provjera |

Putanje u prvom stupcu tablice odnose se na korijen repozitorija (tablica prikazuje nazive, ne relativne linkove). Pregled: [Compose](/opt/stacks/data/docker-compose.postgres-new.yml), [standardni Dockerfile](/opt/stacks/data/Dockerfile.postgres), [Immich Dockerfile](/opt/stacks/data/Dockerfile.immich-db).

Postojeći docker-compose.yml, docker-compose.local.yml, Dockerfile.postgis, .env, .env.example i postgis-tailscale.env nisu promijenjeni; SHA-256 usporedba prije/poslije prošla je. Postojeći data.code-workspace nije diran. Nije napravljen commit.

## Finalni raspored

| Postavka | postgres | immich-db |
| --- | --- | --- |
| container_name | postgres | immich-db |
| image tag | postgres-standard-local:16.16-bookworm-vector0.8.2-cron1.6.7 | immich-db-local:16.16-bookworm-vector0.8.2-vchord1.1.1 |
| Arhitektura | linux/amd64 | linux/amd64 |
| Baza/runtime | PostgreSQL 16.16 / Bookworm | PostgreSQL 16.16 / Bookworm |
| Preload | pg_cron,pg_stat_statements | vchord |
| Host PGDATA | /opt/stacks/data/postgres-standard/data | /opt/stacks/data/immich-postgres/data |
| Container PGDATA | /var/lib/postgresql/data | /var/lib/postgresql/data |
| Mreže | postgis, backend, hetzner_net | postgis |
| Objavljeni host portovi | nema | nema |
| Memory cap / shared_buffers / shm | 12 GiB / 3 GiB / 1 GiB | 4 GiB / 1 GiB / 1 GiB |
| Bootstrap korisnik/baza | postojeći admin postgres / ugrađeni postgres | isti admin / ugrađeni postgres |
| Password izvor | postojeći .env, bez ispisa ili izmjene | postojeći .env, bez ispisa ili izmjene |
| Init SQL / aplikacijske baze | nema | nema |

Novi data direktoriji **stvoreni su prazni**, numeric UID:GID 999:999, mode 0700. Roditeljski direktoriji su novi. Obje data putanje su gitignored, nisu symlinkovi, nisu već korišteni container mountovi i ne preklapaju se s izvornim PGDATA. Ne sadrže PG_VERSION niti inicijalizirani cluster.

Novi servisi imaju mount postojećeg /backups; standardni ima i postojeći /srv/qubit/backups mount prema planu. Svi bind mountovi koriste create_host_path=false, kako typo ili nedostajuća putanja ne bi bili prešutno stvoreni pri pokretanju. Novi servisi nisu pokrenuti pa nisu pisali ni u backup direktorije.

Sve mreže su external s postojećim eksplicitnim imenima. Ne stvaraju se nove mreže niti mijenjaju endpointi/aliasi postojećih kontejnera. U budućem odobrenom up-u samo novi servisi dobit će vlastite endpoint aliase postgres i immich-db. Postojeći postgis endpoint ostaje nepromijenjen.

## pg_cron bootstrap odluka za ovu fazu

Odobreni migracijski plan traži cron metadata u qubit_user. Ta baza u ovoj fazi ne smije biti kreirana. Zato prazni standardni servis koristi **cron.database_name=postgres** i **cron.launch_active_jobs=off**, bez CREATE EXTENSION i bez jobova.

Ovo nije promjena konfiguracije postojećeg postgis servisa niti popravak njegovog zastalog crona. Prije kasnije odobrene migracije qubit_user potrebno je uskladiti cron.database_name=qubit_user i restartati samo novi standardni servis u dogovorenom postupku. Ne ostaviti bootstrap vrijednost pri aktivaciji stvarnih jobova.

Kad se jednom odobri up, službeni entrypoint praznog clustera inicijalizirat će ugrađene template0/template1/postgres baze. Nema produkcijskih aplikacijskih baza, init skripti ni promjene korisničkih lozinki u ovoj konfiguraciji. Ekstenzije su instalacijski artefakti u imageu, a ne automatski aktivirane SQL ekstenzije.

## Verzijskim pinovima provjereni izvori

Registry manifesti pregledani su bez docker pull/build/run:

- postgres:16.16-bookworm, linux/amd64: **sha256:f45d631d050c2fe068f384ed6c4faac506e9cd7f4da605ce703648e4b0985848**
- ghcr.io/tensorchord/vchord-postgres:pg16-v1.1.1, linux/amd64: **sha256:5abd2ad6fa35befa780fbfbea26e649be96a53c7992e0a7f1b90c83330773206**

Runtime oba imagea izravno nasljeđuje prvi pinned PG16.16 image. Iz VectorChord imagea preuzimaju se samo PG16 vchord.so i control/SQL datoteke, ne njegov PostgreSQL server.

Izvorni arhivi preuzeti su u memoriju radi SHA-256 provjere, bez instalacije na host:

| Arhiv | SHA-256 |
| --- | --- |
| pgvector v0.8.2 | 69f4019389af05dc1c9548deb8628e62878e6e207c03907f2b8af2016472cdaa |
| pg_cron v1.6.7 | d950bc29155f31017567e23a31d268ff672e98276c0e9d062512fb7870351f03 |

[pgvector v0.8.2 source](https://github.com/pgvector/pgvector/tree/v0.8.2), [pg_cron v1.6.7 source](https://github.com/citusdata/pg_cron/tree/v1.6.7), [službeni PostgreSQL Dockerfile](https://github.com/docker-library/postgres/blob/master/16/bookworm/Dockerfile).

Build je multi-stage. Builder traži server-dev točno verzije $PG_VERSION iz osnovnog imagea i libpq-dev iste verzije kao runtime libpq5; pgvector se gradi s OPTFLAGS="" radi prijenosnosti, najviše dva make procesa. Runtime ne izvršava apt upgrade niti nasljeđuje build alate. Default SQL verzija pg_cron upstreama 1.6.7 jest 1.6, u skladu s postojećom ekstenzijom.

Nije potvrđena stvarna build dostupnost točno pinanih APT dependency paketa jer build nije pokrenut. Dockerfile namjerno pada ako ih nema, umjesto da zamijeni ciljnu verziju novijom. Pinani imageovi i arhivi ne znače da su svi tranzitivni build dependency paketi bit-po-bit reproducibilni.

Build sadrži provjere verzije servera, extension control datoteka, odsutnosti PostGIS-a i neželjenih dodataka te ldd dependency provjere. Te provjere još **nisu izvršene**; shell sintaksa RUN naredbi jest provjerena. Funkcionalno učitavanje ekstenzija i healthcheck čekaju odobrenu build/start fazu.

## Izvršene provjere i ključni rezultati

Docker Compose verzija: **v5.0.2**.

```bash
docker manifest inspect postgres:16.16-bookworm
docker manifest inspect ghcr.io/tensorchord/vchord-postgres:pg16-v1.1.1
docker network inspect postgis backend hetzner_net
ss -ltn '( sport = :5433 or sport = :5434 )'
docker compose -f docker-compose.postgres-new.yml config --quiet
docker compose -f docker-compose.postgres-new.yml config --services
docker compose -f docker-compose.postgres-new.yml config --images
docker compose -f docker-compose.postgres-new.yml config --no-env-resolution --no-interpolate
```

- config --quiet: **exit 0**.
- config --services: samo **immich-db** i **postgres**.
- config --images: samo nova dva lokalna image taga iz tablice.
- Sanitizirani config prolazi; environment vrijednosti lozinki nisu ispisane ni zapisane.
- Interno parsiran i stvarni resolved model; provjereno da koristi postojeći password izvor, dvije nove PGDATA putanje, nema host portova, nema init SQL mountova ni postojeće postgis usluge.
- Pregledano 144 postojeća kontejnera uključujući zaustavljene: nema konflikta imena postgres/immich-db, DNSNames/aliases, projekta data-postgres-next ili uporabe novih data mountova.
- Mreže postgis/backend/hetzner_net postoje, driver bridge, scope local.
- Portovi 5433/5434 bez TCP listenera u trenutku provjere; nisu konfigurirani niti rezervirani.
- Oba Dockerfilea: sve RUN naredbe prolaze sh -n.
- Oba data direktorija: prazna, 0700, UID:GID 999:999, gitignore provjeren.
- Protected-file hash usporedba: **sve jednako**.
- Postojeći postgis container ID isti, status running, StartedAt **2026-06-26T21:46:10.776564104Z**, originalni image i mountovi.
- Nema kreiranih novih kontejnera, novih SQL baza, migracija, dumpova, restorea, aplikacijskih env promjena ili preusmjerenih klijenata.

Read-only Python parsiranje korišteno je za model, container/network metapodatke i protected-file hasheve. mkdir/chown operacije odnosile su se isključivo na dvije odobrene nove data putanje. Izmjene datoteka ograničene su na popis s početka dokumenta.

## Finalni Compose sadržaj

```yaml
# Standalone project. Never combine this file with docker-compose.yml.
# Phase 1 prepares configuration only; build/up require separate approval.
name: data-postgres-next

services:
  postgres:
    build:
      context: .
      dockerfile: Dockerfile.postgres
    image: postgres-standard-local:16.16-bookworm-vector0.8.2-cron1.6.7
    platform: linux/amd64
    container_name: postgres
    restart: unless-stopped
    env_file:
      - path: .env
        required: true
    environment:
      # Reuse the existing administrator credentials; no application DB creation.
      POSTGRES_USER: postgres
      POSTGRES_DB: postgres
      PGDATA: /var/lib/postgresql/data
      POSTGRES_INITDB_ARGS: --encoding=UTF8 --locale=en_US.utf8
      POSTGRES_HOST_AUTH_METHOD: scram-sha-256
    command:
      - postgres
      - -c
      - shared_preload_libraries=pg_cron,pg_stat_statements
      - -c
      # Bootstrap DB only. Before a future approved qubit_user restore,
      # change this to qubit_user and restart only this new instance.
      - cron.database_name=postgres
      - -c
      - cron.timezone=GMT
      - -c
      - cron.launch_active_jobs=off
      - -c
      - shared_buffers=3GB
      - -c
      - max_connections=100
      - -c
      - work_mem=4MB
      - -c
      - TimeZone=Europe/Zagreb
    mem_limit: 12g
    shm_size: 1g
    volumes:
      - type: bind
        source: /opt/stacks/data/postgres-standard/data
        target: /var/lib/postgresql/data
        bind:
          create_host_path: false
      - type: bind
        source: /opt/stacks/data/backups
        target: /backups
        bind:
          create_host_path: false
      - type: bind
        source: /srv/qubit/backups
        target: /srv/qubit/backups
        bind:
          create_host_path: false
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d postgres"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
    networks:
      - postgis
      - backend
      - hetzner_net

  immich-db:
    build:
      context: .
      dockerfile: Dockerfile.immich-db
    image: immich-db-local:16.16-bookworm-vector0.8.2-vchord1.1.1
    platform: linux/amd64
    container_name: immich-db
    restart: unless-stopped
    env_file:
      - path: .env
        required: true
    environment:
      POSTGRES_USER: postgres
      POSTGRES_DB: postgres
      PGDATA: /var/lib/postgresql/data
      POSTGRES_INITDB_ARGS: --encoding=UTF8 --locale=en_US.utf8
      POSTGRES_HOST_AUTH_METHOD: scram-sha-256
    command:
      - postgres
      - -c
      - shared_preload_libraries=vchord
      - -c
      - shared_buffers=1GB
      - -c
      - max_connections=100
      - -c
      - work_mem=4MB
      - -c
      - TimeZone=Europe/Zagreb
    mem_limit: 4g
    shm_size: 1g
    volumes:
      - type: bind
        source: /opt/stacks/data/immich-postgres/data
        target: /var/lib/postgresql/data
        bind:
          create_host_path: false
      - type: bind
        source: /opt/stacks/data/backups
        target: /backups
        bind:
          create_host_path: false
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d postgres"]
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 30s
    networks:
      - postgis

networks:
  postgis:
    external: true
    name: postgis
  backend:
    external: true
    name: backend
  hetzner_net:
    external: true
    name: hetzner_net
```

## Finalni standardni Dockerfile

```dockerfile
# syntax=docker/dockerfile:1
# linux/amd64 manifest pinned on 2026-11-14. No existing image is retagged.
FROM postgres:16.16-bookworm@sha256:f45d631d050c2fe068f384ed6c4faac506e9cd7f4da605ce703648e4b0985848 AS extension_builder

# Build against the same PG minor and libpq ABI as the final image.
RUN set -eux; \
    test "$PG_MAJOR" = "16"; \
    postgres --version | grep -E ' 16[.]16([[:space:]]|$)'; \
    libpq_version="$(dpkg-query -W -f='${Version}' libpq5)"; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      build-essential ca-certificates curl \
      "postgresql-server-dev-16=$PG_VERSION" \
      "libpq-dev=$libpq_version"; \
    pg_config --version | grep -E ' 16[.]16([[:space:]]|$)'; \
    rm -rf /var/lib/apt/lists/*

# Fixed upstream source release; fail rather than substitute a newer version.
RUN set -eux; \
    curl --fail --location --retry 3 \
      https://codeload.github.com/pgvector/pgvector/tar.gz/refs/tags/v0.8.2 \
      -o /tmp/vector.tar.gz; \
    echo "69f4019389af05dc1c9548deb8628e62878e6e207c03907f2b8af2016472cdaa  /tmp/vector.tar.gz" | sha256sum -c -; \
    mkdir /tmp/vector; \
    tar -xzf /tmp/vector.tar.gz --strip-components=1 -C /tmp/vector; \
    make -C /tmp/vector -j2 OPTFLAGS="" with_llvm=no PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config; \
    make -C /tmp/vector install DESTDIR=/out OPTFLAGS="" with_llvm=no PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config

# pg_cron upstream v1.6.7 exposes SQL extension version 1.6.
RUN set -eux; \
    curl --fail --location --retry 3 \
      https://codeload.github.com/citusdata/pg_cron/tar.gz/refs/tags/v1.6.7 \
      -o /tmp/cron.tar.gz; \
    echo "d950bc29155f31017567e23a31d268ff672e98276c0e9d062512fb7870351f03  /tmp/cron.tar.gz" | sha256sum -c -; \
    mkdir /tmp/cron; \
    tar -xzf /tmp/cron.tar.gz --strip-components=1 -C /tmp/cron; \
    make -C /tmp/cron -j2 with_llvm=no PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config; \
    make -C /tmp/cron install DESTDIR=/out with_llvm=no PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config

FROM postgres:16.16-bookworm@sha256:f45d631d050c2fe068f384ed6c4faac506e9cd7f4da605ce703648e4b0985848

COPY --from=extension_builder /out/usr/lib/postgresql/16/lib/vector.so /usr/lib/postgresql/16/lib/vector.so
COPY --from=extension_builder /out/usr/lib/postgresql/16/lib/pg_cron.so /usr/lib/postgresql/16/lib/pg_cron.so
COPY --from=extension_builder /out/usr/share/postgresql/16/extension/ /usr/share/postgresql/16/extension/

RUN set -eux; \
    postgres --version | grep -E ' 16[.]16([[:space:]]|$)'; \
    grep -Eq "^default_version = '0[.]8[.]2'$" /usr/share/postgresql/16/extension/vector.control; \
    grep -Eq "^default_version = '1[.]6'$" /usr/share/postgresql/16/extension/pg_cron.control; \
    for ext in pg_stat_statements pgcrypto pg_trgm uuid-ossp pageinspect fuzzystrmatch; do \
      test -f "/usr/share/postgresql/16/extension/$ext.control"; \
    done; \
    test ! -e /usr/share/postgresql/16/extension/postgis.control; \
    test ! -e /usr/share/postgresql/16/extension/vchord.control; \
    ldd /usr/lib/postgresql/16/lib/vector.so > /tmp/vector.ldd; \
    ! grep -q 'not found' /tmp/vector.ldd; \
    ldd /usr/lib/postgresql/16/lib/pg_cron.so > /tmp/cron.ldd; \
    ! grep -q 'not found' /tmp/cron.ldd; \
    rm /tmp/vector.ldd /tmp/cron.ldd

LABEL org.opencontainers.image.title="Standard PostgreSQL 16.16 with pgvector 0.8.2 and pg_cron 1.6.7"
```

## Finalni Immich Dockerfile

```dockerfile
# syntax=docker/dockerfile:1
# Extract only PG16 VectorChord artifacts; do not inherit its PostgreSQL version.
FROM ghcr.io/tensorchord/vchord-postgres:pg16-v1.1.1@sha256:5abd2ad6fa35befa780fbfbea26e649be96a53c7992e0a7f1b90c83330773206 AS vchord_ext

FROM postgres:16.16-bookworm@sha256:f45d631d050c2fe068f384ed6c4faac506e9cd7f4da605ce703648e4b0985848 AS extension_builder

# Build against the same PG minor and libpq ABI as the final image.
RUN set -eux; \
    test "$PG_MAJOR" = "16"; \
    postgres --version | grep -E ' 16[.]16([[:space:]]|$)'; \
    libpq_version="$(dpkg-query -W -f='${Version}' libpq5)"; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      build-essential ca-certificates curl \
      "postgresql-server-dev-16=$PG_VERSION" \
      "libpq-dev=$libpq_version"; \
    pg_config --version | grep -E ' 16[.]16([[:space:]]|$)'; \
    rm -rf /var/lib/apt/lists/*

# Fixed upstream source release; fail rather than substitute a newer version.
RUN set -eux; \
    curl --fail --location --retry 3 \
      https://codeload.github.com/pgvector/pgvector/tar.gz/refs/tags/v0.8.2 \
      -o /tmp/vector.tar.gz; \
    echo "69f4019389af05dc1c9548deb8628e62878e6e207c03907f2b8af2016472cdaa  /tmp/vector.tar.gz" | sha256sum -c -; \
    mkdir /tmp/vector; \
    tar -xzf /tmp/vector.tar.gz --strip-components=1 -C /tmp/vector; \
    make -C /tmp/vector -j2 OPTFLAGS="" with_llvm=no PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config; \
    make -C /tmp/vector install DESTDIR=/out OPTFLAGS="" with_llvm=no PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config

FROM postgres:16.16-bookworm@sha256:f45d631d050c2fe068f384ed6c4faac506e9cd7f4da605ce703648e4b0985848

COPY --from=extension_builder /out/usr/lib/postgresql/16/lib/vector.so /usr/lib/postgresql/16/lib/vector.so
COPY --from=extension_builder /out/usr/share/postgresql/16/extension/ /usr/share/postgresql/16/extension/
COPY --from=vchord_ext /usr/lib/postgresql/16/lib/vchord.so /usr/lib/postgresql/16/lib/vchord.so
COPY --from=vchord_ext /usr/share/postgresql/16/extension/vchord.control /usr/share/postgresql/16/extension/vchord.control
COPY --from=vchord_ext /usr/share/postgresql/16/extension/vchord--*.sql /usr/share/postgresql/16/extension/

RUN set -eux; \
    postgres --version | grep -E ' 16[.]16([[:space:]]|$)'; \
    grep -Eq "^default_version = '0[.]8[.]2'$" /usr/share/postgresql/16/extension/vector.control; \
    grep -Eq "^default_version[[:space:]]*=[[:space:]]*'1[.]1[.]1'$" /usr/share/postgresql/16/extension/vchord.control; \
    for ext in cube earthdistance pg_trgm unaccent uuid-ossp; do \
      test -f "/usr/share/postgresql/16/extension/$ext.control"; \
    done; \
    test ! -e /usr/share/postgresql/16/extension/postgis.control; \
    test ! -e /usr/share/postgresql/16/extension/pg_cron.control; \
    ldd /usr/lib/postgresql/16/lib/vector.so > /tmp/vector.ldd; \
    ! grep -q 'not found' /tmp/vector.ldd; \
    ldd /usr/lib/postgresql/16/lib/vchord.so > /tmp/vchord.ldd; \
    ! grep -q 'not found' /tmp/vchord.ldd; \
    rm /tmp/vector.ldd /tmp/vchord.ldd

LABEL org.opencontainers.image.title="Immich PostgreSQL 16.16 with pgvector 0.8.2 and VectorChord 1.1.1"
```

## Granica odobrenja

Ovdje se staje. Nisu pokrenuti docker compose build, create, up ili run; nije povučena niti izmijenjena produkcijska slika. Za buduće operacije koristiti isključivo zasebnu datoteku docker-compose.postgres-new.yml; nikad je kombinirati s postojećim docker-compose.yml niti pokretati cijeli postojeći stack radi ovih servisa.

Novo izričito odobrenje potrebno je prije build/start postupka. Čak ni odobrenje starta praznih clustera neće samo po sebi odobriti restore, kreiranje produkcijskih baza ili promjenu aplikacijskih endpointa.
