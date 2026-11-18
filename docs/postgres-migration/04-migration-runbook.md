# 04 — Runbook migracije

Status: **plan, nije izvršen**. Sve radnje koje stvaraju dump, restore instancu, mijenjaju konfiguraciju ili podatke pripadaju budućoj odobrenoj fazi. Ne pokretati produkcijski Compose, ALTER/CREATE/DROP, REINDEX, reload, restart ni aplikacijske migracije na temelju ovog dokumenta bez izričitog odobrenja.

## Pristup i sigurnosne granice

Migracija ide po bazama ili aplikacijski povezanim skupinama. Izvorni kontejner postgis i /opt/stacks/data/postgres/data ostaju netaknuti tijekom pripreme i prijenosa ostalih baza. Nema kopiranja živog PGDATA i nema montiranja istog direktorija u dva servera. Odredišta su novi direktoriji; čak i probne baze dobivaju zaseban Compose projekt i nazive, bez produkcijskih aliasa i portova.

Tijekom budućeg cutovera kratko se zaustavljaju/prigušuju samo writeri predmetnog vala, uz zasebno odobrenje tog downtimea. Trenutačna analiza ne zaustavlja ništa. Restart postojećeg postgis servisa nije preduvjet za migraciju standardnih baza ili Immicha.

## 0. Gate prije pripreme targeta

1. Korisnik odobrava opseg implementacijske faze, prozor, RPO/RTO i valove. Zatvoriti relevantne stavke iz 06-risks-and-decisions.md.
2. Ponoviti inventar DB/roles/extensions/connections i provjeriti da se broj baza i app verzije nisu promijenili.
3. Zaključati PG16.16 bookworm image digest, paketne verzije i vchord PG16 ABI. Provjeriti release notes za minor update. Ne koristiti latest.
4. Provjeriti slobodne Docker aliase, sve dostupne mreže, host portove ako su potrebni i per-app connection poolove.
5. Izraditi privatni manifest svih potrošača: web, API, Celery worker/beat, cron, CI, test runneri, backup kontejnere, importeri, bridgeovi, host procesi i udaljeni Tailscale klijenti.
6. Potvrditi da app startup neće neočekivano migrirati izvor. Posebno Stay web startup izvršava migrate; docker compose run django nije dopušten kao one-off u tome stacku. U probi koristiti njegov django-run profil i sandbox konfiguraciju.
7. Izračunati vršni prostor i kapacitet bez brisanja starih podataka. Ako gate ne prolazi, zadržati HOLD i osigurati zaseban prostor.

## 1. Backup i restore proba prije produkcijskog prijelaza

- Po bazi izraditi novi custom-format pg_dump kroz kontejner postgis i admin rolu; konzistentan pojedinačni DB snapshot. Arhivu zapisati na host /opt/stacks/data/backups/MIGRATION_ID/DB.dump, bez lozinki na komandnoj liniji. Provjeriti exit code, veličinu i SHA-256.
- Privatno spremiti globals/role definicije i credential hashove, HBA, relevantne PostgreSQL postavke i izvorne image/package identifikatore. Globals s hashovima nikad ne prikazivati niti spremati u git. Sanitizirani role inventar nije backup autentikacije.
- Za baze povezane aplikacijskim transakcijama/importima finalni dumpovi moraju biti uz zajednički write-freeze; pg_dump različitih baza sam ne daje zajednički snapshot.
- Kopirati dumpove i privatne metapodatke izvan hosta, provjeriti hash na drugoj lokaciji.
- Izraditi izoliran restore sandbox na drugom filesystemu/hostu ako space gate to zahtijeva. Bez produkcijskog network aliasa, crona, redova zadataka, emaila/webhookova i writable produkcijskih medija.
- Prazne target baze osnovati iz čistog template0 odgovarajućeg locale/encodinga. Ne klonirati stari template_postgis niti koristiti postojeću target admin bazu s nenadziranim sadržajem.
- Prvo obnoviti potrebne role i vlasništvo/ACL prema mapiranju; instalirati/aktivirati kompatibilne ekstenzije; zatim schema/data/indexes/constraints. Restore mora stati na prvoj neočekivanoj grešci i imati zabilježen exit code.
- Primjer budućih alata: pg_dump -Fc; pg_restore --list za pregled; pg_restore --exit-on-error --jobs=2 za target restore iz regularne datoteke. Ne kombinirati parallel restore i --single-transaction. Ne koristiti --clean prema izvoru niti sve greške proglasiti očekivanima.
- Nakon target restorea izvršiti statističku obradu i validacije iz 05-validation-rollback.md. Takve promjene target baze također zahtijevaju odobrenu fazu.
- Izmjeriti odvojeno dump, prijenos, restore data, izgradnju indeksa, provjeru i preusmjeravanje aplikacije. Probu ponoviti samo ako se mijenjaju relevantni parametri ili nastane greška.
- Privremena target proba ne smije ostati drugi aktivni writer. Kasnije uklanjanje probnih podataka predviđa zasebno eksplicitno odobrenje.

PostgreSQL [dump postupak](https://www.postgresql.org/docs/16/backup-dump.html) zahtijeva odvojeno očuvanje cluster-wide rola; [pg_restore](https://www.postgresql.org/docs/16/app-pgrestore.html) podržava TOC izbor i prekid na grešci. Čitljiv TOC i gzip integritet ne dokazuju obnovljivost.

### Obnova bez nepotrebnog PostGIS-a

Ne uklanjati ekstenziju na izvoru. Na kopiji pregledati puni TOC i sastaviti eksplicitni allow/deny manifest. Za nonspatial kandidate izostaviti PostGIS EXTENSION/COMMENT stavke i samo potvrđene extension-owned/config-dump objekte, uključujući spatial_ref_sys podatke ako su prisutni. Ne izostavljati korisničke tablice, ACL ili proizvoljne GiST indekse.

postgres i farma_db sadrže tiger/topology config objekte i farma orphan funkcije. Za njih nije dovoljan slijepi filter naziva: probati službeni PostGIS restore/upgrade postupak, sačuvati korisničke modifikacije spatial_ref_sys i sve nepoznate podatke. Izostavljanje objekta zahtijeva dokaz o pripadnosti ekstenziji i pregled arhive. Ako se ne može sigurno dokazati, baza ostaje HOLD ili se target obnavlja s PostGIS-om do zasebnog rješenja.

U standardnom targetu postgres ostaje ime Uzorita baze. Potrebna je prethodno pripremljena prazna baza tog imena, a konekcija za administraciju preko druge čiste baze. Ne vraćati dump u već popunjenu admin bazu.

## 2. Predloženi valovi

| Val | Baze / skupina | Gate i svrha |
| --- | --- | --- |
| A | test_predix, test_qubit_user, test_stay_platform_db | tek nakon potvrde vlasnika da nema aktivne upotrebe; test_* ime nije dokaz; provjera općeg restore/ACL postupka |
| B | roamkit staging, omnimsgio, parkschloss, tablio_platform_db | potvrđeni app/CI backend; mali neprostorni kandidati, svaki zaseban cutover prozor |
| C | chatwoot | vector, tri IVFFlat indeksa, web+sidekiq+backup endpoint |
| D | finestar_erp_db i racunai_intermediary; predix; mozzart_db; fiskal/smoke; superclean_db | zasebni app valovi; ERP/Superclean tek nakon PostGIS backend promjene; sačuvati povezane endpoint veze |
| E | postgres (Uzorita), stay_platform_db i povezani Uzorita read klijenti | zajednički write-freeze ako postoji aktivna sinkronizacija; odvojeni primary/legacy aliasi |
| F | qubit_user, headscale i powerdns prema QuBIT vezama; snappymail, mailblocklist, nextcloud | razdvojeni prozori uz koordinaciju identiteta/DNS-a/maila; bez gubitka mrežnog pristupa tijekom rada |
| G | immich | zaseban target s istim vector/vchord verzijama; server i svi bridge/helper writeri u jednom prozoru |
| H | crowdsec | najveća baza, zaseban izmjeren prozor i disk gate; bez paralelnog velikog restorea |
| I | preostale testne PostGIS baze | ostaju na postgis dok se odvojeno ne promijene testne politike; ne preseliti samo radi simetrije |
| J | farma_db, minidepo, preostali postgis/template sadržaj | tek na kraju zaseban plan nadogradnje postojećeg PostGIS servisa, uz odobren restart i probu |

Redoslijed B–H može odrediti poslovni prozor, ali preduvjeti, povezana skupina i single-writer pravilo ostaju obvezni. Neiskorištena baza ne uklanja se bez upute. Status svake baze nalazi se u matrici; uvjetni redak nije spreman za provedbu.

## 3. Cutover za svaki val

1. Zabilježiti vrijeme T0, source/target server identitet, DB owner, aplikacijsku verziju i odobreni manifest endpoint promjena. Aktivni stari image i konfiguraciju zadržati za povrat.
2. Uvesti maintenance/write-freeze u aplikacije vala. Pauzirati njihove workere, beat, importere, CI i host writere; drenirati transakcije. Ne dirati unrelated servise.
3. Onemogućiti sve source scheduler writere koji ciljaju predmetne baze, čak i ako trenutačno izgledaju neaktivni. Potvrditi da nema tekućih poslova i otvorenih write transakcija.
4. U odobrenoj implementaciji primijeniti per-database fence za source klijente te provjeriti postojeće sesije; REVOKE CONNECT sam ne prekida postojeće veze. Ne mijenjati zajedničku rolu globalno ako još služi bazama koje ostaju na izvoru.
5. Napraviti finalni dump, hash i off-host kopiju. Tek snapshot nakon potvrđenog freezea predstavlja cilj RPO=0.
6. Obnoviti u provjeren target postupkom iz probe. Source ne mijenjati, ne čistiti i ne označiti target primary prije validacije.
7. Usporediti data/ACL/schema/sequence/index/extension provjere. Svaka neočekivana razlika znači stop i rollback prije otvaranja pisanja.
8. Promijeniti samo DB host/URL dijelove u odobrenim env/secret izvorima, mreže i backup procese vala. Ista imena DB i role po defaultu ostaju; credentials ne rotirati usput. Env izmjena traži recreate klijenta, ne samo restart sa starim envom.
9. Pokrenuti izolirane/no-side-effect health provjere i read smoke; potvrditi stvarni target endpoint iz klijenta, ne samo pg_isready.
10. Napraviti završnu odluku GO/NO-GO prije prvog produkcijskog pisanja. Zabilježiti T_write. Otvoriti writer samo na targetu i provjeriti transakciju te relevantnu poslovnu putanju.
11. Uključiti target schedulere kontrolirano. Source fence ostaje. Nadzirati greške, reconnectove, poolove, latenciju, disk/WAL, backup i nove veze na source.
12. Zabilježiti ishod i izmjeren downtime po bazi. Ne brisati source podatke; zadržati ih prema naknadno odobrenoj retenciji.

## 4. Poseban pg_cron prijelaz

Target od prvog starta: shared_preload_libraries uključuje pg_cron, cron.database_name=qubit_user, cron.timezone=GMT, cron.launch_active_jobs=off. Dokazi o [ponašanju launchera](https://github.com/citusdata/pg_cron) usklađeni su s lokalnim nalazom.

Sedam rasporeda, SQL naredbe, username, database, nodename/nodeport i active stanje izvesti privatno zajedno s poviješću. Normalni dump ne smije se unaprijed smatrati dovoljnim za sve extension tablice. Na probi provjeriti što se stvarno vraća iz cron.job/job_run_details i sekvenci te pripremiti točno jedan način uvoza. Ne učitati iste jobove i restoreom i ponovnim schedule pozivima.

Preferirati očuvanje metadata/jobid vrijednosti u provjerenom restore postupku; ako instalacijska skripta zahtijeva rekonstrukciju, mapirati stare/nove jobid i povijest tako da se ne izgubi revizijski trag. Sekvence moraju biti iznad najvećeg ID-a. Svi jobovi ostaju inactive na targetu do cutovera, uz globalni launch gate off.

Prije aktivacije:
- source jobovi deaktivirani, nema tekućeg izvršavanja; source se neće ponovno uključiti nakon restarta;
- export putanje postoje s ispravnim UNIX vlasnikom/dozvolama, ne ciljaju originalne datoteke u probi;
- aplikacijski job login/HBA radi; trenutačno pg_cron koristi libpq/localhost, a ne background workers;
- potvrđeni retention/catchup pravila. Satni warmup prvo testirati samo na kopiji; on kreira particije. Prune funkcije mogu uklanjati podatke i zahtijevaju zasebnu potvrdu učinka nakon višemjesečnog zastoja.

Reaktivirati samo odobrene jobove, globalni gate otvoriti jednom i pratiti novi run_details. Provjeriti jedan satni warmup, dnevni ciklus i tjedni export; do tjednog ciklusa ne tvrditi potpunu validaciju. Pri rollbacku prvo zatvoriti target gate i isprazniti tekuće poslove pa tek onda razmotriti source; nikad dva aktivna launchera za iste podatke.

## 5. Downtime i kapacitet

Nema izmjerenih vremena dump/restorea. Planirani write-freeze traje:
T_dump + T_transfer + T_restore + T_index + T_validation + T_reconnect + rezerva.
Neke faze mogu se preklapati tek kada je postupak dokazan; ne unaprijed oduzimati njihovo vrijeme.

Za početno rezerviranje prozora, ne SLA: male baze 15–45 min po aplikacijskom valu; Immich 30–90 min; CrowdSec 1–4 h. To su konzervativne planske procjene, ne benchmark. Objaviti stvarni prozor tek nakon probe i poslovnog odobrenja. Restore/index provjera i stare kolacije mogu bitno produžiti vrijeme.

Za CrowdSec nakon probe koristiti najmanje izmjereno ukupno vrijeme × 1,5 uz dodatno vrijeme rollback odluke. Ako prozor nije prihvatljiv, zaustaviti dump/restore varijantu i zasebno projektirati logičku replikaciju. Sadašnji wal_level=replica nije spreman za nju; zahtijevala bi novi odobreni zahvat, provjere PK/replica identity, sekvenci, DDL-a, extension tablica i slot/WAL retencije.

Kapacitet: uz 179 GiB slobodno predloženi minimalni netaknuti reserve je 80 GiB. Za simultanu punu kopiju svih baza, puni obnovljeni test target, nekomprimirani dump budžet i WAL/temp budžet: približno 39,82 + 39,82 + 39,82 + 20 + 80 = **219,46 GiB dodatnog slobodnog prostora**. To je konzervativni planski budžet, ne izmjerena potreba kompresije; trenutačno ne prolazi. Izvor je već u zauzetom prostoru i nije ponovno pribrojen.

Zato probe i valove izvoditi serijski, koristiti zaseban disk/host za veliku probu ili povećati prostor. Ne oslobađati ga brisanjem produkcijskih podataka. Prije svakog vala provjeriti dostupne bajtove, najveći index/temp/WAL rast, postojeće probe i rast drugih stackova. Stop ako projekcija pada ispod reserve praga.

## 6. Završetak

Po odobrenom prozoru praćenja potvrditi da target backupovi stvarno obnavljaju bazu, da nema aplikacijskih veza prema starim DB i da su svi jobovi jedinstveni. Ažurirati matricu stvarnim odredištem, datumom, hash manifestom i validacijskim rezultatom.

Uklanjanje starih DB, templatea, imagea, direktorija ili backupova nije dio automatskog završetka. Za svako uklanjanje tražiti izričitu uputu. Glavna nadogradnja na PG18 i zamjena preostalog PostGIS imagea zasebne su faze.
