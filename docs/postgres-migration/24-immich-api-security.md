# 24 — Immich: API sigurnost i baseline (faza 8B)

Datum: 15. studenoga 2026. (Europe/Zagreb).
Status: **samo čitanje produkcije; nijedan ključ nije stvoren, opozvan ni mijenjan; nijedna tajna nije ispisana.** Nadovezuje se na [23](23-immich-final-preflight.md).

## 1. Metapodaci ključa `API Key` (`all`)

Čitani su samo `id`, `name`, vlasnik, vremena i `permissions`. Stupac `key` (hash tajne) nije čitan.

| Polje | `API Key` | `nextcloud-immich-bridge` |
| --- | --- | --- |
| id | `d2910c99-…` | `fcdef253-…` |
| vlasnik | Immich Admin (`isAdmin = true`, jedini admin) | isti račun |
| kreiran / izmijenjen | **15.11.2026. 13:00:25** / isto | 4.4.2026. 20:55:13 / isto |
| dozvole | **`all`** (puni pristup API-ju) | `adminUser.create/read/update`, `library.create/read/update/delete/statistics` |

Zaključak: `API Key` je ključ iz zadnjeg koraka (kreiran dan prije ovog izvještaja, nema drugog novog ključa). Tretira se kao kompromitiran: prikazan je u razgovoru i nosi `all`. Bridge ključ nije povezan s tim i ostaje (nema `queue.*`, `server.*`, ne smije se prenamjenjivati).

## 2. Siguran postupak zamjene admin ključa (izvršava vlasnik; ja ne diram ključeve)

1. U Immich UI-ju prijaviti se kao `Immich Admin` → Account Settings → API Keys.
2. **Prvo izdati zamjenu, zatim opozvati stari** (tako nema razdoblja bez ključa): novi ključ `cutover-admin-temp` s točno ovim dozvolama: `queue.read`, `queue.update`, `job.create`, `server.about`, `server.statistics`, `library.read`, `library.statistics`. Tajnu odmah upisati u `/root/.immich-cutover-keys.env` (odjeljak 6), ne u UI polje za bilješke, ne u razgovor.
3. Obrisati ključ `API Key` (`all`). Opoziv je trenutan.
4. Prijaviti se kao korisnik s podacima (40.378 asseta, 6 albuma) i izdati `cutover-user-temp` s `asset.read`, `album.read`, `person.read`. Upisati u isti `/root` file.
5. Provjera bez tajni: `source immich-cutover/keys_env.sh; keys_verify_meta` mora dati 3 × PASS (točno jedan admin ključ s 7 dozvola, točno jedan korisnički ključ s 3 dozvole na računu s fotografijama i albumima, nijedan `all`). Zatim `keys_load` i preflight s API-jem.
6. Nakon cutovera i retencije obrisati oba privremena ključa.

Napomena: dok god je stari ključ aktivan, ma tko ima njegovu vrijednost ima admin pristup. Sesije i lozinka admin računa nisu dio ovog koraka; ako postoji sumnja da je izložena i lozinka, mijenja se zasebno u UI-ju.

## 3. Korisnički ključ

`asset.read` + `album.read` + `person.read`: **ne postoji.** Postojeća dva ključa pripadaju adminu koji nema nijedan asset ni album. Ključ treba izdati na računu s najviše podataka (40.378 asseta, 6 albuma, 6 imenovanih osoba). Ništa nije stvarano.

## 4. Jedan neuspjeli posao u redu `facialRecognition` (samo čitanje Redisa)

Čitano: `ZRANGE …:failed`, `HGET` polja posla; ništa nije ponovno pokrenuto, obrisano ni mijenjano.

| Polje | Vrijednost |
| --- | --- |
| posao | `FacialRecognitionQueueAll` (naredba "pokreni prepoznavanje lica za sve", `force: false`), ne obrada pojedine slike |
| kreiran / završio neuspjehom | **4.4.2026. 18:58:53 UTC / 19:15:14 UTC** |
| razlog | `job stalled more than allowable limit` (`UnrecoverableError`, BullMQ `worker.js`) |
| opcije | `attempts: 1`, `removeOnFail: false` (zato ostaje zauvijek), TTL ključa −1 |

Procjena: posao je stariji od 7 mjeseci i nastao je na dan prve migracije (4.4.2026., isti dan kad je kreiran bridge ključ) kad je server bio restartan dok je orkestracijski posao radio ("stalled"). Nema veze s cutoverom ni s podacima (ne referencira asset). Nije aktivan, red je prazan. **Preporuka:** ne brisati ga; u K13 prihvatiti **baseline `failed = 1`** za `facialRecognition` (nakon cutovera mora ostati točno 1, bez porasta). Redis se ne dira (nije pri cutoveru, ni ovdje; Redis nema volumen, pa restart bez posljedica briše taj zapis).

## 5. Pretraga stvarnih tajni (vrijednosti nisu prikazane)

Metoda: fiksni uzorci (9 stvarnih vrijednosti: admin ključ iz `/root` datoteke, ključ koji je bio u razgovoru, `DB_PASSWORD` iz okoline kontejnera, tajne iz `/opt/stacks/data/.env`, `postgis-tailscale.env` i `/opt/stacks/immich/.env` koje su ≥ 12 znakova) preko `grep -F`/`git grep -F`, uzorci u privremenoj datoteci 0600 koja je obrisana. Kontrole: pozitivna (uzorak nađen u `/root` datoteci) i negativna (nije u repozitorijskom `.example`) ispravne.

| Područje | Rezultat |
| --- | --- |
| Git indeks i HEAD (praćene datoteke) | **0 pogodaka**; praćena je samo `.env.example` (nema pravog `.env`) |
| Cijela povijest (2 commita, 4 refa, sve revizije) | **0 pogodaka**; reflog 2 zapisa, 0 stashova |
| Radno stablo uključujući neprаćene datoteke (`docs/`, `immich-cutover/`, `immich-app-test/`, bez `backups/` i podataka baze) | **0 pogodaka** |
| Privatna evidencija `backups/` (tekstualne datoteke) | **0 pogodaka** |
| Generički obrasci (privatni ključevi, `tskey-`, `password=`) u praćenim datotekama | 0 |
| `/root/.bash_history` | ključ nije prisutan |
| `.gitignore` | `.env` i `postgis-tailscale.env` ignorirani |

Nalazi koji nisu curenje, ali ih treba znati:
1. **Datoteke s tajnama su `0644` (čitljive svima na hostu):** `/opt/stacks/data/.env`, `/opt/stacks/data/postgis-tailscale.env`, `/opt/stacks/immich/.env`. Preporuka: `chmod 600` (nije izvršeno: ne mijenjam `.env`; promjena prava ne mijenja sadržaj i Compose ih čita kao root, ali to je vaša odluka).
2. **`POSTGRES_PASSWORD` u `/opt/stacks/data/.env` ima samo 8 znakova** (nije otkriven u pretrazi samo zato što je ispod praga uzorka). Slaba lozinka superusera klastera; zaseban zadatak jačanja (izvan cutovera, traži promjenu lozinke i `.env`).

## 6. Pohrana novih ključeva samo u `/root` (0600)

- Datoteka: `/root/.immich-cutover-keys.env` (root:root, 0600; `/root` je 0700), izvan repozitorija; već postoji s placeholderima i admin vrijednošću koju treba zamijeniti novim ključem.
- Nova skripta `immich-cutover/keys_env.sh` (testirana):
  - `keys_new_file`: stvara datoteku s placeholderima 0600, **nikad ne prepisuje** postojeću;
  - `keys_load`: odbija ako vlasnik nije root ili prava nisu točno 0600, odbija datoteku u `/opt/stacks` ili `/tmp`, prihvaća samo znakove `A–Z a–z 0–9 _ -` duljine 20–128 (bez navodnika i razmaka), placeholder tretira kao nepostavljeno, ispisuje samo ime i duljinu (**nikad vrijednost**);
  - `keys_verify_meta`: čita samo metapodatke `api_key` (bez stupca `key`) i traži točno jedan admin ključ s 7 dozvola, točno jedan korisnički s 3 na računu s fotografijama i albumima, nijedan `all`.
- Rezultat danas: `keys_load` OK za admin (duljina 43), korisnički ne postavljen; odbijanja radi (prava 0644, datoteka u repozitoriju, prepisivanje); `keys_verify_meta` **FAIL ×3** (očekivano: nema 7-dozvolnog admin ključa, nema korisničkog, postoji `all`).
- `.example` u repozitoriju sadrži samo placeholdere; ključ se nikad ne upisuje u njega (greška iz prethodnog koraka je ispravljena).

## 7. Što je izvršeno

Samo čitanje: `api_key` metapodaci, Redis (`ZRANGE`, `HGET`, `TTL`, `TYPE`, `SCAN`), `git grep`/`grep -F`, `stat`. Dodana datoteka `immich-cutover/keys_env.sh` i ovaj dokument. Nije stvoren, opozvan ni mijenjan nijedan API ključ, korisnik ili dozvola; nijedan Redis red nije mijenjan; nijedna tajna nije ispisana; nije pokrenut `immich-db` ni cutover; nijedan backup nije kopiran.

## 8. Što vlasnik treba napraviti (točno)

U Immich UI-ju kao `Immich Admin`: izdati admin ključ `cutover-admin-temp` s točno 7 dozvola (`queue.read queue.update job.create server.about server.statistics library.read library.statistics`), upisati ga u `/root/.immich-cutover-keys.env` (zamijeniti postojeću vrijednost), **zatim obrisati ključ `API Key` (`all`)**, i na računu s 40.378 asseta izdati `cutover-user-temp` (`asset.read album.read person.read`) i upisati ga u isti file. Zatim javiti "spremljeno".

**Stati ovdje. Produkcijska migracija nije odobrena.**
