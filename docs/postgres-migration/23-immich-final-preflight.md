# 23 — Immich: završni preflight prije cutovera (faza 8A)

Datum: 15. studenoga 2026. (Europe/Zagreb).
Status: **samo čitanje; ništa nije stvoreno, promijenjeno ni kopirano; cutover nije odobren ni pokrenut.** Nadovezuje se na [17](17-immich-production-cutover.md)–[22](22-immich-backup-gate.md). U dokumentu nema nijedne tajne.

## 0. Sažetak

- U bazi postoje **dva** API ključa: stari ključ za Nextcloud bridge i **novi ključ s dozvolom `all`** (admin, kreiran danas 13:00:26). Nijedan od njih nije predviđeni minimalni ključ.
- **Administratorski ključ s točno potrebnih 7 dozvola ne postoji. Korisnički ključ (`asset.read`, `album.read`, `person.read`) ne postoji.** Ništa nisam stvarao.
- Ključ koji je zalijepljen u razgovor **tretira se kao kompromitiran**: nisam ga spremio, nisam ga koristio, ne bilježim ga. Treba ga opozvati i zamijeniti (odjeljak 2).
- Preflight u produkciji (`--skip-api`): **0 FAIL, 1 WARN** (API provjere preskočene jer sigurno dostupnih ključeva nema). RAID1 zdrav, `lb_check` OK, `/home` prazan i spreman, produkcijske kopije ne postoje.
- GO još nije moguć (odjeljak 5).

## 1. API ključevi u produkcijskoj bazi (bez vrijednosti, samo metapodaci)

| Ime | Vlasnik | Admin račun | Kreiran | Dozvole |
| --- | --- | --- | --- | --- |
| `nextcloud-immich-bridge` | Immich Admin | da | 4.4.2026. 20:55 | `adminUser.create/read/update`, `library.create/read/update/delete/statistics` |
| `API Key` | Immich Admin | da | **15.11.2026. 13:00:26** | **`all`** (puni pristup) |

Čitani su samo `name`, vlasnik, vremena i `permissions`; hash ključa i tajne nisu čitani niti uspoređivani s ičim.

| Zahtjev | Status |
| --- | --- |
| Admin ključ s `queue.read`, `queue.update`, `job.create`, `server.about`, `server.statistics`, `library.read`, `library.statistics` | **NEDOSTAJE.** Ključ `API Key` formalno pokriva sve (`all`), ali je prekomjeran i izložen (odjeljak 2). Bridge ključ nema nijednu od tih dozvola. |
| Korisnički ključ `asset.read`, `album.read`, `person.read` | **NEDOSTAJE.** Nijedan ključ nije vezan uz običnog korisnika. |
| Račun za korisnički ključ | postoji: korisnik s najviše podataka ima **40.378 asseta, 6 albuma i 6 imenovanih osoba** (isti kriterij kao u rehearsalu); drugi račun ima 13.535 asseta, 1 album, 57 osoba. Ključ treba izdati upravo na računu s 40.378 asseta. |

## 2. Kompromitirani admin ključ

- Ključ je prikazan u razgovoru, pa se smatra kompromitiranim. Najvjerojatnije je to ključ `API Key` s dozvolom `all` kreiran danas u 13:00 (**nisam to provjeravao usporedbom hasha**, da tajnu ne bih koristio). Treba pretpostaviti da jest.
- Rizik: `all` na admin računu daje potpuni pristup API-ju (korisnici, knjižnice, brisanje, poslovi, postavke), ne samo ono što cutover treba.
- **Prijedlog prije cutovera (izvršava vlasnik u UI-ju, ja ne diram ključeve):**
  1. prijaviti se kao admin → Account Settings → API Keys → **obrisati `API Key`** (opoziv je trenutan);
  2. izdati novi admin ključ s točno 7 dozvola, ime npr. `cutover-admin-temp`;
  3. na računu s 40.378 asseta izdati ključ s 3 dozvole, ime npr. `cutover-user-temp`;
  4. nove ključeve upisati samo u vlastiti terminal (`read -rs IMMICH_ADMIN_API_KEY; export IMMICH_ADMIN_API_KEY`; isto za korisnički), **nikad u razgovor, datoteku ni zapisnik**;
  5. nakon cutovera i retencije obrisati oba privremena ključa.
- Ključ koji je u razgovoru ne spremam ni u koju datoteku (`.env`, evidencija, shell): alati čitaju samo iz okoline operatera, a spremanje bi tajnu trajno upisalo na disk. Provjeravanje ključa pozivom API-ja nisam radio.
- Ključ ostaje u povijesti razgovora; zato je opoziv jedino pravo rješenje.

## 3. Produkcijski preflight (samo čitanje, `--skip-api`)

`preflight.py --phase before-target --skip-api`: **RESULT PASS (0 FAIL, 1 WARN)**. Zeleno među ostalim: disk 425 GiB slobodno (prag 96), `postgis` i `immich_server` zdravi bez restartova, jedini potrošač baze je `immich_server`, najnoviji Immich backup star 11,0 h (`…20261115T020000-v3.3.5-pg16.13.sql.gz`), ostali redci kao u [19](19-immich-production-readiness.md). WARN `A0`: baseline redova i statistike ne postoji dok ne bude sigurnih ključeva (API provjere nisu izvršene, `IMMICH_*_API_KEY` nisu postavljeni). Zapis: `/opt/stacks/data/backups/immich-cutover-final-preflight-20261115` (0700).

## 4. Lokalni backup mehanizam, RAID1, prostor

| Provjera | Nalaz |
| --- | --- |
| RAID1 | `md0`–`md3` `[2/2] [UU]`, bez degradacije/resynca (kao u [21](21-immich-local-backup-plan.md)) |
| `lb_check` | **OK** (`mismatch_cnt`, NVMe `live`, temperatura, prostor) |
| Prostor | `/home` 1.454 GiB slobodno (1 %), `/` 425 GiB (78 %); potrebno ≈ 1,1 GiB za drugu kopiju |
| Kopije | `/home/immich-cutover-backups` **ne postoji**; nijedan produkcijski backup nije kopiran; G14 vrata zato ne bi prošla |
| Ograničenje | SMART brojači i dalje nedostupni (`smartmontools` nije instaliran, O17) |

## 5. Preostali GO/NO-GO blokeri

1. **G10:** nema admin ključa s 7 dozvola ni korisničkog ključa; `API Key (all)` treba opozvati i zamijeniti. Zatim ponoviti preflight s ključevima (da `A0` prođe).
2. **G14 / O16:** kopije na `/home` ne postoje; `s_open` ih traži (exit 6 bez njih). Treba odobrenje i izvršenje `lb_copy_app_backup`, `lb_copy_cutover_dumps`, `lb_verify`.
3. **G6 ostaje neispunjen** (nema off-host kopije): potrebno pisano prihvaćanje rizika lokalne RAID1 zaštite.
4. **G2, G7, G8, G3, G11:** pragovi (osobito recall 0,90 za `face_index`), termin, retencija izvora 7 dana, odobrenje izmjene `.env`/recreatea i zaštite izvora, osoba za OIDC provjeru, obavijest korisnicima i utišan monitoring.
5. **O14/O15:** tko izdaje token nakon HALT-a; dodatni kratki start servera u `s_freeze`.
6. **O17 (preporuka):** `smartmontools` za SMART baseline.
7. Neprobano jer postoji samo u produkciji: Traefik, `media-operations` i bridge tijekom cutovera, OIDC, kanarski testovi, stvarni promet, stvarni kvar diska. Preporuka: odobrena "proba bez otvaranja" (`s_freeze` → `s_dark_launch` → `s_rollback_r1`).

## 6. Preporučena sljedeća radnja (jedna)

**Vlasnik u Immich UI-ju (kao admin) opoziva ključ `API Key` (`all`) i na njegovo mjesto izdaje admin ključ s točno 7 dozvola, uneseno samo u vlastiti terminal.**

## 7. Što je izvršeno

Samo čitanje: popis `api_key` (ime, vlasnik, vremena, dozvole), brojevi asseta/albuma/osoba po računu, `preflight.py --skip-api`, `lb_check`, `/proc/mdstat`, `df`. Zapisana je samo privatna evidencija preflighta. Nije stvoren, mijenjan ni brisan nijedan ključ; zalijepljeni ključ nije spremljen ni korišten; nije kopiran nijedan backup; nijedan mutirajući korak `steps.sh` nije izvršen; kontejneri (`immich_server` `StartedAt` 3.11.), baze, `.env`, Compose i mreže nepromijenjeni; `immich-db` ne postoji.

**Stati ovdje. Produkcijska migracija nije odobrena.**

## 8. Dodatak: preflight s admin ključem (samo čitanje GET, 15.11.2026.)

Admin ključ je iz `/root/.immich-cutover-keys.env` (0600, izvan repozitorija) učitan u okolinu bez ispisa. Ključ je prvo greškom spremljen u `immich-cutover/cutover-keys.env.example` (u repozitoriju); premješten je u `/root` datoteku, a `.example` vraćen na placeholder. Ključ nije bio commitan (`immich-cutover/` nije u gitu), a u `/opt/stacks/data` izvan `backups/` ne postoji nijedna druga kopija.

- `preflight.py` s API-jem: **0 FAIL, 1 WARN**. PASS: A1 (`GET /server/about`, v3.3.5), A2 (`queue.read`), A4 (nijedan red nije pauziran), A5 (`server.statistics`), A6 (8 knjižnica). WARN A7: korisnički ključ nije postavljen (preskočeni baseline albuma, osoba i pametnog pretraživanja).
- `queues status`: svi redovi `active=0 waiting=0 delayed=0`, nijedan pauziran. **`facialRecognition` ima `failed=1`** (postojeći neuspjeli posao, nije naš): kriterij K13 ("failed 0 nakon otvaranja") treba prilagoditi baselineu 1 ili taj posao ručno pregledati prije cutovera.
- Pozivi su bili samo GET; ništa nije pauzirano, nije pokrenut posao backupa, nije izvršen nijedan mutirajući korak. Zapis: `/opt/stacks/data/backups/immich-cutover-final-preflight-api-20261115` (0700).
- Ključ je očito aktivan, ali ako je to `API Key` s dozvolom `all` (ili ključ koji je bio u razgovoru), i dalje vrijedi opoziv i zamjena iz odjeljka 2 prije pravog cutovera.
