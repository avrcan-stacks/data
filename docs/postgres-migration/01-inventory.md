# 01 — Inventar PostgreSQL infrastrukture

Status: završena read-only analiza, 14. studenoga 2026. (Europe/Zagreb). Ovo nije odobrenje za implementaciju. Veličine i veze su presjek živog sustava, ne zajednički transakcijski snapshot.

## Sažetak nalaza

- Host `Ubuntu-2204-jammy-amd64-base`; stack `/opt/stacks/data`; kontejner `postgis`.
- Server: PostgreSQL **16.13**, Debian paket `16.13-1.pgdg12+1`, x86_64; glibc **2.36** (`2.36-9+deb12u13`).
- Image `postgis-local:16-bookworm-postgis3-cron-vchord1.1.1` gradi se preko `Dockerfile.postgis`, baze `postgres:16-bookworm` i VectorChord artefakata za PG16.
- **31 netemplate baza + 3 template baze = 34 baze**; približno **39,82 GiB** ukupno. `crowdsec` zauzima **37,42 GiB** i dominira trajanjem dump/restore postupka.
- Data direktorij fizički oko **41 GiB**. Filesystem `/dev/md2`, ext4, 2,0 TiB, 91% zauzet, **179 GiB slobodno**. Oba backup mounta su na istom filesystemu.
- 32 CPU; približno 126 GiB RAM, oko 75 GiB MemAvailable u trenutku provjere. Swap oko 4 GiB potpuno zauzet; trenutna aktivnost swapa nije mjerena.
- `shared_preload_libraries=vchord,pg_cron`; `max_connections=100`; `max_worker_processes=8`; `wal_level=replica`; `archive_mode=off`; nema replication slotova ni subscriptiona u pregledanom cluster katalogu.
- `data_checksums=off`; postojeći server bez memorijskog limita, `shm_size=64 MiB`.
- Baza `postgres` sadrži **aplikacijske podatke Uzorite** i pristupa joj Stay. Ne tretirati je kao praznu administracijsku bazu.
- Sedam cron zadataka označeno je aktivnima u `qubit_user`, ali launcher radi u `postgres`; povijest izvršavanja prestaje 4. travnja 2026.
- PostGIS biblioteka **3.6.2**, SQL ekstenzije dijelom **3.4.3**; `postgis_full_version()` u `farma_db` izričito prijavljuje potrebu nadogradnje core/topology procedura.

## Baze, vlasnici, veličine i ekstenzije

Prazan ACL znači PostgreSQL zadana pravila, ne odsutnost privilegija. `plpgsql 1.0` postoji u pregledanim bazama; ostale ekstenzije navedene su dolje. `template0` ne dopušta vezu i njegov sadržaj nije pregledan.

| Baza | Vlasnik | MiB | Template | Kolacija zabilježena → aktualna | Ekstenzije |
| --- | --- | --- | --- | --- | --- |
| chatwoot | chatwoot | 21.08 | ne | 2.36 → 2.36 | vector 0.8.2; pg_trgm 1.6; pgcrypto 1.3; pg_stat_statements 1.10 |
| crowdsec | crowdsec | 38321.71 | ne | 2.31 → 2.36 | plpgsql 1.0 |
| farma_db | farma_app | 39.31 | ne | 2.36 → 2.36 | fuzzystrmatch 1.2; postgis 3.4.3; postgis_tiger_geocoder 3.4.3; postgis_topology 3.4.3 |
| finestar_erp_db | postgis | 133.13 | ne | 2.36 → 2.36 | postgis 3.6.2 |
| fiskal | fiskal | 39.01 | ne | 2.36 → 2.36 | postgis 3.6.2 |
| fiskal_f1_pts_smoke | fiskal | 9.22 | ne | 2.36 → 2.36 | pgcrypto 1.3 |
| headscale | headscale | 9.08 | ne | 2.31 → 2.36 | uuid-ossp 1.1 |
| immich | immich | 1191.79 | ne | 2.36 → 2.36 | postgis 3.6.2; cube 1.5; earthdistance 1.2; pg_trgm 1.6; unaccent 1.1; uuid-ossp 1.1; vector 0.8.2; vchord 1.1.1 |
| mailblocklist | mailblocklist | 36.58 | ne | 2.36 → 2.36 | plpgsql 1.0 |
| minidepo | postgres | 18.11 | ne | 2.36 → 2.36 | postgis 3.6.2 |
| mozzart_db | postgis | 203.37 | ne | 2.31 → 2.36 | postgis 3.4.3 |
| nextcloud | nextcloud | 131.97 | ne | 2.36 → 2.36 | plpgsql 1.0 |
| omnimsgio | omnimsgio | 8.27 | ne | 2.36 → 2.36 | plpgsql 1.0 |
| parkschloss | parkschloss | 7.63 | ne | 2.36 → 2.36 | plpgsql 1.0 |
| postgres | postgres | 67.89 | ne | 2.36 → 2.36 | postgis 3.4.3; postgis_topology 3.4.3; fuzzystrmatch 1.2; postgis_tiger_geocoder 3.4.3 |
| powerdns | qubit | 7.98 | ne | 2.31 → 2.36 | plpgsql 1.0 |
| predix | predix | 134.12 | ne | 2.36 → 2.36 | postgis 3.6.2 |
| qubit_user | qubit | 22.49 | ne | 2.31 → 2.36 | pg_cron 1.6 |
| racunai_intermediary | postgis | 102.63 | ne | 2.36 → 2.36 | plpgsql 1.0 |
| roamkit | roamkit | 18.11 | ne | 2.36 → 2.36 | plpgsql 1.0 |
| roamkit_production | roamkit | 17.08 | ne | 2.36 → 2.36 | plpgsql 1.0 |
| snappymail | snappymail | 7.85 | ne | 2.31 → 2.36 | plpgsql 1.0 |
| stay_platform_db | stay | 48.66 | ne | 2.36 → 2.36 | pageinspect 1.12 |
| stay_platform_test_db | stay | 22.97 | ne | 2.36 → 2.36 | postgis 3.6.2 |
| superclean_db | superclean | 17.41 | ne | 2.36 → 2.36 | postgis 3.6.2 |
| tablio_platform_db | tablio | 10.12 | ne | 2.36 → 2.36 | plpgsql 1.0 |
| template0 | postgres | 7.31 | da | nije zabilježena → 2.36 | nije pregledano |
| template1 | postgres | 7.37 | da | 2.36 → 2.36 | plpgsql 1.0 |
| template_postgis | postgres | 18.89 | da | 2.31 → 2.36 | postgis 3.4.3; postgis_topology 3.4.3; fuzzystrmatch 1.2; postgis_tiger_geocoder 3.4.3 |
| test_finestar_erp_db | postgis | 33.16 | ne | 2.36 → 2.36 | postgis 3.6.2 |
| test_predix | predix | 13.65 | ne | 2.36 → 2.36 | plpgsql 1.0 |
| test_qubit_user | qubit | 12.49 | ne | 2.31 → 2.36 | plpgsql 1.0 |
| test_stay_platform_db | stay | 13.92 | ne | 2.36 → 2.36 | plpgsql 1.0 |
| test_stay_platform_test_db | stay | 24.42 | ne | 2.36 → 2.36 | postgis 3.6.2 |

PostGIS ima 12 netemplate baza; dodatno je instaliran u `template_postgis`. Osam netemplate baza ima mismatch zadane kolacije, dodatno i `template_postgis`. U svih 33 pregledanih connectable baza postoje dva libc i 784 ICU kataloška zapisa s neusklađenom verzijom. Izravne `pg_depend` ovisnosti o tim eksplicitnim kolacijama nisu pronađene; to ne obuhvaća indekse koji koriste zadanu kolaciju baze.

## Role, privilegije i autentikacija

21 korisnički definirana rola. Superuser role: `postgres`, `qubit`, `farma_app`. Aplikacijske superuser privilegije zadržati kao zasebnu odluku; ne mijenjati ih prešutno tijekom prijenosa. `postgis` ima CREATEDB, ali nije superuser; `minidepo` je u vlasništvu `postgres`. Ne kopirati sve role sa svim privilegijama u sva tri nova clustera bez mapiranja.

```text
rolname     | rolsuper | rolinherit | rolcreaterole | rolcreatedb | rolcanlogin | rolreplication | rolbypassrls | rolconnlimit | rolvaliduntil 
-----------------+----------+------------+---------------+-------------+-------------+----------------+--------------+--------------+---------------
 chatwoot        | f        | f          | f             | f           | t           | f              | f            |           -1 | 
 crowdsec        | f        | t          | f             | f           | t           | f              | f            |           -1 | 
 farma_app       | t        | t          | f             | t           | t           | f              | f            |           -1 | 
 fiskal          | f        | t          | f             | f           | t           | f              | f            |           -1 | 
 headscale       | f        | t          | f             | f           | t           | f              | f            |           -1 | 
 immich          | f        | t          | f             | f           | t           | f              | f            |           -1 | 
 mailblocklist   | f        | t          | f             | t           | t           | f              | f            |           -1 | 
 nextcloud       | f        | t          | f             | f           | t           | f              | f            |           -1 | 
 omnimsgio       | f        | t          | f             | f           | t           | f              | f            |           -1 | 
 parkschloss     | f        | t          | f             | f           | t           | f              | f            |           -1 | 
 postgis         | f        | t          | f             | t           | t           | f              | f            |           -1 | 
 postgres        | t        | t          | t             | t           | t           | t              | t            |           -1 | 
 powerdns        | f        | t          | f             | f           | t           | f              | f            |           -1 | 
 predix          | f        | t          | f             | f           | t           | f              | f            |           -1 | 
 qubit           | t        | t          | t             | t           | t           | t              | t            |           -1 | 
 roamkit         | f        | t          | f             | t           | t           | f              | f            |           -1 | 
 snappymail      | f        | t          | f             | f           | t           | f              | f            |           -1 | 
 stay            | f        | t          | f             | t           | t           | f              | f            |           -1 | 
 stay_uzorita_ro | f        | t          | f             | f           | t           | f              | f            |           -1 | 
 superclean      | f        | t          | f             | f           | t           | f              | f            |           -1 | 
 tablio          | f        | t          | f             | f           | t           | f              | f            |           -1 | 
(21 rows)

         role         |   member   | admin_option 
----------------------+------------+--------------
 pg_read_all_settings | pg_monitor | f
 pg_read_all_stats    | pg_monitor | f
 pg_stat_scan_tables  | pg_monitor | f
(3 rows)

  spcname   | pg_get_userbyid | pg_tablespace_location | spcacl 
------------+-----------------+------------------------+--------
 pg_default | postgres        |                        | 
 pg_global  | postgres        |                        | 
(2 rows)
```

Postoje samo `pg_default` i `pg_global`; nema korisničkih tablespaceova. Nisu pronađena korisnička role-membership članstva. DB/role postavke: `search_path` na razini `farma_db`, `postgres`, `template_postgis`; vrijednosti treba privatno prenijeti i provjeriti na restore probi.

HBA: lokalni Unix socket i localhost koriste trust; vanjske veze SCRAM. Chatwoot ima dopuštenje samo na svoju bazu, potom eksplicitni reject za druge baze. Na odredištu očuvati taj redoslijed i provjeriti login stvarnim aplikacijskim korisnikom. Dokument ne sadrži password hashove ni vjerodajnice. Za obnovu autentikacije potreban je zaseban šifriran globals backup ili kontrolirano postavljanje postojećih vjerodajnica iz tajnog spremišta.

### ACL inventar po bazama

Ispod su DB ACL, schema ACL, grupirani ACL odnosa i funkcija, default/column ACL, vlasništvo, RLS i triggeri. Grupiranje istog ACL-a čuva grantee/grantor i broj objekata; pojedinačno mapiranje objekata mora se usporediti iz privatnog schema dumpa prije cutovera. Inventar ne tvrdi da je NULL ACL ekvivalent zabrani pristupa.

<details>
<summary>chatwoot</summary>

```json
{
  "database_acl": [
    "chatwoot=CTc/chatwoot"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "chatwoot",
      "objects": 199
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": [
    {
      "owner": "postgres",
      "acl": "{postgres=X/postgres}",
      "objects": 1
    }
  ],
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": [
    {
      "table": "public.accounts",
      "trigger": "camp_dpid_before_insert",
      "function": "camp_dpid_before_insert()",
      "enabled": "O"
    },
    {
      "table": "public.accounts",
      "trigger": "accounts_after_insert_row_tr",
      "function": "accounts_after_insert_row_tr()",
      "enabled": "O"
    },
    {
      "table": "public.campaigns",
      "trigger": "campaigns_before_insert_row_tr",
      "function": "campaigns_before_insert_row_tr()",
      "enabled": "O"
    },
    {
      "table": "public.conversations",
      "trigger": "conversations_before_insert_row_tr",
      "function": "conversations_before_insert_row_tr()",
      "enabled": "O"
    }
  ],
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>crowdsec</summary>

```json
{
  "database_acl": [
    "=T/crowdsec",
    "crowdsec=CTc/crowdsec"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "crowdsec",
      "acl": [
        "crowdsec=UC/crowdsec",
        "=U/crowdsec"
      ]
    }
  ],
  "owners": [
    {
      "owner": "crowdsec",
      "objects": 55
    }
  ],
  "relation_acl_groups": [
    {
      "acl": "{crowdsec=rwU/crowdsec}",
      "objects": 13
    },
    {
      "acl": "{crowdsec=arwdDxt/crowdsec}",
      "objects": 14
    }
  ],
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>farma_db</summary>

```json
{
  "database_acl": [
    "=Tc/farma_app",
    "farma_app=CTc/farma_app"
  ],
  "schemas": [
    {
      "name": "tiger",
      "owner": "postgres",
      "acl": null
    },
    {
      "name": "tiger_data",
      "owner": "postgres",
      "acl": null
    },
    {
      "name": "topology",
      "owner": "postgres",
      "acl": [
        "postgres=UC/postgres",
        "=U/postgres"
      ]
    },
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner",
        "farma_app=UC/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "postgres",
      "objects": 281
    },
    {
      "owner": "farma_app",
      "objects": 56
    }
  ],
  "relation_acl_groups": [
    {
      "acl": "{farma_app=rwU/farma_app}",
      "objects": 5
    },
    {
      "acl": "{postgres=arwdDxt/postgres,farma_app=arwdDxt/postgres}",
      "objects": 113
    },
    {
      "acl": "{postgres=rwU/postgres,farma_app=rwU/postgres}",
      "objects": 168
    },
    {
      "acl": "{farma_app=arwdDxt/farma_app}",
      "objects": 4
    }
  ],
  "function_acl_groups": [
    {
      "owner": "postgres",
      "acl": "{=X/postgres,postgres=X/postgres,farma_app=X/postgres}",
      "objects": 802
    }
  ],
  "default_acl": [
    {
      "role": "postgres",
      "schema": "public",
      "type": "r",
      "acl": [
        "farma_app=arwdDxt/postgres"
      ]
    },
    {
      "role": "postgres",
      "schema": "public",
      "type": "S",
      "acl": [
        "farma_app=rwU/postgres"
      ]
    },
    {
      "role": "postgres",
      "schema": "public",
      "type": "f",
      "acl": [
        "farma_app=X/postgres"
      ]
    }
  ],
  "column_acl": null,
  "rls": null,
  "triggers": [
    {
      "table": "topology.layer",
      "trigger": "layer_integrity_checks",
      "function": "layertrigger()",
      "enabled": "O"
    },
    {
      "table": "public.odrzavanje_dionice_rute",
      "trigger": "trigger_calculate_route_length",
      "function": "calculate_route_length()",
      "enabled": "O"
    }
  ],
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>finestar_erp_db</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "postgis",
      "acl": [
        "postgis=UC/postgis",
        "=U/postgis"
      ]
    }
  ],
  "owners": [
    {
      "owner": "postgis",
      "objects": 250
    }
  ],
  "relation_acl_groups": [
    {
      "acl": "{postgis=rwU/postgis}",
      "objects": 124
    },
    {
      "acl": "{postgis=arwdDxt/postgis}",
      "objects": 126
    }
  ],
  "function_acl_groups": [
    {
      "owner": "postgres",
      "acl": "{=X/postgres,postgres=X/postgres,postgis=X/postgres}",
      "objects": 776
    }
  ],
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>fiskal</summary>

```json
{
  "database_acl": [
    "=Tc/fiskal",
    "fiskal=CTc/fiskal"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner",
        "fiskal=UC/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "fiskal",
      "objects": 32
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": [
    {
      "role": "postgres",
      "schema": "public",
      "type": "r",
      "acl": [
        "fiskal=arwdDxt/postgres"
      ]
    },
    {
      "role": "postgres",
      "schema": "public",
      "type": "S",
      "acl": [
        "fiskal=rwU/postgres"
      ]
    }
  ],
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>fiskal_f1_pts_smoke</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "fiskal",
      "objects": 32
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>headscale</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "headscale",
      "objects": 11
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>immich</summary>

```json
{
  "database_acl": [
    "=Tc/immich",
    "immich=CTc/immich"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner",
        "immich=UC/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "postgres",
      "objects": 52
    },
    {
      "owner": "immich",
      "objects": 21
    }
  ],
  "relation_acl_groups": [
    {
      "acl": "{postgres=arwdDxt/postgres,immich=arwdDxt/postgres}",
      "objects": 52
    }
  ],
  "function_acl_groups": [
    {
      "owner": "postgres",
      "acl": "{=X/postgres,postgres=X/postgres,immich=X/postgres}",
      "objects": 1088
    }
  ],
  "default_acl": [
    {
      "role": "postgres",
      "schema": "public",
      "type": "r",
      "acl": [
        "immich=arwdDxt/postgres"
      ]
    },
    {
      "role": "postgres",
      "schema": "public",
      "type": "S",
      "acl": [
        "immich=rwU/postgres"
      ]
    },
    {
      "role": "postgres",
      "schema": "public",
      "type": "f",
      "acl": [
        "immich=X/postgres"
      ]
    }
  ],
  "column_acl": null,
  "rls": null,
  "triggers": [
    {
      "table": "public.workflow",
      "trigger": "workflow_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.asset_ocr",
      "trigger": "asset_ocr_delete_audit",
      "function": "asset_ocr_delete_audit()",
      "enabled": "O"
    },
    {
      "table": "public.album_user",
      "trigger": "album_user_delete",
      "function": "album_user_delete()",
      "enabled": "O"
    },
    {
      "table": "public.asset_ocr",
      "trigger": "asset_ocr_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.person",
      "trigger": "person_delete_audit",
      "function": "person_delete_audit()",
      "enabled": "O"
    },
    {
      "table": "public.cluster_group",
      "trigger": "cluster_group_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.person_group",
      "trigger": "person_group_delete_audit",
      "function": "person_group_delete_audit()",
      "enabled": "O"
    },
    {
      "table": "public.person_group",
      "trigger": "person_group_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.person",
      "trigger": "person_delete_shares",
      "function": "person_delete_shares()",
      "enabled": "O"
    },
    {
      "table": "public.person_user",
      "trigger": "person_user_after_insert",
      "function": "person_user_after_insert()",
      "enabled": "O"
    },
    {
      "table": "public.person_user",
      "trigger": "person_user_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.asset_face",
      "trigger": "asset_face_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.asset",
      "trigger": "asset_face_update_asset_state",
      "function": "asset_face_update_asset_state()",
      "enabled": "O"
    },
    {
      "table": "public.asset_face",
      "trigger": "asset_face_set_asset_state",
      "function": "asset_face_set_asset_state()",
      "enabled": "O"
    },
    {
      "table": "public.activity",
      "trigger": "activity_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.album_asset",
      "trigger": "album_asset_delete_audit",
      "function": "album_asset_delete_audit()",
      "enabled": "O"
    },
    {
      "table": "public.album_asset",
      "trigger": "album_asset_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.album",
      "trigger": "album_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.album_user",
      "trigger": "album_user_after_insert",
      "function": "album_user_after_insert()",
      "enabled": "O"
    },
    {
      "table": "public.album_user",
      "trigger": "album_user_delete_audit",
      "function": "album_user_delete_audit()",
      "enabled": "O"
    },
    {
      "table": "public.album_user",
      "trigger": "album_user_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.api_key",
      "trigger": "api_key_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.asset",
      "trigger": "asset_delete_audit",
      "function": "asset_delete_audit()",
      "enabled": "O"
    },
    {
      "table": "public.asset_edit",
      "trigger": "asset_edit_audit",
      "function": "asset_edit_audit()",
      "enabled": "O"
    },
    {
      "table": "public.asset_edit",
      "trigger": "asset_edit_delete",
      "function": "asset_edit_delete()",
      "enabled": "O"
    },
    {
      "table": "public.asset_edit",
      "trigger": "asset_edit_insert",
      "function": "asset_edit_insert()",
      "enabled": "O"
    },
    {
      "table": "public.asset_edit",
      "trigger": "asset_edit_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.asset_exif",
      "trigger": "asset_exif_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.asset_face",
      "trigger": "asset_face_audit",
      "function": "asset_face_audit()",
      "enabled": "O"
    },
    {
      "table": "public.asset_file",
      "trigger": "asset_file_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.asset_metadata",
      "trigger": "asset_metadata_audit",
      "function": "asset_metadata_audit()",
      "enabled": "O"
    },
    {
      "table": "public.asset_metadata",
      "trigger": "asset_metadata_updated_at",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.asset",
      "trigger": "asset_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.library",
      "trigger": "library_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.memory_asset",
      "trigger": "memory_asset_delete_audit",
      "function": "memory_asset_delete_audit()",
      "enabled": "O"
    },
    {
      "table": "public.memory_asset",
      "trigger": "memory_asset_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.memory",
      "trigger": "memory_delete_audit",
      "function": "memory_delete_audit()",
      "enabled": "O"
    },
    {
      "table": "public.memory",
      "trigger": "memory_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.notification",
      "trigger": "notification_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.partner",
      "trigger": "partner_delete_audit",
      "function": "partner_delete_audit()",
      "enabled": "O"
    },
    {
      "table": "public.partner",
      "trigger": "partner_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.person",
      "trigger": "person_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.session_sync_checkpoint",
      "trigger": "session_sync_checkpoint_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.session",
      "trigger": "session_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.stack",
      "trigger": "stack_delete_audit",
      "function": "stack_delete_audit()",
      "enabled": "O"
    },
    {
      "table": "public.stack",
      "trigger": "stack_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.tag",
      "trigger": "tag_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.user",
      "trigger": "user_delete_audit",
      "function": "user_delete_audit()",
      "enabled": "O"
    },
    {
      "table": "public.user_metadata",
      "trigger": "user_metadata_audit",
      "function": "user_metadata_audit()",
      "enabled": "O"
    },
    {
      "table": "public.user_metadata",
      "trigger": "user_metadata_updated_at",
      "function": "updated_at()",
      "enabled": "O"
    },
    {
      "table": "public.user",
      "trigger": "user_updatedAt",
      "function": "updated_at()",
      "enabled": "O"
    }
  ],
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>mailblocklist</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "mailblocklist",
      "objects": 52
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": [
    {
      "table": "public.sender_blocklist_rules",
      "trigger": "trg_sender_blocklist_rules_updated_at",
      "function": "set_sender_blocklist_rules_updated_at()",
      "enabled": "O"
    }
  ],
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>minidepo</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "postgres",
      "objects": 31
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>mozzart_db</summary>

```json
{
  "database_acl": [
    "=Tc/postgis",
    "postgis=CTc/postgis"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "postgis",
      "acl": [
        "postgis=UC/postgis",
        "=U/postgis"
      ]
    }
  ],
  "owners": [
    {
      "owner": "postgis",
      "objects": 247
    }
  ],
  "relation_acl_groups": [
    {
      "acl": "{postgis=rwU/postgis}",
      "objects": 114
    },
    {
      "acl": "{postgis=arwdDxt/postgis}",
      "objects": 117
    }
  ],
  "function_acl_groups": [
    {
      "owner": "postgres",
      "acl": "{=X/postgres,postgres=X/postgres,postgis=X/postgres}",
      "objects": 777
    }
  ],
  "default_acl": [
    {
      "role": "postgis",
      "schema": "public",
      "type": "r",
      "acl": [
        "postgis=arwdDxt/postgis"
      ]
    },
    {
      "role": "postgis",
      "schema": "public",
      "type": "S",
      "acl": [
        "postgis=rwU/postgis"
      ]
    },
    {
      "role": "postgis",
      "schema": "public",
      "type": "f",
      "acl": [
        "postgis=X/postgis"
      ]
    }
  ],
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>nextcloud</summary>

```json
{
  "database_acl": [
    "nextcloud=CTc/nextcloud"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "nextcloud",
      "objects": 437
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>omnimsgio</summary>

```json
{
  "database_acl": [
    "=Tc/omnimsgio",
    "omnimsgio=CTc/omnimsgio"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "omnimsgio",
      "acl": [
        "omnimsgio=UC/omnimsgio",
        "=U/omnimsgio"
      ]
    }
  ],
  "owners": [
    {
      "owner": "omnimsgio",
      "objects": 9
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>parkschloss</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "parkschloss",
      "objects": 5
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>postgres</summary>

```json
{
  "database_acl": [
    "=Tc/postgres",
    "postgres=CTc/postgres",
    "stay_uzorita_ro=c/postgres"
  ],
  "schemas": [
    {
      "name": "topology",
      "owner": "postgres",
      "acl": [
        "postgres=UC/postgres",
        "=U/postgres"
      ]
    },
    {
      "name": "tiger",
      "owner": "postgres",
      "acl": null
    },
    {
      "name": "tiger_data",
      "owner": "postgres",
      "acl": null
    },
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner",
        "stay_uzorita_ro=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "postgres",
      "objects": 63
    }
  ],
  "relation_acl_groups": [
    {
      "acl": "{postgres=arwdDxt/postgres,stay_uzorita_ro=r/postgres}",
      "objects": 32
    }
  ],
  "function_acl_groups": null,
  "default_acl": [
    {
      "role": "postgres",
      "schema": "public",
      "type": "r",
      "acl": [
        "stay_uzorita_ro=r/postgres"
      ]
    }
  ],
  "column_acl": null,
  "rls": null,
  "triggers": [
    {
      "table": "topology.layer",
      "trigger": "layer_integrity_checks",
      "function": "layertrigger()",
      "enabled": "O"
    }
  ],
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>powerdns</summary>

```json
{
  "database_acl": [
    "=Tc/qubit",
    "qubit=CTc/qubit",
    "powerdns=CTc/qubit"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "qubit",
      "objects": 13
    }
  ],
  "relation_acl_groups": [
    {
      "acl": "{qubit=rwU/qubit,powerdns=rwU/qubit}",
      "objects": 6
    },
    {
      "acl": "{qubit=arwdDxt/qubit,powerdns=arwdDxt/qubit}",
      "objects": 7
    }
  ],
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>predix</summary>

```json
{
  "database_acl": [
    "=Tc/predix",
    "predix=CTc/predix"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner",
        "predix=UC/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "predix",
      "objects": 191
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>qubit_user</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    },
    {
      "name": "cron",
      "owner": "postgres",
      "acl": null
    }
  ],
  "owners": [
    {
      "owner": "qubit",
      "objects": 175
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": [
    {
      "owner": "postgres",
      "acl": "{postgres=X/postgres}",
      "objects": 2
    }
  ],
  "default_acl": null,
  "column_acl": null,
  "rls": [
    {
      "table": "cron.job",
      "policy": "cron_job_policy",
      "roles": [
        "public"
      ],
      "command": "ALL"
    },
    {
      "table": "cron.job_run_details",
      "policy": "cron_job_run_details_policy",
      "roles": [
        "public"
      ],
      "command": "ALL"
    }
  ],
  "triggers": [
    {
      "table": "cron.job",
      "trigger": "cron_job_cache_invalidate",
      "function": "cron.job_cache_invalidate()",
      "enabled": "O"
    },
    {
      "table": "public.headscale_log",
      "trigger": "trg_route_headscale_log",
      "function": "route_headscale_log()",
      "enabled": "O"
    },
    {
      "table": "public.user_log",
      "trigger": "trg_route_user_log",
      "function": "route_user_log()",
      "enabled": "O"
    }
  ],
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>racunai_intermediary</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "postgis",
      "acl": [
        "postgis=UC/postgis",
        "=U/postgis"
      ]
    },
    {
      "name": "gateway",
      "owner": "postgis",
      "acl": [
        "postgis=UC/postgis"
      ]
    }
  ],
  "owners": [
    {
      "owner": "postgis",
      "objects": 11
    }
  ],
  "relation_acl_groups": [
    {
      "acl": "{postgis=rwU/postgis}",
      "objects": 1
    },
    {
      "acl": "{postgis=arwdDxt/postgis}",
      "objects": 10
    }
  ],
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>roamkit</summary>

```json
{
  "database_acl": [
    "=Tc/roamkit",
    "roamkit=CTc/roamkit"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "roamkit",
      "acl": [
        "roamkit=UC/roamkit",
        "=U/roamkit"
      ]
    }
  ],
  "owners": [
    {
      "owner": "roamkit",
      "objects": 65
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>roamkit_production</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "roamkit",
      "objects": 65
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>snappymail</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "snappymail",
      "objects": 7
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>stay_platform_db</summary>

```json
{
  "database_acl": [
    "=Tc/stay",
    "stay=CTc/stay"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner",
        "stay=UC/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "stay",
      "objects": 175
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": [
    {
      "role": "postgres",
      "schema": "public",
      "type": "r",
      "acl": [
        "stay=arwdDxt/postgres"
      ]
    },
    {
      "role": "postgres",
      "schema": "public",
      "type": "S",
      "acl": [
        "stay=rwU/postgres"
      ]
    }
  ],
  "column_acl": null,
  "rls": null,
  "triggers": [
    {
      "table": "public.communications_conversation",
      "trigger": "communications_conversation_tenant_matches_reservation_trg",
      "function": "communications_conversation_tenant_matches_reservation()",
      "enabled": "O"
    },
    {
      "table": "public.communications_guestmessage",
      "trigger": "communications_guestmessage_tenant_matches_conversation_trg",
      "function": "communications_guestmessage_tenant_matches_conversation()",
      "enabled": "O"
    },
    {
      "table": "public.communications_guestmessagesource",
      "trigger": "communications_guestmessagesource_tenant_matches_message_trg",
      "function": "communications_guestmessagesource_tenant_matches_message()",
      "enabled": "O"
    }
  ],
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>stay_platform_test_db</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "stay",
      "objects": 163
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": [
    {
      "table": "public.communications_conversation",
      "trigger": "communications_conversation_tenant_matches_reservation_trg",
      "function": "communications_conversation_tenant_matches_reservation()",
      "enabled": "O"
    },
    {
      "table": "public.communications_guestmessage",
      "trigger": "communications_guestmessage_tenant_matches_conversation_trg",
      "function": "communications_guestmessage_tenant_matches_conversation()",
      "enabled": "O"
    },
    {
      "table": "public.communications_guestmessagesource",
      "trigger": "communications_guestmessagesource_tenant_matches_message_trg",
      "function": "communications_guestmessagesource_tenant_matches_message()",
      "enabled": "O"
    }
  ],
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>superclean_db</summary>

```json
{
  "database_acl": [
    "=Tc/superclean",
    "superclean=CTc/superclean"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner",
        "superclean=UC/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "superclean",
      "objects": 57
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>tablio_platform_db</summary>

```json
{
  "database_acl": [
    "=Tc/tablio",
    "tablio=CTc/tablio"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "tablio",
      "objects": 51
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>template1</summary>

```json
{
  "database_acl": [
    "=c/postgres",
    "postgres=CTc/postgres"
  ],
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": null,
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>template_postgis</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    },
    {
      "name": "topology",
      "owner": "postgres",
      "acl": [
        "postgres=UC/postgres",
        "=U/postgres"
      ]
    },
    {
      "name": "tiger",
      "owner": "postgres",
      "acl": null
    },
    {
      "name": "tiger_data",
      "owner": "postgres",
      "acl": null
    }
  ],
  "owners": null,
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": [
    {
      "table": "topology.layer",
      "trigger": "layer_integrity_checks",
      "function": "layertrigger()",
      "enabled": "O"
    }
  ],
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>test_finestar_erp_db</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "postgis",
      "objects": 166
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>test_predix</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "predix",
      "objects": 177
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>test_qubit_user</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "qubit",
      "objects": 106
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>test_stay_platform_db</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "stay",
      "objects": 129
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": null,
  "foreign_servers": null,
  "publications": null
}
```

</details>

<details>
<summary>test_stay_platform_test_db</summary>

```json
{
  "database_acl": null,
  "schemas": [
    {
      "name": "public",
      "owner": "pg_database_owner",
      "acl": [
        "pg_database_owner=UC/pg_database_owner",
        "=U/pg_database_owner"
      ]
    }
  ],
  "owners": [
    {
      "owner": "stay",
      "objects": 171
    }
  ],
  "relation_acl_groups": null,
  "function_acl_groups": null,
  "default_acl": null,
  "column_acl": null,
  "rls": null,
  "triggers": [
    {
      "table": "public.communications_conversation",
      "trigger": "communications_conversation_tenant_matches_reservation_trg",
      "function": "communications_conversation_tenant_matches_reservation()",
      "enabled": "O"
    },
    {
      "table": "public.communications_guestmessage",
      "trigger": "communications_guestmessage_tenant_matches_conversation_trg",
      "function": "communications_guestmessage_tenant_matches_conversation()",
      "enabled": "O"
    },
    {
      "table": "public.communications_guestmessagesource",
      "trigger": "communications_guestmessagesource_tenant_matches_message_trg",
      "function": "communications_guestmessagesource_tenant_matches_message()",
      "enabled": "O"
    }
  ],
  "foreign_servers": null,
  "publications": null
}
```

</details>

## Aktivne aplikacijske veze

Ovo je trenutni presjek; odsutnost veze nije dokaz nekorištenja baze. Nije ispisivan SQL tekst aktivnih upita.

```text
datname        |    usename    |       application_name       |  client_addr  | state  | count 
----------------------+---------------+------------------------------+---------------+--------+-------
 chatwoot             | chatwoot      | /gems/ruby/3.4.0/bin/sidekiq | 172.28.0.43   | idle   |     6
 crowdsec             | crowdsec      |                              | 172.28.0.3    | idle   |     1
 crowdsec             | crowdsec      |                              | 172.28.0.6    | idle   |     1
 farma_db             | farma_app     |                              | 172.28.0.12   | idle   |     3
 finestar_erp_db      | postgis       |                              | 192.168.16.25 | idle   |     1
 fiskal               | fiskal        |                              | 192.168.16.27 | idle   |     1
 fiskal               | fiskal        |                              | 192.168.16.30 | idle   |     4
 fiskal_f1_pts_smoke  | fiskal        |                              | 172.28.0.38   | idle   |     1
 immich               | immich        | postgres.js                  | 172.28.0.11   | idle   |    11
 mailblocklist        | mailblocklist |                              | 172.28.0.16   | idle   |     1
 mailblocklist        | mailblocklist |                              | 172.28.0.39   | idle   |     1
 omnimsgio            | omnimsgio     |                              | 192.168.16.33 | idle   |     1
 omnimsgio            | omnimsgio     |                              | 192.168.16.34 | idle   |     1
 omnimsgio            | omnimsgio     |                              | 192.168.16.35 | idle   |     1
 parkschloss          | parkschloss   |                              | 172.28.0.40   | idle   |     5
 postgres             | postgres      |                              | 192.168.16.6  | idle   |     1
 postgres             | postgres      | psql                         |               | active |     1
 racunai_intermediary | postgis       |                              | 192.168.16.31 | idle   |     1
 stay_platform_db     | stay          |                              | 192.168.16.11 | idle   |    12
 tablio_platform_db   | tablio        |                              | 192.168.16.40 | idle   |     3
(20 rows)
```

## Docker Compose i endpointi

Produkcijski data Compose: `docker-compose.yml`; lokalni override: `docker-compose.local.yml`. Lokalni override uklanja Tailscale i vanjske mreže, no postojeći data path ostaje isti; ne pokretati ga na ovom hostu za testiranje.

Postojeći `postgis`: `127.0.0.1:5432 → 5432`; mreže `data_default`, `postgis`, `backend`, `hetzner_net`; IP-ovi trenutačno 172.18.0.2, 172.28.0.22, 172.20.0.11, 192.168.16.15. IP nije stabilni API.

Mountovi:
- `/opt/stacks/data/postgres/data → /var/lib/postgresql/data`
- `/opt/stacks/data/backups → /backups`
- `/srv/qubit/backups → /srv/qubit/backups`

`tailscale-postgis` koristi host networking, vlastiti state direktorij i prosljeđuje TCP 5432 na localhost 5432. Ovaj endpoint ostaje postojeći PostGIS endpoint; migrirane klijente preusmjeriti eksplicitno. Inventar ne obuhvaća udaljene konfiguracije klijenata koje nisu dostupne na hostu.

Runtime i Compose izvori aplikacija s DB varijablama:

| Kontejner | Compose izvor | Mreže |
| --- | --- | --- |
| /nextcloud-cron | /opt/stacks/nextcloud/docker-compose.yml | nextcloud_default, postgis |
| /nextcloud | /opt/stacks/nextcloud/docker-compose.yml | nextcloud_default, postgis, proxy |
| /mailserver-mail-mcp | /opt/stacks/mailserver/compose.yaml | mailserver_default, postgis, proxy |
| /mailserver | /opt/stacks/mailserver/compose.yaml | hetzner_net, mailserver_default, proxy |
| /immich_media_operations | /opt/stacks/immich/docker-compose.yml | immich_default, proxy |
| /nextcloud_immich_bridge | /opt/stacks/immich/docker-compose.yml | immich_default |
| /immich_server | /opt/stacks/immich/docker-compose.yml | immich_default, postgis, proxy |
| /immich_machine_learning | /opt/stacks/immich/docker-compose.yml | immich_default |
| /finestar_erp | /opt/stacks/racunai.hr/docker-compose.yml | hetzner_net, postgis, proxy |
| /finestar_erp_celery_worker | /opt/stacks/racunai.hr/docker-compose.yml | hetzner_net, postgis |
| /finestar_erp_celery_beat | /opt/stacks/racunai.hr/docker-compose.yml | hetzner_net, postgis |
| /racunai_mps | /opt/stacks/racunai.hr/docker-compose.yml | hetzner_net, proxy |
| /stay_django | /opt/stacks/stay.hr/docker-compose.yml | hetzner_net, postgis, proxy, stay_internal |
| /stay_celery_worker | /opt/stacks/stay.hr/docker-compose.yml | hetzner_net, postgis, stay_internal |
| /stay_celery_beat | /opt/stacks/stay.hr/docker-compose.yml | hetzner_net, postgis, stay_internal |
| /roamkit-web-production | /opt/stacks/roamkit-production/docker-compose.yml | proxy |
| /roamkit-celery-beat-production | /opt/stacks/roamkit-production/docker-compose.yml | hetzner_net, postgis |
| /roamkit-celery-production | /opt/stacks/roamkit-production/docker-compose.yml | hetzner_net, postgis |
| /roamkit-api-production | /opt/stacks/roamkit-production/docker-compose.yml | hetzner_net, postgis, proxy |
| /roamkit-web-staging | /opt/stacks/roamkit-net/docker-compose.yml | proxy |
| /roamkit-celery-beat-staging | /opt/stacks/roamkit-net/docker-compose.yml | hetzner_net, postgis |
| /roamkit-api-staging | /opt/stacks/roamkit-net/docker-compose.yml | hetzner_net, postgis, proxy |
| /roamkit-celery-staging | /opt/stacks/roamkit-net/docker-compose.yml | hetzner_net, postgis |
| /omnimsgio-worker | /opt/stacks/omnimsgio/docker/production/docker-compose.yml | hetzner_net, postgis, proxy |
| /omnimsgio-gateway | /opt/stacks/omnimsgio/docker/production/docker-compose.yml | hetzner_net, postgis, proxy |
| /omnimsgio-api | /opt/stacks/omnimsgio/docker/production/docker-compose.yml | hetzner_net, postgis, proxy |
| /chatwoot-rails | /opt/stacks/Das-Parkschloss/chatwoot/docker-compose.yml | chatwoot-internal, postgis, proxy |
| /chatwoot-backup | /opt/stacks/Das-Parkschloss/chatwoot/docker-compose.yml | postgis |
| /chatwoot-sidekiq | /opt/stacks/Das-Parkschloss/chatwoot/docker-compose.yml | chatwoot-internal, postgis |
| /parkschloss-api | /opt/stacks/Das-Parkschloss/docker-compose.yml | parkschloss-internal, postgis, proxy |
| /stay_web_booking | /opt/stacks/stay.hr/docker-compose.yml | proxy, stay_internal |
| /f1-pts-api | nije označeno | postgis |
| /omnimsgio-web | /opt/stacks/omnimsgio/docker/production/docker-compose.yml | proxy |
| /tablio_django | /opt/stacks/tablio.hr/api/docker-compose.yml | api_tablio_internal, hetzner_net, postgis, proxy |
| /tablio_celer…581 tokens truncated…ode/backend/docker-compose.yml | nije označeno |  |
| /predix-celery-beat | /opt/stacks/qubit/predix.club/docker-compose.yml | predixclub_predix_internal |
| /predix-celery-worker | /opt/stacks/qubit/predix.club/docker-compose.yml | postgis, predixclub_predix_internal |
| /mozzart-celery-beat | /opt/stacks/mozart/docker-compose.yml | hetzner_net |
| /mozzart-celery-worker | /opt/stacks/mozart/docker-compose.yml | hetzner_net |
| /mozzart | /opt/stacks/mozart/docker-compose.yml | hetzner_net, proxy |
| /mozzart-print-bridge | /opt/stacks/mozart/docker-compose.yml | hetzner_net |
| /fiskal_api | /opt/stacks/fiskal.hr/docker-compose.yml | fiskalhr_fiskal_int, hetzner_net, postgis, proxy |
| /fiskal_worker | /opt/stacks/fiskal.hr/docker-compose.yml | fiskalhr_fiskal_int, hetzner_net, postgis |
| /fiskal_domibus_mysql | /opt/stacks/fiskal.hr/docker-compose.yml | fiskalhr_fiskal_domibus_int |
| /fiskal_mps | /opt/stacks/fiskal.hr/docker-compose.yml | fiskalhr_fiskal_int, hetzner_net |
| /predix-api | /opt/stacks/qubit/predix.club/docker-compose.yml | postgis, predixclub_predix_internal, proxy |
| /farma_frontend | /opt/stacks/dalekopro/docker-compose.yml,/opt/stacks/dalekopro/docker-compose.putni-list-dev.yml | proxy |
| /farma_backend | /opt/stacks/dalekopro/docker-compose.yml | postgis, proxy |
| /mailserver-mailadmin | /opt/stacks/mailserver/compose.yaml | mailserver_default, postgis, proxy |
| /predix-sync | /opt/stacks/qubit/predix.club/docker-compose.yml | postgis, predixclub_predix_internal |
| /racunai_domibus_mysql | /opt/stacks/racunai.hr/as4-gateway/docker-compose.yml | as4-gateway_domibus_int |
| /crowdsec-cloudflare-bouncer | /opt/stacks/crowdsec/docker-compose.yml | proxy |
| /superclean_django | /opt/stacks/sauber.hr/docker-compose.yml,/opt/stacks/sauber.hr/docker-compose.prod.yml | hetzner_net, postgis, proxy, superclean_internal |
| /superclean_web | /opt/stacks/sauber.hr/docker-compose.yml,/opt/stacks/sauber.hr/docker-compose.prod.yml | proxy, superclean_internal |
| /superclean_web_admin | /opt/stacks/sauber.hr/docker-compose.yml,/opt/stacks/sauber.hr/docker-compose.prod.yml | proxy, superclean_internal |
| /snappymail | /opt/stacks/snappymail/compose.yaml | hetzner_net, postgis, proxy |
| /tailscale-booking-browser | /opt/stacks/uzorita/rooms/code/backend/docker-compose.yml | hetzner_net, proxy |
| /mailserver-mailindex-sync | /opt/stacks/mailserver/compose.yaml | mailserver_default, postgis |
| /minidepo_web | /opt/stacks/minidepo.hr/docker-compose.yml | postgis, proxy |
| /tailscale-postgis | /opt/stacks/data/docker-compose.yml | host |
| /postgis | /opt/stacks/data/docker-compose.yml | backend, data_default, hetzner_net, postgis |
| /crowdsec-importer | /opt/stacks/crowdsec/docker-compose.yml | postgis, proxy |
| /crowdsec-scheduler | /opt/stacks/crowdsec/docker-compose.yml | postgis, proxy |
| /crowdsec-django | /opt/stacks/crowdsec/docker-compose.yml | postgis, proxy |
| /crowdsec | /opt/stacks/crowdsec/docker-compose.yml | proxy |
| /qubit | /opt/stacks/qubit/docker-compose.yml | backend, proxy |
| /diun | /opt/stacks/diun/docker-compose.yml | diun_default |
| /headscale | /opt/stacks/headscale/docker-compose.yml | backend, proxy |

### DB konfiguracijski ključevi i sanitizirani endpointi

Vrijednosti lozinki su uklonjene. URI-ji su rastavljeni; nema izvornog URI-ja ni query vrijednosti. Prisutnost DB varijable u frontendu ne dokazuje da frontend uspostavlja vezu. U cutover uključiti sve stvarne potrošače i backup procese.

- **nextcloud-cron**: `POSTGRES_USER`=`nextcloud`; `POSTGRES_HOST`=`postgis`; `POSTGRES_PORT`=`5432`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_DB`=`nextcloud`
- **nextcloud**: `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_DB`=`nextcloud`; `POSTGRES_HOST`=`postgis`; `POSTGRES_USER`=`nextcloud`; `POSTGRES_PORT`=`5432`
- **nextcloud-mcp**: `TOKEN_STORAGE_DB`=[REDACTED]
- **mailserver-mail-mcp**: `DATABASE_URL`=`postgresql / mailblocklist / postgis / 5432 / mailblocklist`
- **mailserver**: `BLOCKLIST_DB_NAME`=`mailblocklist`; `BLOCKLIST_DB_PASSWORD`=[REDACTED]; `BLOCKLIST_DB_USER`=`mailblocklist`
- **immich_media_operations**: `DB_USERNAME`=`immich`; `DB_DATABASE_NAME`=`immich`; `DB_PASSWORD`=[REDACTED]; `DB_HOSTNAME`=`postgis`; `DB_PORT`=`5432`
- **nextcloud_immich_bridge**: `DB_PORT`=`5432`; `DB_DATABASE_NAME`=`immich`; `DB_HOSTNAME`=`postgis`; `DB_USERNAME`=`immich`; `DB_PASSWORD`=[REDACTED]
- **immich_server**: `DB_HOSTNAME`=`postgis`; `DB_PORT`=`5432`; `DB_DATABASE_NAME`=`immich`; `DB_USERNAME`=`immich`; `DB_PASSWORD`=[REDACTED]
- **immich_machine_learning**: `DB_PORT`=`5432`; `DB_USERNAME`=`immich`; `DB_HOSTNAME`=`postgis`; `DB_PASSWORD`=[REDACTED]; `DB_DATABASE_NAME`=`immich`
- **finestar_erp**: `DATABASE_PORT`=`5432`; `DATABASE_HOST`=`postgis`; `GATEWAY_DATABASE_URL`=`postgresql+psycopg / postgis / postgis / 5432 / racunai_intermediary`; `DATABASE_NAME`=`finestar_erp_db`; `DATABASE_PASSWORD`=[REDACTED]; `DATABASE_USER`=`postgis`
- **finestar_erp_celery_worker**: `DATABASE_PORT`=`5432`; `GATEWAY_DATABASE_URL`=`postgresql+psycopg / postgis / postgis / 5432 / racunai_intermediary`; `DATABASE_HOST`=`postgis`; `DATABASE_PASSWORD`=[REDACTED]; `DATABASE_USER`=`postgis`; `DATABASE_NAME`=`finestar_erp_db`
- **finestar_erp_celery_beat**: `DATABASE_PORT`=`5432`; `GATEWAY_DATABASE_URL`=`postgresql+psycopg / postgis / postgis / 5432 / racunai_intermediary`; `DATABASE_USER`=`postgis`; `DATABASE_PASSWORD`=[REDACTED]; `DATABASE_HOST`=`postgis`; `DATABASE_NAME`=`finestar_erp_db`
- **racunai_mps**: `DATABASE_USER`=`postgis`; `DATABASE_NAME`=`finestar_erp_db`; `DATABASE_PORT`=`5432`; `DATABASE_PASSWORD`=[REDACTED]; `GATEWAY_DATABASE_URL`=`postgresql+psycopg / postgis / postgis / 5432 / racunai_intermediary`; `DATABASE_HOST`=`postgis`
- **stay_django**: `DB_PASSWORD`=[REDACTED]; `DB_NAME`=`stay_platform_db`; `DB_HOST`=`postgis`; `UZORITA_DB_PASSWORD`=[REDACTED]; `UZORITA_DB_PORT`=`5432`; `UZORITA_DB_HOST`=`postgis`; `UZORITA_DB_USER`=`stay_uzorita_ro`; `DB_USER`=`stay`; `UZORITA_DB_NAME`=`postgres`; `DB_PORT`=`5432`
- **stay_celery_worker**: `DB_PASSWORD`=[REDACTED]; `UZORITA_DB_USER`=`stay_uzorita_ro`; `DB_NAME`=`stay_platform_db`; `UZORITA_DB_PORT`=`5432`; `DB_PORT`=`5432`; `UZORITA_DB_HOST`=`postgis`; `UZORITA_DB_PASSWORD`=[REDACTED]; `DB_HOST`=`postgis`; `DB_USER`=`stay`; `UZORITA_DB_NAME`=`postgres`
- **stay_celery_beat**: `DB_USER`=`stay`; `UZORITA_DB_USER`=`stay_uzorita_ro`; `UZORITA_DB_PASSWORD`=[REDACTED]; `DB_PASSWORD`=[REDACTED]; `DB_HOST`=`postgis`; `DB_NAME`=`stay_platform_db`; `UZORITA_DB_HOST`=`postgis`; `UZORITA_DB_PORT`=`5432`; `DB_PORT`=`5432`; `UZORITA_DB_NAME`=`postgres`
- **roamkit-web-production**: `POSTGRES_PORT`=`5432`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_HOST`=`postgis`; `POSTGRES_DB`=`roamkit_production`; `POSTGRES_USER`=`roamkit`
- **roamkit-celery-beat-production**: `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_DB`=`roamkit_production`; `POSTGRES_PORT`=`5432`; `POSTGRES_USER`=`roamkit`; `POSTGRES_HOST`=`postgis`
- **roamkit-celery-production**: `POSTGRES_USER`=`roamkit`; `POSTGRES_DB`=`roamkit_production`; `POSTGRES_PORT`=`5432`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_HOST`=`postgis`
- **roamkit-api-production**: `POSTGRES_PORT`=`5432`; `POSTGRES_HOST`=`postgis`; `POSTGRES_USER`=`roamkit`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_DB`=`roamkit_production`
- **roamkit-web-staging**: `POSTGRES_DB`=`roamkit`; `POSTGRES_PORT`=`5432`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_USER`=`roamkit`; `POSTGRES_HOST`=`postgis`
- **roamkit-celery-beat-staging**: `POSTGRES_DB`=`roamkit`; `POSTGRES_HOST`=`postgis`; `POSTGRES_PORT`=`5432`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_USER`=`roamkit`
- **roamkit-api-staging**: `POSTGRES_PORT`=`5432`; `POSTGRES_DB`=`roamkit`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_HOST`=`postgis`; `POSTGRES_USER`=`roamkit`
- **roamkit-celery-staging**: `POSTGRES_PORT`=`5432`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_DB`=`roamkit`; `POSTGRES_USER`=`roamkit`; `POSTGRES_HOST`=`postgis`
- **omnimsgio-worker**: `DATABASE_URL`=`postgresql / omnimsgio / postgis / 5432 / omnimsgio`
- **omnimsgio-gateway**: `DATABASE_URL`=`postgresql / omnimsgio / postgis / 5432 / omnimsgio`
- **omnimsgio-api**: `DATABASE_URL`=`postgresql / omnimsgio / postgis / 5432 / omnimsgio`
- **chatwoot-rails**: `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_USERNAME`=`chatwoot`; `POSTGRES_HOST`=`postgis`; `POSTGRES_PORT`=`5432`
- **chatwoot-backup**: `PGDATABASE`=`chatwoot`; `PGHOST`=`postgis`; `PGPORT`=`5432`; `PGUSER`=`chatwoot`
- **chatwoot-sidekiq**: `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_USERNAME`=`chatwoot`; `POSTGRES_PORT`=`5432`; `POSTGRES_HOST`=`postgis`
- **parkschloss-api**: `DATABASE_URL`=`postgresql+psycopg / parkschloss / postgis / 5432 / parkschloss`
- **stay_web_booking**: `UZORITA_DB_NAME`=`postgres`; `UZORITA_DB_PASSWORD`=[REDACTED]; `UZORITA_DB_PORT`=`5432`; `DB_NAME`=`stay_platform_db`; `UZORITA_DB_HOST`=`postgis`; `DB_PORT`=`5432`; `DB_PASSWORD`=[REDACTED]; `DB_HOST`=`postgis`; `DB_USER`=`stay`; `UZORITA_DB_USER`=`stay_uzorita_ro`
- **f1-pts-api**: `DATABASE_PASSWORD`=[REDACTED]; `DATABASE_PORT`=`5432`; `DATABASE_USER`=`fiskal`; `REDIS_DB`=`0`; `DATABASE_HOST`=`postgis`; `DATABASE_NAME`=`fiskal_f1_pts_smoke`
- **omnimsgio-web**: `DATABASE_URL`=`postgresql / omnimsgio / postgis / 5432 / omnimsgio`
- **tablio_django**: `DB_NAME`=`tablio_platform_db`; `DB_PASSWORD`=[REDACTED]; `DB_USER`=`tablio`; `DB_PORT`=`5432`; `DB_HOST`=`postgis`
- **tablio_celery_worker**: `DB_HOST`=`postgis`; `DB_PASSWORD`=[REDACTED]; `DB_PORT`=`5432`; `DB_USER`=`tablio`; `DB_NAME`=`tablio_platform_db`
- **crowdsec-firewall-bouncer**: `POSTGRES_USER`=`crowdsec`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_HOST`=`postgis`; `POSTGRES_PORT`=`5432`; `POSTGRES_DB`=`crowdsec`
- **uzorita-celery-worker**: `DB_NAME`=`postgres`; `DB_USER`=`postgres`; `DB_PORT`=`5432`; `DB_HOST`=`postgis`; `DB_PASSWORD`=[REDACTED]; `DB_ENGINE`=`django.db.backends.postgresql`
- **uzorita-celery-beat**: `DB_HOST`=`postgis`; `DB_PORT`=`5432`; `DB_PASSWORD`=[REDACTED]; `DB_NAME`=`postgres`; `DB_USER`=`postgres`; `DB_ENGINE`=`django.db.backends.postgresql`
- **uzorita-celery-booking-browser**: `DB_USER`=`postgres`; `DB_PASSWORD`=[REDACTED]; `DB_PORT`=`5432`; `DB_HOST`=`postgis`; `DB_ENGINE`=`django.db.backends.postgresql`; `DB_NAME`=`postgres`
- **predix-celery-beat**: `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_PORT`=`5432`; `POSTGRES_USER`=`predix`; `POSTGRES_DB`=`predix`; `POSTGRES_HOST`=`postgis`
- **predix-celery-worker**: `POSTGRES_USER`=`predix`; `POSTGRES_DB`=`predix`; `POSTGRES_PORT`=`5432`; `POSTGRES_HOST`=`postgis`; `POSTGRES_PASSWORD`=[REDACTED]
- **mozzart-celery-beat**: `DATABASE_URL`=`postgresql / postgis / postgis / 5432 / mozzart_db`
- **mozzart-celery-worker**: `DATABASE_URL`=`postgresql / postgis / postgis / 5432 / mozzart_db`
- **mozzart**: `DATABASE_URL`=`postgresql / postgis / postgis / 5432 / mozzart_db`
- **mozzart-print-bridge**: `DATABASE_URL`=`postgresql / postgis / postgis / 5432 / mozzart_db`
- **fiskal_api**: `DATABASE_HOST`=`postgis`; `DATABASE_PASSWORD`=[REDACTED]; `REDIS_DB`=`5`; `DATABASE_NAME`=`fiskal`; `DATABASE_USER`=`fiskal`; `DATABASE_PORT`=`5432`
- **fiskal_worker**: `DATABASE_HOST`=`postgis`; `REDIS_DB`=`5`; `DATABASE_NAME`=`fiskal`; `DATABASE_PORT`=`5432`; `DATABASE_PASSWORD`=[REDACTED]; `DATABASE_USER`=`fiskal`
- **fiskal_mps**: `REDIS_DB`=`5`; `DATABASE_USER`=`fiskal`; `DATABASE_PORT`=`5432`; `DATABASE_PASSWORD`=[REDACTED]; `DATABASE_NAME`=`fiskal`; `DATABASE_HOST`=`postgis`
- **predix-api**: `POSTGRES_HOST`=`postgis`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_USER`=`predix`; `POSTGRES_DB`=`predix`; `POSTGRES_PORT`=`5432`
- **farma_frontend**: `POSTGRES_DB`=`farma_db`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_PORT`=`5432`; `POSTGRES_USER`=`farma_app`; `POSTGRES_HOST`=`postgis`
- **farma_backend**: `POSTGRES_PORT`=`5432`; `POSTGRES_HOST`=`postgis`; `POSTGRES_DB`=`farma_db`; `POSTGRES_USER`=`farma_app`; `POSTGRES_PASSWORD`=[REDACTED]
- **mailserver-mailadmin**: `DATABASE_URL`=`postgresql / mailblocklist / postgis / 5432 / mailblocklist`
- **predix-sync**: `POSTGRES_HOST`=`postgis`; `POSTGRES_PORT`=`5432`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_USER`=`predix`; `POSTGRES_DB`=`predix`
- **crowdsec-cloudflare-bouncer**: `POSTGRES_HOST`=`postgis`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_DB`=`crowdsec`; `POSTGRES_PORT`=`5432`; `POSTGRES_USER`=`crowdsec`
- **superclean_django**: `DB_PORT`=`5432`; `DB_HOST`=`postgis`; `DB_PASSWORD`=[REDACTED]; `DB_USER`=`superclean`; `DB_NAME`=`superclean_db`
- **superclean_web**: `DB_USER`=`superclean`; `DB_PASSWORD`=[REDACTED]; `DB_NAME`=`superclean_db`; `DB_PORT`=`5432`; `DB_HOST`=`postgis`
- **superclean_web_admin**: `DB_NAME`=`superclean_db`; `DB_PASSWORD`=[REDACTED]; `DB_HOST`=`postgis`; `DB_PORT`=`5432`; `DB_USER`=`superclean`
- **snappymail**: `SNAPPYMAIL_DB_PASSWORD`=[REDACTED]; `SNAPPYMAIL_DB_PORT`=`5432`; `SNAPPYMAIL_DB_USER`=`snappymail`; `SNAPPYMAIL_DB_NAME`=`snappymail`; `SNAPPYMAIL_DB_HOST`=`postgis`
- **tailscale-booking-browser**: `DB_ENGINE`=`django.db.backends.postgresql`; `DB_NAME`=`postgres`; `DB_HOST`=`postgis`; `DB_USER`=`postgres`; `DB_PORT`=`5432`; `DB_PASSWORD`=[REDACTED]
- **mailserver-mailindex-sync**: `DATABASE_URL`=`postgresql / mailblocklist / postgis / 5432 / mailblocklist`
- **minidepo_web**: `DB_PASSWORD`=[REDACTED]; `DB_PORT`=`5432`; `DB_USER`=`postgres`; `DB_NAME`=`minidepo`; `DB_HOST`=`postgis`
- **postgis**: `POSTGRES_USER`=`postgres`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_DB`=`postgres`
- **crowdsec-importer**: `POSTGRES_USER`=`crowdsec`; `POSTGRES_PORT`=`5432`; `POSTGRES_DB`=`crowdsec`; `POSTGRES_HOST`=`postgis`; `POSTGRES_PASSWORD`=[REDACTED]
- **crowdsec-scheduler**: `POSTGRES_HOST`=`postgis`; `POSTGRES_USER`=`crowdsec`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_PORT`=`5432`; `POSTGRES_DB`=`crowdsec`
- **crowdsec-django**: `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_PORT`=`5432`; `POSTGRES_HOST`=`postgis`; `POSTGRES_DB`=`crowdsec`; `POSTGRES_USER`=`crowdsec`
- **crowdsec**: `POSTGRES_HOST`=`postgis`; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_DB`=`crowdsec`; `POSTGRES_PORT`=`5432`; `POSTGRES_USER`=`crowdsec`
- **qubit**: `DB_PASSWORD`=[REDACTED]; `POSTGRES_PASSWORD`=[REDACTED]; `POSTGRES_DB`=`qubit_user`; `POSTGRES_HOST`=`postgis`; `HEADSCALE_DB_NAME`=`headscale`; `POSTGRES_USER`=`qubit`; `HEADSCALE_DB_HOST`=`postgis`; `DB_HOST`=`postgis`; `DB_NAME`=`qubit_user`; `DB_USER`=`qubit`; `HEADSCALE_DB_PORT`=`5432`; `POSTGRES_PORT`=`5432`; `DB_PORT`=`5432`; `HEADSCALE_DB_PASSWORD`=[REDACTED]; `HEADSCALE_DB_USER`=`headscale`
- **headscale**: `DATABASE_HOST`=`postgis`; `DATABASE_PORT`=`5432`; `DATABASE_NAME`=`headscale`; `DATABASE_USER`=`headscale`

### Environment i secrets izvori

Data stack koristi `.env` (ključevi TZ, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB), `postgis-tailscale.env` i Tailscale state. Pratiti samo `.env.example` s praznim vrijednostima. Ostali stackovi najčešće koriste vlastiti `.env`; Superclean dodaje `.env.prod`, Roamkit production `runtime.env`, Omnimsgio `../../.env` u odnosu na Compose datoteku.

```text
ENV_FILES_DATA
/opt/stacks/data/.env 0o644
keys: TZ,POSTGRES_USER,POSTGRES_PASSWORD,POSTGRES_DB
/opt/stacks/data/postgis-tailscale.env 0o644
keys: TS_AUTHKEY
```

Nazivi mountova pod `/run/secrets` i izvori env datoteka pregledani su preko Docker metapodataka, bez čitanja vrijednosti. Nisu svi secrets Docker secrets objekti: velik dio vjerodajnica dolazi iz environment varijabli. Vanjski CI/CD secrets, udaljena računala i neprikazani host procesi nisu potpuno inventarizirani; R06 u registru rizika.

## PostGIS kataloške ovisnosti bez LIMIT-a

Metoda: članstvo `deptype=e` uz `refclassid=pg_extension`, rekurzivni interni objekti `deptype=i`, stupci preko pripadnosti cijele relacije te parent veze za indekse, default izraze, constraints, rewrite pravila i operatorske familije. Triggeri na tablicama ekstenzije prikazani su odvojeno radi ručne potvrde, umjesto da se automatski proglase aplikacijskim ili odbace. Ne isključivati funkcije samo po prefiksu `ST_`: u `farma_db` postoje C funkcije bez članstva u ekstenziji.

Brojevi su broj različitih dependency bridova, ne broj aplikacijskih objekata.

| Baza | Interni bridovi | Bridovi preko parent objekta | Kandidati | Triggeri za provjeru |
| --- | --- | --- | --- | --- |
| farma_db | 1246 | 94 | 38 | 1 |
| finestar_erp_db | 1135 | 4 | 0 | 0 |
| fiskal | 1135 | 4 | 0 | 0 |
| immich | 1135 | 4 | 0 | 0 |
| minidepo | 1135 | 4 | 10 | 0 |
| mozzart_db | 1117 | 4 | 0 | 0 |
| postgres | 1200 | 94 | 0 | 1 |
| predix | 1135 | 4 | 0 | 0 |
| stay_platform_test_db | 1135 | 4 | 0 | 0 |
| superclean_db | 1135 | 4 | 0 | 0 |
| template_postgis | 1200 | 94 | 0 | 1 |
| test_finestar_erp_db | 1135 | 4 | 0 | 0 |
| test_stay_platform_test_db | 1135 | 4 | 0 | 0 |

U devet dodatnih PostGIS baza nema preostalih aplikacijskih kandidata nakon ove klasifikacije. U `postgres` i `template_postgis` ostaje samo trigger `topology.layer_integrity_checks` na tablici ekstenzije. To je odvojeno od aplikacijskih ovisnosti.

### farma_db

| Kategorija | Ovisni objekt | Referenca |
| --- | --- | --- |
| candidate | function fieldwork_make_workitem_geom(integer,text,numeric,text,numeric) | type geometry |
| candidate | function st_collect(_geometry) | type geometry |
| candidate | function st_coverageunion(_geometry) | type geometry |
| candidate | function st_hasm(geometry) | type geometry |
| candidate | function st_hasz(geometry) | type geometry |
| candidate | function st_makeline(_geometry) | type geometry |
| candidate | function st_makepolygon(geometry,_geometry) | type geometry |
| candidate | function st_polygonize(_geometry) | type geometry |
| candidate | function st_union(_geometry) | type geometry |
| candidate | column geom of table fieldwork_roadsection | type geometry |
| candidate | column geom of view ceste_aktivne | type geometry |
| candidate | column geom of table fieldwork_workitem | type geometry |
| candidate | column geom of table odrzavanje_dionice_rute | type geometry |
| candidate | column geom of table parcele_arkod | type geometry |
| candidate | column geom of table parcele_katastarskacestica | type geometry |
| candidate | column geom of table parcele_parcelaobrada | type geometry |
| candidate | column geom of table parcele_parcelaposjed | type geometry |
| candidate | column geom of table roads_roadsection | type geometry |
| candidate | column geom of view sibenik_ceste_2024_view | type geometry |
| candidate | column geom of view sibenik_ceste_2025_view | type geometry |
| candidate | column geom of table test_geom | type geometry |
| candidate | index fieldwork_roadsection_geom_c1ce5de4_id | operator class gist_geometry_ops_2d for access method gist |
| candidate | index fieldwork_roadsection_geom_gix | operator class gist_geometry_ops_2d for access method gist |
| candidate | index fieldwork_workitem_geom_f205c737_id | operator class gist_geometry_ops_2d for access method gist |
| candidate | index idx_arkod_geom | operator class gist_geometry_ops_2d for access method gist |
| candidate | index idx_kc_geom | operator class gist_geometry_ops_2d for access method gist |
| candidate | index idx_parcelaobrada_geom | operator class gist_geometry_ops_2d for access method gist |
| candidate | index idx_parcelaposjed_geom | operator class gist_geometry_ops_2d for access method gist |
| candidate | index idx_rute_geom | operator class gist_geometry_ops_2d for access method gist |
| candidate | index roads_roadsection_geom_b8d6aa35_id | operator class gist_geometry_ops_2d for access method gist |
| candidate | index test_geom_gix | operator class gist_geometry_ops_2d for access method gist |
| candidate | default value for column length_m of table fieldwork_roadsection | function st_length(geometry) |
| candidate | rule _RETURN on view sibenik_ceste_2024_view | function st_length(geometry) |
| candidate | rule _RETURN on view sibenik_ceste_2024_view | function st_srid(geometry) |
| candidate | rule _RETURN on view sibenik_ceste_2024_view | function st_transform(geometry,integer) |
| candidate | rule _RETURN on view sibenik_ceste_2025_view | function st_length(geometry) |
| candidate | rule _RETURN on view sibenik_ceste_2025_view | function st_srid(geometry) |
| candidate | rule _RETURN on view sibenik_ceste_2025_view | function st_transform(geometry,integer) |
| review_trigger_on_extension_table | trigger layer_integrity_checks on table layer | function layertrigger() |

### minidepo

| Kategorija | Ovisni objekt | Referenca |
| --- | --- | --- |
| candidate | column geometry of table core_parcel | type geometry |
| candidate | column center of table core_site | type geometry |
| candidate | column geometry of table core_container | type geometry |
| candidate | column geometry of table core_gate | type geometry |
| candidate | column geometry of table core_accessroad | type geometry |
| candidate | index core_parcel_geometry_3d2ea530_id | operator class gist_geometry_ops_2d for access method gist |
| candidate | index core_site_center_d7264c0f_id | operator class gist_geometry_ops_2d for access method gist |
| candidate | index core_container_geometry_1f25090e_id | operator class gist_geometry_ops_2d for access method gist |
| candidate | index core_gate_geometry_0e101ee1_id | operator class gist_geometry_ops_2d for access method gist |
| candidate | index core_accessroad_geometry_1c42a1c4_id | operator class gist_geometry_ops_2d for access method gist |

### postgres

| Kategorija | Ovisni objekt | Referenca |
| --- | --- | --- |
| review_trigger_on_extension_table | trigger layer_integrity_checks on table layer | function layertrigger() |

### template_postgis

| Kategorija | Ovisni objekt | Referenca |
| --- | --- | --- |
| review_trigger_on_extension_table | trigger layer_integrity_checks on table layer | function layertrigger() |


Prostorni stupci aplikacijskih tablica:

| Baza | Tablica | Stupac | Tip i deklarirani SRID |
| --- | --- | --- | --- |
| farma_db | public.parcele_katastarskacestica | geom | geometry(MultiPolygon,3765) |
| farma_db | public.fieldwork_workitem | geom | geometry(MultiPolygon,3765) |
| farma_db | public.odrzavanje_dionice_rute | geom | geometry |
| farma_db | public.parcele_parcelaobrada | geom | geometry(Polygon,3765) |
| farma_db | public.parcele_arkod | geom | geometry(Polygon,3765) |
| farma_db | public.test_geom | geom | geometry(Point,3765) |
| farma_db | public.parcele_parcelaposjed | geom | geometry(Polygon,3765) |
| farma_db | public.fieldwork_roadsection | geom | geometry(LineString,3765) |
| farma_db | public.roads_roadsection | geom | geometry |
| minidepo | public.core_accessroad | geometry | geometry(LineString,4326) |
| minidepo | public.core_site | center | geometry(Point,4326) |
| minidepo | public.core_container | geometry | geometry(Polygon,4326) |
| minidepo | public.core_parcel | geometry | geometry(Polygon,4326) |
| minidepo | public.core_gate | geometry | geometry(Point,4326) |

Dva stupca u `farma_db` imaju generički tip geometry bez typmod SRID-a. Poznati SRID 3765 nije dokaz da svaki spremljeni red ima taj SRID; raspodjelu i valjanost mjeriti na restore probi.

## Statička provjera aplikacijskog koda

Pregledani su Python/SQL/JS/TS izvori u 14 dostupnih aplikacijskih korijena. Regex je indikator; `os.stat().st_size` i `st_mtime` su lažno pozitivni nalazi. Nije pokrenut Django setup, migrate ili aplikacijski test protiv produkcije.

| Korijen | Podudarne linije | Datoteke |
| --- | --- | --- |
| /opt/stacks/racunai.hr/api | 1 | 1 |
| /opt/stacks/qubit/predix.club/backend | 4 | 2 |
| /opt/stacks/sauber.hr | 6 | 2 |
| /opt/stacks/mozart/app | 2 | 2 |
| /opt/stacks/stay.hr/backend | 8 | 7 |
| /opt/stacks/fiskal.hr | 4 | 2 |
| /opt/stacks/dalekopro/backend | 76 | 31 |
| /opt/stacks/minidepo.hr | 17 | 6 |
| /opt/stacks/immich | 1 | 1 |
| /opt/stacks/qubit/user | 3 | 2 |
| /opt/stacks/uzorita/rooms/code/backend | 0 | 0 |
| /opt/stacks/roamkit-net | 0 | 0 |
| /opt/stacks/roamkit-production | 0 | 0 |
| /opt/stacks/tablio.hr/api | 4 | 3 |

- ERP: `api/app/config/settings.py:150`, u runtimeu `/app/config/settings.py:150`, PostGIS backend. Django backend `prepare_database()` pokušava instalirati PostGIS ako ga nema. Promjena hosta sama nije dovoljna za migracije.
- Superclean: `backend/config/settings/base.py:98`, PostGIS backend potvrđen i u runtimeu. `scripts/init_db.sql` uključuje PostGIS bootstrap.
- Predix: trenutačno obični PostgreSQL backend, potvrđen i u kontejneru. `bets/migrations/0002_replace_location_with_lat_lng.py` koristi ST_X/ST_Y samo ako postoji legacy location stupac; migracija je evidentirana kao primijenjena 18. lipnja 2026. Fresh-install i restore putanju treba zasebno testirati.
- Stay: produkcija obični PostgreSQL backend; poseban PostGIS testni workflow i setup skripte prema lokalnom AGENTS.md. `UZORITA_DB_*` predstavlja drugu vezu prema bazi `postgres`.
- Tablio: produkcija obični PostgreSQL backend; zasebne test postavke i dokumentacija spominju PostGIS.
- Mozzart: URL parser za PostgreSQL; riječ postgis u default URL-u označava rolu/host i sama ne dokazuje prostorni backend.
- Farma i Minidepo: izravni GIS modeli, migracije i funkcije. Farma dodatno koristi ST_Buffer, ST_Difference, ST_Collect, ST_LineMerge, ST_LineInterpolatePoint i ST_ClosestPoint.
- Immich lokalni media helper koristi postgis kao naziv hosta. To nije dokaz PostGIS SQL ovisnosti.
- Uzorita i dostupni Roamkit deployment repozitoriji: nisu pronađeni indikatori; potpuni runtime izvor i sve udaljene putanje nisu potvrđeni.

Podudarni objekti SQL funkcija/pogleda pregledani su iz kataloga; poznati extension pogledi geometry_columns/geography_columns nisu aplikacijske ovisnosti. Farma ima i `calculate_route_length()`, `fieldwork_make_workitem_geom(...)` te generirani/default izraz za `fieldwork_roadsection.length_m`. Statička analiza ne može dokazati odsutnost dinamičkog SQL-a.

## Vektorski indeksi

Immich server runtime verzija **v3.3.5**, revision `8303cb117e197c700332b33b61b45314c9cc5bb4`. Chatwoot image **v4.18.0**. Sve pronađene vektorske strukture:

| Baza | Tablica | Indeks | Metoda | MiB | Valid/ready |
| --- | --- | --- | --- | --- | --- |
| chatwoot | public.article_embeddings | index_article_embeddings_on_embedding | ivfflat | 1.57 | true/true |
| chatwoot | public.captain_assistant_responses | vector_idx_knowledge_entries_embedding | ivfflat | 1.57 | true/true |
| chatwoot | public.captain_faq_suggestions | vector_idx_captain_faq_suggestions_embedding | ivfflat | 1.57 | true/true |
| immich | public.smart_search | clip_index | vchordrq | 202.74 | true/true |
| immich | public.face_search | face_index | vchordrq | 166.13 | true/true |

### chatwoot.index_article_embeddings_on_embedding

```sql
CREATE INDEX index_article_embeddings_on_embedding ON public.article_embeddings USING ivfflat (embedding)
```

### chatwoot.vector_idx_knowledge_entries_embedding

```sql
CREATE INDEX vector_idx_knowledge_entries_embedding ON public.captain_assistant_responses USING ivfflat (embedding)
```

### chatwoot.vector_idx_captain_faq_suggestions_embedding

```sql
CREATE INDEX vector_idx_captain_faq_suggestions_embedding ON public.captain_faq_suggestions USING ivfflat (embedding vector_cosine_ops)
```

### immich.clip_index

```sql
CREATE INDEX clip_index ON public.smart_search USING vchordrq (embedding vector_cosine_ops) WITH (options='
        residual_quantization = false
        [build.internal]
        lists = [1]
        spherical_centroids = true
        build_threads = 4
        sampling_factor = 1024
        ')
```

### immich.face_index

```sql
CREATE INDEX face_index ON public.face_search USING vchordrq (embedding vector_cosine_ops) WITH (options='
        residual_quantization = false
        [build.internal]
        lists = [1]
        spherical_centroids = true
        build_threads = 4
        sampling_factor = 1024
        ')
```

Immich embedding stupci u `smart_search` i `face_search` su vector(512). Nisu pronađeni HNSW indeksi. Immich ima i GiST indekse nevezane uz potvrđene PostGIS ovisnosti; ne brisati sve GiST indekse pod pretpostavkom da su prostorni.

| Baza | Metode: broj indeksa / MiB |
| --- | --- |
| chatwoot | btree: 536 / 5.46; gin: 7 / 0.29; ivfflat: 3 / 4.71 |
| crowdsec | btree: 180 / 9912.14 |
| farma_db | gist: 16 / 0.16; btree: 695 / 10.59 |
| finestar_erp_db | btree: 692 / 14.55 |
| fiskal | btree: 152 / 10.14 |
| fiskal_f1_pts_smoke | btree: 154 / 1.45 |
| headscale | btree: 58 / 0.67 |
| immich | btree: 326 / 142.13; vchordrq: 2 / 368.88; gist: 2 / 28.20; gin: 7 / 77.97 |
| mailblocklist | btree: 195 / 14.70 |
| minidepo | gist: 5 / 0.08; btree: 101 / 1.70 |
| mozzart_db | btree: 588 / 65.23 |
| nextcloud | btree: 872 / 65.52 |
| omnimsgio | btree: 78 / 0.85 |
| parkschloss | btree: 52 / 0.47 |
| postgres | gist: 6 / 0.05; btree: 255 / 4.54 |
| powerdns | btree: 65 / 0.59 |
| predix | btree: 520 / 55.87 |
| qubit_user | btree: 565 / 6.77 |
| racunai_intermediary | btree: 69 / 2.40 |
| roamkit | btree: 377 / 6.52 |
| roamkit_production | btree: 377 / 5.84 |
| snappymail | btree: 50 / 0.48 |
| stay_platform_db | btree: 567 / 16.59 |
| stay_platform_test_db | btree: 519 / 5.16 |
| superclean_db | btree: 147 / 1.75 |
| tablio_platform_db | btree: 157 / 1.78 |
| template1 | btree: 40 / 0.34 |
| template_postgis | gist: 6 / 0.05; btree: 132 / 1.74 |
| test_finestar_erp_db | btree: 443 / 14.87 |
| test_predix | btree: 488 / 4.05 |
| test_qubit_user | btree: 299 / 3.28 |
| test_stay_platform_db | btree: 391 / 4.27 |
| test_stay_platform_test_db | btree: 558 / 5.69 |

## pg_cron

```text
WARNING:  database "qubit_user" has a collation version mismatch
DETAIL:  The database was created using collation version 2.31, but the operating system provides version 2.36.
HINT:  Rebuild all objects in this database that use the default collation and run ALTER DATABASE qubit_user REFRESH COLLATION VERSION, or build PostgreSQL with the right library version.
            name             |    setting     |    source    | sourcefile | sourceline 
-----------------------------+----------------+--------------+------------+------------
 cron.database_name          | postgres       | command line |            |           
 cron.enable_superuser_jobs  | on             | default      |            |           
 cron.host                   | localhost      | default      |            |           
 cron.launch_active_jobs     | on             | default      |            |           
 cron.log_min_messages       | warning        | default      |            |           
 cron.log_run                | on             | default      |            |           
 cron.log_statement          | on             | default      |            |           
 cron.max_running_jobs       | 32             | default      |            |           
 cron.timezone               | GMT            | default      |            |           
 cron.use_background_workers | off            | default      |            |           
 max_worker_processes        | 8              | default      |            |           
 shared_preload_libraries    | vchord,pg_cron | command line |            |           
(12 rows)

 jobid |          jobname           |  schedule  |                             command                              | nodename  | nodeport |  database  | username | active 
-------+----------------------------+------------+------------------------------------------------------------------+-----------+----------+------------+----------+--------
     1 | headscale_log_prune        | 15 2 * * * | SELECT run_headscale_log_prune(60);                              | localhost |     5432 | qubit_user | qubit    | t
     2 | headscale_log_export       | 15 3 * * 0 | SELECT run_headscale_log_export('/srv/qubit/backups/headscale'); | localhost |     5432 | qubit_user | qubit    | t
     3 | user_log_prune             | 30 2 * * * | SELECT run_user_log_prune(60);                                   | localhost |     5432 | qubit_user | qubit    | t
     4 | user_log_export            | 30 3 * * 0 | SELECT run_user_log_export('/srv/qubit/backups/user');           | localhost |     5432 | qubit_user | qubit    | t
     5 | nginx_log_prune            | 0 2 * * *  | SELECT run_nginx_log_prune(60);                                  | localhost |     5432 | qubit_user | qubit    | t
     6 | nginx_log_export           | 0 3 * * 0  | SELECT run_nginx_log_export('/srv/qubit/backups/nginx');         | localhost |     5432 | qubit_user | qubit    | t
     7 | nginx_log_partition_warmup | 0 * * * *  | SELECT ensure_nginx_partitions(1, 3);                            | localhost |     5432 | qubit_user | qubit    | t
(7 rows)

 jobid |  status   | count |              min              |              max              |              max              
-------+-----------+-------+-------------------------------+-------------------------------+-------------------------------
     1 | succeeded |   142 | 2025-11-14 03:15:00.010302+01 | 2026-04-04 04:15:00.005431+02 | 2026-04-04 04:15:00.008586+02
     2 | failed    |    13 | 2025-11-16 04:15:00.010782+01 | 2026-02-08 04:15:00.009706+01 | 2026-02-08 04:15:00.019287+01
     2 | succeeded |     7 | 2026-02-15 04:15:00.005678+01 | 2026-03-29 05:15:00.006176+02 | 2026-03-29 05:15:00.008707+02
     3 | succeeded |   142 | 2025-11-14 03:30:00.009669+01 | 2026-04-04 04:30:00.005392+02 | 2026-04-04 04:30:00.00848+02
     4 | failed    |    13 | 2025-11-16 04:30:00.010313+01 | 2026-02-08 04:30:00.006078+01 | 2026-02-08 04:30:00.010402+01
     4 | succeeded |     7 | 2026-02-15 04:30:00.005512+01 | 2026-03-29 05:30:00.005178+02 | 2026-03-29 05:30:00.007666+02
     5 | succeeded |   142 | 2025-11-14 03:00:00.013218+01 | 2026-04-04 04:00:00.004609+02 | 2026-04-04 04:00:00.011718+02
     6 | failed    |    13 | 2025-11-16 04:00:00.014318+01 | 2026-02-08 04:00:00.013948+01 | 2026-02-08 04:00:00.054343+01
     6 | succeeded |     7 | 2026-02-15 04:00:00.004891+01 | 2026-03-29 05:00:00.004959+02 | 2026-03-29 05:00:00.011071+02
     7 | succeeded |  3409 | 2025-11-13 20:00:00.012237+01 | 2026-04-04 23:00:00.004465+02 | 2026-04-04 23:00:00.007622+02
(10 rows)

 jobid | runid |  status   |          start_time           |           end_time            
-------+-------+-----------+-------------------------------+-------------------------------
     7 |  3895 | succeeded | 2026-04-04 23:00:00.004465+02 | 2026-04-04 23:00:00.007622+02
     7 |  3894 | succeeded | 2026-04-04 22:00:00.004611+02 | 2026-04-04 22:00:00.008343+02
     7 |  3893 | succeeded | 2026-04-04 21:00:00.005142+02 | 2026-04-04 21:00:00.008158+02
     7 |  3892 | succeeded | 2026-04-04 20:00:00.005848+02 | 2026-04-04 20:00:00.018098+02
     7 |  3891 | succeeded | 2026-04-04 19:00:00.004487+02 | 2026-04-04 19:00:00.007525+02
     7 |  3890 | succeeded | 2026-04-04 18:00:00.004949+02 | 2026-04-04 18:00:00.010698+02
     7 |  3889 | succeeded | 2026-04-04 17:00:00.004597+02 | 2026-04-04 17:00:00.009246+02
     7 |  3888 | succeeded | 2026-04-04 16:00:00.005472+02 | 2026-04-04 16:00:00.01081+02
     7 |  3887 | succeeded | 2026-04-04 15:00:00.005509+02 | 2026-04-04 15:00:00.009974+02
     7 |  3886 | succeeded | 2026-04-04 14:00:00.005011+02 | 2026-04-04 14:00:00.010363+02
     7 |  3885 | succeeded | 2026-04-04 13:00:00.005209+02 | 2026-04-04 13:00:00.007659+02
     7 |  3884 | succeeded | 2026-04-04 12:00:00.003489+02 | 2026-04-04 12:00:00.00633+02
     7 |  3883 | succeeded | 2026-04-04 11:00:00.005103+02 | 2026-04-04 11:00:00.009629+02
     7 |  3882 | succeeded | 2026-04-04 10:00:00.005557+02 | 2026-04-04 10:00:00.010867+02
(14 rows)

   backend_type   | datname  | state 
------------------+----------+-------
 pg_cron launcher | postgres | 
(1 row)

 pg_size_pretty 
----------------
 40 GB
(1 row)
```

Vremena u izvornom psql ispisu imaju Europe/Zagreb offset. Scheduler koristi GMT/UTC. Zadnji zabilježeni warmup: **4. travnja 2026. 23:00 CEST**, odnosno 21:00 UTC. Trenutačni postmaster pokrenut 26. lipnja 2026.; uzrok promjene konfiguracije nije povijesno dokazan.

Pregled funkcija: prune funkcije uklanjaju stare particije (retencija 60 dana); export funkcije server-side COPY-jem pišu CSV u `/srv/qubit/backups/{headscale,user,nginx}`; warmup poziva `ensure_daily_partition`. Funkcije su SECURITY INVOKER, vlasnik qubit. Ne izvršavati ih tijekom analize niti slijepo uključiti prune nakon višemjesečnog zastoja.

## Backupovi i prostor

```text
/opt/stacks/data/backups files= 41 bytes= 97169478
2026-11-13T23:18:50.204032+00:00 446582 /opt/stacks/data/backups/chatwoot/chatwoot-20261113T231850Z.dump
2026-11-12T23:18:50.070242+00:00 446582 /opt/stacks/data/backups/chatwoot/chatwoot-20261112T231849Z.dump
2026-11-11T23:18:49.926743+00:00 446582 /opt/stacks/data/backups/chatwoot/chatwoot-20261111T231849Z.dump
2026-11-10T23:18:49.698220+00:00 446582 /opt/stacks/data/backups/chatwoot/chatwoot-20261110T231849Z.dump
2026-11-09T23:18:49.509714+00:00 446582 /opt/stacks/data/backups/chatwoot/chatwoot-20261109T231849Z.dump
2026-11-08T23:18:49.352065+00:00 446641 /opt/stacks/data/backups/chatwoot/chatwoot-20261108T231849Z.dump
2026-11-07T23:18:49.212173+00:00 446641 /opt/stacks/data/backups/chatwoot/chatwoot-20261107T231849Z.dump
2026-11-06T23:18:49.027640+00:00 446641 /opt/stacks/data/backups/chatwoot/chatwoot-20261106T231848Z.dump
2026-11-05T23:18:48.897542+00:00 446641 /opt/stacks/data/backups/chatwoot/chatwoot-20261105T231848Z.dump
2026-11-04T23:18:48.739655+00:00 446641 /opt/stacks/data/backups/chatwoot/chatwoot-20261104T231848Z.dump
2026-11-03T23:18:48.586080+00:00 446641 /opt/stacks/data/backups/chatwoot/chatwoot-20261103T231848Z.dump
2026-11-02T23:18:48.423350+00:00 446641 /opt/stacks/data/backups/chatwoot/chatwoot-20261102T231848Z.dump
2026-11-01T23:18:48.289621+00:00 446641 /opt/stacks/data/backups/chatwoot/chatwoot-20261101T231848Z.dump
2026-10-31T23:18:48.149457+00:00 446641 /opt/stacks/data/backups/chatwoot/chatwoot-20261031T231848Z.dump
2026-10-30T23:18:47.961896+00:00 446641 /opt/stacks/data/backups/chatwoot/chatwoot-20261030T231847Z.dump
2026-06-09T05:57:18.008974+00:00 337951 /opt/stacks/data/backups/finestar_erp_db_2026-06-09.dump
2026-04-04T21:15:18.273075+00:00 2809 /opt/stacks/data/backups/pre-immich-cutover/postgis-globals-2026-04-04-231518.sql
2026-02-11T01:43:20.454732+00:00 4467 /opt/stacks/data/backups/RESTORE_PG16_RUNBOOK.md
2026-02-11T01:42:39.586633+00:00 16189 /opt/stacks/data/backups/restore_qubit_user_2026-02-11_024238.log
2026-02-11T01:42:24.022596+00:00 692 /opt/stacks/data/backups/restore_qubit_user_2026-02-11_024223.log
/srv/qubit/backups files= 22 bytes= 2715
2026-03-29T03:30:00.002627+00:00 60 /srv/qubit/backups/user/user_log_20260322_20260329.csv
2026-03-29T03:15:00.002908+00:00 65 /srv/qubit/backups/headscale/headscale_log_20260322_20260329.csv
2026-03-29T03:00:00.007293+00:00 230 /srv/qubit/backups/nginx/nginx_log_20260322_20260329.csv
2026-03-22T03:30:00.004051+00:00 60 /srv/qubit/backups/user/user_log_20260315_20260322.csv
2026-03-22T03:15:00.004345+00:00 65 /srv/qubit/backups/headscale/headscale_log_20260315_20260322.csv
2026-03-22T03:00:00.004772+00:00 230 /srv/qubit/backups/nginx/nginx_log_20260315_20260322.csv
2026-03-15T03:30:00.003369+00:00 60 /srv/qubit/backups/user/user_log_20260308_20260315.csv
2026-03-15T03:15:00.003665+00:00 65 /srv/qubit/backups/headscale/headscale_log_20260308_20260315.csv
2026-03-15T03:00:00.007926+00:00 230 /srv/qubit/backups/nginx/nginx_log_20260308_20260315.csv
2026-03-08T03:30:00.004514+00:00 60 /srv/qubit/backups/user/user_log_20260301_20260308.csv
2026-03-08T03:15:00.004885+00:00 65 /srv/qubit/backups/headscale/headscale_log_20260301_20260308.csv
2026-03-08T03:00:00.005243+00:00 230 /srv/qubit/backups/nginx/nginx_log_20260301_20260308.csv
2026-03-01T03:30:00.003560+00:00 60 /srv/qubit/backups/user/user_log_20260222_20260301.csv
2026-03-01T03:15:00.004064+00:00 65 /srv/qubit/backups/headscale/headscale_log_20260222_20260301.csv
2026-03-01T03:00:00.008495+00:00 230 /srv/qubit/backups/nginx/nginx_log_20260222_20260301.csv
2026-02-22T03:30:00.002651+00:00 60 /srv/qubit/backups/user/user_log_20260215_20260222.csv
2026-02-22T03:15:00.003400+00:00 65 /srv/qubit/backups/headscale/headscale_log_20260215_20260222.csv
2026-02-22T03:00:00.008440+00:00 230 /srv/qubit/backups/nginx/nginx_log_20260215_20260222.csv
2026-02-15T03:30:00.004825+00:00 60 /srv/qubit/backups/user/user_log_20260208_20260215.csv
2026-02-15T03:15:00.001707+00:00 65 /srv/qubit/backups/headscale/headscale_log_20260208_20260215.csv
```

Dodatno pronađeno **15 Immich SQL gzip backupova**, ukupno približno 4,89 GB, pod `/opt/stacks/immich/docker-data/library/backups`. Najnoviji: `immich-db-backup-20261114T020000-v3.3.5-pg16.13.sql.gz`, 355.180.212 bajtova, mtime 14.11.2026. 02:00:47 CET. Potpuno čitanje/dekompresija završilo bez gzip greške, 924.877.877 dekomprimiranih bajtova. To nije restore test.

Chatwoot: najnoviji pregledani archive TOC čitljiv, 1041 stavka, custom format, dump/server 16.13. Gzip integritet povijesnih pg14/pg16 SQL dumpova također prolazi. Nije izvršen nijedan restore. Svježa i provjerena pokrivenost svih 31 baze, off-host kopija i obnova medijskih datoteka nisu potvrđeni.

`/srv/qubit/backups` sadrži CSV izvoze logova, ne zamjenu za DB backup. Immich fotografije su na `/opt/stacks/immich/docker-data/library`, a external library koristi Nextcloud data; DB dump ne štiti te datoteke.

## Dnevnik naredbi i ograničenja

Izvršavane su samo inspekcije: `hostname`, `pwd`, `git status --short`, `rg --files`, `rg --json`, `cat`/odabrani `sed`, `df -hT`, `du -sh`, `docker ps`, sanitizirani `docker inspect`, `docker logs --since 24h --tail 3000 postgis`, `dpkg-query -W`, te `docker exec postgis psql -X -U postgres -d DB ...` sa SELECT upitima. Python stdlib korišten za parsiranje, os.stat i gzip čitanje. Nijedan aplikacijski modul nije pokrenut kroz njegov startup.

Glavni ponovljivi SELECT za ovisnosti (bez LIMIT-a; zadnji SELECT ovdje je uži prikaz istih CTE-ova korištenih u inventaru):

```sql
WITH RECURSIVE
members AS (
 SELECT d.classid,d.objid,d.objsubid FROM pg_depend d JOIN pg_extension e ON e.oid=d.refobjid
 WHERE d.refclassid='pg_extension'::regclass AND d.deptype='e' AND e.extname LIKE 'postgis%'
),
internals(classid,objid,objsubid) AS (
 SELECT * FROM members
 UNION
 SELECT d.classid,d.objid,d.objsubid FROM pg_depend d JOIN internals p
 ON d.refclassid=p.classid AND d.refobjid=p.objid AND (p.objsubid=0 OR p.objsubid=d.refobjsubid)
 WHERE d.deptype='i'
),
raw AS (
 SELECT DISTINCT d.classid,d.objid,d.objsubid,d.refclassid,d.refobjid,d.refobjsubid
 FROM pg_depend d JOIN internals p ON d.refclassid=p.classid AND d.refobjid=p.objid
 AND (p.objsubid=0 OR p.objsubid=d.refobjsubid) WHERE d.deptype='n'
),
classified AS (
 SELECT r.*,
 CASE WHEN EXISTS(SELECT 1 FROM internals x WHERE x.classid=r.classid AND x.objid=r.objid AND (x.objsubid=0 OR x.objsubid=r.objsubid)) THEN 'extension_internal'
 WHEN r.classid='pg_class'::regclass AND EXISTS(SELECT 1 FROM pg_index i JOIN internals x ON x.classid='pg_class'::regclass AND x.objid=i.indrelid WHERE i.indexrelid=r.objid) THEN 'extension_parent'
 WHEN r.classid='pg_attrdef'::regclass AND EXISTS(SELECT 1 FROM pg_attrdef a JOIN internals x ON x.classid='pg_class'::regclass AND x.objid=a.adrelid WHERE a.oid=r.objid) THEN 'extension_parent'
 WHEN r.classid='pg_constraint'::regclass AND EXISTS(SELECT 1 FROM pg_constraint c JOIN internals x ON x.classid='pg_class'::regclass AND x.objid=c.conrelid WHERE c.oid=r.objid) THEN 'extension_parent'
 WHEN r.classid='pg_rewrite'::regclass AND EXISTS(SELECT 1 FROM pg_rewrite w JOIN internals x ON x.classid='pg_class'::regclass AND x.objid=w.ev_class WHERE w.oid=r.objid) THEN 'extension_parent'
 WHEN r.classid='pg_trigger'::regclass AND EXISTS(SELECT 1 FROM pg_trigger t JOIN internals x ON x.classid='pg_class'::regclass AND x.objid=t.tgrelid WHERE t.oid=r.objid) THEN 'review_trigger_on_extension_table'
 WHEN r.classid='pg_amop'::regclass AND EXISTS(SELECT 1 FROM pg_amop a JOIN internals x ON x.classid='pg_opfamily'::regclass AND x.objid=a.amopfamily WHERE a.oid=r.objid) THEN 'extension_operator_family_parent'
 WHEN r.classid='pg_amproc'::regclass AND EXISTS(SELECT 1 FROM pg_amproc a JOIN internals x ON x.classid='pg_opfamily'::regclass AND x.objid=a.amprocfamily WHERE a.oid=r.objid) THEN 'extension_operator_family_parent'
 ELSE 'candidate' END AS category
 FROM raw r
)
SELECT category, pg_describe_object(classid,objid,objsubid) AS dependent_object, pg_describe_object(refclassid,refobjid,refobjsubid) AS referenced_object FROM classified ORDER BY category,dependent_object,referenced_object;
```

Ključne ostale provjere:

```bash
docker inspect postgis --format 'Image: {{.Config.Image}}{{println}}{{range .Mounts}}Mount: {{.Source}} -> {{.Destination}}{{println}}{{end}}'
docker exec postgis psql -X -U postgres -d postgres -c 'SELECT version();'
docker exec postgis psql -X -U postgres -d qubit_user -c 'SELECT jobid,jobname,schedule,command,nodename,nodeport,database,username,active FROM cron.job ORDER BY jobid;'
docker exec postgis psql -X -U postgres -d qubit_user -c 'SELECT jobid,status,count(*),min(start_time),max(start_time),max(end_time) FROM cron.job_run_details GROUP BY jobid,status ORDER BY jobid,status;'
docker exec postgis psql -X -U postgres -d farma_db -c 'SELECT postgis_full_version();'
docker exec postgis pg_restore --list /backups/chatwoot/chatwoot-20261113T231850Z.dump
df -hT /opt/stacks/data/postgres/data /opt/stacks/data/backups /srv/qubit/backups
```

Neuspjele dijagnostike: `regdatabase` nije PostgreSQL tip (upit ispravljen JOIN-om na pg_database); import Django backenda bez settingsa nije uspio (zamijenjen čitanjem izvornog koda); query pg_stat_statements u bazi postgres ne postoji (ekstenzija je samo u chatwoot, a nije preloaded). Početni veliki izlazi bili su skraćeni i JSON višeredni ispis krivo parsiran; završni inventar ponovno je prikupljen po bazi i sadrži svih 33 connectable baza bez parser grešaka. Ne koristiti početne nepotpune ispise kao dokaz.

Nisu izvršeni dump nove produkcijske baze, restore, DDL, REINDEX, reload, restart ili promjena konfiguracije. Promjene u repozitoriju odnose se samo na ovih šest Markdown dokumenata; postojeći `data.code-workspace` nije diran.

## Dopuna: svi aktivni Compose izvori i shell workflowi

Docker Compose izvori iz oznaka svih trenutačno pokrenutih kontejnera (uključuju i servise koji DB konfiguraciju ne izlažu kao env):

```text
/opt/stacks/Das-Parkschloss/chatwoot/docker-compose.yml exists=True
/opt/stacks/Das-Parkschloss/docker-compose.yml exists=True
/opt/stacks/PaddleOCR/deploy/pdf-finestar/docker-compose.yml exists=True
/opt/stacks/PaddleOCR/docker/wsl2-rec-train/docker-compose.yml exists=True
/opt/stacks/barakags.hr/docker-compose.prod.yml exists=True
/opt/stacks/code-server/docker-compose.yml exists=True
/opt/stacks/coturn/docker-compose.yml exists=True
/opt/stacks/crowdsec/docker-compose.yml exists=True
/opt/stacks/dalekopro/docker-compose.putni-list-dev.yml exists=True
/opt/stacks/dalekopro/docker-compose.yml exists=True
/opt/stacks/data/docker-compose.yml exists=True
/opt/stacks/derp/docker-compose.yml exists=True
/opt/stacks/diun/docker-compose.yml exists=True
/opt/stacks/dozzle/docker-compose.yml exists=True
/opt/stacks/emqx/docker-compose.yml exists=True
/opt/stacks/finestar/web/deploy/state/traefik.override.yml exists=True
/opt/stacks/finestar/web/docker-compose.yml exists=True
/opt/stacks/fiskal.hr/docker-compose.yml exists=True
/opt/stacks/gcloud/docker-compose.yml exists=True
/opt/stacks/github-actions-runner-tablio/docker-compose.yml exists=True
/opt/stacks/github-actions-runner/docker-compose.yml exists=True
/opt/stacks/headscale/docker-compose.yml exists=True
/opt/stacks/headscale/exitnode/docker-compose.yml exists=True
/opt/stacks/immich/docker-compose.yml exists=True
/opt/stacks/kuma/docker-compose.yml exists=True
/opt/stacks/mailserver/compose.yaml exists=True
/opt/stacks/minidepo.hr/docker-compose.yml exists=True
/opt/stacks/mozart/docker-compose.yml exists=True
/opt/stacks/nextcloud/docker-compose.yml exists=True
/opt/stacks/omnimsgio/docker/production/docker-compose.yml exists=True
/opt/stacks/portainer/docker-compose.yml exists=True
/opt/stacks/powerdns/docker-compose.yml exists=True
/opt/stacks/qubit/docker-compose.yml exists=True
/opt/stacks/qubit/predix.club/docker-compose.betting-dev.yml exists=True
/opt/stacks/qubit/predix.club/docker-compose.sofascore-tailscale.yml exists=True
/opt/stacks/qubit/predix.club/docker-compose.yml exists=True
/opt/stacks/racunai.hr/as4-gateway/docker-compose.yml exists=True
/opt/stacks/racunai.hr/docker-compose.yml exists=True
/opt/stacks/redis/docker-compose.yml exists=True
/opt/stacks/roamkit-net/docker-compose.yml exists=True
/opt/stacks/roamkit-production/docker-compose.yml exists=True
/opt/stacks/rustdesk/docker-compose.yml exists=True
/opt/stacks/sauber.hr/docker-compose.prod.yml exists=True
/opt/stacks/sauber.hr/docker-compose.yml exists=True
/opt/stacks/snappymail/compose.yaml exists=False
/opt/stacks/stay.hr/docker-compose.yml exists=True
/opt/stacks/stepca/docker-compose.yml exists=True
/opt/stacks/tablio.hr/api/docker-compose.yml exists=True
/opt/stacks/tablio.hr/web/docker-compose.yml exists=True
/opt/stacks/test-whoami/docker-compose.yml exists=True
/opt/stacks/traefik/docker-compose.yml exists=True
/opt/stacks/uzorita/rooms/code/backend/docker-compose.yml exists=True
/opt/stacks/uzorita/rooms/code/frontend/docker-compose.yml exists=True
```

Ovo je popis aktivnih projekata, ne tvrdnja da su sve povijesne/dev Compose datoteke aktivne. Dodatno su preko rg pronađeni lokalni/dev overrideovi; relevantni data override je opisan gore. Konfiguracije nekih host/udaljenih DB potrošača nisu potpuno dostupne i ostaju R06.

Shell setup, test i backup skripte također su pročitane statičkom pretragom, bez pokretanja. Dokazi ispod sadrže samo putanje, brojeve linija i prepoznate tokene, bez vrijednosti konfiguracije.

| Datoteka | Linija | Tokeni |
| --- | --- | --- |
| /opt/stacks/racunai.hr/api/scripts/setup_test_db.sh | 2 | PostGIS |
| /opt/stacks/racunai.hr/api/scripts/setup_test_db.sh | 3 | postgis |
| /opt/stacks/racunai.hr/api/scripts/setup_test_db.sh | 4 | postgis |
| /opt/stacks/racunai.hr/api/scripts/setup_test_db.sh | 8 | postgis |
| /opt/stacks/racunai.hr/api/scripts/setup_test_db.sh | 11 | postgis |
| /opt/stacks/racunai.hr/api/scripts/setup_test_db.sh | 13 | postgis |
| /opt/stacks/racunai.hr/api/scripts/setup_test_db.sh | 17 | postgis |
| /opt/stacks/racunai.hr/api/scripts/setup_test_db.sh | 18 | postgis |
| /opt/stacks/racunai.hr/api/scripts/setup_test_db.sh | 28 | postgis |
| /opt/stacks/racunai.hr/api/scripts/setup_test_db.sh | 29 | postgis |
| /opt/stacks/racunai.hr/api/scripts/setup_test_db.sh | 47 | CREATE EXTENSION, postgis |
| /opt/stacks/racunai.hr/api/scripts/setup_test_db.sh | 55 | PostGIS |
| /opt/stacks/racunai.hr/intermediary/mps/entrypoint.sh | 4 | GATEWAY_DATABASE_URL |
| /opt/stacks/racunai.hr/intermediary/mps/entrypoint.sh | 5 | GATEWAY_DATABASE_URL |
| /opt/stacks/racunai.hr/intermediary/deploy/provision_via_postgis_container.sh | 2 | postgis |
| /opt/stacks/racunai.hr/intermediary/deploy/provision_via_postgis_container.sh | 5 | POSTGIS, postgis |
| /opt/stacks/stay.hr/scripts/run-tests-postgis.sh | 2 | PostGIS |
| /opt/stacks/stay.hr/scripts/run-tests-postgis.sh | 5 | postgis |
| /opt/stacks/stay.hr/scripts/run-tests-postgis.sh | 6 | postgis |
| /opt/stacks/stay.hr/scripts/run-tests-postgis.sh | 7 | postgis |
| /opt/stacks/stay.hr/scripts/run-tests-postgis.sh | 68 | postgis |
| /opt/stacks/stay.hr/scripts/run-tests-postgis.sh | 75 | postgis |
| /opt/stacks/stay.hr/scripts/tests/test_deploy_git_sha.sh | 49 | postgis |
| /opt/stacks/stay.hr/scripts/ensure-test-db.sh | 2 | PostGIS |
| /opt/stacks/stay.hr/scripts/ensure-test-db.sh | 13 | postgis |
| /opt/stacks/stay.hr/scripts/ensure-test-db.sh | 16 | POSTGIS, POSTGIS, postgis |
| /opt/stacks/stay.hr/scripts/ensure-test-db.sh | 23 | POSTGIS |
| /opt/stacks/stay.hr/scripts/ensure-test-db.sh | 29 | POSTGIS |
| /opt/stacks/stay.hr/scripts/ensure-test-db.sh | 32 | postgis |
| /opt/stacks/stay.hr/scripts/ensure-test-db.sh | 33 | POSTGIS |
| /opt/stacks/stay.hr/scripts/ensure-test-db.sh | 34 | CREATE EXTENSION, postgis |
| /opt/stacks/stay.hr/scripts/ensure-test-db.sh | 37 | POSTGIS |
| /opt/stacks/stay.hr/scripts/ensure-test-db.sh | 38 | PostGIS, POSTGIS |
| /opt/stacks/stay.hr/scripts/ensure-test-db.sh | 46 | POSTGIS |
| /opt/stacks/tablio.hr/api/scripts/run-tests.sh | 5 | postgis |
| /opt/stacks/tablio.hr/api/scripts/run-tests.sh | 19 | postgis, postgis |
| /opt/stacks/Das-Parkschloss/chatwoot/restore-test.sh | 3 | postgis |
| /opt/stacks/Das-Parkschloss/chatwoot/restore-test.sh | 16 | postgis |
| /opt/stacks/Das-Parkschloss/chatwoot/restore-test.sh | 17 | postgis |
| /opt/stacks/Das-Parkschloss/chatwoot/restore-test.sh | 18 | postgis |
| /opt/stacks/Das-Parkschloss/chatwoot/restore-test.sh | 19 | postgis, CREATE EXTENSION |
| /opt/stacks/Das-Parkschloss/chatwoot/restore-test.sh | 20 | postgis, pg_restore |
| /opt/stacks/Das-Parkschloss/chatwoot/restore-test.sh | 21 | postgis |
| /opt/stacks/Das-Parkschloss/chatwoot/restore-test.sh | 22 | postgis |
| /opt/stacks/Das-Parkschloss/chatwoot/backup-loop.sh | 11 | pg_dump |

Posebno: ERP setup_test_db.sh, Stay ensure-test-db.sh/run-tests-postgis.sh, Tablio run-tests.sh i Chatwoot restore-test.sh imaju reference na stari postgis kontejner/endpoint. Postojeći Chatwoot restore-test.sh nije pokrenut: prema statičkom nalazu radi DDL i restore u postojećem kontejneru, što nije prihvatljivo u ovoj fazi niti kao izolirana proba bez prerade.

Dodatni read-only nalazi: pg_wal trenutačno oko **145 MiB**; ss nije pokazao listener na TCP 5433/5434. Portove svejedno ponovo provjeriti na dan implementacije. Ova provjera ne rezervira port niti odobrava njegov bind.
