# 32 — Immich produkcijski cutover: F4 (zamrzavanje)

Datum: 15. studenoga 2026. (izvedba 13:33:40–13:36:40 UTC).
**`CUTOVER_ID=20261115t130331z`** · evidencija `/opt/stacks/data/backups/immich-cutover-20261115t130331z` (`f4-freeze.out`, `freeze-order.log`, `T0`, `source-db-acl.before`, `api-baseline.json`, `server-frozen-read.log`, `write-probe-frozen-A.json`, `write-probe-f4-postcheck.json`, `f4-postcheck-report.json`).
Odobreno: samo F4. **F5 i kasniji koraci nisu pokrenuti.** Produkcijski Immich je privremeno **nedostupan**.

## 1. Sažetak

| Stavka | Rezultat |
| --- | --- |
| `s_freeze` | **`s_freeze OK`, exit 0** |
| Žurnal | **`FROZEN`** (seq 3), hash lanac valjan (`cutstate.py verify`) |
| HALT / STOP | nije bilo |
| Baseline (API-only, izvorna baza) | zapisan: 55.535 fotografija, 1.306 videa |
| Zaštita izvora | `REVOKE CONNECT` primijenjen, 0 veza |
| Nema novih zapisa nakon zamrzavanja | **PASS** (C0–C5) |
| Sigurno na F5? | **Tehnički da**; čeka novu operativnu uputu |

## 2. Prethodne provjere (PASS prije zaustavljanja)

Dokumenti 17, 20, 22, 30, 31 (17 i 31 čitani detaljno; 20/22/30 samo odjeljci o F4/okolini — nisu pročitani u cijelosti). Žurnal `PREPARED`, lanac valjan; `CUTOVER_ID` markeri odgovaraju; `lb_check OK`, `lb_verify OK` (SHA-256 `25b7780f…` original = kopija); `StartedAt` svih kontejnera identičan F3, 0 restartova; `immich-db` healthy, 0 tablica u `public`; redovi: svi `active=0`, jedini `failed` poznati `facialRecognition=1`; javni rub 200; Redis `PONG`; 11 veza na izvornu bazu (`immich_server`). Nema odstupanja od F3. Ključevi učitani (`keys_load`, vrijednosti nisu prikazane).

## 3. Redoslijed zaustavljanja (`freeze-order.log`, UTC)

| Vrijeme | Događaj |
| --- | --- |
| 13:33:40 | `FREEZING`, `T0`, ACL izvora spremljen (`PUBLIC\|CONNECT,TEMPORARY`; `immich\|CONNECT,CREATE,TEMPORARY`) |
| 13:35:42 | `nextcloud_immich_bridge`, zatim `immich_media_operations` zaustavljeni (`scripted_writers_stopped`) |
| 13:35:47 | redovi pauzirani i ispražnjeni (`queues_paused_and_drained`), ≈0 s čekanja |
| 13:35:49 | `immich_server` zaustavljen (`users_cut_server_stopped`); 0 veza (STOP-2 OK) |
| 13:36:38 | baseline iz API-only instance bez rute na izvornoj bazi (`baseline_taken_after_all_writers_frozen`) |
| 13:36:39 | instanca zaustavljena, 0 veza; `REVOKE CONNECT` (`source_fenced`) |
| 13:36:40 | sonda pisanja A; `FROZEN` |

## 4. Redovi poslova

Svi pausable redovi pauzirani (API 200); `backgroundTask` nije pausable po dizajnu (HTTP 400, poznata iznimka). `DRAINED`: `active==0` na svim redovima, backlog 0. Drain trajao ≪ 10 min.

## 5. API-only baseline (O15)

Instanca `immich_server` podignuta s `docker-compose.frozen.yml`: healthy, `traefik.enable=false`, `DB_HOSTNAME=postgis`, bez workera (u `server-frozen-read.log` nema "Starting microservices worker"). `api-baseline.json` (SHA-256 `bce55d3f…`): 55.535 fotografija, 1.306 videa. Instanca zatim zaustavljena.

## 6. Zaštita izvorne baze

`REVOKE CONNECT … FROM PUBLIC` i `FROM immich`; `datacl` sada `{=T/immich,immich=CT/immich}` (CONNECT uklonjen; prije: `{=Tc/immich,immich=CTc/immich}`). `pg_stat_activity` za `immich`: **0**. Povrat: `s_unfence` / `s_rollback_r1`.

## 7. Dokaz nepromijenjenih podataka

Sonda A (`write-probe-frozen-A.json`, 73 tablice, 1 sekvenca; SHA-256 `ac01b764…`) uspoređena s novom sondom `write-probe-f4-postcheck.json` (`write_probe.py check`): C0–C5 **PASS** (postmaster nije restartan, statistike nisu resetirane, isti skup tablica, nijedan insert/update/delete izvan allow-liste, nijedna sekvenca pomaknuta). Napomena: ovo je dodatna samo-čitajuća provjera izvan `s_freeze`; službena sonda B i `freeze-gap-proof.json` rade se u F5.

## 8. Status kontejnera (nakon F4)

| Kontejner | Stanje |
| --- | --- |
| `immich_server` | **zaustavljen** (Exited 143); nakon baselinea je kontejner recreatean s frozen override-om (label `traefik.enable=false`) — prije F10 `s_dark_launch`/`s_open` ili `s_rollback_r1` recreate iz bazne datoteke |
| `immich_media_operations` | zaustavljen (Exited 137) |
| `nextcloud_immich_bridge` | zaustavljen (Exited 137) |
| `immich_machine_learning` | radi, healthy |
| `postgis` | radi, healthy, `StartedAt` 26.6. nepromijenjen, 0 restartova |
| `immich_redis` | radi, healthy, `PONG`, `StartedAt` 26.6. nepromijenjen |
| `immich-db` | radi, healthy, prazan |
| `traefik` | radi; javni rub `media.finestar.hr` vraća 404 (nema aktivnog Immich servisa) |

## 9. Što nije dirano

`.env`, `DB_HOSTNAME`, Compose, Traefik konfiguracija, Redis, fotografije/videi, backupovi, `CUTOVER_ID`; nije bilo dumpa ni restorea. `CUTOVER_APPROVED` bio je postavljen samo prefiksom za poziv `s_freeze` (provjereno: nije postavljen u ljusci poslije).

## 10. Je li sigurno nastaviti na F5?

**Tehnički da** (stanje `FROZEN`, svi pisci zaustavljeni, izvor zaštićen i dokazano nepromijenjen, backupovi provjereni). **Stajem nakon F4.** Do nove operativne upute Immich ostaje nedostupan; ako se odluči odustati, dopušten je `s_rollback_r1` (stanje `FROZEN` ga dopušta).
