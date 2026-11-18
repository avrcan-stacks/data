# 67 — Borg backup/restore smoke test

Test je izvršio vlasnik ručno u privatnom terminalu (pristupna fraza unesena samo na Borg prompt). Agent je pripremio naredbe i dokumentirao izlaz; fraza nije zapisana u naredbe, datoteke, dokumente ni Git.

## Sažetak

| Stavka | Vrijednost |
|---|---|
| Datum/vrijeme testa | 2026-11-18, ~07:42 UTC (arhiv 07:42:29–07:42:30) |
| Borg verzije | klijent (dedicated) 1.2.0; Storage Box 1.2.9 (prema zadatku; SSH shell ne dopušta `borg --version`) |
| Repozitorij | `ssh://storagebox/./backups/postgres/repository` |
| ID repozitorija | `0d89819fb0aa07c6adc1583c0f0696955391535a536b6645141b9bc10ce1b86b` (podudara se s očekivanim) |
| Šifriranje | repokey BLAKE2b |
| Testni arhiv | `postgres-borg-smoke-20261118T074205Z` |
| Fingerprint arhiva | `027b4906fa2f04807e89fcfa791f291732b089dfefd416bda752052225027438` |
| SHA-256 izvornika | `9455c6212515a3d8f37780e5c3c20299531f04569c9bd1886b8b74a55fd0a6ff` |
| SHA-256 vraćene datoteke | `9455c6212515a3d8f37780e5c3c20299531f04569c9bd1886b8b74a55fd0a6ff` |
| Broj datoteka u arhivu | 1 (`test.txt`, 53 B; compressed 96 B; deduplicated 896 B) |

## Rezultati

- **Preflight:** ID repozitorija podudara se; repozitorij je prije testa imao 0 arhiva; arhiv s tim imenom nije postojao.
- **borg create:** uspjeh (`A test.txt`, 1 datoteka, trajanje 0.20 s, bez grešaka prijenosa).
- **borg list arhiva:** točno jedna datoteka, `test.txt`.
- **borg check** (`--archives-only -a`, bez `--repair`): uspjeh. Nije ispisao ništa, a skripta je radila sa `set -e`, pa bi nenulti izlazni kod prekinuo izvršenje prije `extract`; `extract` se nakon toga izvršio.
- **borg extract:** uspjeh u zaseban direktorij `/tmp/borg-acceptance-test-20261118T074205Z/restore/`.
- **SHA-256:** potpuno podudaranje (`SHA256 MATCH`).
- Pronađene datoteke u privremenom direktoriju: `src/test.txt`, `restore/test.txt`, `src.sha256`, `restored.sha256`; nema neočekivanih datoteka.

## Potvrde

- Korištena je isključivo sintetička datoteka; nisu korišteni produkcijski podaci, dumpovi, konfiguracije ni tajne.
- PostgreSQL (`postgres`, `postgis`, `immich-db`) i Docker nisu mijenjani ni restartani.
- Nije izvršen `prune`, `delete`, `compact` ni `repair`; nema backup automatizacije; nisu mijenjani ključ ni fraza; nije bilo Git commit/push operacija.
- Testni arhiv ostavljen je u repozitoriju. Privremeni direktorij `/tmp/borg-acceptance-test-20261118T074205Z/` ostavljen je radi pregleda; uklanjanje je na vlasniku.

## Preostali sigurnosni rizici

1. **Pristupna fraza je kompromitirana.** Bila je ispisana u razgovoru (dvaput) i mora se rotirati: `borg key change-passphrase`, zatim ponovni `borg key export`. Do rotacije treba smatrati da repozitorij štiti samo pristup Storage Boxu.
2. Postojeći izvoz ključa (`/root/borg-postgres-recovery.key`) zaštićen je starom frazom i treba ga zamijeniti nakon rotacije; kopija ključa i fraze mora biti pohranjena izvan Storage Boxa i izvan ovog servera.
3. Razlika verzija (klijent 1.2.0, poslužitelj 1.2.9) funkcionalno je potvrđena ovim testom za create/list/check/extract; nije testirano za veće repozitorije ni za `prune`/`compact`.
4. Test pokriva 53 B; ne potvrđuje propusnost, trajanje ni restore velikog PostgreSQL dumpa.
5. Nema automatizacije, nadzora ni periodičkog `borg check` cijelog repozitorija.

**BORG_BACKUP_RESTORE_SMOKE_TEST_PASS**
