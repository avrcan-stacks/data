# 60 — Backup politika standardnog servisa `postgres` (B1)

Datum: 18.11.2026. Način: **isključivo čitanje i pisanje ovog dokumenta.** Nije pokrenut Docker, nije izvršen `pg_dump`/restore/backup, nema SQL-a, nema izmjena `.env`, Compose ili Dockerfile datoteka, nema Git operacija. Jedino što je pročitano izvan dokumentacije jest popis datoteka u `/opt/stacks/data/backups` i `/srv/qubit/backups`, korisnički crontab, systemd timeri i `df` (samo metapodaci).

Pročitano: 04, 05, 06, 58, 59 (cjeloviti sadržaj). Sve preporuke ispod su **prijedlog**; ništa nije odobreno niti izvršeno.

Status politike: `PROPOSED_PENDING_OWNER_APPROVAL`

---

## 1. Politika pokretanja praznog clustera

| Točka | Prijedlog | Status |
|---|---|---|
| P1 | Novi, prazni cluster `postgres` smije se inicijalizirati bez prethodnog backupa vlastitih podataka (nema ih), **nakon zasebnog izričitog odobrenja vlasnika**. | `PROPOSED_PENDING_OWNER_APPROVAL` |
| P2 | Ta politika **nije** odobrenje za pokretanje servisa. Start i dalje traži odobrenje B2/B3 iz dokumenta 58 (naredba iz §9.2, provjere §9.1/§9.3). | — |
| P3 | Prije migracije **bilo koje** postojeće baze obavezno je osigurati provjerene sigurnosne kopije (§2 ovog dokumenta). Bez toga: HOLD. | `PROPOSED_PENDING_OWNER_APPROVAL` |
| P4 | Nijedan postojeći produkcijski podatak ne smije se brisati ni mijenjati (izvori `postgis`, `immich-db` i njihovi PGDATA ostaju netaknuti; vidi AGENTS.md). | postojeće pravilo |

Obrazloženje P1: prazan cluster nema što izgubiti; rizik starta nije gubitak podataka nego recreate `immich-db` (doc 58 §8), što backup novog servisa ne rješava. Zato je B1 (backup) i B2 (naredba) potrebno držati odvojenima, ali P1 omogućuje da B1 ne blokira sam start.

---

## 2. Trenutačno stanje backupa (činjenice, 18.11.2026.)

| Područje | Nalaz | Izvor |
|---|---|---|
| Backup novog servisa `postgres` | **Ne postoji** (servis ne postoji, PGDATA prazan). | doc 58, 59 |
| Svježi dumpovi 25 ciljnih baza | **Ne postoje.** U `/opt/stacks/data/backups` najnoviji generički dumpovi su iz **11.02.2026.** (`pg14_*`, `pg16_dump.sql.gz`, `pg_dumps_2026-02-11.tar.gz`, globals). Uz njih su radni/neuspjeli artefakti (npr. nulte veličine `pg16_powerdns_block_patched.sql`, `powerdns_restore2.log`). Pojedinačno: `finestar_erp_db_2026-06-09.dump` (338 KB). | `ls` backups |
| Globals (`pg_dumpall --globals-only`) | Samo veljača 2026. (`pg16_globals.sql.gz`, 705 B; filtrirane verzije). Neaktualno, nepoznato pokriva li sve role. | `ls` backups |
| Chatwoot | Dnevni `pg_dump -Fc`, zadnji `chatwoot-20261117T231850Z.dump`, aktivan kroz **chatwoot-backup** proces (cron ~23:18 UTC). **Zapažanje:** svih 8 vidljivih dumpova (10.–17.11.) ima **identičnu veličinu 446 582 B** — treba provjeriti jesu li legitimni (npr. baza gotovo nepromijenjena) ili backup ne bilježi promjene. Nije utvrđeno. | `ls` backups/chatwoot |
| Immich | Dnevni DB backup postoji (doc 06 R13, 58), plus zaštićeni cutover/post-cutover backupi (doc 29, 35, 48). Ovdje **nije ponovno provjeren**; ne štiti medije. | doc 06, 58 |
| Off-host kopija | **Nije potvrđena. Ne pretpostavlja se da postoji.** `/opt/stacks/data/backups` i `/srv/qubit/backups` su na istom `/dev/md2` kao PGDATA. Nema `restic`/`borg`/`rclone`/`aws` u PATH-u, nema relevantnog cron/systemd timera za backup (korisnički crontab: samo aplikacijski poslovi; systemd: dpkg-db-backup, bez DB backupa). Moguće da off-host mehanizam postoji izvan hosta ili u kontejneru — **NOT VERIFIED**. | doc 06 R03, 58; provjera ovdje |
| Restore proba cijelog clustera | **Nije izvršena.** Doc 05: „Nema potvrde obnovljivosti cijelog clustera”; čitljiv TOC i gzip integritet ne dokazuju obnovljivost. | doc 05 |
| SHA-256 manifesti | Nema manifesta za ciljne baze. | — |
| Šifriranje backupa | Nije potvrđeno; datoteke su na disku u `root:root 755` direktoriju (čitljive svima). Dumpovi/globals bi nosili role hasheve — doc 04 zabranjuje njihovo prikazivanje i git. | ls, doc 04 |
| Monitoring/alarmiranje neuspjelog backupa | Nije potvrđeno da postoji (za Chatwoot/Immich nije provjereno). | — |
| Prostor | 414 GB slobodno od 2,0 TB (78 %); doc 04 budžet ≈ 219,5 GiB najgori slučaj → prolazi uz serijske valove. Backupi dijele disk s PGDATA. | `df`, doc 58 |
| `data_checksums` | Odobreno za novi cluster (doc 59); backup ne ovisi o tome, ali omogućuje `pg_amcheck`/detekciju korupcije na novom clusteru. | doc 59 |

Zaključak: **R03 iz doc 06 (nema svježeg, obnovljivog, off-host backupa svih baza) ostaje u cijelosti otvoren.**

---

## 3. Obavezne provjere prije prve migracije (po bazi)

Vrijedi za **svaku** bazu koja se migrira. Sve stavke su preduvjet (gate); izostanak = HOLD. Svi koraci su buduća, odobrena faza — ovdje se ne izvršavaju.

| # | Provjera | Kriterij prolaza / napomena |
|---|---|---|
| 1 | Svježi `pg_dump -Fc` te baze | Izrađen unutar odobrenog prozora, kroz `postgis` kontejner i admin rolu, u `backups/MIGRATION_ID/DB.dump`; bez lozinki u komandnoj liniji; exit code 0, veličina > 0. Za aplikacijski povezane baze (doc 04 §1) uz zajednički write-freeze; za finalni cutover dump mora biti pod freezeom (RPO=0 ciljan samo tada). |
| 2 | `pg_dumpall --globals-only` | Po izvornom clusteru (`postgis`; za Immich `immich-db`). Pohranjen privatno, s hash lozinki, **nikad u git niti prikazan**. Uz njega: HBA, relevantne `pg_settings`, identifikatori imagea/paketa (doc 04 §1). Sanitizirani inventar rola nije backup autentikacije. |
| 3 | SHA-256 dumpova | `sha256sum` manifest po migraciji (datoteka, veličina, hash, vrijeme, izvor, verzija alata). Hash se ponovno provjerava nakon svakog prijenosa. |
| 4 | Čitljivost i integritet dumpa | `pg_restore --list` (TOC čitljiv, broj stavki razuman, ekstenzije prisutne) + provjera da arhiva nije skraćena. **Ovo nije dokaz obnovljivosti** (doc 04/05) — vidi točku 6. |
| 5 | Kopija izvan fizičkog servera | Dump + globals + manifest kopirani off-host, hash provjeren **na odredištu**. Lokacija i mehanizam moraju biti potvrđeni (§5, odluka O2). Bez potvrđene off-host kopije: HOLD. |
| 6 | Uspješna restore proba na izoliranom testnom clusteru | `pg_restore --exit-on-error` iz regularne datoteke, bez `--clean` prema izvoru, u izolirani sandbox (bez produkcijskih aliasa, crona, webhookova, writable medija; zaseban Compose projekt i nazivi, doc 04 §0). Zatim acceptance iz doc 05 (identitet, shema, ekstenzije, COUNT/checksum, sekvence, ACL, indeksi). Restore exit code i rezultati se bilježe. |
| 7 | Evidencija verzije PostgreSQL-a i ekstenzija | Za izvor i cilj: `server_version`, image digest, `pg_extension` + `full_version`, locale/encoding/provider, collation mismatch (doc 05, R05). Posebno vector/vchord (Immich), PostGIS 3.4.3 SQL / 3.6.2 library (R02), pg_cron (R01). |
| 8 | Plan povratka na izvornu bazu | Dokumentiran po doc 05 rollback tablici: prije T_write → povrat na izvor uz uklanjanje fencea; nakon T_write → **nije** dopušten povrat promjenom hosta; nužan testirani reverse dump/restore u novi recovery cluster ili forward-fix. Potvrđeno da je PG16→PG18 odvojena faza. |
| 9 | Očuvanje izvorne baze | Izvorna baza i PGDATA ostaju netaknuti **do zasebnog izričitog odobrenja vlasnika** (D10). Nema `DROP`, čišćenja ni „oslobađanja prostora” iz izvora. |

Dodatni uvjeti (iz doc 04/05/06): popis writera potpisan, write-freeze plan, prag diska (rezerva 80 GiB), jedan val u isto vrijeme, odobreni downtime/RPO/RTO (R09).

### 3.1 Poseban slučaj: `crowdsec` (val H)

Najveća baza (≈ 37,4 GiB prema doc 06 / ≈ 38,9 GiB prema doc 58 — **nesklad dviju brojki, treba ponovno izmjeriti**; ukupno 25 ciljnih baza ≈ 39,8 GiB, tj. CrowdSec je dominantan).

Rizici i mjere:

| Rizik | Mjera (prijedlog) |
|---|---|
| **Potrošnja prostora**: dump (-Fc, komprimiran; stvarna kompresija nepoznata), restore na istom disku, indeksi, WAL/temp. Doc 04 koristi konzervativnu nekompresiranu procjenu 39,82 GiB za svaku kopiju. | Gate prije vala: izmjeriti stvarnu veličinu baze i velike tablice/indekse; provjeriti `df` da nakon projiciranog dumpa + restorea ostaje ≥ 80 GiB rezerve. Ako ne ide — zasebni disk/host za probu. Ne oslobađati prostor brisanjem produkcijskih podataka. |
| **Duga transakcija `pg_dump` na živom izvoru** drži snapshot → zadržava VACUUM horizont i može napuhati tablice/WAL na izvoru `postgis` (CrowdSec je write-heavy). | Probni dump izvesti u mirnijem prozoru uz praćenje `pg_stat_activity` (xmin age), WAL i latencije; pauzirati/prigušiti CrowdSec writer samo uz odobren prozor. Izmjeriti trajanje. |
| **IO/swap** na zajedničkom disku (R17, swap 4/4 GiB popunjen). | `nice`/`ionice`, jedan veliki posao istodobno, nikad paralelno s drugim velikim restoreom (doc 04 val H). Prekid pri degradaciji produkcije. |
| **Restore trajanje** (index build, WAL). Planski prozor 1–4 h, nije benchmark. | Restore proba izmjeri vrijeme; prozor = izmjereno × 1,5 + rollback odluka (doc 04). Prije vala odluka o privremenom `max_wal_size`/`maintenance_work_mem` na ciljnom clusteru (doc 58 §5.4). |
| **Kolacija** glibc 2.31→2.36 mismatch na `crowdsec` (R05). | Restore u čisti target s novim indeksima; provjera unique/PK grešaka (doc 05). |
| Smanjenje podataka (npr. prune starih alerta) bi smanjilo dump, ali **mijenja produkcijske podatke**. | **Ne radi se** u okviru ove politike. Moguće samo kao zasebna odluka vlasnika aplikacije, i to na kopiji ili uz izričito odobrenje. |
| Ako prozor nije prihvatljiv | Zaustaviti dump/restore varijantu; zasebni projekt logičke replikacije (`wal_level=replica` nije spreman, R16). |

Parallel dump (`pg_dump -Fd -j`) smanjuje trajanje, ali povećava IO i broj snapshot-veza; razmatrati tek nakon mjerenja i uz odobrenje. Ne kombinirati parallel restore i `--single-transaction`.

---

## 4. Predložena operativna backup strategija (za novi servis nakon migracija)

Ništa od ovoga nije odobreno ni implementirano. Brojke su **prijedlozi za odluku vlasnika**, ne izmjereni zahtjevi.

### 4.1 Raspored

| Vrsta | Prijedlog | Napomena |
|---|---|---|
| Logički dump po bazi (`pg_dump -Fc`) | Dnevno, jedan prozor izvan vršnog opterećenja (npr. 02:30–04:30 UTC; ne preklapati s `0 2` dalekopro i `*/2` Uzorita cronovima niti s Immich/Chatwoot backupom ~23:18 UTC), baze serijski | CrowdSec zaseban, tjedni ili dnevni ovisno o izmjerenom trajanju i prostoru |
| Globals (`pg_dumpall --globals-only`) | Dnevno, uz dumpove, plus nakon svake promjene rola | privatno, šifrirano, nikad u git |
| Konfiguracija (`pg_hba`, `postgresql.conf` izvedeni parametri, Compose/env manifest) | Pri svakoj promjeni + tjedno | tajne zasebno |
| WAL arhiviranje / PITR | **Ne predlaže se** u prvoj fazi (`archive_mode=off`); RPO = interval dumpa (do 24 h). Ako je RPO < 24 h potreban, to je zasebna odobrena faza (pgBackRest/WAL-G). | odluka vlasnika O4 |
| Pre-cutover dump | Izvanredni, uz svaki val (doc 04 §1, §3) | pod write-freezeom |

### 4.2 Retencija (prijedlog)

| Razred | Lokalno | Off-host |
|---|---|---|
| Dnevni | 7 dana | 14 dana |
| Tjedni | 4 tjedna | 8 tjedana |
| Mjesečni | — | 6 mjeseci |
| Pre-migration / pre-cutover dumpovi | **ne brišu se automatski** do izričite odluke vlasnika | isto |

Pravilo: **retencija nikad ne briše posljednji uspješno verificirani backup** niti ijedan dump koji je jedina kopija izvora u migracijskom valu. Automatsko brisanje se uvodi tek nakon potvrđene restore probe i odobrene retencije (AGENTS.md: ne brisati bez uputa). Veličine su ograničene prostorom na disku: 7 dnevnih kopija svih baza + CrowdSec zahtijeva provjeru budžeta prije aktivacije.

### 4.3 Off-host lokacija i zaštita

**Nema potvrđene lokacije.** Odluka O2. Mogući kandidati (bez pretpostavke da su dostupni): drugi vlastiti host preko Tailscalea (append-only/zaseban korisnik), objektno spremište (npr. S3-kompatibilno) s versioningom/object lock, ili drugi datacentar. Zahtjevi koje svaka opcija mora ispuniti:

- fizički i administrativno odvojeno od `dedicated-hel1` (RAID1 nije backup);
- pristup samo pisanjem iz produkcije (kompromitirani host ne smije moći obrisati/prepisati stare kopije): append-only, versioning ili object lock;
- zasebne vjerodajnice, ne dijeliti admin lozinku PostgreSQL-a (doc 58 §7: lozinka je ista na sva tri clustera);
- potvrđen hash na odredištu nakon prijenosa;
- troškovi i lokacija podataka (GDPR/rezidencija) odobreni od vlasnika.

### 4.4 Šifriranje

- Šifriranje **prije** napuštanja hosta (npr. `age` ili `gpg` s javnim ključem; privatni ključ nije na produkcijskom hostu) — dumpovi i globals sadrže podatke i role hasheve.
- Ključ i recovery fraza čuvaju se odvojeno od backupa; **bez testirane dešifracije backup se ne računa važećim.**
- Lokalni backup direktoriji: najmanje `chmod 700` i vlasnik root/backup korisnik (trenutno `root:root 755`; izmjena je zasebno odobrena radnja). Datoteke s hash lozinki nikad `644`.
- Šifriranje diska (LUKS) nije prisutno/potvrđeno; ne zamjenjuje šifriranje arhiva.

### 4.5 Provjera uspješnosti (svaki backup)

Backup se smatra uspješnim samo ako su ispunjeni **svi** uvjeti:

1. exit code svih koraka 0, bez neočekivanih redaka u logu;
2. veličina unutar očekivanog raspona (alarm pri naglom padu/rastu, uključujući slučaj „identična veličina svaki dan” kao kod Chatwoota — treba objasniti);
3. `pg_restore --list` čitljiv, broj TOC stavki ≈ prethodni;
4. SHA-256 zapisan u manifest, ponovno provjeren nakon off-host prijenosa;
5. off-host kopija postoji i hash se podudara;
6. zapis u strukturiranom logu (vrijeme, baza, veličina, trajanje, hash, rezultat).

### 4.6 Periodične restore probe

| Učestalost | Opseg |
|---|---|
| **Mjesečno** | Puni restore najnovijeg off-host dumpa 1–2 rotirajuće baze + globals u izolirani sandbox, s COUNT/checksum provjerom (doc 05) |
| **Kvartalno** | Restore svih baza; CrowdSec mjeri trajanje/prostor; evidentira se RTO |
| **Nakon svake promjene** | verzije PG-a/ekstenzija, imagea, scheme alata ili backup postupka |

Proba se vodi u zasebnom Compose projektu, na disku s dovoljno rezerve, bez produkcijskih aliasa/webhookova/medija. Rezultat se bilježi u doc-izvještaj (hash, exit kod, trajanje, razlike).

### 4.7 Monitoring i alarmiranje

Nije potvrđeno da postoji bilo kakav alarmni mehanizam za DB backupe. Prijedlog (odluka O6 o kanalu):

- **Dead-man's-switch** (heartbeat) po poslu: svaki uspješan backup šalje ping; izostanak ping-a u 26 h → alarm. Hvata i slučaj da cron/kontejner uopće nije pokrenut.
- Alarm pri: non-zero exit, nedostatku datoteke, anomaliji veličine, neslaganju hasha, neuspjehu off-host prijenosa, restore probi koja nije prošla.
- Praćenje: starost najnovijeg backupa po bazi, slobodan prostor (alarm < 150 GiB i hard stop < 80 GiB rezerve), rast WAL-a, trajanje backupa.
- Zasebno upozorenje na kontejnere koji se restartaju ili izlaze (u doc 58 §12 uočeni `fiskal_otel_collector`, `paddle-ocr-fastapi`) — ne mijenjati ih bez zadatka.
- Kanal alarma (e-mail/Telegram/Slack/…): odluka vlasnika; mora biti izvan hosta koji se nadzire.

---

## 5. Otvorene odluke vlasnika

| ID | Odluka | Preporuka / napomena |
|---|---|---|
| O1 | Odobriti politiku §1 (start praznog clustera bez backupa vlastitih podataka, uz zasebno odobrenje starta). | Preporučeno; nije odobrenje starta |
| O2 | **Off-host lokacija**: gdje, tko pristupa, proračun, rezidencija podataka, mehanizam zaštite od brisanja. | Bez toga prva migracija ostaje HOLD |
| O3 | Šifriranje: alat, tko drži privatni ključ i recovery, gdje se čuva izvan hosta. | |
| O4 | RPO/RTO prema bazi/val; treba li PITR (WAL arhiva) ili je dnevni dump dovoljan. | Doc 06 R09 — još nije zadano |
| O5 | Retencija (§4.2) i budžet prostora; hoće li se pre-migration dumpovi čuvati neograničeno. | Samo uz izričitu odluku; bez automatskog brisanja |
| O6 | Kanal i odgovorna osoba za alarmiranje. | |
| O7 | Hoće li se backupi pisati iz kontejnera `postgres` (zahtijevao bi `/backups` rw; doc 58 §7 predlaže `read_only`) ili iz zasebnog backup kontejnera/hosta. | Utječe na Compose izmjene — zasebno odobrenje |
| O8 | Tko izvršava i potpisuje restore probe i s kojom učestalošću (§4.6). | |
| O9 | CrowdSec: prihvatljiv prozor, retencija/prune podataka na razini aplikacije, zasebni disk za probu. | Prune mijenja podatke — ne bez odluke |
| O10 | Postupak za usklađenje Chatwoot/Immich backupa s novom politikom (obrazac imenovanja, off-host, hash). | Ne mijenjati rad postojećih backup procesa bez odobrenja |

---

## 6. Rizici i blokade

| ID | Rizik / blokada | Težina | Stanje |
|---|---|---|---|
| R03 | Nema svježeg obnovljivog backupa svih baza, globals ni off-host kopije | kritično | **Otvoren**; blokira prvu migraciju |
| BL-1 | Off-host lokacija nepotvrđena (O2) | kritično | Blokada |
| BL-2 | Restore proba na izoliranom clusteru ne postoji (doc 05) | kritično | Blokada |
| BL-3 | Backup, backup lokacije i PGDATA isti disk (`/dev/md2`); jedan kvar/ransomware/krivi `rm` gubi sve | visoko | RAID1 ≠ backup |
| BL-4 | Dumpovi/globals u `root:root 755`, bez šifriranja; globals nose hasheve rola | visoko | Zasebno odobrenje za ojačanje |
| BL-5 | Staro stanje: dumpovi iz veljače 2026., uz neuspjele/radne artefakte; ne smiju se smatrati backupom | visoko | Ne brisati; nepouzdani |
| BL-6 | Prostor: CrowdSec; budžet ≈ 219,5 GiB uz 414 GB slobodno — prolazi samo serijski, bez retencije više dnevnih kopija | visoko | Mjeriti prije vala |
| BL-7 | Duga snapshot-transakcija na živom `postgis` (CrowdSec dump) | srednje–visoko | Mjeriti na probi |
| BL-8 | Zajednička admin lozinka na sva tri clustera (doc 58 §7) — kompromitacija jednog = svi; ulazi u backup vjerodajnice | srednje | Zasebna odluka |
| BL-9 | Nema alarma za neuspjeli backup | visoko | O6 |
| BL-10 | Nejasno stanje Chatwoot backupa (identična veličina) i Immich backup nije u ovom auditu ponovno provjeren | srednje | Prije oslanjanja na njih |
| BL-11 | Nesklad hasha `immich-db` (doc 58 §8): nenamjeran `up` bi recreateao `immich-db`; ne pokretati bez odobrene naredbe | visoko | Povezano s B2 |
| BL-12 | PostGIS-ovisne baze (gate D), pg_cron (R01), kolacije (R05) utječu na restore, ne na backup, ali moraju se zabilježiti u evidenciji (§3 t.7) | visoko | Odvojeni gateovi |
| R09 | RPO/RTO nisu zadani | blokada | O4 |

Procjene i brojke u ovom dokumentu nisu mjerenja. Izostanak podatka = HOLD, ne pretpostavljeni prolaz.

---

## 7. Odnos prema dokumentima 58 i 59

- **Doc 58, blokada B1** („Ima definiranu strategiju backupa”): ovaj dokument je *prijedlog* strategije; **B1 ostaje otvoren dok vlasnik ne odobri** politiku (§1, O1) i odluke O2–O4. Za sam start praznog clustera dovoljno je O1 uz B2/B3; za migraciju je nužno §3.
- **Doc 58 B2 i B3** (naredba bez recreatea, plan inicijalizacije): ovdje nisu dirane. Backup politika ne zamjenjuje ih; zabrane iz doc 58 §8.3 (npr. `up` bez servisa) vrijede i za sve backup/restore skripte (doc 06 R20: izbjegavati hardkodirani `docker exec postgis`).
- **Doc 58 §5.6** (backup strategija nije definirana): zamijenjeno prijedlogom §4.
- **Doc 59** (`--data-checksums`): potvrđuje da novi cluster dobiva checksums pri `initdb`. Posljedice za backup: izvorni clusteri (`data_checksums=off`) i ciljni (`on`) nisu istog tipa — **logički dump/restore je neovisan o checksumima**, pa je kompatibilan; fizički `pg_basebackup` između njih nije predmet ove politike. Checksums ne zamjenjuju backup niti restore probu; omogućuju detekciju korupcije stranica (`pg_amcheck`, `pg_stat_database.checksum_failures`) i trebaju ući u monitoring novog clustera.
- **Doc 59 B1/B2** ostaju kako su zapisani; ovaj dokument je odgovor na B1 (prijedlog).
- **Doc 04/05/06**: ovaj dokument ih ne zamjenjuje; konkretizira §1 doc 04 (backup/restore proba) i R03/R04/R09 iz doc 06. Acceptance kriteriji restorea ostaju kako su u doc 05.

---

## 8. Potvrda da nije mijenjano

Izvršeno: čitanje dokumenata 04, 05, 06, 58, 59; `ls`/`du`/`df`, `crontab -l`, `ls` cron.d/cron.daily, `systemctl list-timers`, `which` (samo metapodaci). Izrađen samo ovaj dokument.

Nije izvršeno: Docker (ni `ps`/`inspect`), `initdb`, `pg_dump`, `pg_dumpall`, `pg_restore`, SQL, izmjene `.env`/Compose/Dockerfile, bilo što na `postgis` i `immich-db`, brisanje/premještanje backupa, Git commit/push/PR.

Stajem. Čekam odluke vlasnika O1–O10.

## Završna oznaka

`POSTGRES_BACKUP_POLICY_PROPOSED — OWNER_APPROVAL_PENDING`
