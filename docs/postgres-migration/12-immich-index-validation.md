# 12 — Immich: validacija indeksa asset_localDateTime_month_idx i nastavak target validacije

Datum: 14. studenoga 2026. (Europe/Zagreb).
Case: **20261114t161905z-ef3367** (privatni direktorij `/opt/stacks/data/backups/immich-index-validation-20261114t161905z-ef3367`).
Ulaz: [izvještaj 11](11-immich-restore-retest.md); sanitizirana arhiva iz faze 4B `immich.no-postgis.dump`, SHA-256 `27d2bbf36980888b050d0e7a502a8d111fecf2889fa30d21113f3a38dc6cf415` (potvrđen prije i poslije testa). Novi produkcijski dump nije rađen.

**Status: PASS.** Razlika u definiciji indeksa potvrđena je kao isključivo tekstualno formatiranje i evidentirana kao ograničena dopuštena iznimka. Nastavak validacije targeta (PG 16.16) prošao je bez ijedne druge razlike.

Ovo je rezultat SQL restore probe nad kopijom. **Nije produkcijski GO**: aplikacija nije pokretana, pragovi recall-a/latencije nisu dogovoreni, a autentikacija, mediji i cutover nisu predmet testa.

## Rezultat po koracima

| Korak | Rezultat | Napomena |
| --- | --- | --- |
| Provjera ulaza (sanitizirani dump, full dump, SHA256SUMS obaju prethodnih slučajeva) | PASS | |
| Dva izolirana clustera: 16.13 (originalni bridge image) i 16.16 (novi image) | PASS | network none, bez portova, mountovi samo PGDATA + read-only dump |
| Restore iste sanitizirane arhive u oba | PASS | exit 0, prazni logovi, 18.1 s / 17.9 s |
| Normalizacija sekvence na bigint (samo kopije) | PASS | oba clustera, vidi niže |
| Metapodaci source → 16.13 (bez PostGIS članova) | PASS | 0 razlika |
| Semantička usporedba indeksa 16.13 ↔ 16.16 | PASS | 254 indeksa, 0 strukturnih razlika |
| Izvršavanje ekvivalentnog upita i korištenje indeksa | PASS | oba servera, vidi niže |
| Iznimka za tekstualno formatiranje | evidentirana | samo `asset_localDateTime_month_idx`, samo `pg_get_indexdef` |
| Metapodaci 16.13 → 16.16 i source → 16.16 (s iznimkom) | PASS | 0 drugih razlika |
| Hashovi 72 tablice | PASS | 72/72 na oba servera = source |
| PostGIS odsutnost | PASS | 776 funkcija, 24 tipa, 5 relacija, 1 indeks, 2 constrainta ne postoje ni na jednom serveru |
| Integritet (indeksi, constraintovi, triggeri, amcheck) | PASS | vidi niže |
| ACL / efektivna prava | PASS | vidi niže |
| VectorChord recall@10 i latencija | PASS (izmjereno) | vidi niže; prag nije dogovoren |
| Sigurnost produkcije | PASS | vidi niže |

## Sekvenca naturalearth_countries_tmp_id_seq1

Obje obnove vraćaju `integer` jer arhiva ne sadrži `AS bigint`. Normalizacija je izvršena odmah nakon restorea na oba clustera:

~~~sql
ALTER SEQUENCE public.naturalearth_countries_tmp_id_seq1
  AS bigint MINVALUE 1 MAXVALUE 2147483647
  START WITH 1 INCREMENT BY 1 CACHE 1 NO CYCLE;
~~~

| Provjera | 16.13 prije → nakon | 16.16 prije → nakon |
| --- | --- | --- |
| Tip | integer → **bigint** | integer → **bigint** |
| min / max / start / inc / cache / cycle | 1 / 2147483647 / 1 / 1 / 1 / false (nepromijeno) | isto |
| Owner / ACL | immich / SELECT, UPDATE, USAGE (nepromijeno) | isto |
| last_value / is_called | 4274 / true | 4274 / true |
| Identity dependency na naturalearth_countries.id | da (deptype i) | da (deptype i) |
| max(id) / broj redaka | 4274 / 4274 | 4274 / 4274 |

Nema RESTART-a. Arhivirani `setval` je `4274, true`. Nakon normalizacije metadata usporedba sa sourceom prošla je bez razlika.

## Usporedba indeksa asset_localDateTime_month_idx

Tablica `public.asset`, btree, jedan izrazni stupac, bez predikata.

| Svojstvo | 16.13 | 16.16 | Jednako |
| --- | --- | --- | --- |
| Pohranjeno stablo izraza (`indexprs`, pg_node_tree) | funcid 2069 (timezone) nad funcid 2020 (date_trunc) nad funcid 1159 (timezone) nad stupcem `localDateTime` | isto, znak po znak | DA |
| `pg_get_expr(indexprs, indrelid)` | `(date_trunc('MONTH'::text, ("localDateTime" AT TIME ZONE 'UTC'::text)) AT TIME ZONE 'UTC'::text)` | isto | DA |
| `pg_get_expr(..., pretty)` | isto | isto | DA |
| Tip izraza (atribut indeksa) | timestamp with time zone | timestamp with time zone | DA |
| Kolacija indeksa / inputcollid izraza | nema / 100 (default) | nema / 100 (default) | DA |
| Operatorska klasa | timestamptz_ops (datetime_ops, default) | isto | DA |
| indkey / indoption / natts / nkeyatts | 0 / 0 / 1 / 1 | isto | DA |
| Pristupna metoda, unique, nulls_not_distinct, primary, exclusion | btree, ne, ne, ne, ne | isto | DA |
| valid / ready / live | true / true / true | true / true / true | DA |
| reloptions, tablespace, owner | nema, pg_default, postgres | isto | DA |
| `pg_get_indexdef(oid)` | `... USING btree ((date_trunc(...) AT TIME ZONE 'UTC'::text))` | `... USING btree (((date_trunc(...) AT TIME ZONE 'UTC'::text)))` | **NE** (dodatni par zagrada) |
| `pg_get_indexdef(oid, 1, true)` (stupac) | `(...)` | `((...))` | **NE** (dodatni par zagrada) |

Ista usporedba strukturnih atributa napravljena je za **svih 254 indeksa** u public shemi (uključujući clip_index i face_index): 0 strukturnih razlika. Jedini indeks s razlikom u tekstualnom prikazu je ovaj.

### Upit i korištenje indeksa

Upit s izrazom identičnim izrazu indeksa, uz jednakost na vrijednost mjeseca, izvršen je na oba servera (nakon `ANALYZE`) za 4 mjeseca: najraniji, srednji, najkasniji i najgušći (od ukupno 183 različitih mjeseci). Za svaki: (a) indeks forsiran (`enable_seqscan=off`), (b) heap forsiran (indeksi isključeni), (c) planner bez ograničenja. Rezultat je count plus md5 sortiranih ID-eva; ID-evi nisu ispisivani.

| Redaka u mjesecu | Rezultat (count+md5 id-eva) | 16.13 indeks / heap / planner (ms) | 16.16 indeks / heap / planner (ms) |
| --- | --- | --- | --- |
| 1 | jednak u svih 6 izvedbi | 0.28 / 20.40 / 0.29 | 0.28 / 17.55 / 0.28 |
| 165 | jednak u svih 6 izvedbi | 0.64 / 20.85 / 0.56 | 0.66 / 17.93 / 0.67 |
| 550 | jednak u svih 6 izvedbi | 1.12 / 20.99 / 1.19 | 1.71 / 27.88 / 1.48 |
| 1839 | jednak u svih 6 izvedbi | 3.11 / 19.39 / 3.00 | 3.00 / 19.74 / 2.98 |

- Rezultati su identični između sve tri izvedbe i oba servera za svaki mjesec.
- Forsirani indeks: plan koristi `asset_localDateTime_month_idx` (Bitmap Index Scan) na 16.13 i na 16.16. Forsirani heap: Seq Scan bez indeksa.
- Planner bez ograničenja bira isti indeks na oba servera u svih 4 mjeseca.
- Razlike u ms između servera su unutar šuma jednog kratkog mjerenja (medijan 3 izvršenja); to nije benchmark.

### Zaključak i dopuštena iznimka

Pohranjeno stablo izraza, tip, kolacija, operatorska klasa, opcije i ponašanje upita jednaki su. Razlika je samo u dodatnom paru zagrada koji `pg_get_indexdef` na 16.16 stavlja oko izraznog stupca; `pg_get_expr` je identičan. Semantička jednakost je potvrđena.

**Iznimka (ograničena):** u usporedbama metapodataka 16.13 ↔ 16.16 i source ↔ 16.16 smije se razlikovati isključivo polje `definition` (tekst `pg_get_indexdef`) indeksa `asset_localDateTime_month_idx`. Bilo koja druga razlika na tom ili bilo kojem drugom indeksu i dalje zaustavlja test. Za buduće usporedbe između verzija treba uspoređivati izraze indeksa strukturno, ne samo `pg_get_indexdef` tekstom. Uzrok promjene formatiranja u PostgreSQL minor verziji nije istraživan; tvrdnja se temelji na izmjerenoj jednakosti, ne na release notesima.

## Svih 72 tablice

Isti postupak hashiranja kao u fazama 4 i 4B (kanonski JSONB COPY stream, PK redoslijed ili COLLATE "C", SHA-256). Retci nisu ispisivani. **72/72 identične, 1.080.420 redaka, na 16.13 i na 16.16.**

| Tablica | Redaka | Source SHA-256 | 16.13 = source | 16.16 = source |
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

## Stanje indeksa na targetu (16.16)

| Stavka | Rezultat |
| --- | --- |
| Ukupno indeksa (btree / gin / gist / vchordrq) | 254 (243 / 7 / 2 / 2) |
| Nevaljani, nespremni ili neaktivni | 0 |
| Nevalidirani constraintovi / onemogućeni triggeri | 0 / 0 |
| Constraintovi (check / foreign key / primary / unique) | 6 / 73 / 72 / 15 |
| clip_index (vchordrq, valid/ready) | da / da; 169.975.808 B; opcije `lists=[1]`, `spherical_centroids=true`, `build_threads=4`, `sampling_factor=1024`, `vector_cosine_ops` jednake izvoru |
| face_index (vchordrq, valid/ready) | da / da; 156.868.608 B; iste opcije |
| IDX_geodata_gist_earthcoord, IDX_asset_exif_gist_earthcoord | valid/ready; definicije jednake izvoru |
| Embeddingi | smart_search 57502 redaka, face_search 53059; 0 NULL; svi vector(512) |
| amcheck (`bt_index_check` s heapallindexed, `verify_heapam` s TOAST) | 243 btree indeksa i 72 tablice provjereno, 0 grešaka; ekstenzija je stvorena u transakciji koja je poništena (nije ostala u bazi) |
| Nepostojanje PostGIS binarne ovisnosti | 0 funkcija s PostGIS bibliotekom; PostGIS nije dostupan u 16.16 imageu |
| Katalog nakon `ANALYZE` | nepromijenjen (usporedba prije/poslije bez razlika) |

## ACL i efektivna prava

- Efektivna prava role immich (SET LOCAL ROLE): 72/72 tablice imaju SELECT, INSERT, UPDATE i DELETE; role nije superuser; `ll_to_earth_public` i `f_unaccent` izvršivi; sve 319 public funkcija izvršivo (0 neizvršivih); USAGE/CREATE na public shemi i CONNECT/CREATE na bazi kao u izvoru.
- Rezultat je identičan između 16.13 i 16.16 i identičan prethodnom bridge rezultatu iz faze 4B.
- Vlasništvo i ACL u katalogu (relacije, funkcije, tipovi, sekvence, default ACL, shema, baza) uspoređeni su s izvorom bez razlika.
- Ovo su provjere privilegija, ne stvarni INSERT/UPDATE retci. Testna rola je NOLOGIN; autentikacija nije testirana.

## VectorChord recall@10 i latencija (PG 16.16)

Deterministički uzorak: prvih 10 ne-NULL, ne-nultih vektora po tablici, redom po ID-u. Upit kao u aplikaciji: nova transakcija, `SET LOCAL vchordrq.probes=1`, kosinusna udaljenost, LIMIT 10, uloga immich. Recall je ANN top-10 naspram egzaktnog top-10 (indeksi isključeni). Latencija je medijan tri `EXPLAIN ANALYZE` izvršenja po upitu, zatim medijan/maksimum preko 10 uzoraka.

| Tablica / indeks | Recall@10 prosjek / minimum | Tie-aware recall@10 | ANN medijan / maks (ms) | Egzaktno medijan / maks (ms) | Planner bez ograničenja koristi indeks | Zero-distance pogodak |
| --- | --- | --- | --- | --- | --- | --- |
| smart_search / clip_index | 1.00 / 1.00 | 1.00 | 4.01 / 29.54 | 220.4 / 234.5 | 10/10 | 10/10 |
| face_search / face_index | 1.00 / 1.00 | 1.00 | 3.41 / 139.94 | 199.0 / 233.4 | 10/10 | 10/10 |

- Forsirani ANN plan koristi clip_index odnosno face_index; maksimalna razlika udaljenosti ANN naspram egzaktnog je 0.
- Maksimum ANN latencije face_index (139.9 ms) odskače od medijana (3.4 ms); uzrok nije istražen (moguće hladna cache prvog upita, ali to nije potvrđeno).
- **Ograničenja:** uzorak je samo 10 vektora po tablici, a upiti su vlastiti postojeći vektori (zato uvijek postoji zero-distance pogodak), što je blaža provjera od stvarnih tekstualnih/slikovnih upita. Recall 1.0 uz `lists=[1]` i `probes=1` očekivan je za ovako malu konfiguraciju, ali nije dokaz za buduće veće tablice. Mjerenje je na izoliranom kontejneru s 4 GiB memorije bez opterećenja aplikacije. Prag recall-a i dopuštene latencije nije dogovoren, pa se rezultat evidentira, ne ocjenjuje.

## Sigurnost i izolacija

| Provjera | Rezultat |
| --- | --- |
| postgis kontejner: Id, image, StartedAt, restart count, running, mountovi, mreže, hash Config-a | nepromijenjeno |
| Hash Compose/Dockerfile/.env/.env.example/tailscale env i Immich compose+env | nepromijenjeno |
| Produkcijska baza | nije kontaktirana (samo `docker inspect postgis`) |
| postgres-standard/data i immich-postgres/data | prazni |
| Izvorni `immich.full.dump` i sanitizirani dump | SHA-256 nepromijenjen; nijedan backup nije brisan ni mijenjan |
| Immich aplikacija, Docker Compose, produkcijske konekcije | nisu pokretani/mijenjani |
| Testni kontejneri | network none, bez portova, bez produkcijskih mountova i credova; PGDATA u /tmp; limiti 4 GiB / 2 CPU |

## Čišćenje

Dva testna kontejnera (`immich-idx-a1613-…`, `immich-idx-b1616-…`) i `/tmp/immich-idx-20261114t161905z-ef3367` uklonjeni su nakon spremanja ovog izvještaja (provjereni label, mountovi i da ih nijedan proces ne koristi). Privatni direktorij slučaja ostaje s manifestima, logovima, `results.json` i SHA256SUMS. Dokazi faza 4 i 4B ostaju netaknuti.

## Granica rezultata

Rezultat vrijedi za jedan snapshot (14. 11. 2026.) uz živi izvor bez write-freezea. Za stvarnu migraciju ostaje potrebno: dogovoreni pragovi recall-a/latencije, test s aplikacijom (migracije i automatsko reindeksiranje pri startu), autentikacija/HBA, plan prekida rada i novi dump u trenutku cutovera.

**Stati ovdje. Produkcijska migracija nije odobrena niti pripremljena.**
