# 11 — Immich restore retest: rezultati faze 4B

Datum: 14. studenoga 2026. (Europe/Zagreb).
Case: **20261114t160754z-c96917** (privatni direktorij `/opt/stacks/data/backups/immich-retest-20261114t160754z-c96917`).
Ulaz: SHA-256 provjerena puna arhiva iz [faze 4](10-immich-restore-results.md) (`immich.full.dump`, 354261195 B, SHA-256 `9d901f555df93f909290c6a505e3836ad9dc1d0e97e371227f599797d3632a5e`); novi produkcijski dump nije rađen.

**Status: HALT — test zaustavljen na usporedbi bridge → PG 16.16 target zbog jedne razlike u tekstualnom prikazu definicije indeksa.**

Bridge dio (restore, normalizacija sekvence, hash svih 72 tablica, `DROP EXTENSION postgis RESTRICT`, sanitizirani dump) prošao je bez razlike. Restore na PG 16.16 je uspio, no usporedba metapodataka pokazala je neočekivanu razliku pa, prema pravilu zaustavljanja, nisu izvršeni hash podataka targeta, integritet targeta, ACL provjera targeta i VectorChord recall/latencija. **Nema rezultata pretraživanja i nema produkcijskog GO-a.**

## Rezultat po koracima

| Korak | Rezultat | Napomena |
| --- | --- | --- |
| Provjera izvornih dokaza (dump + SHA256SUMS) | PASS | hash dumpa i svih privatnih datoteka potvrđen prije i poslije testa |
| Bridge (originalni image, network none, vlastiti PGDATA) | PASS | PG 16.13, 2 mounta (data + read-only dokazi/dump) |
| Full restore u bridge | PASS | exit 0, prazan log, 18.2 s |
| Normalizacija sekvence (bridge) | PASS | integer → bigint, last_value 4274, is_called true |
| Metapodaci source → bridge | PASS | 0 razlika u svim odjeljcima, uključujući sekvence |
| Sadržajni hash 72 tablice source → bridge | PASS | 72/72 jednako, 1.080.420 redaka |
| `DROP EXTENSION postgis RESTRICT` (samo bridge) | PASS | bez CASCADE; nije odbijen |
| Bridge prije → poslije RESTRICT | PASS | 0 razlika nakon izuzimanja PostGIS članova; prava aplikacije nepromijenjena |
| Hash 72 tablice nakon RESTRICT | PASS | 72/72 jednako izvoru |
| Sanitizirani dump bez PostGIS-a | PASS | 354049789 B, SHA-256 `27d2bbf36980888b050d0e7a502a8d111fecf2889fa30d21113f3a38dc6cf415`, 40.3 s |
| Restore sanitiziranog dumpa u PG 16.16 | PASS | exit 0, prazan log, 17.9 s |
| Normalizacija sekvence (target) | PASS | integer → bigint, last_value 4274, is_called true |
| Metapodaci bridge → target | **FAIL / HALT** | 1 razlika: indeks `asset_localDateTime_month_idx` |
| Hash podataka targeta, integritet, ACL, amcheck | NIJE IZVRŠENO | zaustavljeno |
| VectorChord recall@10 / latencija | NIJE MJERENO | zaustavljeno |

## Sekvenca naturalearth_countries_tmp_id_seq1

Arhiva ne sadrži `AS bigint` u identity DDL-u ni u punom ni u sanitiziranom dumpu (potvrđeno čitanjem iz obje arhive), pa restore uvijek vraća `integer`. Normalizacija je zato potrebna nakon **svakog** restorea i primijenjena je dvaput.

~~~sql
ALTER SEQUENCE public.naturalearth_countries_tmp_id_seq1
  AS bigint MINVALUE 1 MAXVALUE 2147483647
  START WITH 1 INCREMENT BY 1 CACHE 1 NO CYCLE;
~~~

| Provjera | Source | Bridge prije | Bridge nakon | Target prije | Target nakon |
| --- | --- | --- | --- | --- | --- |
| Tip | bigint | integer | **bigint** | integer | **bigint** |
| min / max / start / inc / cache / cycle | 1 / 2147483647 / 1 / 1 / 1 / false | isto | isto | isto | isto |
| Owner | immich | immich | immich | immich | immich |
| ACL | — | immich: SELECT, UPDATE, USAGE | isto | isto | isto |
| last_value / is_called | 4274 / — | 4274 / true | 4274 / true | 4274 / true | 4274 / true |
| Identity dependency na naturalearth_countries.id (deptype i) | da | da | da | da | da |
| Tip stupca id / identity | integer / ALWAYS | integer / a | integer / a | integer / a | integer / a |
| max(id) / broj redaka | — | 4274 / 4274 | 4274 / 4274 | 4274 / 4274 | 4274 / 4274 |

Nema RESTART-a, brojač nije resetiran, owner i ACL nisu mijenjani. Nakon RESTRICT-a bridge je ponovno provjeren (bigint, 4274, is_called true). Nakon normalizacije sekvenca bridgea odgovara source manifestu (source-to-bridge metadata usporedba prošla je bez razlika). Za target je ista usporedba odrađena u okviru bridge → target koraka, koji je zaustavljen samo zbog indeksa; sekvence u tom koraku nisu bile među razlikama.

## Usporedba svih 72 tablica (source ↔ bridge)

Hash je SHA-256 kanonskog JSONB COPY streama (PK redoslijed, ili COLLATE "C" bez PK), isti postupak kao u fazi 4. Source hashovi su iz snapshota faze 4. Retci nisu ispisivani.

Ukupno: **72/72 tablice identične, 1.080.420 redaka**, i prije i nakon `DROP EXTENSION postgis RESTRICT`.

| Tablica | Redaka | Source SHA-256 | Bridge prije = source | Bridge nakon RESTRICT = source |
| --- | --- | --- | --- | --- |
| activity | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| album | 11 | b0990c4fe5c71c339bc9f5062b36259411849f0349af1459dbf836546bf4f3ef | DA | DA |
| album_asset | 23898 | 998709c6867fbe9f3f2e755ea0c5ef656a86b1144b62d7f7b700a7a4ab876be5 | DA | DA |
| album_asset_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| album_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| album_user | 12 | babfa1cd3101a4016427df4a14898c1bfa5aaba747dd97d2e9ce994c0c1f300e | DA | DA |
| album_user_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| api_key | 1 | 195eb5ecb6677d99cd0f4c72629ad278493b163251f12a9730036a27b001b50f | DA | DA |
| asset | 57627 | 621a36ace208db943b0275b6416439dc8c2a5f316cc0c327e1a997529a8c89cf | DA | DA |
| asset_audio | 147 | 21db12ff3dcd235747f1c7c9ffe1c7a3c6cc4ebccdda5b0af248a02f27d8778c | DA | DA |
| asset_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| asset_edit | 105 | ffb052bab9f70642ee6b8a793609477433dff8a16ac86300db9a53e1bcd2da4e | DA | DA |
| asset_edit_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| asset_exif | 57615 | aa435caf5637e87dc49c15b7ffa78585e30cc254df45a7b813405de97059e01e | DA | DA |
| asset_face | 53063 | 39c4d2f015514a27867c87cbd84a8c810b3014bb154738c86524853cd7fac3a0 | DA | DA |
| asset_face_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| asset_file | 123512 | daf5a6381fb65974feec028a6b05742dba7eb4ab9e1e76255923205f90c4dae0 | DA | DA |
| asset_job_status | 57614 | bdfe5d7ed76a579bea96ca03b31ab797370f1887aff8d5fad384f61ce3f065b5 | DA | DA |
| asset_keyframe | 150 | 4a27b1a4c4ebad07a7c1114d3e857afa0cd52beab15c5e6836f8bc30bea2441a | DA | DA |
| asset_metadata | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| asset_metadata_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| asset_ocr | 325889 | b4b3352b0f6a6d404a1ec18be4b1f19240bfb53404f8381c292347ecaef9ffb5 | DA | DA |
| asset_ocr_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| asset_video | 150 | a744c78f4730a5d9fa4a1474b890c78bf119024ac232c871727ce57f477ddd3e | DA | DA |
| cluster_group | 8 | 8708a912d76632e6ec522fbabc07353ed2c9f2681190d6668577202aadf0a35c | DA | DA |
| cluster_group_request | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| face_search | 53059 | 4ee4ff842131867a817b396d3e37213ee5f9abc7d180785468d426b53efb3370 | DA | DA |
| geodata_places | 229133 | 1d563aa821118fe9ce6c672de613eb488d47a8bfe23779e05b91151ff2735dda | DA | DA |
| integrity_report | 8033 | cb5e30351b69e984440be900c3fe6de060187f1187faebf5be6773afe0fca207 | DA | DA |
| kysely_migrations | 101 | 866ba36a16a9c992d600461a4fac9f6866f58b9b058c7442462bf768c43a40a5 | DA | DA |
| kysely_migrations_lock | 1 | 25daccf03b160b452d7bc8acf2d4887b73464ea817ebdcb8cca01b447840df7b | DA | DA |
| library | 8 | 0b268037363649e870bb6e883d4ae29bf0182bd50c915b8c8f030be039b9238a | DA | DA |
| memory | 486 | 1b75cf1b7227c7d6fff7d86ca4ad75428a07d333942bb4f204a82cf86eb3258b | DA | DA |
| memory_asset | 3934 | bfd578b5fbaf3e2a7e1d656408d00a8675fb89da742d842e2d942917012e859a | DA | DA |
| memory_asset_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| memory_audit | 446 | 9da5f61a0d8af1fad69c1cf8a7dc9b8bf0cce2483e181e524d143391df7cd1a4 | DA | DA |
| migration_overrides | 98 | 201da8ccdedd7af2bd5b2da2dfb1a96f2f593876db78656de92af380f2c9e0c5 | DA | DA |
| move_history | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| naturalearth_countries | 4274 | 3eacee14dbdf366b629a252739a4371fbf727060ac853581e10848d482ead7a0 | DA | DA |
| notification | 13 | 46b666cde758cf183747ffbeb90a0509b848be74d2a9d7acb67dd1ab47d7a71c | DA | DA |
| ocr_search | 20691 | bfd3aa8c0b28b86d1711791e6130b9eabf6d8e8aff3ef78f3a4bdb8dcc19146c | DA | DA |
| partner | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| partner_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| person | 1197 | f96d75c94ba7938e945fb16b6ad61e1c90d1613a20112b8ff7117b6f9c5fa3cd | DA | DA |
| person_audit | 142 | e47865a0047e43405a22cef329e4e75a40b9f633bba7f719ec95213c5cb0c9d4 | DA | DA |
| person_group | 1197 | 521fd30702656439deb130c08a1e1cd42b5b032f5b282d1992738b74c8eeb9c8 | DA | DA |
| person_group_audit | 142 | 671b06a4923e4fc855efc2685430918db2732bd5e9cd82dc7733330292367191 | DA | DA |
| person_user | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| plugin | 1 | 5781542a38b94f80705870d4aa01a6c481993692dd5e4b8e929cf51a78c49d5d | DA | DA |
| plugin_method | 14 | a4153ee04ef75cebc62ca7e6e1664a55536669e4565d0a303eee7b32ffd0e4d9 | DA | DA |
| session | 12 | f27e17222e8c5b1d7420440b408a02475e42c866817d3cd508e521de161d494f | DA | DA |
| session_sync_checkpoint | 59 | 107790a36deccfc40cc9c2d16f04310ae47c004bc45ba9efbc5df30a4dabb753 | DA | DA |
| shared_link | 13 | 63408c4f99886e10a7ec3a81c6d574b8d14ed6085782a41c92f7c24ad7970b18 | DA | DA |
| shared_link_asset | 13 | bcdbf3edb2515864548f10dc51382c3925c707666948989a58df26375389384d | DA | DA |
| smart_search | 57502 | 089352c10499e637f757749d9865d65a9d3d0b48e28cc11c6fabc9d02d5e8924 | DA | DA |
| stack | 8 | aa27277e2d331e36cefb0f1adb89910a6e833a43d6a82dd93c16d0c3934ac1e6 | DA | DA |
| stack_audit | 1 | 4ed416f8499afa69ce2f8ba5eb676f11fad2de96fbf479c196d716129c17710f | DA | DA |
| system_metadata | 8 | 157fb46e0c8699b2266ae3eaa6906638d9a863381939ac0903ca0a43c3abcb1f | DA | DA |
| tag | 7 | 7b91b1af107f45a46f6e53ef59375d29e4b39ce1d3cf9f8aab067a559a2ff85a | DA | DA |
| tag_asset | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| tag_closure | 7 | 928327a8cd861c2aaec1e91cd00fdf0f6170c09c4ba7a6e89e6cf3ee842e587c | DA | DA |
| user | 8 | 1ba5bce7c34ac4de118296344ea723c3d2f8f4a3817e23b384677ea419a7609f | DA | DA |
| user_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| user_metadata | 8 | 5e0d630fdd40e7ab1a7c49938d52c0dbc5621e0a3d95002b8b326bcfc4e799fb | DA | DA |
| user_metadata_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| version_history | 2 | d0e66105ed49ccb82c8f31ecd6c56f92356ba29f6c0e42ade3080166a91b0e2b | DA | DA |
| video_stream_segment | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| video_stream_session | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| video_stream_variant | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| workflow | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| workflow_log | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |
| workflow_step | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | DA | DA |

Hash podataka na PG 16.16 targetu **nije** izračunat (HALT).

## PostGIS uklanjanje

- 776 funkcija, 24 tipa, 5 relacija, 1 indeks i 2 constrainta koji su pripadali PostGIS-u prije RESTRICT-a: nijedan više ne postoji na bridgeu, a nijedan se ne pojavljuje ni u sanitiziranoj arhivi ni na targetu.
- Bridge nakon RESTRICT-a: nema `spatial_ref_sys`, `geometry`, `geography` tipova niti funkcija s PostGIS bibliotekom u `probin` (0).
- Sanitizirana arhiva: 0 spominjanja `postgis`, 0 `spatial_ref_sys`, 0 geometry/geography/box2d/box3d/raster tipova u shemi, 0 imena PostGIS funkcija u TOC-u. TOC: 1725 → 943 stavki, ACL stavki 1148 → 369.
- Ostale ekstenzije (8): cube 1.5, earthdistance 1.2, pg_trgm 1.6, plpgsql 1.0, unaccent 1.1, uuid-ossp 1.1, vchord 1.1.1, vector 0.8.2 — jednake na bridgeu i targetu (provjera `extensions()` prošla).
- Metapodaci bridge prije → poslije (bez PostGIS članova): constraints 166, funkcije 319, indeksi 254, relacije 78, triggeri 51, tipovi 184, default ACL 3 — nula razlika.

## Stanje indeksa

| | Source / bridge prije | Bridge nakon RESTRICT | Target (kataloška usporedba) |
| --- | --- | --- | --- |
| Ukupno indeksa | 255 | 254 (−1 PostGIS indeks spatial_ref_sys) | 254 |
| btree / gin / gist / vchordrq | 244 / 7 / 2 / 2 | 243 / 7 / 2 / 2 | — (nije mjereno) |
| Nevaljani ili nespremni | 0 | 0 | — |
| clip_index (vchordrq, valid/ready) | da / da | da / da | definicija jednaka bridgeu |
| face_index (vchordrq, valid/ready) | da / da | da / da | definicija jednaka bridgeu |
| IDX_geodata_gist_earthcoord, IDX_asset_exif_gist_earthcoord | da / da | da / da | definicija jednaka bridgeu |
| Nevalidirani constraintovi / onemogućeni triggeri | 0 / 0 | 0 / 0 | — |

Embeddingi na bridgeu: smart_search 57502 redaka, face_search 53059, 0 NULL, sve vector(512). VectorChord opcije (`lists=[1]`, `spherical_centroids=true`, `build_threads=4`, `sampling_factor=1024`, `vector_cosine_ops`) jednake.

### Uzrok HALT-a: asset_localDateTime_month_idx

Jedina razlika između bridgea (PG 16.13) i targeta (PG 16.16), po `pg_get_indexdef`:

~~~text
bridge 16.13: ... USING btree ((date_trunc('MONTH'::text, ("localDateTime" AT TIME ZONE 'UTC'::text)) AT TIME ZONE 'UTC'::text))
target 16.16: ... USING btree (((date_trunc('MONTH'::text, ("localDateTime" AT TIME ZONE 'UTC'::text)) AT TIME ZONE 'UTC'::text)))
~~~

Razlika je samo jedan dodatni par zagrada oko izraza u tekstualnom prikazu; owner, metoda, valid/ready i options su jednaki. Vjerojatno je riječ o razlici u formatiranju izlaza `pg_get_indexdef` između minor verzija, ali to **nije dokazano** (nije uspoređen `indexprs`/`pg_node_tree` niti planer). Razlika nije prešutno prihvaćena i nije poduzeto nikakvo popravljanje.

## Rezultati pretraživanja

**Nisu mjereni.** Recall@10, exact/ANN latencija, planner izbor i zero-distance provjera nisu izvršeni jer target nije prošao metadata gate. Rezultati iz faze 2 (sintetički) ne vrijede kao zamjena. Prag recall-a/latencije i dalje nije dogovoren.

## Sigurnost i izolacija

| Provjera | Rezultat |
| --- | --- |
| postgis kontejner: Id, image, StartedAt, restart count, running | nepromijenjeno |
| postgis mountovi, mreže, hash Config-a | nepromijenjeno |
| Hash Compose/Dockerfile/.env/.env.example/tailscale env i Immich compose+env | nepromijenjeno |
| Production DB/Compose/connections | nisu diranuti; u ovom testu produkcijska baza nije kontaktirana (samo docker inspect postgis) |
| postgres-standard/data i immich-postgres/data | prazni |
| Izvorni `immich.full.dump` i privatni manifesti faze 4 | netaknuti, SHA256SUMS OK |
| Immich aplikacija na testnoj bazi | nije pokretana |
| Testni kontejneri | network none, bez portova, bez produkcijskih mountova/credova; PGDATA u /tmp |

## Čišćenje

Samo testni kontejneri ovog casea (`immich-retest-bridge-…`, `immich-retest-target-…`) i `/tmp/immich-retest-20261114t160754z-c96917` uklanjaju se nakon spremanja ovog izvještaja. Privatni direktorij `/opt/stacks/data/backups/immich-retest-20261114t160754z-c96917` (sanitizirani dump, manifesti, logovi, results.json) i sav sadržaj faze 4 ostaju zadržani.

## Sljedeći korak (nije izvršen)

Potrebna je odluka o kriteriju: ili (a) usporedba indeksa po semantici (`indexprs`/`pg_get_expr`) umjesto po `pg_get_indexdef` tekstu za izraze, uz isti nastavak testa iz iste sanitizirane arhive, ili (b) zaustavljanje. Nijedno nije započeto.

**Produkcijska migracija nije odobrena niti pripremljena.**
