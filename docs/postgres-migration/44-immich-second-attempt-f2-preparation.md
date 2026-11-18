# 44 — Immich: priprema F2 za postojeću rolu i praznu bazu

15. studenoga 2026., UTC. CUTOVER_ID **`20261115t150714z`**.

**Postupak je pripremljen i testiran izolirano. Produkcijski F2 nije izvršen i produkcijski PREPARED nije zapisan.** Novi žurnal ostaje **NONE**; Immich radi na **`postgis/immich`**, javni `/` i `/api/server/ping` vraćaju **HTTP 200**. Za izvršenje treba zasebno pisano odobrenje F2 i zapisa PREPARED za ovaj ID.

Pročitani dokumenti [17](17-immich-production-cutover.md), [20](20-immich-cutover-safety.md), [40](40-immich-cutover-safety-hardening.md), [41](41-immich-second-attempt-readiness.md), [42](42-immich-second-attempt-f0.md) i [43](43-immich-second-attempt-target-reset.md), postojeći `s_prepare_target`, backup, žurnal, snapshot i write-probe alati. Prvo očitanje sata: **16:07:30Z**.

## Pripremljeni postupak i datoteke

| Datoteka | Sadržaj |
| --- | --- |
| `immich-cutover/steps.sh` | Nova zasebna funkcija **`s_prepare_existing_target`**; postojeći `s_prepare_target` nije mijenjan ni pozvan. |
| `immich-cutover/prepare_existing_target.py` | Žive READ ONLY provjere; nova trajno zapisana potvrda provjera, pa tek uz odobrenje jedan početni zapis PREPARED. |
| `immich-cutover/policies/f2-20261115t150714z.json` | Zaključan identitet ovog pokušaja: postojeći kontejneri/config hashovi, kanonski mountovi, OID-i, rola, arhiva i hashovi 137 zaštićenih datoteka. Nema lozinki ili API ključeva. |
| `immich-cutover/run_f2_existing.sh` | Budući produkcijski driver, svježa Bash ljuska, točne putanje i identiteti, odbijanje nedostajućeg/pogrešnog tokena, uklanjanje tokena pri izlazu. **Nije pokrenut.** |
| `immich-cutover/tests/f2_existing_selftest.py` | Offline pozitivni, negativni i fault-injection testovi, uključujući Bash uvjetne kontekste. |
| `immich-cutover/tests/f2_existing_rehearsal.py` | Stvarni PG 16.16 i sintetski fixture u zasebnoj internoj mreži, samo `immich-apptest-*` imena i `/tmp` mountovi. |
| `immich-cutover/tests/offline_selftest.sh` | Novi F2 test uključen u postojeći offline skup. |
| Dokument 17, F2 | Dodana uputa za ovu posebnu putanju i poveznica na ovaj dokument. |

Funkcija zahtijeva valjan žurnal **NONE**, provjerava status svake obavezne naredbe i pokreće zaseban Python proces. Ne koristi Compose, CREATE ROLE, CREATE DATABASE, ALTER ROLE, instalaciju ekstenzija, reset, restore ili Docker lifecycle naredbe. SQL provjere su unutar READ ONLY transakcija. Postojeća aplikacijska lozinka čita se iz okoline servera samo u memoriju; oba mrežna login testa koriste samo SELECT. API ključevi nisu potrebni za F2.

Python ne prihvaća raniju PASS potvrdu kao zamjenu za provjere. Svako izvođenje ponovno skuplja žive dokaze u novi `$EV/f2-existing-*`; ništa se ne prepisuje. `checks.json` piše se i fsynca **prije** žurnala. PREPARED se smije zapisati samo nakon svih provjera, iz **NONE**, s provjerom povratnog statusa i ponovnim čitanjem žurnala. Greška žurnala/pohrane znači HALT i provjeru stvarnog stanja, bez ručnog označavanja uspjeha.

## Obavezni F2 uvjeti

| Izvorni F2 zahtjev | Posebna putanja za postojeći cilj |
| --- | --- |
| Odobrenje i valjan prethodnik | `_gate`, točan ID/EV, valjan novi NONE i točan prethodni ROLLED_BACK hash lanac; nema T_open. Produkcijski policy override nije dopušten. |
| Pokrenuti cilj i čekati healthy | Cilj već postoji: nema `idb_up`. Dokazuju se isti kontejner, StartedAt, restart count, running/healthy, config hash, svi mountovi i mreže. |
| PostgreSQL 16.16 | Točno `server_version_num=160016`. |
| Nema PostGIS-a | Nula dostupnih `postgis%` ekstenzija; ne samo odsutnost instalirane ekstenzije. |
| Pripremljene ekstenzije | Dostupne točne verzije: plpgsql 1.0, cube 1.5, earthdistance 1.2, pg_trgm 1.6, unaccent 1.1, uuid-ossp 1.1, vector 0.8.2, vchord 1.1.1; vchord u preloadu. **Ne instalirati ih u praznu bazu u F2**; očekuje se samo plpgsql 1.0. |
| LOGIN bez povišenih ovlasti | Točan postojeći role OID, LOGIN/INHERIT, bez SUPERUSER, CREATEDB, CREATEROLE, REPLICATION, BYPASSRLS; nema članstva u drugim rolama; SCRAM verifier postoji. |
| Baza owner immich, template0, UTF8/en_US.utf8 | Točan novi database OID **129819**, vlasnik i ACL, UTF8, oba localea `en_US.utf8`; OID različit od arhivskog. Dokaz nastanka s template0 sačuvan je iz reseta; sada se provjerava očekivana praznina. |
| Ovlasti | Strogi JSON booleani za CONNECT/CREATE/TEMP baze i USAGE/CREATE sheme; public owner `pg_database_owner`. `t/f`, prazno, neispravan JSON, nepoznato i SQL greška ne postaju PASS. |
| Stvarna SCRAM prijava | Mrežna adresa, ne loopback trust; pozitivan rc 0 i točno `immich`, negativan rc **2** i `password authentication failed`; provjera HBA i password_encryption. Docker/mrežna greška nije uspješna negativna kontrola. |
| Praznina | Nema korisničkih relacija, funkcija, dodatnih shema, tipova, operatora, collation/conversion objekata, foreign servera, event triggera ili default ACL-ova. Samo default public/plpgsql. |
| Konfiguracija | Isti PGDATA/backups mountovi, cijeli kanonski sadržaj mountova, samo očekivana mreža, bez objavljenog DB porta. Server ostaje konfiguriran na izvor; konfiguracija i Traefik dokazi hashom nepromijenjeni. |
| Očuvanost arhive | Točno ime **`immich_failed_20261115t150714z_`**, izvorni OID **16385**, owner/ACL/locale; ponovni snapshot svih **72 tablice**, potpuni metapodaci i sekvence identični referenci; strogi write-probe bez allow-liste. Restart/stat reset/UNKNOWN također blokiraju. |
| F0 | Obavezni markeri i isti jednočlani manifesti, `lb_verify`, gzip obje datoteke, starost izvornog backupa <26 h. Nedostajući manifest nije dopušten INFO/PASS. |
| Završna granica | Ponovljena praznina, nula drugih veza na cilj/arhivu, isti kontejneri i hashovi zaštićenih datoteka te još uvijek NONE neposredno prije završnog zapisa. |

Za mountove se sortira JSON prikaz **cijelog sadržaja svakog mounta**, uz očuvanje svih atributa i duplikata; promjena redoslijeda prolazi, promjena sadržaja ne prolazi. Nije ponovljena greška iz 43.

## Stvarno provjereno na produkciji — samo čitanje

- `lb_verify` za novi ID: **rc 0 / OK**, uz dodatnu provjeru obaju manifesta. Original i `/home` kopija postoje i nose SHA-256 **`25b7780f666822c99bc8bcfc50d3e9c5851f203f29d7149b65d429821d73b0fd`**. Nema novih kopiranja. `INFO no dump manifest yet` očekivan je samo za F0.
- Postojeći novi database OID/owner/ACL/locale očitani su READ ONLY radi zaključavanja policyja; odgovaraju resetu iz 43. **Cijeli novi F2 validator nije pokretan nad produkcijom.** Njegove žive DB/SCRAM/arhivske provjere moraju ponovno proći pri budućem odobrenom izvršenju; dokaz iz 43 nije zamjena.
- Završna zaštitna provjera **16:18:51Z: 10/10 PASS**. Osam kontejnera zadržalo je isti identitet, start, restart count, config hash i kanonske mountove. Redis nije restartan. Svih **137** zaštićenih datoteka identično je referenci; to uključuje prethodne dokaze, dumpove/kopije, novi F0, konfiguraciju i reset reference.
- Server healthy na `postgis/immich`; oba javna URL-a ponovno **HTTP 200 u 16:19:02Z**.
- Stari žurnal `20261115t130331z`: **ROLLED_BACK**, isti tip `c25c344676e5145e9b9cf23a5f74ed40410a5d695adc43a68593e29b3ccb85da`. Novi: **NONE**, bez produkcijskog PREPARED i T_open.
- Produkcijski CUTOVER_APPROVED i F0 token nisu postavljani. Nema izmjena baza, arhive, `.env`, Composea, Redisa ili Traefika; nema stop/restart/recreate, freeze ili kasnijih koraka.

G14 ostaje **PENDING**: verificirani F0 nije F6b. Nema novih frozen dumpova, njihovih kopija ni COPIES_DONE. Stari dumpovi i arhivirana baza ne smiju postati izvor novog restorea.

## Rezultati testiranja

| Skup | Rezultat |
| --- | --- |
| Novi offline F2 test | **146/146 PASS, rc 0**. Pozitivne strukture; nedostajući/neispravni izlazi; strogi booleani i brojači; svaka obavezna tvrdnja pojedinačno rušena; greške Docker/SQL/snapshot/probe/backupa; neuspjeli fsync potvrde; odsutan/pogrešan token. Nijedan takav kvar ne dolazi do PREPARED. |
| Bash konteksti | Direktno, `if`, `&&`, `||`, `!`: pozitivni poziv uspijeva, neuspjeli validator/zapis vraća grešku i testni žurnal ostaje NONE. Ne oslanja se samo na `set -e`. |
| Stvarni izolirani rehearsal | **17/17 PASS, rc 0**. Pet pozitivnih konteksta za stvarni PG16.16/SCRAM, 72 sintetske tablice i jednu sekvencu. Negativno: povišena rola, tablica u cilju, enum bez tablica, nedostajuće ovlasti, pogrešan vlasnik, promijenjena konfiguracija, loš F0 i stvarni UPDATE arhive. Svaki negativni EV ostao je NONE. |
| Postojeći safety test | **352/352 PASS, 0 FAIL**. |
| Završni integrirani offline skup | **ALL OFFLINE CHECKS PASSED, rc 0**, uključujući novi F2 test, backup gate, žurnal i sigurnosne provjere F8. Bash/Python sintaksa prolazi. |

PREPARED je zapisivan **isključivo u izolirane `/tmp/immich-apptest-*` testne žurnale**. Rehearsal je koristio lokalni image, internu testnu mrežu bez portova, zaseban PGDATA, sintetske podatke i lozinke. Server/source stand-in kontejneri služe samo provjeri okoline/identiteta; nije pokretan puni Immich API i nije testiran F3–F10. Testni kontejneri i mreže uklonjeni su; evidencija i fixture direktoriji ostali su sačuvani.

Sačuvane neuspjele iteracije: prvi rehearsal stao je pri testnoj instalaciji vchord prije vector ekstenzije; drugi na fixtureu koji je OID tretirao kao integer, dok PostgreSQL JSON za OID vraća string. Ispravljeni su **testni fixturei**, bez ublažavanja produkcijskih provjera. Treća iteracija 16/16 je prošla, potom je dodana provjera dodatnih objekata i završni rehearsal 17/17. Nijedan raniji FAIL nije izbrisan ili označen PASS-om.

## Kasnije izvršenje — samo uz zasebno odobrenje

Vlasnik mora zasebno odobriti **samo F2 provjeru postojećeg cilja i početni PREPARED za `20261115t150714z`**. Tek tada, u pouzdanom izvršnom kontekstu, pokrenuti ovu jednu naredbu iz `/opt/stacks/data`:

```bash
CUTOVER_APPROVED=20261115t150714z /bin/bash --noprofile --norc /opt/stacks/data/immich-cutover/run_f2_existing.sh
```

**Gornja naredba ovdje nije izvršena.** Driver ne stvara odobrenje sam; bez vanjskog točnog tokena odmah odbija rad. Poziv nema `&&`, `||` ili `eval` wrapper; sve obavezne operacije unutar funkcije dodatno provjeravaju status. Token vrijedi samo za taj proces i uklanja se pri izlazu. Uspjeh mora dati rc 0, novi `checks.json` i valjan žurnal PREPARED. Tada stati; taj poziv ne pokreće F3, freeze niti bilo koji kasniji korak.

Pri bilo kojem FAIL/UNKNOWN, promijenjenom kontejneru/dokazu, isteklom F0 ili neodgovarajućem žurnalu: **HALT**. Ne pokretati originalni `s_prepare_target`, ne prilagođavati policy samo radi PASS-a, ne popravljati ovlasti/lozinke/ekstenzije i ne resetirati cilj bez nove upute. Promjena policyja ili opsega zahtijeva novi pregled i odgovarajuće testove. Pripremljeni F2 ne odobrava novi produkcijski prozor ni F4/F9/F10.

## Evidencija

Privatni audit pripreme: `/opt/stacks/data/backups/immich-f2-preparation-20261115t160950z/`: `lb-verify.out`, `unit-final.out`, `unit-results-final.json`, `safety-selftest.out`, `offline-final.out`, `rehearsal*.out`, putanje svih rehearsala te `production-before.json`, `production-after.json`, `production-final.json`.

Završni izolirani rehearsal: `/tmp/immich-apptest-f2-ha6luwgc/`: `results.json`, `audit.jsonl`, policy, snapshot/probe reference, svaki pozitivni/negativni izlaz i zasebni testni žurnali. Raniji fixturei `/tmp/immich-apptest-f2-pucjlvz1`, `...-x88z17me` i `...-58ty9s7g` sačuvani su.

**Stajem nakon pripreme i izvještaja. Produkcijski F2 i PREPARED nisu izvršeni.**
