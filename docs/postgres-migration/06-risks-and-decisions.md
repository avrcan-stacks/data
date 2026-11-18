# 06 — Rizici, odluke i preduvjeti

Status: analiza 14.11.2026.; **implementacija nije odobrena**. Ovaj dokument evidentira nejasnoće; ne zamjenjuje ih pretpostavkama.

## Odluke predložene za odobrenje

| ID | Prijedlog | Razlog i granica |
| --- | --- | --- |
| D01 | Tri trajna servisa: postgres, postgis, immich-db | izolacija prostornih i AI ekstenzija; nema HA zaštite |
| D02 | Najprije PG16 razdioba, cilj 16.16; PG18.7 poslije | razdvojiti promjenu glavne verzije od funkcionalnog premještanja |
| D03 | Dump/restore u nove direktorije, bez kopiranja PGDATA | izvorni cluster ostaje raspoloživ za rollback |
| D04 | PostGIS 3.6.4 na budućem čistom odredištu; ne popravljati izvor sada | ukloniti SQL/library nesklad kroz dokazanu probu |
| D05 | vector 0.8.2 / vchord 1.1.1 za prvi Immich prijelaz | očuvati postojeću kombinaciju; bez downgradea i bez paralelnog app upgradea |
| D06 | pg_cron metadata ostaje u qubit_user; cron.database_name=qubit_user na novom clusteru | uskladiti launcher s postojećim job tablicama; startup launch_active_jobs=off |
| D07 | postgres aplikacijska baza seli kao cjelina s Uzoritom, Stay ostaje povezan zasebnim aliasom | baza nije prazna; ime postgres privremeno ostaje |
| D08 | ERP/Superclean ne seliti na non-PostGIS bez promjene i probe Django backenda | nema prostornih tablica, ali postoji lifecycle ovisnost |
| D09 | PostGIS test baze ostaju dok se zasebno ne odobri promjena testne politike | postojeći AGENTS i test workflow zahtijevaju ih |
| D10 | Bez brisanja ili čišćenja izvora nakon prijelaza | svako kasnije uklanjanje podataka zahtijeva izričitu uputu |

To su preporuke, a ne tvrdnja da je korisnik odobrio runtime promjene. Nisu mijenjani imageovi, env datoteke, HBA, role, scheduler ili aplikacije.

## Registar rizika i blokada

| ID | Rizik / dokaz | Prioritet | Potrebno prije cutovera |
| --- | --- | --- | --- |
| R01 | pg_cron launcher u postgres, jobovi u qubit_user; povijest završava 04.04.2026. | kritično | odobriti popravak raspoređivanja; obnoviti na probi, provjeriti UTC i sve funkcije; bez slijepog catchupa prune zadataka |
| R02 | PostGIS SQL 3.4.3 / library 3.6.2; orphan C funkcije u farma_db | visoko | probni hard/soft upgrade na kopiji, pregled dumpa i TOC-a, usklađen full_version |
| R03 | Nema potvrđenog svježeg obnovljivog backupa svih baza i off-host kopije | kritično | puni privatni dumpovi, globals, hashevi, off-host kopija i stvarni restore test |
| R04 | 179 GiB slobodno, svi backup mountovi na istom filesystemu; CrowdSec 37,42 GiB | visoko | proračun vršnog prostora, mjerenje rasta/WAL-a i ograničenje paralelizma; po potrebi zaseban disk |
| R05 | 8 netemplate + template_postgis default collation mismatch; ICU/libc zapisi u svim connectable bazama | visoko | rebuild u čistom targetu ili odobren REINDEX prije REFRESH; provjera unique/PK i sortiranja |
| R06 | Udaljeni/CI secrets i klijenti nisu potpuno vidljivi; headscale/powerdns config nije cjelovito parsiran | visoko | vlasnici aplikacija potvrđuju sve endpoint potrošače, CI/test/backup i Tailscale klijente |
| R07 | ERP/Superclean PostGIS backend; Stay/ERP/Tablio testni workflow | visoko | odvojena app promjena i fresh-schema + restore probe; dotad hold u PostGIS-u |
| R08 | postgres je Uzorita aplikacijska baza i drugi DB alias Staya | visoko | konzistentan val svih write/read klijenata; ACL stay_uzorita_ro; zabrana zamjene praznom admin bazom |
| R09 | RPO, poslovni downtime, prozor i RTO nisu zadani ni izmjereni | blokada | restore benchmark i korisnikovo prihvaćanje prozora; nema jamstva nultog downtimea |
| R10 | Nakon otvaranja pisanja na targetu izvor je zastario | kritično | prije-write rollback ili kontrolirano povratno preseljenje; nikad samo vratiti URL |
| R11 | prune jobovi mogu izbrisati mjesece zaostalih particija; export COPY piše datoteke | visoko | poslovna odluka o retenciji/catchupu; test samo na kopiji i privremenom export direktoriju |
| R12 | superuser aplikacijske role qubit/farma_app/postgres; lokalni trust | srednje | eksplicitni privilege mapping; minimizacija kao zasebna promjena, ne skrivena u migraciji |
| R13 | Dnevni Immich DB backup ne štiti fotografije/external Nextcloud library | visoko | usklađen backup medija i baze; hash/uzorak datoteka; restore app bez pisanja u originalne medije |
| R14 | Nema konačnih image digestova ni potvrđene dostupnosti svih pinned paketa | visoko | reproduktibilan build, zapis paketa i arhitekture, release-note pregled prije probe |
| R15 | Samo statička pretraga ne otkriva sav dinamički SQL; pg_stat_statements nije preloaded | srednje | testovi stvarnih aplikacijskih putanja i kontrolirano promatranje; ne uključivati logging sada |
| R16 | Logička replikacija nije pripremljena; wal_level=replica | visoko za low-downtime varijantu | nema odobrene logical konfiguracije; DDL, sekvence i extension tablice trebaju zaseban plan |
| R17 | Swap popunjen, trenutna aktivnost swapanja nepoznata; zajednički disk | srednje | izmjeriti IO/swap tijekom probe; zaustaviti probu pri ugrozi produkcijske latencije |
| R18 | template_postgis nije dio ranijih 31 baza | srednje | arhivirati i dokumentirati predložak; ne kopirati ga u standardni target niti ga uklanjati s izvora |
| R19 | Snapshot veza/veličina nije kontinuirano praćenje; NULL ACL implicira default prava | srednje | ponoviti inventar u cutover prozoru; objektne ACL diffove iz schema dumpa |
| R20 | Bootstrap skripte mogu hardkodirati docker exec postgis | srednje | odvojiti host endpoint od SQL enginea; pregledati setup/test/backup skripte prije svakog vala |
| R21 | Neke prošle provjere dale su skraćen ispis ili parser grešku | riješeno za inventar | završno prikupljeno po bazi bez LIMIT-a i parser grešaka; stari ispisi nisu temelj odluke |

Nije dokazana odsutnost svih SQL funkcijskih poziva niti app ovisnosti. Završna matrica razlikuje potvrđene strukturalne ovisnosti, backend/test zahtjeve i uvjetne kandidate.

## Otvorene odluke koje trebaju vlasnika

1. Poslovni vlasnik potvrđuje prihvatljive downtime/RPO/RTO i raspored svakog vala. Cilj plana je RPO=0 za finalni snapshot uz zabranu pisanja; to nije trenutačno jamstvo.
2. Vlasnik QuBIT-a odlučuje o ponovnom uključivanju zastalog crona i obradi starih particija. Prune se ne uključuje automatski.
3. ERP/Superclean/Stay/Tablio vlasnici prihvaćaju eventualnu promjenu backenda i testnih skripti; bez nje baze s tim uvjetom ostaju na postojećem servisu.
4. Operater potvrđuje privatni prijenos credentials/role hashova, ciljna HBA pravila, Tailscale i CI endpoint popis.
5. Operater potvrđuje diskovni prag, privatnu off-host lokaciju i rok čuvanja starih baza. Do izričite odluke nema brisanja.
6. Operater zaključava image digeste i paketne verzije, uz provjeru novih security objava na dan implementacije.
7. Ako izmjeren downtime nije prihvatljiv, potrebna je zasebna odobrena faza logičke replikacije; nije implicitno dio ovog runbooka.

## Kriterij spremnosti

Val smije krenuti tek kada su za njegove baze zatvorene sve kritične/visoke relevantne blokade, benchmark prolazi, popis svih writera je potpisan, postoji testirana obnova i izvediv rollback. Izostanak podatka znači **HOLD**, ne pretpostavljeni prolaz.

Za implementaciju je potrebno novo izričito odobrenje korisnika. Odobrenje dokumentacije samo po sebi ne odobrava restart, DDL, migraciju ili promjenu podataka.

## Službeni izvori pregledani 14.11.2026.

- [PostgreSQL izdanja 12.11.2026.](https://www.postgresql.org/about/news/postgresql-187-1712-1616-1520-1425-and-19-rc-2-released-3442/)
- [PostGIS administracija i nadogradnje](https://postgis.net/docs/en/postgis_administration.html)
- [PostgreSQL kolacije i REFRESH ograničenja](https://www.postgresql.org/docs/16/sql-altercollation.html)
- [pg_cron konfiguracija i ponašanje](https://github.com/citusdata/pg_cron)
- [Immich v3.3.5 rasponi](https://raw.githubusercontent.com/immich-app/immich/v3.3.5/server/src/constants.ts)
- [pgvector dokumentacija](https://github.com/pgvector/pgvector)

## Završna provjera isporuke

Svih šest dokumenata postoji. Matrica sadrži točno 31 netemplate bazu, uz odvojeno navedena tri predloška. Provjereni su lokalni linkovi, zatvorenost code fence blokova, obrasci URI-ja/vjerodajnica i poznate tajne bez njihova ispisivanja; nema pronađenog curenja. Ponovno je izvršen dokumentirani read-only dependency SELECT nad minidepo i potvrdio je očekivane aplikacijske stupce. Dokumentacija je jedina nova promjena ove faze; postojeći data.code-workspace ostao je netaknut. Restore i produkcijski acceptance testovi nisu izvršeni.
