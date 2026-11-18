# 03 — Migracijska matrica za svih 31 bazu

Status: prijedlog 14.11.2026.; **nijedna baza nije preseljena**. Sadašnje odredište svih redaka je postojeći kontejner postgis. Ciljevi u tablici nisu odobrenje za provedbu.

UVJETNO znači da najprije treba zatvoriti navedene gateove. ZADRŽATI znači da se baza zasad ne seli iz PostGIS-a zbog potvrđenog testnog zahtjeva ili nerazjašnjene namjene. Ni redak bez te oznake nije oslobođen backup/restore, single-writer i app-validation preduvjeta.

## Inventar i predloženi servis

| Baza | Vlasnik | MiB | Instalirane ekstenzije osim plpgsql | Predloženi servis |
| --- | --- | --- | --- | --- |
| chatwoot | chatwoot | 21.08 | vector 0.8.2; pg_trgm 1.6; pgcrypto 1.3; pg_stat_statements 1.10 | postgres |
| crowdsec | crowdsec | 38321.71 | samo plpgsql | postgres |
| farma_db | farma_app | 39.31 | fuzzystrmatch 1.2; postgis 3.4.3; postgis_tiger_geocoder 3.4.3; postgis_topology 3.4.3 | postgis |
| finestar_erp_db | postgis | 133.13 | postgis 3.6.2 | postgres — UVJETNO |
| fiskal | fiskal | 39.01 | postgis 3.6.2 | postgres — UVJETNO |
| fiskal_f1_pts_smoke | fiskal | 9.22 | pgcrypto 1.3 | postgres |
| headscale | headscale | 9.08 | uuid-ossp 1.1 | postgres — UVJETNO |
| immich | immich | 1191.79 | postgis 3.6.2; cube 1.5; earthdistance 1.2; pg_trgm 1.6; unaccent 1.1; uuid-ossp 1.1; vector 0.8.2; vchord 1.1.1 | immich-db — UVJETNO |
| mailblocklist | mailblocklist | 36.58 | samo plpgsql | postgres |
| minidepo | postgres | 18.11 | postgis 3.6.2 | postgis |
| mozzart_db | postgis | 203.37 | postgis 3.4.3 | postgres — UVJETNO |
| nextcloud | nextcloud | 131.97 | samo plpgsql | postgres |
| omnimsgio | omnimsgio | 8.27 | samo plpgsql | postgres |
| parkschloss | parkschloss | 7.63 | samo plpgsql | postgres |
| postgres | postgres | 67.89 | postgis 3.4.3; postgis_topology 3.4.3; fuzzystrmatch 1.2; postgis_tiger_geocoder 3.4.3 | postgres — UVJETNO |
| powerdns | qubit | 7.98 | samo plpgsql | postgres — UVJETNO |
| predix | predix | 134.12 | postgis 3.6.2 | postgres — UVJETNO |
| qubit_user | qubit | 22.49 | pg_cron 1.6 | postgres — UVJETNO |
| racunai_intermediary | postgis | 102.63 | samo plpgsql | postgres |
| roamkit | roamkit | 18.11 | samo plpgsql | postgres — UVJETNO |
| roamkit_production | roamkit | 17.08 | samo plpgsql | postgres — UVJETNO |
| snappymail | snappymail | 7.85 | samo plpgsql | postgres — UVJETNO |
| stay_platform_db | stay | 48.66 | pageinspect 1.12 | postgres |
| stay_platform_test_db | stay | 22.97 | postgis 3.6.2 | postgis — ZADRŽATI |
| superclean_db | superclean | 17.41 | postgis 3.6.2 | postgres — UVJETNO |
| tablio_platform_db | tablio | 10.12 | samo plpgsql | postgres |
| test_finestar_erp_db | postgis | 33.16 | postgis 3.6.2 | postgis — ZADRŽATI |
| test_predix | predix | 13.65 | samo plpgsql | postgres — UVJETNO |
| test_qubit_user | qubit | 12.49 | samo plpgsql | postgres — UVJETNO |
| test_stay_platform_db | stay | 13.92 | samo plpgsql | postgres — UVJETNO |
| test_stay_platform_test_db | stay | 24.42 | postgis 3.6.2 | postgis — ZADRŽATI |

## Ovisnosti, potrošači i promjene

| Baza | Ovisnost / nalaz | Potrošači | Potrebne promjene | Rizik / val |
| --- | --- | --- | --- | --- |
| chatwoot | vector 0.8.2; 3 IVFFlat; pg_trgm/pgcrypto/pg_stat_statements | rails, sidekiq, chatwoot-backup | POSTGRES_HOST; PGHOST backupa; provjera preload pg_stat_statements | R03,R10; vector test; C |
| crowdsec | bez dodatnih ekstenzija; 37,42 GiB | crowdsec-django/importer/scheduler i povezani procesi | POSTGRES_HOST na svim writerima i jobovima; rekonfigurirati backup | R04,R05,R09; najveći downtime; H |
| farma_db | 9 aplikacijskih geometry stupaca; pogledi/funkcije/default; SQL 3.4.3/library 3.6.2 | farma_backend; konfiguracija farma_frontend | postojeći endpoint ostaje; future PostGIS normalizacija i SRID test | R02,R12; HOLD upgrade; J |
| finestar_erp_db | PostGIS 3.6.2 bez app catalog kandidata; Django GIS backend | finestar_erp, celery worker/beat, racunai_mps | ENGINE na obični PostgreSQL tek uz probu; DATABASE_HOST i GATEWAY_DATABASE_URL zasebno | R07; dotad ostaje postgis; D |
| fiskal | PostGIS 3.6.2 bez app catalog kandidata; bootstrap skripta | fiskal_api, fiskal_worker, fiskal_mps | DATABASE_HOST; bootstrap bez PostGIS-a nakon probe | R06,R20; integracije bez slanja računa; D |
| fiskal_f1_pts_smoke | pgcrypto 1.3; ime smoke ne znači neaktivnost | f1-pts-api | DATABASE_HOST i CI/test konfiguracija | R06; potvrditi vlasnika smokea; D |
| headscale | uuid-ossp 1.1; libc mismatch | headscale; qubit koristi HEADSCALE_DB_* | DATABASE_HOST/config i HEADSCALE_DB_HOST; provjeriti config prioritet | R05,R06; sačuvati operatorov pristup; F |
| immich | vchord 1.1.1/vector 0.8.2; 2 vchordrq; contrib; PostGIS bez app kandidata | immich_server, media_operations, nextcloud_immich_bridge; ML env pregledati | DB_HOSTNAME na stvarnim potrošačima; ne mijenjati verziju aplikacije | R03,R10,R13,R14; medijski backup; G |
| mailblocklist | bez dodatnih ekstenzija | mailserver-mailadmin, mailindex-sync, mail-mcp; provjeriti mailserver host config | DATABASE_URL host; mailserver config; backup | R06; utjecaj na mail filtriranje; F |
| minidepo | 5 geometry stupaca SRID 4326; 5 GiST; PostGIS 3.6.2 | minidepo_web | postojeći DB_HOST ostaje; kasniji upgrade u zasebnom prozoru | R02,R12; owner postgres; J |
| mozzart_db | PostGIS SQL 3.4.3, bez app kandidata; libc mismatch | mozzart, celery worker/beat, print-bridge | DATABASE_URL host; potvrditi SQL bootstrap i driver | R05,R06; test print bez stvarnog slanja; D |
| nextcloud | bez dodatnih ekstenzija | nextcloud, nextcloud-cron; trajni config.php provjeriti | POSTGRES_HOST i učinkoviti Nextcloud dbhost; backup | R06; env ne jamči izmjenu već upisanog configa; F |
| omnimsgio | bez dodatnih ekstenzija | api, gateway, worker; web ima DB env | DATABASE_URL u production Compose env; provjeriti web potrebu | R06; zaustaviti sve writere vala; B |
| parkschloss | bez dodatnih ekstenzija | parkschloss-api | DATABASE_URL; provjeriti zasebni CMS ako postoji | R06; B |
| postgres | Uzorita app public shema; tiger/topology extension config; Stay RO alias | uzorita celery/booking-browser/tailscale env, Stay primary/legacy potrošači | DB_HOST za Uzoritu; UZORITA_DB_HOST u Stay; sačuvati stay_uzorita_ro ACL | R02,R08; ne mijenjati u praznu admin bazu; E |
| powerdns | bez dodatnih ekstenzija; owner qubit; grants powerdns; libc mismatch | powerdns; stvarni gpgsql config izvan DB env tablice | gpgsql host u konfiguraciji, odvojeno od Tailscale endpointa | R05,R06; DNS kontinuitet; F |
| predix | PostGIS 3.6.2 bez app kandidata; legacy ST_X/ST_Y migracija već primijenjena | predix-api, celery worker/beat, predix-sync | POSTGRES_HOST; fresh-install legacy migracije provjeriti | R06,R20; D |
| qubit_user | pg_cron 1.6; sedam active jobova, scheduler mismatch; libc mismatch | qubit; povezani log produceri, host/remote jobovi | DB_HOST/POSTGRES_HOST; cron.database_name=qubit_user; isti export mount | R01,R05,R11,R12; aktivacija zasebno; F |
| racunai_intermediary | bez dodatnih ekstenzija; vezan uz ERP gateway | ERP GATEWAY_DATABASE_URL i racunai_mps | GATEWAY_DATABASE_URL host; uskladiti val s finestar_erp_db | R06; povezani ERP snapshot; D |
| roamkit | bez dodatnih ekstenzija; staging | roamkit-api/celery/beat staging; web env | POSTGRES_HOST u staging env; driver/runtime izvor potvrditi | R06; pilot tek uz potvrdu vlasnika; B |
| roamkit_production | bez dodatnih ekstenzija | roamkit-api/celery/beat production; web env | POSTGRES_HOST u runtime.env, bez diranja staginga | R06; nakon staging probe; zaseban prozor B |
| snappymail | bez dodatnih ekstenzija; libc mismatch | snappymail; wrapper i trajna aplikacijska konfiguracija | SNAPPYMAIL_DB_HOST; provjeriti wrapper/config prioritet | R05,R06; F |
| stay_platform_db | pageinspect 1.12; obični PG backend; dodatni Uzorita alias | stay_django, celery worker/beat; booking env | DB_HOST i zaseban UZORITA_DB_HOST; ne pokretati prod migrate probe | R08,R20; testne baze zasebno; E |
| stay_platform_test_db | PostGIS 3.6.2; eksplicitni testni workflow | Stay django-run i CI | bez promjene dok se ne odobri PostgreSQL test policy; TEST_DB_HOST po potrebi | R07,R20; nema dokaza geometrijske app upotrebe; I |
| superclean_db | PostGIS 3.6.2 bez app kandidata; Django GIS backend | superclean_django; web/admin env | ENGINE promjena i bootstrap; DB_HOST u .env.prod precedence | R07; dotad ostaje postgis; D |
| tablio_platform_db | bez dodatnih ekstenzija; obični PG runtime backend | tablio_django, celery worker; CI test konfiguracija | DB_HOST; test settings provjeriti zasebno | R06,R07; B |
| test_finestar_erp_db | PostGIS 3.6.2; ERP AGENTS/test setup zahtijeva ekstenziju | ERP CI/test runner --keepdb | bez premještanja dok se ne odobri backend i test bootstrap promjena | R07,R20; I |
| test_predix | bez dodatnih ekstenzija | vlasnik predix; CI/local test klijenti nisu potvrđeni | test endpoint u env/CI, ne zaključivati iz imena baze | R06; A |
| test_qubit_user | bez dodatnih ekstenzija; libc mismatch | vlasnik qubit; test klijenti nisu potvrđeni | test endpoint u env/CI; bez uvoza produkcijskih cron jobova | R05,R06; A |
| test_stay_platform_db | bez dodatnih ekstenzija; namjena razlučiti od druga dva test DB | vlasnik stay; CI/local klijenti nepotvrđeni | TEST_DB_NAME/host mapiranje; potvrditi koju bazu koristi koji runner | R06,R07; A |
| test_stay_platform_test_db | PostGIS 3.6.2; mogući Django prefiks test_ za postojeći test DB | Stay test runner; točna namjena nepotvrđena | bez premještanja do razjašnjenja test naming/policy | R06,R07; I |

## Kako čitati odluku

- Farma i Minidepo imaju potvrđene aplikacijske prostorne strukture i ostaju u PostGIS servisu.
- Immich je kandidat za zaseban servis s identičnim vector/vchord verzijama, uz kontrolirano izostavljanje potvrđeno nekorištenih PostGIS extension stavki na restore kopiji.
- ERP i Superclean nemaju nađene prostorne katalog objekte, ali njihov potvrđeni Django PostGIS backend utječe na schema lifecycle. Bez aplikacijske promjene ostaju na postgis.
- Stay i Tablio produkcija koriste obični PostgreSQL backend. Njihova testna politika nije isto što i produkcijska prostorna ovisnost; relevantni testni workflow ostaje sačuvan.
- Predix ima primijenjenu legacy prostornu migraciju. Kopiranje postojeće sheme i izgradnja prazne sheme moraju se testirati odvojeno.
- Svi netemplate redci s instaliranim PostGIS-om osim Farma/Minidepo imaju nula preostalih aplikacijskih dependency kandidata nakon parent/internal klasifikacije. To nije dokaz odsutnosti runtime SQL-a.
- postgres je aplikacijska baza: prenositi public podatke, owner/ACL i Uzorita/Stay veze; tiger/topology config sadržaj se ne odbacuje bez pregleda.

Trenutačno preporučena razdioba nakon zatvaranja uvjeta: **25 baza prema postgres, 5 prema postgis (2 prostorne + 3 zadržane testne), 1 prema immich-db**. Broj 5 nije tvrdnja da svih pet koristi aplikacijske geometrije. Ako se odobri i dokaže uklanjanje PostGIS testne politike, te tri baze mogu kasnije u postgres; prije toga cilj 28 + 2 + 1 nije odobren.

ERP/Superclean do zatvaranja svojih uvjeta povećavaju privremeni broj baza na postojećem postgis servisu. Konačna matrica zato mora biti ažurirana rezultatima probe, ne samo željenom arhitekturom.

## Template baze izvan 31 retka

| Template | Vlasnik | Plan |
| --- | --- | --- |
| template0 | postgres | nije dopuštena veza; ostaviti izvor, na targetu koristiti svježi template0 |
| template1 | postgres | pregledan, samo plpgsql; ne kopirati fizički |
| template_postgis | postgres | PostGIS/tiger/topology 3.4.3; mismatch; privatno arhivirati i provjeriti korisničke dorade; zadržati izvor dok korisnik ne odluči |

Ne brojiti template_postgis kao 32. aplikacijsku bazu niti ga ignorirati u backup inventaru.

## Privilegije i nazivi

DB nazivi i vlasnici ostaju kao u prvom dijelu tablice, osim zasebno odobrene promjene. Na svaki target prenijeti sve potrebne vlasnike objekata i grantee role, ne samo datdba. Postojeći roles/ACL detalji u [inventaru](01-inventory.md) uključuju stay_uzorita_ro i grants powerdns roli. Ne stvarati istu superuser rolu u svakom clusteru bez eksplicitne potrebe.

Naziv postgis pojavljuje se i kao servis, rola i network. SQL korisnik postgis može postojati na standardnom postgres servisu; sam naziv role nije prostorna ovisnost. Promjena hosta ne podrazumijeva promjenu korisnika, lozinke ili naziva baze.
