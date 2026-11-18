# 05 — Validacija, collation postupak i rollback

Status: plan; stvarni restore, REINDEX, promjene kolacija i aplikacijski testovi nisu izvršeni.

## Što je provjereno sada

- Read-only inventar 31 netemplate i 2 connectable template baze; template0 samo metadata.
- Ekstenzije, roles/ACL grupe, default ACL, RLS, triggeri, tablespaceovi, trenutne veze, index metode i svih pet aplikacijskih vektorskih indeksa.
- PostGIS dependency klasifikacija bez LIMIT-a i statička provjera 14 dostupnih kodnih korijena.
- Gzip integritet najnovijeg Immich backupa i povijesnih pg14/pg16 dumpova; čitljiv TOC jednog aktualnog Chatwoot custom dumpa.
- Nema potvrde obnovljivosti cijelog clustera. Nisu pokrenuti produkcijski testovi, jobovi, benchmark dump/restorea ili medijski restore.

## Obvezni acceptance kriteriji po bazi

| Područje | Provjera na izoliranoj probi, zatim nakon finalnog snapshot restorea | Prolaz |
| --- | --- | --- |
| Identitet | server_version, database, owner, encoding, locale, endpoint | očekivani target i verzije |
| Shema | schema-only dump/diff, tables, partitions, constraints, views, functions, triggers, policies, default values, generated columns | nula neobjašnjenih razlika |
| Ekstenzije | pg_extension + binarne biblioteke + full_version gdje postoji | točan manifest, bez procs need upgrade |
| Podaci | exact COUNT po fizičkoj tablici/particiji, NULL profili i deterministični checksumi po PK segmentima | isti finalni snapshot; nula neobjašnjenih razlika |
| Particije | pg_inherits stablo, bounds i default particije; ne brojiti parent i children dvostruko | isto pokriće i broj fizičkih redaka |
| Sekvence/identity | last_value/is_called, increment, owner, usporedba s max ključem bez pozivanja nextval na izvoru | nema buduće kolizije |
| Veliki objekti | broj, duljina i kontrolne sume large object sadržaja ako postoje | identično |
| ACL | DB/schema/table/sequence/function/column grants, grantor, default ACL i RLS | isto odobreno ponašanje stvarnih app rola |
| Indeksi | sve očekivane definicije, indisvalid/indisready, constraints i query planovi | nema nevaljanih indeksa ni regresije ključnih upita |
| Backup | novi target dump + hash + prava obnova na odvojenom mjestu | restore uspješan i dokumentiran |
| Aplikacija | login, čitanje, kontrolirana write transakcija na targetu, worker/beat, integracije | poslovni smoke prolazi; source bez novih writera |

Za velike tablice provjere segmentirati i streamati sortirane rezultate; ne graditi golemi string_agg u memoriji. Binary/JSON normalizacija i NULL razdvajanje moraju biti fiksni; floating-point/geometrijski izračuni mogu se promijeniti s bibliotekom, ali izvorni podaci ne smiju nestati. Ako pun checksum nije vremenski prihvatljiv, to je odluka o smanjenju dokaza koju treba unaprijed odobriti, ne prešutno zamijeniti uzorkom.

COUNT i checksum baseline za finalni prijelaz mora biti pod istim write-freezeom kao finalni dump. Rezultat živog izvora iz ranije probe nije referenca za kasniji restore.

## Prostorne baze

- Farma: svih devet aplikacijskih geometry stupaca, prostorni indeksi, calculate_route_length, fieldwork_make_workitem_geom, generirani/default length_m izraz i pogledi ceste_aktivne, sibenik_ceste_2024_view, sibenik_ceste_2025_view.
- Potvrditi ST_SRID raspodjelu, GeometryType, NULL/empty counts i ST_IsValid raspodjelu po tablici; ne pretpostaviti SRID za dva generička geometry stupca.
- Minidepo: pet stupaca, deklarirani SRID 4326, pet GiST indeksa; karta, parcel/container/gate/accessroad/site čitanje i uređivanje na kopiji.
- Usporediti geometrijski sadržaj kanonskim EWKB kontrolnim sumama po PK; validnost nije isto što i jednakost.
- Za promjene GEOS/PROJ provjeriti reprezentativne ST_Transform/ST_Length i buffer rezultate uz unaprijed definiranu domensku toleranciju. Ne mijenjati projekciju ni koordinatni sustav u istom zahvatu.
- Tiger/topology objekte i podatke očuvati dok se ne potvrdi da nisu potrebni; extension parent objekti nisu automatski prazni.
- Orphan C funkcije u farma_db zahtijevaju zaseban restore dokaz i usporedbu s ciljnom definicijom. Ne ignorirati duplicate-function greške.

## Immich i Chatwoot

Immich: dvije vchordrq definicije, options i operator class usporediti s inventarom. Potvrditi vector(512), broj redaka smart_search/face_search, NULL embedding raspodjelu i očuvanje vektorskih vrijednosti. Nakon obnavljanja indeksa provjeriti planove i reprezentativno semantičko/face pretraživanje u izoliranoj aplikaciji iste v3.3.5 verzije. ANN rezultati nisu nužno bit-identični nakon rebuilda; top-k kvalitetu usporediti s exact baselineom i odobrenom tolerancijom, bez toleriranja izgubljenih embeddinga.

Fotografije i video nisu u DB dumpu. Provjeriti uzorak originala, thumbnails i external Nextcloud library putanje te hashove usklađenog medijskog backupa. Probnu aplikaciju ne spojiti na writable originalne medije, produkcijski Redis ili webhookove.

Chatwoot: sva tri IVFFlat indeksa nad article_embeddings, captain_assistant_responses i captain_faq_suggestions moraju biti valid/ready. Provjeriti logine, inbox, Sidekiq i AI lookup bez slanja produkcijskih poruka tijekom probe. Uključiti chatwoot-backup PGHOST u prijelaz i potvrditi sljedeći backup.

Ne izvršavati produkcijski upload, stvarnu poruku, fiskalizaciju, mail ili webhook kao usputni smoke. Za takve write testove unaprijed odrediti testni zapis/tenant i pravila čišćenja u odobrenoj fazi.

## pg_cron

Acceptance ima dvije razine: svih sedam job definicija/metadata/povijesti očuvano; zatim dokaz njihovih budućih izvršavanja bez duplikata. Oznaka active nije dokaz rada.

Provjeriti cron.database_name=qubit_user, GMT raspored, job login i file write prava, source disabled i target gate otvara se jednom. U probi svaki job izvršiti samo nad kopijom, uz sandbox export putanje; prune rezultat usporediti s odobrenom retencijom. U produkciji pratiti novi satni warmup i dnevni/tjedni ciklus. Evidentirati sve nedovršene vremenske acceptance točke do sljedećeg rasporeda.

Run history prestaje u travnju: ne pokušavati automatski reproducirati propuštene cron minute. Catchup podataka/retencije zasebna je odluka vlasnika.

## Kolacije: siguran postupak

Potvrđeno osam netemplate baza sa zadanim libc mismatchom 2.31 → 2.36: crowdsec, headscale, powerdns, qubit_user, test_qubit_user, snappymail, mozzart_db, te dodatno template_postgis. Svi 33 connectable DB imaju i zastarjele ICU/libc collation katalog zapise; njihova prisutnost ne dokazuje upotrebu.

### Preferirani put: logički restore u čisti target

1. U targetu koristiti svježi template0 s odabranim bookworm/glibc localeom. Ne prenijeti staru collversion metapodatkovnu tvrdnju kao gotovu činjenicu.
2. Dump prenosi logičke retke; indeksi se izgrađuju iznova pod ciljnim providerom. Pratiti unique/PK build greške: novi poredak/jednakost mogu otkriti konflikt.
3. Provjeriti sve unique constraintove i kritične ORDER BY/range/lookup upite; provjeriti raspodjele i checksum.
4. Provjeriti default i eksplicitne kolacije te njihove stvarne verzije. Ako je target čist i indeksi upravo pravilno izgrađeni, ne raditi dodatni REINDEX samo radi formalnosti.
5. Custom kolacije i expression/partial indekse pregledati zasebno. Zadana kolacija nije potpuno pokrivena pg_depend upitom za eksplicitne pg_collation OID-ove.

### Ako baza ostaje ili se radi fizički upgrade

Prije odobrenog zahvata napraviti backup, inventar svih potencijalno zahvaćenih indeksa/objekata i rezervirati disk/lock prozor. **Prvo rebuild zahvaćenih objekata, potom REFRESH VERSION.** REFRESH sam samo ažurira metapodatak i ne popravlja indeks, prema [službenoj dokumentaciji](https://www.postgresql.org/docs/16/sql-altercollation.html).

Za indeksne rebuildove odabrati standardni ili concurrent REINDEX prema vrsti objekta i dostupnosti. Concurrent varijanta traži dodatni prostor, više prolaza i ima ograničenja za sistemske/posebne objekte; nakon prekida provjeriti nevaljane indekse. Restore proba treba pokazati potrebni prostor i trajanje. [REINDEX dokumentacija](https://www.postgresql.org/docs/16/sql-reindex.html).

REFRESH DATABASE primjenjuje se na default kolaciju tek nakon rebuilda. REFRESH COLLATION za pojedine ICU/libc objekte tek nakon provjere njihovih dependenta. Ne osvježavati stotine kataloških zapisa naslijepo niti zamijeniti ovaj postupak samo utišavanjem upozorenja. U ovoj fazi ništa od navedenoga nije izvršeno.

## Rollback: prije i poslije prvog pisanja

| Trenutak | Dopušteni plan povrata | Što se mora provjeriti |
| --- | --- | --- |
| prije promjene endpointa | odbaciti cutover, nastaviti source nakon zatvaranja sandbox writera | source i dalje authoritative |
| nakon promjene endpointa, prije T_write | zatvoriti target klijente/schedulere, vratiti raniji env manifest, ukloniti odobreni source fence, ponovno spojiti source | dokaz da nema target-only pisanja i nema duplog crona |
| nakon T_write | maintenance na targetu, backup targeta, izmjeriti razliku i provesti testirani reverse dump/restore u zaseban recovery cluster ili kontrolirani forward-fix | izvor je zastario; novi target podaci moraju se sačuvati |
| problem samo jednog aplikacijskog procesa | rollback procesa/configa samo ako je shema kompatibilna i endpoint ostaje authoritative | ne vraćati DB kao automatski dio app rollbacka |

Nakon T_write nije dopušten povrat na stari DB samo promjenom hosta jer bi izgubio nove transakcije. Nema automatske dvosmjerne sinkronizacije. Ako se traži RPO=0 i nakon-cutover povrat, mora se unaprijed probati reverse put ili implementirati zasebna replikacijska strategija. PG16→PG18 dump natrag na PG16 nije zajamčen kompatibilan; zato se major upgrade ne spaja s prvim preseljenjem.

Source se ne prepisuje target dumpom bez nove izričite upute. Sve povratne obnove rade se u nove recovery direktorije/clustere. Za podatke koji nemaju odobrenu reverse proceduru poslije-write incident znači HOLD i forward-fix/recovery, ne improvizirani rollback.

## Nadzor i zatvaranje

Tijekom prvih 30 minuta po valu pratiti DB/app greške, reconnectove, pool usage, latency, disk/WAL, source veze i scheduler jedinstvenost; zatim usporediti 24-satni ciklus i sljedeći tjedni export. To su predloženi prozori, ne odobreni SLA.

Zatvaranje vala zahtijeva dokumentirane hasheve dumpova, restore exit kodove, data/ACL diff rezultate, endpoint manifest, T_write i RPO/RTO mjerenja. Završetak cijele migracije zahtijeva nove restore-testirane backupove za sva tri servisa. Brisanje izvora ili backupova nije dio acceptancea.
