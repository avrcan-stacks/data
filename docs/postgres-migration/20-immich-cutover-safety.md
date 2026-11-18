# 20 — Immich: sigurnost otvaranja i rollbacka (faza 7B)

Datum: 15. studenoga 2026. (Europe/Zagreb).
Status: **implementirano i testirano samo na izoliranom stacku; produkcija nije dirana; cutover nije odobren ni pokrenut.** Nadovezuje se na [17](17-immich-production-cutover.md), [18](18-immich-cutover-rehearsal.md) i [19](19-immich-production-readiness.md). Runbook (doc 17: odjeljci 3, 4, 5/F4, F8, F10, STOP tablica, 6, 9, 10) ažuriran je prema ovom dokumentu.

## 0. Sažetak

- Praznina iz doc 19 (G12) **zatvorena**: `s_open` više ne ovisi o datoteci `T_open`. Cutover ima **eksplicitna stanja u hash-lančanom žurnalu** (`cutstate.py`), a oporavak djelomično neuspjelog otvaranja (`s_open_abort`) dopušten je **samo uz dokaz** da nova baza nije primila pisanje. Bez dokaza: HALT, server zaustavljen, automatski rollback zabranjen, ručni GO/NO-GO s tokenom.
- Zamrzavanje (D1 iz doc 19) **preuređeno**: bridge i `media-operations` prvi, zatim redovi, zatim server; baseline i snapshot nakon što su svi pisci zamrznuti, uz strogi dokaz bez vremenskog razmaka.
- Rehearsal na novom izoliranom stacku: **234 zabilježena testa, 229 PASS, 5 FAIL**. Svih 5 FAIL-ova su neuspjeli međukoraci ranijih iteracija (pogreška u testu ili skripti), ispravljeni i ponovno izvedeni; nijedan nije otvoren (odjeljak 5).
- Produkcija je provjerena prije i poslije: kontejneri (`StartedAt`), `.env`/Compose datumi, ACL baze `immich`, broj asseta (57.627), 14 backupova i odsutnost `immich-db` nepromijenjeni; audit log od 8.197 naredbi ne sadrži nijedan produkcijski resurs.
- **GO još nije moguć**: ostaju odluke i neprobano iz doc 19 (odjeljak 7).

## 1. Implementirane izmjene

| Datoteka | Izmjena |
| --- | --- |
| `immich-cutover/cutstate.py` (novo) | žurnal stanja: svaki zapis nosi SHA-256 prethodnog retka; `state` mora odgovarati zadnjem retku; brisanje, izmjena, skraćivanje ili neslaganje = `CORRUPT` (exit 6) = HALT; `set` provjerava dopuštena prethodna stanja (exit 5), `can-rollback` / `can-abort` odlučuju o skriptiranom povratku |
| `immich-cutover/write_probe.py` (novo) | sonda pisanja baze (samo čitanje): C1 restart postmastera, C2 reset statistike, C3 skup tablica, C4 brojači `n_tup_ins/upd/del` izvan allow-liste, C5 vrijednosti svih sekvenci; nedostajuća ili nepotpuna sonda = UNKNOWN = nedokazano |
| `steps.sh` | stanja u svim koracima (out-of-order korak = exit 5); novi `s_freeze`; sonde A/B; `s_open` s 9 stanja i točkama kvara; `s_open_abort`; `s_manual_forward`; `s_manual_rollback_accept_loss`; `s_rollback_r1` prema stanju + žive unakrsne provjere; `s_target_reset_after_rollback` traži `PREV_EV` u rolled-back stanju; `s_dark_launch` dopušten i iz `ABORT_VERIFIED` (ponovno pauzira redove) |
| `docker-compose.frozen.yml` (novo) | override za baseline iz zamrznutog stanja: API-only, bez rute, baza izvora |
| `tests/offline_selftest.sh` | +1 provjera: prijelazi, otkrivanje izmjene žurnala, vrata rollbacka/aborta, verdikti sonde (13/13 PASS) |
| `rehearsal/` | stand-in kontejneri za bridge i `media-operations`; `rehearse.py` grupe gC1–gC5, gD1–gD3; API ključevi u rehearsalu sada imaju samo **najmanji skup dozvola** iz doc 19 (7 admin + 3 korisnik): sve provjere rade |

### 1.1 Stanja i prijelazi

`PREPARED → FREEZING → FROZEN → DUMPED → SANITIZED → RESTORED → VALIDATED → DARK_VERIFIED → OPEN_BEGIN → ENV_CHANGED → RECREATING → RECREATED → ROUTE_LIVE → AUX_STARTED → RESUMING → OPEN_CONFIRMED`; izlazi `ABORT_BEGIN → ABORT_VERIFIED`, `HALT_MANUAL`, `ROLLED_BACK`, `ROLLED_BACK_LOSS_ACCEPTED`. Svaki prijelaz se upisuje **prije** sljedeće radnje; očekivani novi `.env` i njegov SHA-256 zapisuju se **prije** izmjene `.env`.

| Stanje | `s_rollback_r1` | `s_open_abort` | Ručna odluka |
| --- | --- | --- | --- |
| `FREEZING … DARK_VERIFIED`, `ABORT_VERIFIED` | dopušten (uz žive provjere) | nema što prekidati (exit 5) | ne |
| `OPEN_BEGIN … AUX_STARTED`, `ABORT_BEGIN` | zabranjen (exit 3) | **dokaz ili HALT** | ne |
| `RESUMING`, `OPEN_CONFIRMED` | zabranjen (exit 3) | zabranjen (exit 3) | ne (R2 ručno) |
| `HALT_MANUAL` | zabranjen (exit 3) | HALT (exit 4) | **GO ili NO-GO s tokenom** |
| `CORRUPT` | HALT (exit 4) | HALT (exit 4), bez ikakve radnje | ručno |

Žive provjere u `s_rollback_r1` (neovisne o žurnalu): `.env` mora upućivati na izvor; `T_open` ne smije postojati; aplikacija ne smije raditi s rutom na novoj bazi. Bilo što drugo = HALT (exit 4).

### 1.2 Dokazi u `s_open_abort` (svi moraju biti PASS)

E1 pisci zaustavljeni (prvo se zaustavljaju, pa se tek onda skuplja dokaz) · E2 lanac žurnala valjan · E3 nijedna veza uloge `immich` na novu bazu · E4 sonda pisanja prema `write-probe-dark.json` · E5 72 hasha i metapodaci jednaki snapshotu nakon dark launcha · E6 nijedna datoteka u `upload` s `ctime` poslije T0 · E7 `.env` točno zabilježeni sadržaj. Allow-lista za pokretanje aplikacije: `system_metadata, version_history, plugin, plugin_method`. Sve ostalo (npr. `session`, `asset`, `user`) je pisanje korisnika ili poslova.

### 1.3 Novi redoslijed zamrzavanja

1 ACL izvora → 2 **stop bridge i `media-operations`** → 3 pauza redova i `wait-drain` → 4 stop servera → 5 0 veza → 6 **baseline iz API-only instance bez rute na izvornoj bazi** (nitko ne može pisati; ista slika kao produkcijski server) → stop, 0 veza → 7 fence izvora → 8 sonda A. Snapshot (F5) slijedi i **sonda B mora biti identična sondi A** (`freeze-gap-proof.json`). Baseline iz živog servera više ne postoji.

## 2. Što je rehearsal otkrio i ispravio u ovoj fazi

| # | Nalaz | Ispravak |
| --- | --- | --- |
| 1 | `find -newermt` ne vidi uploade: Immich zadržava vrijeme datoteke klijenta (`mtime` stariji od T0); prvi test s pravim uploadom prošao je E6 neopaženo (FAIL u testu) | E6 koristi `ctime` (`-newerct`); dokazano u D2; doc 17 R2 također ispravljen |
| 2 | Nakon abortа iz stanja u kojem je radio puni server aplikacija je sama nastavila `metadataExtraction` (Q5 FAIL pri ponovnom dark launchu) | `s_dark_launch` iz `ABORT_VERIFIED` prvo ponovno pauzira redove |
| 3 | `s_validate_target` zahtijeva `baseline-*.json` iz preflighta (test je preskočio preflight) | rehearsal pokreće preflight; postupak je u doc 17 (F1) |
| 4 | (dizajn) između `sed` i zapisa hasha postojao bi mali prozor bez dokaza | očekivani sadržaj i hash zapisuju se prije izmjene `.env` |

## 3. Testirani scenariji kvara

### 3.1 Kritične točke `s_open` (ubrizgani kvar, nova baza **bez** pisanja)

| Točka kvara | Stanje u žurnalu | `.env` | R1 | `s_open_abort` | Rezultat |
| --- | --- | --- | --- | --- | --- |
| prije izmjene `.env` | `OPEN_BEGIN` | nepromijenjen | odbijen (3) | E1–E7 PASS → `ABORT_VERIFIED` | PASS |
| nakon izmjene `.env` | `ENV_CHANGED` | promijenjen | odbijen (3) | E1–E7 PASS, `.env` vraćen bajt-u-bajt | PASS |
| tijekom Docker recreatea (server već pokrenut s rutom) | `RECREATING` | promijenjen | odbijen (3) | E1–E7 PASS | PASS |
| prije healthchecka | `RECREATED` | promijenjen | odbijen (3) | E1–E7 PASS | PASS |
| nakon što ruta postane dostupna | `ROUTE_LIVE` | promijenjen | odbijen (3); zastarjeli žurnal + `.env` na novu bazu → HALT (4) | E1–E7 PASS | PASS |

Nakon svakog abortа: `.env` bajt-u-bajt jednak izvorniku, server, bridge i `media-operations` zaustavljeni, `T_open` uklonjen, ponovni dark launch `DARK_VERIFIED`. Točke `before-env-edit` i `after-route` ponovljene su u D3 sa završnim kodom dokaza (E6 po `ctime`).

### 3.2 Nova baza je primila zapis: automatski rollback blokiran

| Scenarij | Dokazi koji padaju | Ishod |
| --- | --- | --- |
| **pravi upload korisnika** (prijava + 2 fotografije kroz živi server, `ROUTE_LIVE`) | E4 (`asset`, `asset_exif`, `asset_job_status`, `session`, `user`), E5, E6 (`ctime`) | exit 4, `HALT_MANUAL`, `HALT-REPORT.txt`; R1 odbijen (3); ponovljeni abort ostaje HALT |
| poništen UPDATE (sadržaj isti, brojač se vidi) | E4 | HALT |
| `nextval` sekvence (potrošen failed insertom) | E4 (C5) | HALT |
| samo datoteka u `upload` (nema retka u bazi) | E6 | HALT |
| ručna izmjena `.env` | E7 | HALT |
| restart nove baze (statistika nedokaziva) | E4 (C1) | HALT |
| nedostaje `write-probe-dark.json` | E4 (UNKNOWN) | HALT |
| oštećen žurnal | — | HALT bez ikakve radnje; R1 odbijen (4) |

Sonda na klonovima baze (zaustavljen server): kontrola PASS; committed UPDATE, rolled-back DELETE, `nextval`, promjena `session` → FAIL; samo `system_metadata` → PASS (dopušteno pri startu).

### 3.3 Ručni GO/NO-GO nakon HALT-a

- Bez tokena, s tokenom drugog cutovera ili s tuđim tokenom (NO-GO token ne otključava GO): **odbijeno** (exit 3), stanje nepromijenjeno.
- **NO-GO s točnim tokenom** (C5): izvor vraćen, `.env` identičan, ACL izvora vraćen, aplikacija na izvoru s rutom, **nova baza nije obrisana** (preimenovana u sljedećem pokušaju).
- **GO s točnim tokenom** (D2): otvaranje dovršeno na novoj bazi, `OPEN_CONFIRMED`, 2 uploadane fotografije postoje u novoj bazi, bridge i `media-operations` rade.

### 3.4 Zamrzavanje i redoslijed

Redoslijed iz `freeze-order.log` točan u tri neovisna pokretanja; `FinishedAt` bridgea i `media-operations` ≤ trenutak odsijecanja servera ≤ baseline. **Zamrzavanje pod opterećenjem** (20 uploada tijekom `s_freeze`): fotografije u frozen baselineu = fotografije u bazi izvora (55.555 = 55.555) i sonda B = sonda A. STOP-1 (istek pražnjenja): `s_freeze` stane, bridge i `media-operations` već zaustavljeni, server radi, izvor nije zaštićen, daljnji koraci odbijeni (5); oporavak `s_rollback_r1` iz `FREEZING` (WARN: baseline još ne postoji).

## 4. Rezultati PASS / FAIL

| Grupa | Što pokriva | PASS / ukupno |
| --- | --- | --- |
| g0, g1 | offline selftest; zaštite rehearsal načina; 15 mutirajućih koraka bez `CUTOVER_APPROVED` odbijeno; audit log bez produkcijskih resursa | 15 / 15 |
| gC1, gC10 | novi redoslijed zamrzavanja, odbijanje koraka izvan redoslijeda (8 provjera), sonda A = B, lanac do `DARK_VERIFIED` | 28 / 28 |
| gC2 | 5 točaka kvara `s_open` + abort + ponovni dark | 25 / 25 |
| gC3 | 7 integriranih scenarija blokiranog aborta | 33 / 33 |
| gC4 | verdikti sonde na klonovima (6) + re-dark | 7 / 7 |
| gC5 | pravi upload → blokada → odbijanja tokena → NO-GO | 9 / 10 (1 FAIL zamijenjen u D2, nalaz 1) |
| gD1 | STOP-1 + oporavak R1; vrata `s_target_reset_after_rollback`; zamrzavanje pod opterećenjem; R1 iz `DARK_VERIFIED` s API verifyem prema zamrznutom baselineu; odbijanje poslije | 28 / 28 |
| gD2 | pravi upload → blokada (E4/E5/E6) → GO s tokenom → `OPEN_CONFIRMED` → 6 odbijanja | 30 / 30 |
| gD3 | 2 čista aborta sa završnim kodom + fault-free `s_open` (`OPEN_CONFIRMED`, puni lanac stanja) + 6 odbijanja + pražnjenje reda na novoj bazi + API verify PASS + izvor nepromijenjen | 33 / 33 |
| povijesni FAIL-ovi | 3 greške u toku testa/fixturea (nedostajao `baseline-*.json`, nedostajao testni backup za preflight, kriva očekivana lista stanja), 2 stvarna nalaza (E6/`mtime`; ponovno pauziranje nakon aborta) | 5 FAIL, svi ispravljeni i ponovljeni |
| **Ukupno** | | **229 PASS / 234 zabilježeno, 0 otvorenih FAIL** |

Dokazi (privatni, 0700): `/opt/stacks/data/backups/immich-rehearsal-20261115t090733z-2905f8` (`rehearsal-results.json`, `audit.jsonl`, svaki `immich-cutover-reh*` s `state.log`, `abort-evidence.log`, `HALT-REPORT.txt`, `freeze-order.log`). Rehearsal stack je uklonjen (kontejneri, mreža, testni direktorij); backupovi i prethodni dokazi sačuvani.

### Ograničenja testa (iskreno)

- Kvarovi su ubrizgani u točkama (`CUTOVER_FAULT`, aktivno **samo** u rehearsal načinu), a ne stvarnim `kill -9` skripte usred `docker compose`. Točka "tijekom recreatea" je odmah nakon što je `compose up` vratio kontrolu (server već pokrenut), što je najopasniji djelomični slučaj.
- Scenariji C2 i C3 (file-only) izvedeni su s ranijom verzijom E6 (`mtime`); odlučujuća inačica (`ctime`) provjerena je u D2 (otkrivanje) i D3 (čiste granice), pa ostaje samo nepokazan scenarij "file-only" s `ctime`; logika je ista kao u D2.
- Stack nema pravi Traefik, mobilne klijente koji ponavljaju zahtjeve ni produkcijski promet; allow-lista pokretanja (`ALLOW_STARTUP`) kalibrirana je na rehearsalu. Ako produkcijska aplikacija pri startu dira još neku tablicu, abort će završiti u HALT-u (sigurna strana), nikad pogrešno u rollbacku.

## 5. Što to znači u produkciji

- Abort **čistih** kvarova (prije `RECREATED`, ili s praznim redovima) radi. Realno očekivati da će abort iz `ROUTE_LIVE`/`AUX_STARTED` na produkciji često završiti u **HALT-u**: aplikacija odmah nastavlja `metadataExtraction` i obrađuje zadržane poslove na novoj bazi, a mobilni klijenti ponavljaju upload. To nije greška, to je namjera: ručna odluka (GO ili NO-GO s gubitkom).
- `s_freeze` sada jednom dodatno recreateira `immich_server` (API-only, bez rute) na izvornoj bazi radi baselinea; ukupno prije dark launcha su dva dodatna starta (O15).
- Redis se i dalje ne dira (nijedna naredba prema `immich_redis`); poslovi koje abort ostavi u redu ostaju u Redisu.

## 6. Ažurirani STOP uvjeti i GO/NO-GO (sažetak; potpuno u doc 17)

STOP-1 (pražnjenje/zaustavljanje pisca/baseline) → R1 iz `FREEZING`; STOP-2…6 nepromijenjeni; **novi STOP-7**: bilo koji kvar `s_open` → samo `s_open_abort`; **HALT**: oštećen žurnal, nedostajući ili FAIL dokaz, pisanje u novu bazu, neočekivan `.env` → bez automatskih radnji, `HALT-REPORT.txt`, ručni token.
Novi kriteriji: **K9** baseline iz zamrznutog stanja bez dopuštene razlike; **K15** žurnal valjan i slijed stanja ispravan prije `s_open`; **K16** redoslijed zamrzavanja i `freeze-gap-proof` PASS; **K17** `s_open_abort` smije se prihvatiti samo uz E1–E7 PASS, a svaki HALT traži pisanu odluku. Nova operacija **O15** (frozen-read instanca) i proširen **O14** (tko izdaje token nakon HALT-a).

## 7. Preostali blokeri za produkcijski GO

1. **G6** off-host kopija: nema odredišta i ključa za šifriranje (doc 19).
2. **G10** privremeni API ključevi nisu kreirani (točan najmanji skup je potvrđen i u rehearsalu); preflight s ključevima (A0) još nije izvršen.
3. **G2, G7, G8, G3, G11**: pragovi (osobito minimalni recall 0,90 za `face_index`), termin, retencija, odobrenje izmjene `.env`/recreatea, osoba za OIDC, obavijest korisnicima i utišan monitoring.
4. **O14/O15 (novo):** imenovati tko smije izdati token za `s_manual_forward` / `s_manual_rollback_accept_loss` i odobriti dodatni kratki start servera u `s_freeze`.
5. **Nije probano jer postoji samo u produkciji:** stvarni Traefik, `media-operations` i bridge tijekom cutovera, OIDC, kanarski testovi, stvarni promet i mobilni klijenti, stvarni `kill -9` usred koraka. Preporuka: probati `s_freeze` → `s_dark_launch` → `s_rollback_r1` na produkciji kao zasebnu odobrenu "probu bez otvaranja" prije pravog prozora.

Odluke D2 iz doc 19 (kopija Redisa) i potvrda off-host statusa medija i dalje su otvorene, ali nisu blokeri.

## 8. Što je izvršeno

Samo izolirani stack (`immich-apptest-*`), bez portova, bez `docker.sock` i produkcijskih mountova, bez produkcijskih tajni i medija. Produkcija: samo čitanje za provjeru nepromijenjenosti. Izmijenjene datoteke u repozitoriju: `immich-cutover/` (nove `cutstate.py`, `write_probe.py`, `docker-compose.frozen.yml`; izmijenjene `steps.sh`, `tests/offline_selftest.sh`, `rehearsal/*`) i dokumenti 17 i 20. Nije izvršeno: pokretanje `immich-db`, promjena produkcijskih kontejnera, baza, mreža, `.env`, API ključeva, zaustavljanje produkcijskog Immicha, cutover; nijedan backup ni dokaz nije obrisan.

**Stati ovdje. Produkcijska migracija nije odobrena.**
