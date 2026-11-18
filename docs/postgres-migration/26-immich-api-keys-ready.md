# 26 — Immich: API ključevi spremni (faza 8D)

Datum: 15. studenoga 2026. (Europe/Zagreb). Status: **samo čitanje produkcije; nijedan ključ nije stvoren, opozvan ni mijenjan; nijedna tajna nije ispisana ni zapisana u dokumentaciju ili Git.** Nadovezuje se na [24](24-immich-api-security.md) i [25](25-immich-api-key-setup.md).

## 0. Sažetak

**Svi API ključevi su spremni.** Admin i korisnički ključ spremljeni su u `/root/.immich-cutover-keys.env` (`root:root`, `0600`), metapodaci su točni, stari ključ `all` ne postoji, preflight je 0 FAIL / 0 WARN, a puni baseline s oba ključa je zabilježen. Jedan lažni neuspjeh provjere (`failed` poslovi) ispravljen je u skripti (odjeljak 5).

## 1. Spremanje ključeva

| Provjera | Rezultat |
| --- | --- |
| Čitanje retka `cutover-user-temp-carolina` bez `source` | PASS (jedan redak, 42 znaka, dopušteni znakovi; vrijednost nije prikazana) |
| Zapis u `IMMICH_USER_API_KEY` | PASS (atomski: privremena datoteka 0600 u `/root`, `rename`; privremenih kopija nema) |
| Admin ključ sačuvan | PASS (redak `IMMICH_ADMIN_API_KEY` bajt-za-bajt isti prije i poslije) |
| Datoteka | `/root/.immich-cutover-keys.env`, `root:root`, `0600`; `/root` je `0700` |
| `.example` očišćen | PASS (sva četiri retka su placeholderi, uključujući `cutover-user-temp-carolina`); diff nije prikazan |

## 2. Kopije tajni (samo lokacije i brojevi)

| Područje | Pogodaka (korisnički / admin ključ) |
| --- | --- |
| Git indeks | 0 |
| Git povijest (2 commita, svi refovi) | 0 |
| Radno stablo projekta (bez `backups/` i podataka baza) | 0 |
| Privatna evidencija `backups/` | 0 |
| `/root/.bash_history` | 0 |
| `/home`, `/tmp`, `/var/tmp`, `docs/`, `immich-cutover/` | 0 |
| **VS Code History** | **1 / 1**: `/root/.vscode-server/data/User/History/-6eec6eb5/TMcB.example` (korisnički), `…/XbSt.example` (admin); obje `0600`, vlasnik root |

Povijest uređivača **nije brisana** (traži odobrenje). Preporuka: obrisati te dvije datoteke (i druge `*.example` snimke u istom direktoriju, 9 ih ima) nakon cutovera ili prije, po vašoj odluci. Ključevi nikad nisu bili u Gitu pa rotacija zbog Gita nije potrebna.

## 3. Metapodaci u Immich bazi (bez stupca `key`)

| Ključ | Vlasnik | Dozvole | Rezultat |
| --- | --- | --- | --- |
| `cutover-admin-temp` | Immich Admin (admin) | točno 7: `queue.read queue.update job.create server.about server.statistics library.read library.statistics` | **PASS** |
| `cutover-user-temp-carolina` | Carolina Plaza (običan korisnik, 40.378 asseta, 6 albuma) | točno 3: `asset.read album.read person.read` | **PASS** |
| `API Key` (`all`) | — | — | **ne postoji** (potvrđeno; nema nijednog ključa s `all`) |
| `nextcloud-immich-bridge` | Immich Admin | nepromijenjene dozvole, `createdAt`/`updatedAt` 4.4.2026. | **nepromijenjen** |

U tablici `api_key` su točno 3 retka. `keys_verify_meta` (kriteriji nisu smanjivani; identifikacija je po dozvolama, ne po imenu, pa ime nije trebalo prilagođavati): **3 × PASS, rc 0**. `keys_load`: oba ključa učitana (duljina 42, vrijednost nije prikazana).

## 4. Preflight i puni baseline (samo GET, plus `POST /search/smart` koji ne mijenja podatke)

- `preflight.py`: **PASS, 0 FAIL, 0 WARN** (A1 `server.about` v3.3.5, A2 `queue.read`, A4 nijedan red nije pauziran, A5 `server.statistics`, A6 8 knjižnica, A7 korisnički ključ čita albume).
- `api_checks.py baseline` s oba ključa: zapisan u `/opt/stacks/data/backups/immich-cutover-api-keys-ready-20261115/api-baseline-full.json` (0700/0600). Ponovni `verify` prema njemu: **10/10 PASS**.

### Početno stanje (kontrolna slika 15.11.2026., prije prozora)

| Područje | Vrijednost |
| --- | --- |
| Verzija | v3.3.5 |
| Fotografije / videi / korištenje | 55.535 / 1.306 / 4.453.836.664 B |
| Korisnika s podacima / knjižnica | 8 / 8 (ukupno 56.001 asseta u statistici knjižnica) |
| Albumi (račun Carolina) | 6; broj asseta po albumu: 0, 0, 7, 27, 248, 20.311 |
| Osobe | 792 (0 skrivenih) |
| Pametno pretraživanje | 10 upita, top-20 preklapanje s ponovljenim mjerenjem 1,00 (min i prosjek); topli p95 baseline 314 ms (sada 252 ms); hladni upit 255 ms |
| Redovi | 19 redova: `active`, `waiting`, `delayed` = 0, nijedan pauziran |
| `facialRecognition` | **`failed = 1`** (poznati stari `FacialRecognitionQueueAll` iz 4.4.2026., doc 24); svi ostali redovi `failed = 0` |

Ovo je kontrolna slika. **Pravi baseline cutovera uzima `s_freeze`** nakon što su svi pisci zamrznuti (doc 20); ovaj služi za usporedbu i za provjeru da alati i ključevi rade.

## 5. Ispravak u `api_checks.py` (jedna izmjena)

`verify` je kriterij Q4 imao kao "nijedan neuspjeli posao ni u jednom redu", pa bi s poznatim `failed = 1` pao uvijek (lažni FAIL; vidjelo se pri samoprovjeri). Sada: **nijedan red ne smije imati više neuspjelih poslova nego u baselineu**; red kojeg nema u baselineu računa se kao 0. Tj. `facialRecognition` ostaje 1, ali 2 ili bilo koji neuspjeh u drugom redu i dalje daje FAIL; ako `failed` padne na 0, prolazi. Logika provjerena na četiri slučaja (isti 1 → PASS, 2 → FAIL, drugi red 1 → FAIL, 0 → PASS); `offline_selftest.sh` PASS. Kriterij K13 u doc 17 treba čitati kao "ne više nego baseline (facialRecognition = 1)".

## 6. Preostali GO/NO-GO uvjeti

1. **G14 / O16:** druga kopija na `/home` ne postoji; `s_open` bez nje daje HALT (exit 6). Treba odobrenje i izvršenje `lb_copy_app_backup` (F0), `lb_copy_cutover_dumps` (F6b), `lb_verify`.
2. **G6 neispunjen:** pisano prihvaćanje rizika lokalne RAID1 zaštite (doc 21 §6).
3. **G2, G7, G8, G3, G11:** pragovi (recall 0,90 za `face_index`), termin, retencija izvora 7 dana, odobrenje izmjene `.env`/recreatea i zaštite izvora, osoba za OIDC provjeru, obavijest korisnicima i utišan Uptime Kuma.
4. **O14/O15:** tko izdaje token za ručni GO/NO-GO nakon HALT-a; odobrenje dodatnog kratkog starta servera (API-only, bez rute) u `s_freeze`.
5. Preporuke (nisu blokeri): obrisati kopije ključeva u VS Code povijesti; `chmod 600` na `.env` datotekama (sada 0644); jačanje `POSTGRES_PASSWORD` (8 znakova); `smartmontools` (O17); nakon cutovera i retencije obrisati oba privremena ključa.
6. Neprobano jer postoji samo u produkciji: Traefik, `media-operations` i bridge tijekom cutovera, OIDC, kanarski testovi, stvarni promet.

## 7. Jedna preporučena sljedeća radnja

**Odobriti O16 i izvršiti lokalnu drugu kopiju (F0): `lb_copy_app_backup` + `lb_verify` na `/home/immich-cutover-backups/<ID>`.** To je jedini preostali tehnički uvjet (G14) koji je odmah izvediv, bez prekida usluge, i čiji neuspjeh bi inače zaustavio `s_open`.

## 8. Što je izvršeno

Čitanje metapodataka `api_key` (bez stupca `key`), GET pozivi API-ja, `preflight.py`, `api_checks.py baseline`/`verify`, pretrage `grep -F`/`git grep -F` s uzorcima u privremenoj datoteci (obrisana), `stat`. Pisanje: `/root/.immich-cutover-keys.env` (zamjena jedne varijable), `cutover-keys.env.example` (placeholder), `api_checks.py` (Q4), evidencija u `backups/immich-cutover-api-keys-ready-20261115` (0700) i ovaj dokument. Nije dirano: kontejneri (nijedan zaustavljen ni restartan; `StartedAt` isti), PostgreSQL, Redis, `.env`, Compose, korisnici, ključevi i dozvole; nije pokrenut `immich-db` ni cutover; nijedan backup nije kopiran; nijedan mutirajući korak `steps.sh` nije izvršen.

**Stati ovdje. Produkcijski cutover nije odobren.**
