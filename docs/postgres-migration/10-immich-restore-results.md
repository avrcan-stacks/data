# 10 — Immich restore test: rezultati faze 4

Datum: 14. studenoga 2026. (Europe/Zagreb).
Case: **20261114t152235z-1bb3b8**.
Početak source snapshota: **2026-11-14T16:25:34.923995+01:00**.

**Status: HALT — test zaustavljen na početnoj bridge validaciji zbog razlike tipa identity sekvence.**

Puni konzistentni dump i restore u izoliranu bridge bazu završili su uspješno. Metapodaci, vlasništvo i ACL-ovi podudaraju se osim tipa jedne sekvence. U skladu s izričitim pravilom zaustavljanja nisu nastavljeni hash testovi bridge podataka, DROP EXTENSION, sanitizirani dump, drugi restore ili ANN mjerenja.

Ovo nije potvrda produkcijske spremnosti niti potpune jednakosti obnovljenih podataka. Produkcijski postgis ostao je aktivan i nepromijenjen; aplikacijske konekcije nisu mijenjane.

## Rezultat svakog koraka

| Korak | Rezultat | Dokaz / granica |
| --- | --- | --- |
| Preflight imageova, kapaciteta i izolacije | PASS | Oba pinana image ID-a dostupna; oko 439 GiB slobodno; budući migracijski direktoriji prazni |
| Konzistentni source snapshot | PASS | READ ONLY REPEATABLE READ; isti snapshot za manifest/SRS/dump; zatvoren nakon 65.87 s |
| Manifest sadržaja svih 72 source tablica | PASS | 1.080.420 redaka; COUNT iz COPY streama i SHA-256 po tablici |
| Puni dump immich | PASS | exit 0; 354.261.195 bajtova; 40.73 s |
| SRS sidecar | PASS | Puni CSV spatial_ref_sys iz istog snapshota; 8500 redaka plus header |
| Bridge pokretanje i full restore | PASS | network none, vlastiti PGDATA, originalni image; pg_restore exit 0 u 17.90 s |
| Vlasništvo/ACL/definicije objekata | DJELOMIČNO PASS | Svi uspoređeni odjeljci jednaki osim tipa sekvence; details niže |
| Tip sekvence | FAIL / HALT | Izvor bigint, bridge integer; neočekivana definicijska razlika |
| Bridge hash usporedba svih 72 tablice | NIJE IZVRŠENO | Zaustavljeno prije tog koraka; source baseline je sačuvan |
| DROP EXTENSION postgis RESTRICT | NIJE IZVRŠENO | Uvjet početne validacije nije zadovoljen; PostGIS ostaje i na bridge kopiji |
| Sanitizirani dump bez PostGIS-a | NIJE IZVRŠENO | Nema sanitizirane arhive |
| Restore na novi PG16.16 image | NIJE IZVRŠENO | Drugi kontejner nije kreiran |
| VectorChord recall / latencija | NIJE MJERENO | Nije dosegnut target test; nema izmišljenih rezultata |
| Produkcijska sigurnost | PASS | Container/image/StartedAt/mountovi/mreže/konfiguracije jednaki; nema restarta ni migracije |

## Izvor, snapshot i puni dump

Korišten je izvor **postgis / immich** prema [odobrenom planu](09-immich-restore-plan.md). Snapshot exporter držao je read-only transakciju samo tijekom prikupljanja manifesta i dumpa, ne tijekom bridge restorea. Source baza ostala je dostupna aplikacijama; nije rađen write-freeze i ovo nije finalni cutover snapshot.

Manifest sadrži svih 72 aplikacijskih tablica, canonical JSONB COPY stream u PK redoslijedu ili COLLATE C za tablice bez PK, uz UTC/ISO/extra_float_digits=3. Sadržaj je streaman u host SHA-256; retci i embeddingi nisu ispisivani u javni izvještaj.

~~~text
Full archive: immich.full.dump
Size: 354261195 bytes (337.85 MiB)
SHA-256: 9d901f555df93f909290c6a505e3836ad9dc1d0e97e371227f599797d3632a5e
Dump duration: 40.731 s
Source capture total: 65.873 s
~~~

Puni SRS sidecar:

~~~text
File: spatial_ref_sys.source.csv
SHA-256: c45afe110288f288558f5ba1491a3273ff2b9ce5498bdc284ff2dff7de4bcf09
Bytes: 7088002
Lines: 8501 (8500 data rows + header)
~~~

Sekvenca nije MVCC snapshot objekt. Source last_value provjeren prije i poslije capturea: **4274 → 4274**, bez zabilježene promjene. Nakon metadata zaustavljanja nije dodatno ispitivana bridge trenutna vrijednost sekvence; njezinu ispravnost ne proglašavati dok nije izvršena zasebna provjera.

Izvorni dump, sidecar, manifesti i logovi trajno su zadržani u privatnom direktoriju:

**/opt/stacks/data/backups/immich-restore-test-20261114t152235z-1bb3b8**

Direktorij je 0700, artefakti 0600, sadržaj je gitignored. Nema produkcijskih role password hashova ni .env kopija; sama DB arhiva i dalje sadrži osjetljive aplikacijske podatke. Retencija i brisanje pune arhive čekaju zasebnu odluku.

## Bridge i izolacija

Kontejner: **immich-restore-bridge-20261114t152235z-1bb3b8**.
Baza: **immich_restore_stage**.
Image: **sha256:33e372cc42ccaa91156d5072e48836abb2e532063dfdc79aa30e17df333a3bf0**.

Provjereno pri startu:

- network mode none, bez port bindings;
- zaseban novi /tmp data direktorij, bez produkcijskog PGDATA i bez budućih migracijskih direktorija;
- samo još read-only mount case artifact direktorija na /restore; nije montiran postojeći zajednički /backups ili /srv/qubit/backups;
- bez produkcijskih mreža, lozinki ili .env; trust samo unutar izoliranog kontejnera;
- memory cap 4 GiB, CPU cap 2, shm 1 GiB, shared_buffers 256 MiB;
- preload samo vchord, bez pg_cron i bez aplikacije;
- rola immich NOLOGIN uz nesuperuser atribute; restore kao postgres radi očuvanja stvarnih vlasnika;
- DB iz čistog template0 s owner immich, UTF8 i en_US.utf8.

Full restore je exit 0, log nema SQL grešaka. Ni taj exit kod sam ne dokazuje potpunu jednakost: metadata validacija otkrila je problem prije sljedećih faza.

## Metapodaci, vlasništvo, ACL i stanje indeksa

Usporedba je koristila stabilna imena/definicije, a ne OID-eve. ACL-ovi su kanonizirani kroz aclexplode (grantee, grantor, privilegija, grant option), uz eksplicitne PostgreSQL default ACL vrijednosti za NULL slučaj; redoslijed ACL zapisa sam po sebi nije razlika.

| Odjeljak | Source / bridge | Rezultat |
| --- | --- | --- |
| Public relacije (tablice, sekvenca, pogledi i composite relacije) | 83 / 83 | jednako; uključuje sve 72 aplikacijske tablice i extension objekte |
| Definicije indeksa | 255 / 255 | jednako |
| Constraintovi | 168 / 168 | jednako |
| Funkcije | 1095 / 1095 | jednako; definicije, owner, ACL i atributi |
| Tipovi | 208 / 208 | jednako |
| Triggeri | 51 / 51 | jednako |
| Default ACL | 3 / 3 | jednako |
| DB owner/locale/ACL i public schema ACL | source / bridge | jednako nakon primjene izvornog DB ACL-a na testno ime |
| Ekstenzije | 9 / 9 | verzije, owner i sheme jednaki |
| Sequence metadata | 1 / 1 | razlikuje se tip; ostali atributi jednaki |

Source i bridge verzije ekstenzija:

| Ekstenzija | Verzija | Owner |
| --- | --- | --- |
| cube | 1.5 | postgres |
| earthdistance | 1.2 | postgres |
| pg_trgm | 1.6 | postgres |
| plpgsql | 1.0 | postgres |
| postgis | 3.6.2 | postgres |
| unaccent | 1.1 | postgres |
| uuid-ossp | 1.1 | postgres |
| vchord | 1.1.1 | postgres |
| vector | 0.8.2 | postgres |

VectorChord i geografski indeksi iz spremljenog bridge manifesta:

| Indeks | Metoda | Valid | Ready |
| --- | --- | --- | --- |
| IDX_asset_exif_gist_earthcoord | gist | True | True |
| IDX_geodata_gist_earthcoord | gist | True | True |
| clip_index | vchordrq | True | True |
| face_index | vchordrq | True | True |

Definicije i options tih indeksa podudaraju se s izvorom. To je potvrda kataloškog stanja nakon restorea, **ne** rezultat search/ANN testa niti dokaz jednakosti svih redaka.

## Uzrok zaustavljanja: identity sekvenca

| Atribut | Source | Bridge |
| --- | --- | --- |
| name | naturalearth_countries_tmp_id_seq1 | naturalearth_countries_tmp_id_seq1 |
| type | bigint | integer |
| owner | immich | immich |
| min | 1 | 1 |
| max | 2147483647 | 2147483647 |
| start | 1 | 1 |
| increment | 1 | 1 |
| cache | 1 | 1 |
| cycle | False | False |

Stupac **public.naturalearth_countries.id** na izvoru i bridgeu jest integer, GENERATED ALWAYS AS IDENTITY. Međutim, njegova source identity sekvenca ima tip bigint s granicama 1..2147483647.

Read-only inspekcija već izrađenog full dumpa pronašla je sljedeću stvarnu DDL definiciju:

~~~sql
ALTER TABLE public.naturalearth_countries ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.naturalearth_countries_tmp_id_seq1
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    MAXVALUE 2147483647
    CACHE 1
);
~~~

Dump ne navodi AS bigint za identity sekvencu. Pri obnovi se njezin tip izvodi iz integer stupca. To objašnjava izmjerenu promjenu bigint → integer uz iste granice i ostale atribute. Nije dokazan gubitak redaka, ali stroga definicijska jednakost nije zadovoljena. Nema osnove da se razlika prešutno prihvati.

Nije izvršen ALTER SEQUENCE, ALTER TABLE, RESTART, setval ili drugo popravljanje kopije. Nakon nalaza nije uklonjen PostGIS niti je nastavljen restore pipeline.

### Predloženi idući korak, nije izvršen

Tražiti zasebno odobrenje za novu probu iz sačuvane full arhive, uz eksplicitnu normalizaciju **samo na testnim kopijama** poslije svakog restorea:

~~~sql
ALTER SEQUENCE public.naturalearth_countries_tmp_id_seq1
  AS bigint
  MINVALUE 1 MAXVALUE 2147483647
  START WITH 1 INCREMENT BY 1 CACHE 1 NO CYCLE;
~~~

Naredba namjerno nema RESTART i ne mijenja owner. Nakon nje treba provjeriti last_value/is_called, ownership/dependency vezu i da tip/granice točno odgovaraju source manifestu. [PostgreSQL dokumentacija](https://www.postgresql.org/docs/16/sql-altersequence.html) upozorava da sama promjena tipa može automatski promijeniti granice; zato su ovdje izričito navedene. START WITH ne resetira trenutni brojač.

Normalizacija mora biti planirana i **nakon restorea sanitiziranog dumpa na target**: ponovni pg_dump identity definicije može opet izostaviti source tip. Ne pretpostaviti da bi izmjena bridge sekvence automatski riješila drugi restore.

Druga mogućnost je izričito prihvaćanje semantički jednakih granica unatoč različitom tipu sekvence; to je odluka o kriteriju, nije prihvaćena u ovom testu. Produkcijska sekvenca i aplikacijski stupac ne mijenjaju se ni u jednoj predloženoj varijanti.

## Usporedba podataka i VectorChord performanse

- Source baseline: **72 tablice**, sadržajni hashovi i broj redaka spremljeni su.
- Bridge data hashovi: **nisu izračunati**, jer je zaustavljanje uslijedilo pri metadata gateu.
- Potpuna jednakost source/bridge podataka: **nije potvrđena**.
- Sanitizirani dump i PG16.16 target: **nisu napravljeni**.
- ANN recall@10, exact/ANN latencija i prirodni planner izbor: **nisu mjereni**.
- Prethodni sintetički rezultati faze 2 nisu preneseni kao rezultati stvarnog restore testa.
- Produkcijska spremnost: **nije proglašena**; pragovi recall-a/latencije i dalje nisu dogovoreni.

### Sačuvani kontrolni hashovi svih 72 source tablica

Ovo su kontrolni hashovi iz istog source snapshota kao full dump. Stupac bridge namjerno označava da usporedba nije izvedena, a ne da je pronađena razlika sadržaja.

| Tablica | Source redaka | Source SHA-256 | Bridge usporedba |
| --- | --- | --- | --- |
| activity | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| album | 11 | b0990c4fe5c71c339bc9f5062b36259411849f0349af1459dbf836546bf4f3ef | nije izvršena |
| album_asset | 23898 | 998709c6867fbe9f3f2e755ea0c5ef656a86b1144b62d7f7b700a7a4ab876be5 | nije izvršena |
| album_asset_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| album_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| album_user | 12 | babfa1cd3101a4016427df4a14898c1bfa5aaba747dd97d2e9ce994c0c1f300e | nije izvršena |
| album_user_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| api_key | 1 | 195eb5ecb6677d99cd0f4c72629ad278493b163251f12a9730036a27b001b50f | nije izvršena |
| asset | 57627 | 621a36ace208db943b0275b6416439dc8c2a5f316cc0c327e1a997529a8c89cf | nije izvršena |
| asset_audio | 147 | 21db12ff3dcd235747f1c7c9ffe1c7a3c6cc4ebccdda5b0af248a02f27d8778c | nije izvršena |
| asset_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| asset_edit | 105 | ffb052bab9f70642ee6b8a793609477433dff8a16ac86300db9a53e1bcd2da4e | nije izvršena |
| asset_edit_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| asset_exif | 57615 | aa435caf5637e87dc49c15b7ffa78585e30cc254df45a7b813405de97059e01e | nije izvršena |
| asset_face | 53063 | 39c4d2f015514a27867c87cbd84a8c810b3014bb154738c86524853cd7fac3a0 | nije izvršena |
| asset_face_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| asset_file | 123512 | daf5a6381fb65974feec028a6b05742dba7eb4ab9e1e76255923205f90c4dae0 | nije izvršena |
| asset_job_status | 57614 | bdfe5d7ed76a579bea96ca03b31ab797370f1887aff8d5fad384f61ce3f065b5 | nije izvršena |
| asset_keyframe | 150 | 4a27b1a4c4ebad07a7c1114d3e857afa0cd52beab15c5e6836f8bc30bea2441a | nije izvršena |
| asset_metadata | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| asset_metadata_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| asset_ocr | 325889 | b4b3352b0f6a6d404a1ec18be4b1f19240bfb53404f8381c292347ecaef9ffb5 | nije izvršena |
| asset_ocr_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| asset_video | 150 | a744c78f4730a5d9fa4a1474b890c78bf119024ac232c871727ce57f477ddd3e | nije izvršena |
| cluster_group | 8 | 8708a912d76632e6ec522fbabc07353ed2c9f2681190d6668577202aadf0a35c | nije izvršena |
| cluster_group_request | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| face_search | 53059 | 4ee4ff842131867a817b396d3e37213ee5f9abc7d180785468d426b53efb3370 | nije izvršena |
| geodata_places | 229133 | 1d563aa821118fe9ce6c672de613eb488d47a8bfe23779e05b91151ff2735dda | nije izvršena |
| integrity_report | 8033 | cb5e30351b69e984440be900c3fe6de060187f1187faebf5be6773afe0fca207 | nije izvršena |
| kysely_migrations | 101 | 866ba36a16a9c992d600461a4fac9f6866f58b9b058c7442462bf768c43a40a5 | nije izvršena |
| kysely_migrations_lock | 1 | 25daccf03b160b452d7bc8acf2d4887b73464ea817ebdcb8cca01b447840df7b | nije izvršena |
| library | 8 | 0b268037363649e870bb6e883d4ae29bf0182bd50c915b8c8f030be039b9238a | nije izvršena |
| memory | 486 | 1b75cf1b7227c7d6fff7d86ca4ad75428a07d333942bb4f204a82cf86eb3258b | nije izvršena |
| memory_asset | 3934 | bfd578b5fbaf3e2a7e1d656408d00a8675fb89da742d842e2d942917012e859a | nije izvršena |
| memory_asset_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| memory_audit | 446 | 9da5f61a0d8af1fad69c1cf8a7dc9b8bf0cce2483e181e524d143391df7cd1a4 | nije izvršena |
| migration_overrides | 98 | 201da8ccdedd7af2bd5b2da2dfb1a96f2f593876db78656de92af380f2c9e0c5 | nije izvršena |
| move_history | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| naturalearth_countries | 4274 | 3eacee14dbdf366b629a252739a4371fbf727060ac853581e10848d482ead7a0 | nije izvršena |
| notification | 13 | 46b666cde758cf183747ffbeb90a0509b848be74d2a9d7acb67dd1ab47d7a71c | nije izvršena |
| ocr_search | 20691 | bfd3aa8c0b28b86d1711791e6130b9eabf6d8e8aff3ef78f3a4bdb8dcc19146c | nije izvršena |
| partner | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| partner_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| person | 1197 | f96d75c94ba7938e945fb16b6ad61e1c90d1613a20112b8ff7117b6f9c5fa3cd | nije izvršena |
| person_audit | 142 | e47865a0047e43405a22cef329e4e75a40b9f633bba7f719ec95213c5cb0c9d4 | nije izvršena |
| person_group | 1197 | 521fd30702656439deb130c08a1e1cd42b5b032f5b282d1992738b74c8eeb9c8 | nije izvršena |
| person_group_audit | 142 | 671b06a4923e4fc855efc2685430918db2732bd5e9cd82dc7733330292367191 | nije izvršena |
| person_user | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| plugin | 1 | 5781542a38b94f80705870d4aa01a6c481993692dd5e4b8e929cf51a78c49d5d | nije izvršena |
| plugin_method | 14 | a4153ee04ef75cebc62ca7e6e1664a55536669e4565d0a303eee7b32ffd0e4d9 | nije izvršena |
| session | 12 | f27e17222e8c5b1d7420440b408a02475e42c866817d3cd508e521de161d494f | nije izvršena |
| session_sync_checkpoint | 59 | 107790a36deccfc40cc9c2d16f04310ae47c004bc45ba9efbc5df30a4dabb753 | nije izvršena |
| shared_link | 13 | 63408c4f99886e10a7ec3a81c6d574b8d14ed6085782a41c92f7c24ad7970b18 | nije izvršena |
| shared_link_asset | 13 | bcdbf3edb2515864548f10dc51382c3925c707666948989a58df26375389384d | nije izvršena |
| smart_search | 57502 | 089352c10499e637f757749d9865d65a9d3d0b48e28cc11c6fabc9d02d5e8924 | nije izvršena |
| stack | 8 | aa27277e2d331e36cefb0f1adb89910a6e833a43d6a82dd93c16d0c3934ac1e6 | nije izvršena |
| stack_audit | 1 | 4ed416f8499afa69ce2f8ba5eb676f11fad2de96fbf479c196d716129c17710f | nije izvršena |
| system_metadata | 8 | 157fb46e0c8699b2266ae3eaa6906638d9a863381939ac0903ca0a43c3abcb1f | nije izvršena |
| tag | 7 | 7b91b1af107f45a46f6e53ef59375d29e4b39ce1d3cf9f8aab067a559a2ff85a | nije izvršena |
| tag_asset | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| tag_closure | 7 | 928327a8cd861c2aaec1e91cd00fdf0f6170c09c4ba7a6e89e6cf3ee842e587c | nije izvršena |
| user | 8 | 1ba5bce7c34ac4de118296344ea723c3d2f8f4a3817e23b384677ea419a7609f | nije izvršena |
| user_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| user_metadata | 8 | 5e0d630fdd40e7ab1a7c49938d52c0dbc5621e0a3d95002b8b326bcfc4e799fb | nije izvršena |
| user_metadata_audit | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| version_history | 2 | d0e66105ed49ccb82c8f31ecd6c56f92356ba29f6c0e42ade3080166a91b0e2b | nije izvršena |
| video_stream_segment | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| video_stream_session | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| video_stream_variant | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| workflow | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| workflow_log | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |
| workflow_step | 0 | e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 | nije izvršena |

## Sačuvani privatni dokazi

U /opt/stacks/data/backups/immich-restore-test-20261114t152235z-1bb3b8 zadržani su:

- immich.full.dump i njegov dump log;
- spatial_ref_sys.source.csv;
- source.metadata.json, source.tables.json i source sequence prije/poslije u results.json;
- bridge-before.metadata.json;
- source-to-bridge.diff.json s točnom sequence razlikom;
- identity-sequence-diagnostic.sql izdvojen iz stvarne full arhive;
- manifest.sql i run.py radi ponovljivosti;
- commands.jsonl, progress.log, snapshot/stream logovi, restore i container logovi;
- case.json i results.json s checkpointovima, vremenima i sigurnosnim provjerama.

Private manifesti sadrže definicije objekata i ACL; javni izvještaj ne sadrži retke aplikacijskih tablica, embeddinge, API ključeve ili lozinke. Dump i privatni artefakti ne smiju u git.

## Produkcijska sigurnost i cleanup

Provjere nakon zaustavljanja:

| Provjera | Rezultat |
| --- | --- |
| postgis_id_unchanged | PASS |
| postgis_image_unchanged | PASS |
| postgis_started_unchanged | PASS |
| postgis_running | PASS |
| mounts_unchanged | PASS |
| networks_unchanged | PASS |
| config_unchanged | PASS |
| files_unchanged | PASS |
| future_dirs_empty | PASS |

Source snapshot veza je zatvorena prije bridge restorea. Bridge je zaustavljen odmah po neočekivanoj razlici; source postgis nije zaustavljan ili restartan. Novi trajni postgres/immich-db servisi nisu pokrenuti, a njihove buduće data putanje ostale su prazne.

**Izvještaj i dijagnostika spremljeni su prije čišćenja testnih resursa.** Status čišćenja nadopunjuje se u završnom odjeljku. Full dump, SRS sidecar i privatni artefakti ostaju zadržani do zasebne odluke o retenciji. Postojeći backupovi nisu prepisani ili brisani.

## Granica ovog rezultata

Faza 4 završava statusom HALT zbog sequence definicije. Nema sanitizacije ni produkcijske migracije. Za normalizaciju testne sekvence i ponovljeni/puni nastavak pipelinea potrebno je novo izričito odobrenje.

## Završeno čišćenje

Nakon spremanja ovog izvještaja, kontrolnih hashova i dijagnostike uklonjen je samo zaustavljeni kontejner immich-restore-bridge-20261114t152235z-1bb3b8 i njegova putanja /tmp/immich-restore-test-20261114t152235z-1bb3b8. Prije uklanjanja provjereni su case label, network none, mountovi i realpath. Target kontejner nije ni stvoren. Nema preostalih kontejnera ovog casea ni testnog PGDATA.

Privatni direktorij s punom arhivom i dokazima zadržan je, ukupno približno 364,6 MB. Datoteka SHA256SUMS pokriva sve privatne dokaze, a hash pune arhive ponovno je potvrđen nakon čišćenja. cleanup.json i results.json bilježe PASS za čišćenje i potvrdu da je izvještaj spremljen prije brisanja testnih resursa. Taj PASS odnosi se samo na čišćenje; ukupni restore test ostaje HALT.
