# 40 — Immich: sigurnosni popravci nakon R1

Datum: 15. studenoga 2026., UTC. Opseg: kod i izolirani testovi. **Novi produkcijski cutover nije pokrenut.** Produkcija ostaje na `postgis/immich`, javni ping HTTP **200**, prethodni žurnal **ROLLED_BACK**.

## Uzrok lažno uspješnog F8

Dokaz iz [37](37-immich-cutover-f8-dark-launch.md): obavezni `api_checks.py verify` pao je jer `IMMICH_ADMIN_API_KEY` nije bio učitan. `s_dark_launch` nije izričito provjeravao povratni kod, pa je nastavio do zapisa `DARK_VERIFIED` i poruke OK. Naknadni API PASS nije dokaz ispravnosti toga koraka.

Bash isključuje djelovanje `errexit` u funkcijama pozvanim u `if`, `&&`, `||` ili negiranom uvjetu, uključujući unutarnje podljuske koje ponovno postave `set -e`. Taj mehanizam nastavka reproduciran je izoliranim testovima. **Točan povijesni vanjski wrapper koji je izazvao ignoriranje `errexit` nije dokazan dostupnom evidencijom**; ne pripisujemo ga određenoj naredbi bez dokaza. Dokazani programski nedostatak bio je oslanjanje na `set -e` umjesto provjere obaveznog rezultata.

## Kritični nalazi i popravci

| Nalaz | Ispravak |
| --- | --- |
| Nezaštićeni API, Docker, SQL, dump/restore, snapshot, usporedba, validator, hash i zapis žurnala mogli su se preskočiti nakon greške u uvjetnom kontekstu. | Izričiti `||` prekidi, `_must`, `_expect`, provjerene dodjele i propagacija statusa. `set -e` ostaje samo dodatna zaštita. |
| API GET/POST pogreške mogle su postati prazne vrijednosti; bez korisničkog ključa Q6–Q10 bili su preskočeni uz WARN/PASS. | Oba ključa obavezna, HTTP 200 i potpuna struktura baselinea/rezultata obavezni; prazni redovi i neispravni brojači odbijeni. Q1–Q10 moraju postojati. |
| Sam exit 0 ili stari API izlaz nisu dovoljan dokaz uspjeha. | Svaka verifikacija proizvodi novu datoteku `api-result.XXXXXX.json`; zasebni parser zahtijeva Q1–Q10 PASS, 0 FAIL, 0 WARN i valjan uzorak. Prazan, neispravan ili nepotpun rezultat zaustavlja korak. |
| Povijesni `DARK_VERIFIED` mogao je postojati bez API dokaza. | F8 izrađuje `dark-verified.json` s identitetom pokušaja/cilja i SHA-256 API dokaza, baselinea, snapshotova i DB dokaza. F10 provjerava cijeli skup prije promjene konfiguracije ili kontejnera. Ponovljeni F8 arhivira prethodnu potvrdu prije rada. |
| Zanemarivanje `docker stop` u abortu i ručnim putanjama. | Obavezan uspješan stop i `Running=false`; greška odmah prekida rad. Nema nastavka prema uspješnom stanju. |
| Greška SQL-a, čitanja ACL-a ili Docker inspecta mogla je biti skrivena usporedbom izlaza. | Status i vrijednost provjeravaju se odvojeno; ACL dokaz mora postojati prije odmrzavanja. |
| Neuspješan `find` mogao je izgledati kao da nema novih datoteka; process substitution skrivao je status usporedbe `.env`. | Provjereni statusi T0/find/hash poziva; `.env` se provjerava točnom transformacijom bajtova u Pythonu. |
| Dva neuspjela TOC poziva mogla su dati jednake nule. | Oba `pg_restore --list` moraju uspjeti, dati neprazan i jednak TOC. Hashiranje, kopiranje i zapis manifesta izričito provjereni. |
| `keys_load` mogao je završiti uspješno nakon ranije neispravne vrijednosti. | Jedinstven zapis svakog ključa, kumulativni status; pri neispravnom sadržaju oba se izvoza uklanjaju i vraća se greška. |
| Neuspješna negativna provjera lozinke nije razlikovala odbijenu lozinku od Docker/mrežne greške. | F2 i V6 traže psql rc 2 i poruku `password authentication failed`. Produkcijski `--skip-login` je zabranjen. |
| Kratak zapis žurnala ili nedovršena pohrana nije bio izričito otkriven. | Provjera broja zapisanih bajtova, fsync žurnala/stanja/direktorija i ponovno čitanje prije uspješnog povratka. Format postojećeg hash lanca ostaje isti. |
| Ponavljanje koraka moglo je prepisati dump ili ukloniti raniji abort snapshot. | Postojeći dumpovi/manifesti odbijaju prepisivanje; raniji snapshotovi i oznake vremena arhiviraju se, novi abort snapshot dobiva jedinstveni direktorij. |

## Audit funkcija i očuvanje R1

Pregledane i zaštićene sve tražene funkcije: `s_prepare_target`, `s_freeze`, `s_dump_source`, `s_bridge_sanitize`, `s_bridge_cleanup`, `s_restore_target`, `s_validate_target`, `s_restore_and_validate`, `s_dark_launch`, `s_open`, `s_open_abort`, `s_manual_forward`, `s_manual_rollback_accept_loss`, `s_rollback_r1`, `s_unfence`, `s_target_reset_after_rollback`.

Žurnal se verificira prije mutirajućih koraka. G14 ostaje prije promjena u `s_open` i `s_manual_forward`. SQL, ACL, snapshot/compare/delta, sonde pisanja, redovi i prijelazi stanja sada provjeravaju povratne kodove. Kod prekida ne upisuje se sljedeće uspješno stanje i ne ispisuje se završni OK koraka.

Dokazani redoslijed R1 iz [38](38-immich-cutover-rollback-r1.md) i [39](39-immich-r1-result.md) ostaje: stop dark servera → potvrda stopped → `s_unfence`/SQL/ACL diff → recreate na izvoru → health/route/DB hostname → pomoćni servisi → resume redova → potpuna API provjera → provjeren zapis `ROLLED_BACK`. U produkciji se ne može koristiti `R1_SKIP_VERIFY`; nedostajući baseline dopušten je samo u dokumentiranom ranom stanju `FREEZING`. Izostanak `env.after.sha256` prije izmjene `.env` ostaje valjan slučaj ranog aborta; postojeća nečitljiva datoteka nije dopuštena zamjena za taj slučaj.

## Izmijenjene datoteke

- `immich-cutover/steps.sh`: svih 16 funkcija, pomoćne provjere i F8/F10 dokaz.
- `api_checks.py`, novi `safety_evidence.py`: strogi API baseline, rezultat i provjera povezanih dokaza.
- `cutstate.py`, `keys_env.sh`, `local_backup.sh`, `validate_target.py`: propagacija grešaka, pohrana žurnala, ključevi, backup/TOC/hash i kontrola prijave.
- `tests/safety_selftest.py` (novo), `tests/offline_selftest.sh`: izolirane injekcije grešaka i uključivanje u postojeći selftest.
- `rehearsal/rehearse.py`: nove grupe `gHardening`/`gHardeningReview`, učitavanje isključivo testnih ključeva iz privatnog testnog stanja, zaseban identifikator svakog testnog izvođenja. Povijesni neuspjesi ostaju sačuvani.

Produkcijski Compose, `.env`, baze i API ključevi nisu mijenjani.

## Negativni testovi

**352/352 provjera PASS**, `safety-results-final.json`/`.out`. Nema pristupa Docker izvršnoj datoteci: vanjske operacije su nadomještene, žurnal i parsiranje rezultata stvarni. Svaki slučaj ima zasebnu `/tmp/immich-apptest-*` okolinu i testni ID.

Pokriveni su nedostajući API ključ, API verify rc 1, neispravan/prazan rezultat uz rc 0, neuspješan dump/restore, validator FAIL, snapshot/compare/delta/probe greške, SHA-256 mismatch, `lb_verify` i G14 greške, Docker stop/start/recreate/inspect/health/logs, SQL/ACL greška te greška zapisa žurnala. Testirane su sve navedene funkcije i pozivi samostalno, u `if`, `&&`, `||` i negiranom kontekstu. Dodatno: neispravan baseline, HTTP/queue odgovori, ključ koji nedostaje ili je dupliciran/neispravan, izmjena svakog F8 dokaza, pogrešan identitet/cilj i kratak zapis žurnala.

Za kvarove se traži nenulti status, izostanak završnog OK i nedopuštenog uspješnog prijelaza te očuvanost postojećih dumpova. Prije otvaranja nema nove javne rute. Kod kasnog R1 kvara izvorna ruta već može biti vraćena dokumentiranim redoslijedom; test izričito dopušta samo rutu prema **izvoru**, nikad prema novoj bazi. Ne tvrdimo da kasni kvar može poništiti već izvedenu operaciju.

Ranije iteracije testova sačuvane su: nakon dodavanja F8 potvrde, stari mock nije ponovno stvarao arhivirani `dst2`; drugi fixture je unaprijed postavljao sanitizirani dump koji novi korak ispravno odbija prepisati. Ti testovi stali su na ranijoj zaštiti umjesto na namjeravanoj injekciji. Fixturei su ispravljeni, nije zaobiđena zaštita. Konačni rezultat gore sadrži provjeru dosezanja namjeravanog kvara.

`offline_selftest.sh`: **rc 0, ALL OFFLINE CHECKS PASSED**, uključujući postojeće provjere žurnala, write probea, 46 backup provjera i novu sigurnosnu matricu. `bash -n` i kompilacija Python datoteka prolaze.

## Izolirani rehearsal

Stack: `immich-apptest-20261115t143953z-bc35b4`; novi testni ID `rehHard144303`. Privatni dokazi: `/opt/stacks/data/backups/immich-rehearsal-20261115t143953z-bc35b4`. Interna mreža, bez produkcijskih mountova/ključeva/portova. Korišten postojeći `setup_stack.py`, `rehearse.py` i teardown.

- F4 → F5 → F6 → F6b → F7 → F8 prošli; 72 tablice uspoređene, validator **22 provjere, 0 FAIL/0 WARN**.
- F8 bez admin ključa u `if` završio HALT-om prije recreatea; stanje ostalo `VALIDATED`, testni sustav nepromijenjen.
- F8 s oba testna ključa prošao, cjelovit API dokaz i F8 potvrda postoje; stanje `DARK_VERIFIED`.
- Svih 13 postojećih G14 negativnih scenarija blokiralo otvaranje uz nepromijenjeni `.env`, kontejnere, žurnal i izvor. Stroga sonda izvora nakon tih testova PASS.
- R1 iz `DARK_VERIFIED` u `if` prošao do `ROLLED_BACK`; aplikacija na testnom izvoru, pomoćni servisi rade, API baseline prolazi, nova testna baza i kopije sačuvane. Testni Redis nije restartan. Daljnji `s_open` odbijen nakon rollbacka.
- Završna grupa `gHardeningReview`: **18/18 PASS, rc 0**. Ponovno provjerila dokaze dovršenog prolaza i stvarni G14, zatim potvrdila da F10 s nedostajućom ili neispravnom F8 potvrdom ne radi nikakvu promjenu ni kad G14 prođe.

Povijest `gHardening` sadrži **55 PASS i 1 raniji FAIL**: prvi poziv preflighta ispravno je stao jer testni driver nije učitao testne ključeve. Driver je ispravljen i nastavljen iz `PREPARED`, prije zamrzavanja. Svi koraci ponovljenog prolaza prošli su. Stari zbirni kod još je brojao povijesni FAIL pa je taj proces završio rc 1; sada se rezultat računa po izvođenju, bez brisanja povijesti. Zasebna završna grupa vratila je rc 0. Jedini preflight WARN: nedostajući `fixture/data/docker-compose.yml` za usporedbu testne konfiguracije, ne produkcijski kvar.

Audit ima **1024 zapisa**, bez produkcijskih kontejnera, produkcijskih mountova ili `docker.sock` među ciljanim argumentima. Audit pokriva setup i naredbe koraka; pojedina izravna očitanja testnog drivera koriste imena iz testnog `state.json` i nisu uključena u taj broj.

Teardown je uklonio isključivo ovaj testni stack, njegovu mrežu i `/tmp` radni direktorij; **dokazi u backups ostaju**. Produkcijski `immich-db` nije diran.

## Potvrda produkcije

Usporedba prije/poslije: **7 kontejnera identičnih Id/StartedAt/Running/RestartCount**, identični hashovi konfiguracije i ključeva te **107 datoteka** prethodnih cutover dokaza i `/home` kopija; razlike **[]**. U 14:58:15 UTC: stari žurnal valjan `ROLLED_BACK`, server `DB_HOSTNAME=postgis`, javni ping **HTTP 200**.

Nisu izvršeni produkcijski SQL/API mutirajući pozivi, stop/start/restart/recreate, F9/F10, novi cutover, reset žurnala, promjena produkcijskog ID-a, postavljanje njegova `CUTOVER_APPROVED`, brisanje ili prepisivanje produkcijskih dumpova/backupova/dokaza. Produkcijski Redis nije mijenjan. Produkcija je bila aktivna; ovo nije tvrdnja da se korisnički sadržaj prirodnim radom nije mogao mijenjati.

## Preostali rizici i preporuka

**Nema otvorenog novog BLOCKER-a u provjerenim popravcima.** Kod je tehnički spreman za novi, zasebno odobren pokušaj uz svježi preflight. Ovo nije produkcijski GO.

Ostaje dokumentirani dizajn djelomičnog otvaranja: Docker recreate može uključiti rutu prije nego naknadni healthcheck ili zapis žurnala završi. Nakon takvog kvara promet nije nužno zatvoren; potreban je dokumentirani `s_open_abort`, a pri pisanju ili nejasnoći HALT i ručna odluka. Taj redoslijed nije mijenjan. Rehearsal ne dokazuje stvarni Traefik, OIDC, promet mobilnih klijenata, fizički kvar diska ni `kill -9` u svakom trenutku. Lokalni hashovi/RAID1 nisu off-host zaštita; ranije prihvaćena strategija nije mijenjana.

Sljedeći pokušaj zahtijeva **novi CUTOVER_ID, novi žurnal, novi preflight, novi dump nakon zamrzavanja, ponovno provjerene backupove i izričito odobrenje vlasnika**. Postojeći produkcijski `immich-db` ostaje sačuvan; njegovo ponovno inicijaliziranje traži zasebno odobrenje. Prethodno produkcijsko stanje `ROLLED_BACK` nije resetirano niti su mu dodavani novi koraci.

## Evidencija i reproducibilnost

Privatna evidencija ovog rada: `/opt/stacks/data/backups/immich-hardening-20261115t143625z` (novi direktorij, odvojen od prethodnog cutovera). Sadrži `source-before/`, hashove završnog koda, `production-before.json`, `production-after.json`, `production-result.json`, sve iteracije izlaza testova, konačnu sigurnosnu matricu, setup/rehearsal/review/teardown izlaze. Nisu zapisivane vrijednosti produkcijskih ključeva.

Ključne naredbe (izolirani rad, bez produkcijskog odobrenja):

```bash
bash -n immich-cutover/steps.sh immich-cutover/local_backup.sh immich-cutover/keys_env.sh
python3 -I immich-cutover/tests/safety_selftest.py <novi-evidence>/safety-results-final.json
bash immich-cutover/tests/offline_selftest.sh
python3 -I immich-cutover/rehearsal/setup_stack.py setup
python3 -I immich-cutover/rehearsal/rehearse.py <novi-rehearsal> gHardening
python3 -I immich-cutover/rehearsal/rehearse.py <novi-rehearsal> gHardeningReview
python3 -I immich-cutover/rehearsal/setup_stack.py teardown <novi-rehearsal>
```

**Rad završen. Produkcijska migracija nije pokrenuta.**
