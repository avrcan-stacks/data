# 02 — Ciljna arhitektura i verzije

Status: prijedlog za odobrenje, 14.11.2026. Implementacija nije pokrenuta. Dokazi su u [inventaru](01-inventory.md), uvjeti u [registru odluka](06-risks-and-decisions.md).

## Preporuka

Tri trajna servisa razuman su kompromis: **postgres**, **postgis**, **immich-db**. Razdvajaju VectorChord/Immich od ostalih nadogradnji i prostorne biblioteke od standardnih baza. Sva tri i dalje dijele host, disk i Docker daemon; ovo nije HA ni zaštita od gubitka hosta.

| Servis | Odgovornost | Ekstenzije i preload |
| --- | --- | --- |
| postgres | standardne baze; qubit_user; Chatwoot | pg_cron, vector; contrib ekstenzije prema matrici; preload pg_cron,pg_stat_statements |
| postgis | farma_db, minidepo; privremeno baze s neriješenim PostGIS backend/test zahtjevom | PostGIS, topology/tiger gdje su potrebni; bez vchord i pg_cron nakon dovršene razdiobe |
| immich-db | samo immich | vector 0.8.2, vchord 1.1.1; cube, earthdistance, pg_trgm, unaccent, uuid-ossp; preload vchord |

`postgres` je image izveden iz službenog PostgreSQL imagea s nužnim paketima; nije neizmijenjeni `postgres` image jer pg_cron i pgvector nisu njegovi standardni binarni dodaci. PostGIS se ne instalira u taj image. Ekstenzije aktivirati samo u bazama koje ih trebaju.

`pg_stat_statements` je instaliran u Chatwootu, ali nije u trenutačnom preloadu. Predloženo uključivanje u novom standardnom servisu eksplicitna je operativna odluka; zabilježiti baseline i overhead u probi. Ne predstavljati postojeću ekstenziju kao funkcionalno praćenje SQL upita.

## Verzijsku nadogradnju razdvojiti od funkcionalnog premještanja

| Sloj | Potvrđeno sada | Predloženi prvi cilj | Naknadna nadogradnja |
| --- | --- | --- | --- |
| PostgreSQL | 16.13 | 16.16, Debian bookworm/glibc baseline | 18.7 po servisu, nakon zasebnih testova drivera i ekstenzija |
| PostGIS | SQL 3.4.3 ili 3.6.2; biblioteka 3.6.2 | 3.6.4, SQL i biblioteke usklađeni u probnoj kopiji | 3.7.0 zasebno |
| pg_cron | SQL 1.6; paket 1.6.7 | SQL 1.6 i kompatibilan PG16 paket, početno 1.6.7 ako je dostupan i prođe pregled aktualnih izdanja | patch nadogradnje odvojeno, uz provjeru startup/config zahtjeva |
| pgvector | 0.8.2 | 0.8.2 radi reprodukcije postojećih vektorskih indeksa | 0.8.7 kao zaseban testirani zahvat |
| VectorChord | 1.1.1 | 1.1.1 za PG16 | ne nadograđivati istodobno s preseljenjem |
| Immich | v3.3.5 | ista aplikacijska verzija/revision | odvojeni upgrade |
| Chatwoot | v4.18.0 | ista aplikacijska verzija | odvojeni upgrade |

PostgreSQL službena objava od 12.11.2026. navodi 16.16 i 18.7; verzija 16 ostaje podržana do studenoga 2028. Na dan provjere versioning tablica u pretraživaču kasnila je za novijom objavom, zato prvenstvo ima [objava izdanja](https://www.postgresql.org/about/news/postgresql-187-1712-1616-1520-1425-and-19-rc-2-released-3442/), uz [politiku podrške](https://www.postgresql.org/support/versioning/).

PostGIS službeni popis navodi 3.6.4 i 3.7.0. Odabir 3.6.4 smanjuje promjenu u odnosu na već prisutne 3.6 biblioteke. Ne tvrdi se da je pronađen gotov image s točno tim kombinacijama: digest, binarni paketi, arhitektura i update putanja moraju se potvrditi prije builda/probe. Ako to nije moguće, zaustaviti val i dopuniti odluku, bez zamjene plutajućim latest tagom. [Izdanja](https://postgis.net/development/source_code/), [politika verzija](https://postgis.net/development/versions_eol/), [nadogradnje](https://postgis.net/docs/en/postgis_administration.html).

PostGIS 3.4.3 SQL / 3.6.2 library nesklad ne popravljati na izvoru tijekom ove faze. Restore i normalizaciju izvesti na izoliranoj kopiji. U farma_db postoje C funkcije bez extension članstva; obični restore može ih pokušati ponovno kreirati uz postojeće definicije. Potreban je provjeren PostGIS hard-upgrade/restore postupak i pregled TOC-a. Ne uklanjati ih po prefiksu ST_.

## Immich kompatibilnost

U stvarnom v3.3.5 runtimeu pročitani su rasponi: PostgreSQL >=14.0.0, VectorChord >=0.3 <2 i pgvector >=0.5 <1. Isti rasponi nalaze se u [kodu točne verzije](https://raw.githubusercontent.com/immich-app/immich/v3.3.5/server/src/constants.ts). To je provjera koju aplikacija radi, ne jamstvo da je svaka novija kombinacija testirana.

Aktualna [Immich dokumentacija za postojeći PostgreSQL](https://docs.immich.app/administration/postgres-standalone/) navodi uži praktični raspon pgvector >=0.7 <0.9 i PostgreSQL >=14 <20. Postojeća kombinacija PG16 / vector 0.8.2 / vchord 1.1.1 zadovoljava oba skupa uvjeta.

Predložiti uski reproducibilni image na postgres:16.16-bookworm s vector 0.8.2 i službenim vchord 1.1.1 artefaktom za PG16. Ako se bira službeni Immich/TensorChord image, prvo provjeriti stvarne verzije svih binarnih komponenti i digest; ne prijeći na često prikazivani stariji vchord 0.4/0.5 image jer bi to bio downgrade. [VectorChord instalacija](https://docs.vectorchord.ai/vectorchord/getting-started/installation.html).

Immich na startupu može kreirati/nadograditi ekstenzije i shemu. [Kod v3.3.5](https://raw.githubusercontent.com/immich-app/immich/v3.3.5/server/src/services/database.service.ts) zato zahtijeva da aplikacijska restore proba bude izolirana od produkcijske baze, maila, webhookova, redova zadataka i medija za pisanje.

## Storage, mreže i endpointi

| Servis | Predloženi host data direktorij | PG16 mount | Klijentski endpoint |
| --- | --- | --- | --- |
| postojeći postgis | /opt/stacks/data/postgres/data | /var/lib/postgresql/data | postgis:5432; postojeći localhost/Tailscale 5432 |
| novi postgres | /opt/stacks/data/postgres-standard/data | /var/lib/postgresql/data | postgres:5432 |
| novi immich-db | /opt/stacks/data/immich-postgres/data | /var/lib/postgresql/data | immich-db:5432 |

Novi direktoriji nisu stvoreni. Nikad ne montirati izvorni direktorij u drugi server. Ime kontejnera `postgis` ostaje postojeće u skladu s AGENTS.md. Buduća zamjena njegova imagea zaseban je zadnji val nakon backup/restore probe; dotad postojeći servis ostaje online i ne mijenja se.

Novi postgres treba mreže `postgis`, `backend`, `hetzner_net` zbog postojećih potrošača. Novi immich-db treba `postgis` mrežu za server i helpere; stvarne članove potvrditi prije cutovera. Ne preuzimati tuđi alias postgis niti globalno mijenjati DNS. Mrežna segmentacija može se pooštriti naknadno bez spajanja s podatkovnim prijelazom.

Novi servisi nemaju host port po defaultu. Za operatorove SSH tunele eventualno rezervirati 127.0.0.1:5433 i :5434; pri analizi `ss` nije pokazao listenere na tim portovima, ali provjeru ponoviti prije implementacije. Postojeći Tailscale 5432 ostaje vezan na PostGIS. Za udaljene migrirane korisnike treba odobriti novi tunel/endpoint i provjeriti ACL; nije dopušteno preusmjeriti sve korisnike postojećeg tunela na standardni servis.

Backupovi: zajednički /backups mount s odvojenim poddirektorijem za svaki cluster; qubit export funkcije dodatno trebaju isti /srv/qubit/backups mount i UNIX write dozvole. Backup artefakti, globals, env i credentials ostaju izvan gita. Korištenje istog diska ne zamjenjuje off-host kopiju.

Za PG18 službeni image koristi PGDATA `/var/lib/postgresql/18/docker` i volume `/var/lib/postgresql`. To je konfiguracija budućeg zasebnog PG18 clustera, ne reinterpretacija PG16 data direktorija. [Službeni Dockerfile](https://github.com/docker-library/postgres/blob/master/18/bookworm/Dockerfile).

## Resursi i mogućnost drukčije podjele

Početni proračun za probu, ne izmjerena produkcijska potreba: postgres memory cap 12 GiB, shared_buffers 3 GiB; immich-db 4 GiB i 1 GiB; nakon kasnije zamjene postgis 4 GiB i 1 GiB. Novi shm_size 1 GiB, max_connections 100, work_mem konzervativno 4 MiB. Restore najviše dva workera istodobno; provjeriti latenciju hosta, WAL i disk prije povećanja. Ove vrijednosti potvrditi probom i sumom stvarnih aplikacijskih poolova; postojeći servis sada ostaje neograničen i ne mijenja se.

Dva servisa ostavila bi Immichov VectorChord vezan za nadogradnje ostalih baza. Četvrti servis za pg_cron trenutačno nema opravdanje: sedam lokalnih zadataka koristi qubit_user podatke, a instalacija pg_cron je mala i pregledna. Četvrti servis za CrowdSec mogao bi dati operativnu izolaciju jer zauzima 94% prostora, ali nema mjerenja CPU/IO zahtjeva koje to opravdava; ne dodavati ga po veličini samoj. Chatwoot se može izdvojiti kasnije ako njegova verzijska politika postane konfliktna.

Tri servisa smanjuju opseg DB upgrade zastoja; pojedinačna glavna PostgreSQL nadogradnja i dalje zahtijeva planirani prijelaz aplikacija. RPO, dopušteni downtime i rollback prozor moraju biti odobreni prije provedbe.
