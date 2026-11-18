# 70 — B2: off-site Borg arhiva B1 backupa

Datum: 2026-11-18, 08:16:03–08:21:10 UTC. Status: **`B2_BORG_OFFSITE_BACKUP_PASS`**

Borg naredbe izvršio je vlasnik u privatnom terminalu (skripta `b2-borg.sh`, fraza unesena skriveno, samo u memoriji procesa). Agent je prije toga provjerio izvor, a nakon toga neovisno provjerio rezultate. Fraza nije zapisana ni u jednu datoteku, log ni dokument.

## Parametri

| Stavka | Vrijednost |
|---|---|
| Izvor | `/opt/stacks/data/backups/b1-20261118T080633Z/` (160 datoteka, `0700`, izvan PGDATA) |
| Odredište | `ssh://storagebox/./backups/postgres/repository` |
| ID repozitorija | `0d89819fb0aa07c6adc1583c0f0696955391535a536b6645141b9bc10ce1b86b` (podudara se) |
| Borg klijent | 1.2.0 (Storage Box 1.2.9) |
| Arhiv | `postgres-b1-20261118T080633Z` |
| Fingerprint arhiva | `e1123f9a7bdb9603c76ca3a6cb64f981c86a215f07e69b76b616da7ac72f85e1` |
| Kompresija | `zstd,3` |
| SHA-256 `SHA256SUMS` (izvor) | `602ff48819f64069ba12413785c0e60d12fe404459842afefd23f6a1599703cb` (nepromijenjen) |

## Izlazni kodovi

| Korak | Izlazni kod | Rezultat |
|---|---|---|
| Provjera izvora `sha256sum -c SHA256SUMS` | 0 | 157/157 OK, 0 neuspjeha (prije i poslije Borga) |
| `borg info` (identitet repozitorija, pristup s novom frazom) | 0 | ID se podudara; arhiv nije prethodno postojao |
| `borg create --stats --compression zstd,3` | **0** | trajanje 57,33 s; 160 datoteka; original 2,80 GB, compressed 2,79 GB, deduplicated 2,79 GB; 1189 unikatnih / 1197 ukupnih chunkova |
| `borg list` | **0** | 162 unosa (160 datoteka + 2 direktorija: `.` i `crowdsec.dir`) |
| `borg check -a` | **0** | bez grešaka |
| `borg check --verify-data -a` | **0** | bez grešaka |
| `borg extract` | **0** | u `/opt/stacks/data/backups/b2-restore-20261118T080633Z/` (`0700`) |
| Restore: `sha256sum -c SHA256SUMS` | 0 | **157/157 OK**, 0 neuspjeha |
| Restore: `globals.sql` | — | prisutan, 6 043 B, **bajtovno identičan izvoru** (`cmp`); sadržaj nije ispisan |
| `diff -rq` izvor ↔ restore | 0 | identično stablo; 160 ↔ 160 datoteka |

Neovisna provjera agenta nakon izvršenja: rezultat datoteka `b2-results-20261118T080633Z.txt` (`0600`) sadrži gornje vrijednosti; `.err` datoteka je prazna; manifest u restoreu ponovno provjeren (157 OK); izvor ponovno provjeren (0 neuspjeha, hash manifesta nepromijenjen).

## Potvrde

- Arhiviran je točno B1 direktorij (uključujući `SHA256SUMS`, `globals.sql`, `run.log`, `monitor.log`, `*.toc`, `*.err`); nikakvi drugi produkcijski podaci nisu dodani.
- Lokalni B1 backup i Borg arhivi **nisu brisani**; izvorni direktorij nije mijenjan.
- Nije korišten `prune`, `delete`, `compact` ni `repair`.
- Docker i PostgreSQL nisu restartani ni mijenjani, novi `postgres` servis nije pokrenut, migracija nije započeta, nema Git operacija.
- Izolirani PostgreSQL restore-test kontejner **nije** pokrenut (traži zasebno odobrenje).
- Lokalni slobodni prostor nakon restorea: 409 GB.

## Preostalo / rizici

1. **Obnovljivost baza nije dokazana.** Provjereno je da su datoteke u Borgu cjelovite i identične; da se dumpovi mogu učitati u PostgreSQL potvrđuje tek restore test (B3), uključujući `qubit_user` (pg_cron mora ostati isključen, doc 68 R9), PostGIS 3.4.3/3.6.2, `vchord`/`vector`.
2. **Jedna off-site kopija** u jednom repozitoriju na jednom Storage Boxu; nema druge lokacije.
3. **Kopija ključa i fraze** mora postojati izvan ovog servera i izvan Storage Boxa; ključ repozitorija je i na ovom serveru (`/root/borg-postgres-recovery*.key`). Potvrditi da je nova fraza pohranjena offline.
4. **Pohrana fraze u `.env`** (placeholder dodan, vrijednost prazna): `.env` je `0644` i učitava se kroz `env_file` u `postgis`; ne upisivati frazu u `.env` bez uklanjanja tog rizika (preporuka: zasebna `0600` datoteka + `BORG_PASSCOMMAND`).
5. **Nema append-only zaštite** na Storage Boxu; kompromitiran server može obrisati arhive.
6. **Lokalna kopija** (`b1-…`, `b2-restore-…`) i dalje sadrži `globals.sql` s hashevima lozinki; brisanje samo uz zasebno odobrenje. `b2-restore-…` je suvišna kopija istih podataka (2,8 GB).
7. Backup je točka u vremenu (08:06–08:10 UTC); promjene u bazama nakon toga nisu pokrivene.

**B2_BORG_OFFSITE_BACKUP_PASS**
