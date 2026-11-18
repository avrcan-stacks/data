# 56 — Immich Migration Closure

## 1. Migracija i vremenska crta

- **CUTOVER_ID:** `20261115t150714z` — identifikator pokušaja, a ne vrijeme početka zamrzavanja.
- **T0:** `2026-11-15T16:54:17Z` — početak cutover sata u F4; stvarni FROZEN potvrđen je u `2026-11-15T16:57:14Z` (dokument 46).
- **T_open:** `2026-11-15T17:05:12Z`; **OPEN_CONFIRMED:** `2026-11-15T17:05:16Z` — završetak prebacivanja baze (dokument 46).
- **MIGRATION_OPERATIONALLY_ACCEPTED:** 18.11.2026. — kasnije operativno prihvaćanje i dokumentacijsko zatvaranje, a ne vrijeme prebacivanja baze.
- **Izvor:** `postgis/immich` (PostgreSQL 16.13); **cilj:** `immich-db/immich` (PostgreSQL 16.16).

## 2. Potvrđeni rezultati i naknadni nalazi

| Nalaz | Izvor i opseg dokaza |
| --- | --- |
| `OPEN_CONFIRMED`; F4–F10 rc 0, HTTP 200, API Q1–Q10 PASS, G14 PASS | Dokument 46: stanje i mjerenja nakon otvaranja. |
| Završna provjera `HALT_FINAL_VALIDATION`, 31 PASS / 1 FAIL | Dokument 46: greške obrade 12 MP4; operativno prihvaćanje ne preoznačuje taj povijesni rezultat u PASS. |
| Valjan žurnal, HTTP 200, Q1–Q10 PASS; Redis bez restarta | Dokument 47: naknadni audit 18.11.; rezultati vrijede za vrijeme te provjere. |
| Ponavljane MP4 greške, dodatne JPEG greške i pet poslovnih grešaka u posljednjem provjerenom bridge ciklusu | Dokument 47: naknadni nalazi; nisu označeni uspješnom obradom. |
| Dvije provjerene kopije za svakih 14 aplikacijskih backupova | Dokument 48: SHA-256, gzip i byte-by-byte PASS. |

Dokument 55 bilježi `INFRASTRUCTURE_ACCEPTANCE_PASS` i neke naknadne metrike; za tehničke činjenice ovog zatvaranja mjerodavni su dokazi iz 46–48. Tvrdnje iz 55 koje ovdje nisu potkrijepljene tim dokazima, uključujući pojedine brojčane metrike opterećenja, ostaju **NOT VERIFIED** u ovom dokumentu. Ne izvodi se tvrdnja o potpunom prolazu svih odgođenih provjera.

## 3. Vlasnikova potvrda i prihvaćena odstupanja

| Provjera / odluka | Status |
| --- | --- |
| OIDC web | `OIDC_WEB_PASS — OWNER_CONFIRMED` — vlasnikova potvrda; dokument 46 ranije ju je evidentirao kao odgođenu, a dokument 55 kao `OWNER_CHECK_PENDING`. |
| OIDC mobilna aplikacija | `OIDC_MOBILE_NOT_TESTED` |
| 12 Motion Photo MP4 i 5 JPEG problema | `KNOWN_MEDIA_DEVIATIONS_ACCEPTED` — poznata odstupanja; njihova obrada nije potvrđena uspješnom. |

## 4. Backupovi i zaštita

**Aplikacijski backupovi:** dokument 48 bilježi 14 tada postojećih backupova i dvije zaštićene kopije svakoga: ukupno **28 dodatnih kopija**, a ne 28 različitih generacija. Provjere SHA-256, gzip i byte-by-byte prošle su prema tom dokumentu. Kopije su lokalne i ne štite od gubitka cijelog servera. Aktivni aplikacijski direktorij zasebno koristi rutinsku rotaciju `keepLastAmount=14`; konfiguracija se ne mijenja ovim dokumentom.

Dokument 47 bilježi da u izvornom aplikacijskom direktoriju više nije bilo triju najstarijih prethodno popisanih backupova, uz nalaz da stanje odgovara automatskoj retenciji. Taj se nalaz čuva; zaštita 14 kasnije postojećih datoteka ne dokazuje očuvanost tih triju ranijih datoteka.

**Migracijski backupovi:** F0 backupovi, izvorni i sanitizirani migracijski dumpovi, njihove druge kopije na `/home` te pripadajući migracijski manifesti i dokazi čine zasebnu zaštitu. Dokumenti 46 i 47 bilježe provjere dumpova i F0 kopija za produkcijske pokušaje; aplikacijska rotacija nije isto što i retencija tih migracijskih dokaza.

## 5. Retencija

`SOURCE_RETENTION_MINIMUM=2026-11-22T17:05:12Z`

To je najraniji trenutak nakon kojeg vlasnik može zasebno razmotriti daljnju sudbinu izvorne baze. Istek roka nije odobrenje za brisanje.

Pravilo **`PRESERVE_UNTIL_EXPLICIT_OWNER_DECISION`** vrijedi zasebno za:

- Izvornu bazu `postgis/immich`.
- Arhiviranu bazu `immich_failed_20261115t150714z_`.
- Zaštićene aplikacijske backupove.
- Migracijske dumpove i njihove kopije, kao i F0 kopije.
- Migracijske manifeste i dokaze.

Promjena ili brisanje tih zaštićenih stavki zahtijeva zasebnu izričitu odluku vlasnika. Rutinska rotacija aktivnih aplikacijskih backupova `keepLastAmount=14` ostaje zaseban mehanizam.

## 6. Otvorene provjere i status

- T+7 provjera: **PENDING**; nema ovdje dokaza da je provedena.
- Mobilna OIDC prijava: **NOT_TESTED**.
- Kanarski upload/video/trash/restore i ostale odgođene provjere bez zasebnog dokaza: **NOT VERIFIED**. Dokument 46 ih nije proglasio dovršenima.
- Noćni poslovi: dokument 47 bilježi opažanja i broj `integrity_report` redaka; potpuna provjera svih noćnih poslova i daljnje praćenje ne proglašavaju se dovršenima bez zasebnog dokaza.
- Poznata medijska odstupanja i poslovne greške bridgea iz dokumenta 47 ostaju dio dokaznog traga.

**Završni operativni status: `MIGRATION_OPERATIONALLY_ACCEPTED`.** Povijesni `OPEN_CONFIRMED` i HALT završne provjere ostaju zabilježeni u dokumentu 46. Ova izmjena ispravlja dokumentaciju i sama po sebi ne pokreće čišćenje niti daje odobrenje za brisanje.
