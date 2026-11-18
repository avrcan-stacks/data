# 37 — Immich produkcijski cutover: F8 (dark launch)

Datum: 15. studenoga 2026. · **`CUTOVER_ID=20261115t130331z`** · evidencija `/opt/stacks/data/backups/immich-cutover-20261115t130331z` (`f8-dark-launch.out`, `server-dark.log`, `api-dark.json`, `f8-api-verify.out`, `dark-delta.json`, `write-probe-dark.json`, `write-probe-dark-after-apiverify.json`).
Odobreno: samo F8 (`s_dark_launch`); vlasnik je prihvatio prekoračenje cilja od 30 min. **F9 i F10 nisu pokrenuti. Promet nije otvoren.**

## 1. Sažetak

| Stavka | Rezultat |
| --- | --- |
| `s_dark_launch` | izlaz `s_dark_launch OK`, exit 0, **ali vidi odjeljak 2 (API provjera se u koraku nije izvršila)** |
| API baseline usporedba | **PASS (0 FAIL, 0 WARN)**, izvršena naknadno, ručno, istom naredbom kao u koraku (odjeljak 2) |
| Žurnal | **`DARK_VERIFIED`** (seq 8, 14:08:42Z), `cutstate.py verify` OK |
| Sigurno na F9? | tehnički da, **uz odluku vlasnika o vremenu** (odjeljak 7) |

## 2. ODSTUPANJE: API provjera u `s_dark_launch` nije se izvršila

Tijekom koraka `api_checks.py verify` pao je s `RuntimeError: environment variable IMMICH_ADMIN_API_KEY is not set` (ključevi nisu bili učitani u okolinu, prije pokretanja nisam pozvao `keys_load`). **Korak je unatoč tome nastavio i zapisao `DARK_VERIFIED` te ispisao `s_dark_launch OK` s exit 0** — iako je skripta pisana s `set -Eeuo pipefail`, pad te naredbe nije zaustavio korak. To je **greška u zaštiti koraka** koju treba istražiti prije F10 (uzrok nisam utvrđivao; stanje je zabilježeno bez API dokaza).
Ispravak učinjen u granicama odobrenja, bez izmjene koda i bez SQL-a: učitani ključevi (`keys_load`, vrijednosti se ne ispisuju) i ponovljena **ista, samo čitajuća** naredba `api_checks.py verify --baseline api-baseline.json --allow-paused --out api-dark.json` → **PASS**. Zatim je `write_probe` provjerio da to nije ništa zapisalo: **PASS** (C0–C5). Žurnal nije ručno mijenjan.

## 3. Vrijeme

Početak F8 **14:07:54Z**, završetak **14:08:42Z** (48 s); naknadna API provjera završena 14:09:23Z. Od T0 (13:33:40Z) do kraja koraka **≈ 35 min 02 s**. Provjera prije F8: 14:07:42Z (≈ 34 min), 45 min nije dosegnuto.

## 4. API baseline (`api-dark.json`)
Q1 verzija v3.3.5 · Q2 statistike servera i po korisniku identične · Q3 8 knjižnica identično · Q4 failed jobs nisu veći od baselinea (facialRecognition=1) · Q5 svi redovi i dalje pauzirani · Q6 albumi identični · Q7 792 osobe · Q8 smart search overlap min/mean 1,00 · Q9 warm p95 235 ms (baseline 248 ms) · Q10 cold max 581 ms.

## 5. Migracije i shema
Log (`server-dark.log`): "Starting api worker", `targetLists=1, current=1` za `clip_index` i `face_index`, "Finished running migrations", **"No schema drift detected"**; nema "Starting microservices worker", nema ERROR/FATAL, nema "Migration … succeeded", reindeksiranja ni promjene ekstenzije. `kysely_migrations` = 101 (kao u izvoru). Server: `IMMICH_WORKERS_INCLUDE=api`, healthy, `DB_HOSTNAME=immich-db` samo u kontejneru.

## 6. Ruta, zapisi, izvor, cilj, Redis
- **Ruta:** `traefik.enable=false`, nema `T_open`, nema statičke Immich rute u Traefik dynamic; GET javnog ruba (`--resolve`, samo čitanje) → **404**. Traefik nije mijenjan.
- **Novi zapisi:** `dark-delta.json`: `changed_tables []`, `outside_allow_list []`, `metadata_sections_changed []`, PASS. Sonda pisanja prije/poslije API provjere PASS (nema promjene brojača ni sekvenci izvan dopuštenih `system_metadata, version_history, plugin, plugin_method`).
- **Izvor `postgis/immich`:** ACL `{=T/immich,immich=CT/immich}`, 0 veza, nije odmrznut.
- **Cilj `immich-db`:** healthy, 0 restartova, `StartedAt` 13:19:51; veze samo od dark servera (uloga `immich`).
- **Redis, `postgis`:** nisu restartani (`StartedAt` 2026-06-26, 0 restartova).
- **`.env`:** `DB_HOSTNAME=postgis` (nepromijenjen). Media-operations i bridge zaustavljeni; produkcijski server **nije** pokrenut s workerima (samo dark API-only kontejner).

## 7. R1 i F9
- **R1 je i dalje siguran i dopušten** (stanje `DARK_VERIFIED`; izvor netaknut, `.env` na izvoru, nema `T_open`, nova baza bez zapisa osim dopuštenih). Napomena: `s_rollback_r1` na kraju ponovno verificira API prema baselineu, pa za njega treba učitati ključeve (`keys_load`) u istoj ljusci.
- **F9:** prozor planiran na T0+25 min davno je prošao; **prag 45 min = 14:18:40Z**, pri 60 min (14:33:40Z) obavezan R1. F10 (`s_open`) uključuje G14 vrata i dulji slijed. **Preporuka: F9 odluka i eventualni F10 samo uz izričitu novu odluku vlasnika prema G2**, uz prethodno razjašnjenje odstupanja iz odjeljka 2.

**Stajem nakon F8. F9 i F10 ne pokrećem bez nove upute.**
