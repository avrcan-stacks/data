# 25 — Immich: postavljanje API ključeva (faza 8C)

Datum: 15. studenoga 2026. (Europe/Zagreb). Status: **nijedan ključ nije stvoren, opozvan ni mijenjan; nijedna tajna nije ispisana ni zapisana u dokumentaciju ili Git.** Nadovezuje se na [24](24-immich-api-security.md).

## Sažetak

| Pitanje | Odgovor |
| --- | --- |
| Je li admin ključ sigurno spremljen? | **Da.** Preneseno parsiranjem (bez `source`) u `/root/.immich-cutover-keys.env` kao `IMMICH_ADMIN_API_KEY`; `root:root`, `0600` (atomski zapis, nema privremenih datoteka). Format provjeren (42 znaka, dopušteni znakovi); vrijednost nije prikazana. |
| Jesu li dozvole ispravne? | **Da.** Ključ `cutover-admin-temp`, vlasnik Immich Admin (admin račun), točno 7 dozvola: `job.create library.read library.statistics queue.read queue.update server.about server.statistics`. Hash ključa nije čitan. |
| Je li `.example` očišćen? | **Da.** Redak `cutover-admin-temp=` vraćen na placeholder; ostali redci su placeholderi. Diff nije prikazan. |
| Postoji li stari ključ s punim pravima? | **DA.** `API Key` (`all`, kreiran 15.11. 13:00) i dalje postoji. **Treba ga opozvati (vlasnik); nisam ga brisao.** |
| Postoji li korisnički ključ? | **NE.** `cutover-user-temp` ne postoji (nijedan ključ nema `asset.read album.read person.read`). |

## 1. Prijenos i čišćenje

- Izvor: redak 4 u `immich-cutover/cutover-keys.env.example` (ime retka `cutover-admin-temp`, vrijednost 42 znaka). Ciljna varijabla: `IMMICH_ADMIN_API_KEY` u `/root/.immich-cutover-keys.env` (stara vrijednost u toj datoteci, 43 znaka, zamijenjena novom). Ništa se nije izvršavalo iz datoteke (`source` nije korišten).
- `.example` je sada samo predložak s placeholderima. U njega se ključ više ne upisuje.

## 2. Pretraga tajne (samo brojevi pogodaka)

| Područje | Pogodaka |
| --- | --- |
| Git indeks (praćene datoteke) | 0 |
| Povijest (2 commita, svi refovi) | 0 |
| Radno stablo projekta (bez `backups/` i podataka baze) | 0 |
| Privatna evidencija `backups/` (tekst) | 0 |
| `/root/.bash_history` | 0 |
| Ostale datoteke u `/root` (osim ključne datoteke) | **1** |

Ključ **nikad nije bio commitan** ni u Git povijesti pa incident rotacije zbog Gita nije potreban.

**Nalaz:** jedna kopija ključa postoji u povijesti uređivača **VS Code** (`/root/.vscode-server/data/User/History/…/*.example`, 274 B, `0600`, vlasnik root). Nastala je kad je ključ upisan u `.example` u IDE-u. Nije u Gitu i nije dostupna drugim korisnicima, ali je to druga kopija tajne na disku. Preporuka: obrisati tu jednu datoteku povijesti (vlasnik ili uz moje odobrenje; ja je nisam dirao). Ključ je privremen i bit će obrisan nakon cutovera.

## 3. Read-only API provjere novog ključa

Ključ je učitan u okolinu (`keys_load`, ispisuje samo duljinu) i korišteni su samo GET pozivi:

- `preflight.py` s API-jem: **0 FAIL, 1 WARN** (A1 `server.about` v3.3.5, A2 `queue.read`, A4 nijedan red nije pauziran, A5 `server.statistics`, A6 popis 8 knjižnica). WARN A7: korisnički ključ nije postavljen.
- `api_checks.py baseline` (samo admin dio): uspješno (55.535 fotografija, 1.306 videa, 8 knjižnica s `library.statistics`); preskočeni su albumi, osobe i pametno pretraživanje.
- Preskočeno namjerno (mutiraju): `queue.update` (pauza) i `job.create` (backup); te dvije dozvole potvrđene su samo metapodacima, a stvarno će se prvi put koristiti u `s_freeze` i F11.
- Red `facialRecognition` i dalje ima 1 stari neuspjeli posao (baseline `failed = 1`, doc 24).

## 4. Korisnik s fotografijama i albumima

`cutover-user-temp` ne postoji. Treba ga izdati na računu s 40.378 asseta, 6 albuma (kao ranije, doc 24 §3).

## 5. Preostali GO/NO-GO blokeri (doc 20–24)

1. **Opozvati `API Key` (`all`)**, ključ koji je bio izložen u razgovoru (vlasnik u UI-ju; ja ne brišem).
2. **Izdati `cutover-user-temp`** (`asset.read album.read person.read`) i upisati ga u `IMMICH_USER_API_KEY`; zatim `keys_verify_meta` mora dati 3 × PASS i preflight s oba ključa (A7 bez WARN-a, puni baseline).
3. **G14 / O16:** druga kopija na `/home` još ne postoji (`s_open` bez nje daje HALT, exit 6).
4. **G6 neispunjen:** pisano prihvaćanje rizika lokalne RAID1 zaštite.
5. **G2, G7, G8, G3, G11:** pragovi (recall 0,90 za `face_index`; K13 s baselineom `failed = 1`), termin, retencija 7 dana, odobrenje `.env`/recreatea, osoba za OIDC, obavijest korisnicima i monitoring.
6. **O14/O15:** tko izdaje token nakon HALT-a; dodatni kratki start servera u `s_freeze`.
7. Preporuke: obrisati kopiju ključa u VS Code povijesti; `chmod 600` na `.env` datotekama (0644); jačanje `POSTGRES_PASSWORD` (8 znakova); O17 `smartmontools`.
8. Neprobano jer postoji samo u produkciji: Traefik, `media-operations` i bridge tijekom cutovera, OIDC, kanarski testovi, stvarni promet.

## 6. Što je izvršeno

Čitanje metapodataka `api_key` (bez stupca `key`), GET pozivi API-ja, `preflight.py`, pretrage `grep -F`/`git grep -F` s uzorkom u privremenoj datoteci (obrisana). Pisanje: samo `/root/.immich-cutover-keys.env` (zamjena jedne varijable), `cutover-keys.env.example` (placeholder), evidencija preflighta (0700) i ovaj dokument. Nije dirano: korisnici, dozvole, ključevi (nijedan nije stvoren ni obrisan), baze, `.env`, Redis; nije pokrenut `immich-db` ni cutover; nijedan backup nije kopiran.

**Stati ovdje. Produkcijska migracija nije odobrena.**
