# 45 — Immich drugi pokušaj: produkcijski F2 dovršen

15. studenoga 2026., UTC. **CUTOVER_ID=`20261115t150714z`**.

**Odobreni F2 izvršen je jednom, rc 0. Novi žurnal ima jedan valjan prijelaz NONE → PREPARED.** Neovisna završna provjera: **31/31 PASS, rc 0**. Immich ostaje dostupan na `postgis/immich`; javni `/` i `/api/server/ping` vraćaju **HTTP 200**. F3 i kasniji koraci nisu pokrenuti.

## Vrijeme i opseg

| Događaj | UTC |
| --- | --- |
| Prvo `date -u`, početak rada | **2026-11-15 16:41:58Z** |
| Neposredni evidencijski zapis prije odobrenog poziva | **16:44:37.231283Z** |
| `checks.json` trajno zapisan | **16:45:18.179683Z** |
| Žurnal PREPARED | **16:45:18Z** |
| Povratni kod drivera 0 evidentiran nakon završetka | **16:45:34.103809Z** |
| Neovisne završne provjere dovršene | **16:45:49.672463Z** |

Provjere i izvršenje trajali su približno **3 min 52 s** od prvog očitanja do završnog PASS-a. Evidencijski interval oko drivera je približno **57 s**; završni trenutak u toj brojci označava očitanje/evidentiranje rezultata, ne zasebno izmjeren trenutak izlaska procesa.

Pročitani dokumenti [17](17-immich-production-cutover.md), [40](40-immich-cutover-safety-hardening.md), [41](41-immich-second-attempt-readiness.md), [42](42-immich-second-attempt-f0.md), [43](43-immich-second-attempt-target-reset.md) i [44](44-immich-second-attempt-f2-preparation.md), te stvarni `steps.sh`, `prepare_existing_target.py`, `run_f2_existing.sh` i zaključani policy.

**9/9 hashova** koda/testova/policyja/dokumentacije odgovara `reviewed-source-hashes.json` iz pripreme 44. Ostale hardening ovisnosti također su provjerene prema referenci iz 40; očekivane prethodno dokumentirane izmjene steps/offline testa provjerene su novijom referencom iz 44. Kod, policy i pragovi nisu mijenjani.

## Aktualni preduvjeti — svi PASS

Prije drivera izvedena je zasebna read-only provjera: **22/22 PASS, rc 0**, uključujući cijeli testirani validator bez poziva `execute()`/`--prepare` i bez zapisa PREPARED. Driver je zatim ponovno izvršio sve svoje žive provjere.

| # | Preduvjet | Rezultat |
| --- | --- | --- |
| 1 | Prethodni žurnal | **ROLLED_BACK**, valjan lanac, 9 zapisa; identičan zaključanom tipu lanca. `cutstate.py verify` rc 0. |
| 2 | Novi žurnal prije poziva | **NONE**, bez ranijeg PREPARED; `cutstate.py verify` rc 0. |
| 3 | F0 original i `/home` kopija | Postoje; `lb_verify` unutar provjerenog F0 postupka **rc 0** prije izvršenja, ponovno u driveru i nakon njega. Manifesti/markeri i gzip provjere prolaze. |
| 4 | Starost izvornog aplikacijskog backupa | Oko **15,71 h** pri prechecku, manje od 26 h. |
| 5 | Produkcijski Immich | Healthy, server konfiguriran na **postgis/immich**, ne cilj. |
| 6 | Javni URL-ovi | `/` i `/api/server/ping` **HTTP 200**, prije i poslije. |
| 7 | Bridge / media-operations | Oba running/healthy prije i poslije. |
| 8 | Redis | Healthy, isti Id i StartedAt **2026-06-26T21:46:10.698303676Z**, restart count **0**. |
| 9 | Cilj | `immich-db` healthy, isti kontejner/start/config; PostgreSQL točno **16.16**, očekivane dostupne ekstenzije, vchord preload, bez dostupnog PostGIS-a. |
| 10 | Nova `immich` | Prazna; točan OID **129819**, owner `immich`, ACL i UTF8/en_US.utf8. Nema dodatnih korisničkih objekata; samo plpgsql 1.0. |
| 11 | Arhiva | `immich_failed_20261115t150714z_`, OID **16385**, isti owner/ACL/locale; 72 tablice, 57.627 asseta. Potpuni snapshot/hashovi/metapodaci/sekvence jednaki reset referenci; strogi write-probe C0–C5 PASS. |
| 12 | Rola `immich` | Postojeći OID, LOGIN/INHERIT, bez povišenih ovlasti i članstava; SCRAM verifier, očekivane efektivne DB/schema ovlasti. |
| 13 | SCRAM | Mrežni pozitivan login **rc 0**, točno immich; negativan **rc 2** uz potvrđen `password authentication failed`; HBA/password_encryption ispravni. Tajne nisu ispisane ili zapisane. |
| 14 | Kontejneri/mountovi/config i dokazi | Svih 8 kontejnera i **137 zaštićenih datoteka** odgovara policyju prije i poslije. Mountovi uspoređeni kanonski po cijelom sadržaju, uz očuvanje duplikata. |
| 15 | Operativni token | Prije izvršenja **CUTOVER_APPROVED nije postojao u okolini**. Točan token dodijeljen samo jednom driver procesu; potvrđeno uklanjanje pri izlazu i odsutnost u roditeljskoj okolini. |

## Jedino produkcijsko izvršenje

Iz `/opt/stacks/data` pokrenuto je točno:

```bash
CUTOVER_APPROVED=20261115t150714z /bin/bash --noprofile --norc /opt/stacks/data/immich-cutover/run_f2_existing.sh
```

Naredba je bila samostalna, bez `if`, `&&`, `||`, `eval` ili Bash wrappera. **Stvarni povratni kod procesa: 0. Broj izvršenja: 1.** Originalni `s_prepare_target` nije pozvan. Sve provjere drivera prošle su; završni izlaz:

```text
F2 existing target PASS; PREPARED
s_prepare_existing_target OK
F2_RC=0; PREPARED verified; approval token removed. STOP.
```

Driver je stvorio jedan novi privatni direktorij:

`/opt/stacks/data/backups/immich-cutover-20261115t150714z/f2-existing-jyqh0oab/`

U njemu je **checks.json**, status `CHECKS_PASSED`, točan ID, `requested_prepare=true`, UTC iz tablice, prava **0600**. Kod je prije zapisa žurnala izvršio flush/fsync potvrde i direktorija. Neovisno su provjereni svježina, sadržaj i prava potvrde.

SHA-256 `checks.json`:

`27ca077229580de68f5f0dbe06c580d2dc24ad3529e4141f614d1f3f86fae945`

## Završno stanje i očuvanost

- Novi žurnal: **PREPARED**, jedan zapis `seq=1`, `from=NONE`; hash lanac valjan i neovisni CLI verify rc 0. Tip lanca **`75f4335c5151bc722ae0eb249c558c2bc89db4659cfe139b7d84f9c60e5c6a75`**. Nema drugih novih prijelaza.
- Prethodni žurnal: **ROLLED_BACK**, 9 zapisa, isti tip **`c25c344676e5145e9b9cf23a5f74ed40410a5d695adc43a68593e29b3ccb85da`**. Nije mijenjan.
- Nova `immich` nakon drivera: **0 korisničkih tablica, 0 public relacija, 0 public funkcija**, samo `plpgsql 1.0`; identitet/owner/ACL/locale nepromijenjeni.
- Arhiva nakon drivera: **72 tablice, 57.627 asseta**, isti OID/ACL/locale. Driverov novi snapshot za svih 72 tablice, metapodatke i sekvence neovisno uspoređen s referencom. Nova post-F2 stroga sonda pisanja ponovno **C0–C5 PASS**, bez allow-liste.
- Produkcijski server i dalje **postgis/immich**, healthy; oba javna URL-a HTTP 200. Bridge i media-operations healthy. Redis nije restartan.
- Svi kontejneri zadržali su Id/StartedAt/restart count/config hash/mountove/mreže. `.env`, Compose i Traefik konfiguracija hashom nepromijenjeni.
- Svih **137** zaključanih datoteka identično prije/poslije. Dodatno, svih **14 aplikacijskih `.sql.gz` backupova** ima isti skup putanja, SHA-256, veličine, mtime, vlasnika i prava prije/poslije. Stari dumpovi, `/home` kopije i dokazi ostali su očuvani.

**F0 PASS; G14 PENDING.** Original i kopija F0 nose isti SHA-256 `25b7780f666822c99bc8bcfc50d3e9c5851f203f29d7149b65d429821d73b0fd`. F6b nije izvršen: novi dumpovi, njihovi manifesti i COPIES_DONE ne postoje. T0 i T_open također ne postoje. PREPARED nije odobrenje nastavka migracije.

## Odstupanje pomoćne evidencije

Prvi alatni poziv uspješno je pokrenuo driver kao proces **65910**. Pomoćni JavaScript zapis pokušao je odmah spremiti još nedostupan povratni kod procesa koji je tada još radio; spremanje vrijednosti `undefined` alat je odbio. **To nije bio nenulti izlaz drivera.** Identifikator procesa prethodno je bio sačuvan, pa je praćen isti proces do stvarnog **rc 0**. Driver nije prekinut ili ponovno pokrenut. Njegov potpuni izlaz i konačni status sačuvani su. Nema drugih utvrđenih odstupanja ili neuspjelih produkcijskih provjera.

## Evidencija i granica izvršenja

Privatni audit: `/opt/stacks/data/backups/immich-f2-execution-20261115t164218z/`:

- `code-identity.json`, `precheck.py`, `precheck.out`, `precheck.json`, `precheck-evidence/`.
- `app-backups-before.json`, `before-driver.json`, `driver.out`, `execution.json`.
- `postcheck.py`, `postcheck.out`, `postcheck.json`, `archive-post-probe.json`.
- Novi F2 direktorij u `$EV` sadrži `checks.json`, `archive-snapshot/` i `archive-probe.json`.

Izvršene su samo odobrene read-only provjere, pisanje novih dokaza/izvještaja i jedan početni PREPARED. Nisu mijenjane baze, podaci ili role; nisu pokrenuti CREATE ROLE/DATABASE, target reset, freeze, restore, F3/F4/F8/F9/F10, Docker lifecycle operacije, Redis restart ni Git commit/push/PR.

**Nakon F2 stajem. Svaki nastavak zahtijeva novu uputu vlasnika.**
