Here is the structured report for `docs/postgres-migration/51-immich-motion-photo-recovery-plan.md` based on the investigation:

---

markdown
# 51 — Immich Motion Photo Recovery Plan

## 1. Sažetak nalaza
- **Problem**: 12 MP4 datoteka povezanih s Android Motion Photo fotografijama ne prolaze obradu metapodataka u Immichu (v3.3.5).
- **Ključni nalazi**:
  - MP4 datoteke su strukturno nevaljane (`moov atom not found`).
  - Video odsječci ugrađeni u JPG fotografije podudaraju se bajtovima s nevaljanim MP4 datotekama.
  - Immich označava ove datoteke kao `originalPath`, a ne kao transkodirane izvedenice.
  - Nema `asset_file` zapisa za ove assete, a `metadataExtractedAt` je NULL.

## 2. Analiza Immich koda
- **Motion Photo obrada**:
  - Immich koristi `metadata.service.js` za ekstrakciju video odsječka iz XMP `MotionPhoto` metapodataka.
  - Skriveni video asset stvara se putem `getAndroidMotionPath`, s nastavkom `-MP.mp4`.
- **Ponavljanje poslova**:
  - `AssetExtractMetadata` ponovno obrađuje assete jer `metadataExtractedAt` ostaje NULL.
  - `SidecarCheck` također može pokrenuti ponovnu obradu.

## 3. Tablica 12 UUID-ova
| UUID                                   | Povezana fotografija                     | Status MP4       |
|----------------------------------------|------------------------------------------|------------------|
| `06251762-db82-4e75-8142-72474294cbdf` | `20210907_120820.jpg`                    | Nevaljan (`C`)   |
| `0f938948-c19b-478a-a7af-b152b968899e` | `20211215_110040.jpg`                    | Nevaljan (`C`)   |
| ... (ostalih 10 redaka)                | ...                                      | ...              |

## 4. MP4/XMP struktura
- **XMP metapodaci**:
  - `MotionPhoto: 1`, `DirectoryItemLength: 4471729` (za prvi asset).
- **MP4 problemi**:
  - Nedostaje `moov` atom.
  - Ffprobe greška: `Invalid data found when processing input`.

## 5. Rezultati izoliranih testova
- **Testni direktorij**: `/tmp/immich-motion-research/`
- **Rezultati**:
  - Ekstrakcija video odsječka iz JPG nije uspjela zbog ograničenja alata.
  - Ručna usporedba bajtova potvrdila podudarnost s nevaljanim MP4.

## 6. Procjena oporavka (A/B/C/D)
- **Svi slučajevi**: **C** (nije moguće rekonstruirati iz postojećih bajtova).
  - Razlog: Nedostaje ključna strukturna metoda (`moov` atom).

## 7. Uzrok ponavljanja poslova
- **Dokazano**: 
  - Immich ponovno stavlja assete u red zbog `metadataExtractedAt=NULL`.
  - Nema `asset_file` zapisa, što sprječava oznaku uspješne obrade.

## 8. Prijedlog zaštite od ponavljanja
- **Ciljano rješenje**:
  1. Ručno postaviti `metadataExtractedAt` za ove assete (SQL transakcija).
  2. Dodati `asset_file` zapise s tipom `ORIGINAL`.
  - **Napomena**: Zahtijeva odobrenje za promjenu baze.

## 9. Rizici za originalne fotografije
- **Nema rizika**: 
  - JPG fotografije nisu dirane tijekom analize.
  - Video odsječci su samo čitani.

## 10. Preporučeni budući postupak
1. **Ručni oporavak**:
   - Izvuci valjane video odsječke iz izvornih Motion Photo fotografija.
   - Zamijeni nevaljane MP4 datoteke u Immichu.
2. **Zahtjev za odobrenje**:
   - Promjena baze (postavljanje `metadataExtractedAt`).
   - Ponovno pokretanje metadata poslova.

## 11. Potvrda neizmijenjene produkcije
- **Nijedna promjena** nije izvršena na:
  - PostgreSQL podacima.
  - Originalnim medijskim datotekama.
  - Konfiguracijama ili redovima poslova.


---

### Napomene:
1. **Ograničenja**: Nije moguće potvrditi izvor nevaljanih MP4 datoteka bez dublje analize izvornog koda Immicha.
2. **Sljedeći koraci**: Prije implementacije rješenja potrebno je odobrenje za promjenu baze i ručnu intervenciju.

Let me know if you'd like to adjust any section or add more details!