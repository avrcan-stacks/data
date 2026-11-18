"""Validation of the restored target database (immich-db). READ ONLY except the optional --amcheck (rolled-back transaction on the TARGET only).

PREPARED IN PHASE 6, NOT EXECUTED AGAINST PRODUCTION.
    CUTOVER_ID=... python3 -I validate_target.py --baseline evidence/baseline-*.json [--samples 20] [--min-recall-mean 0.95] [--min-recall-min 0.90] [--amcheck]

Thresholds are PROPOSALS (see docs/postgres-migration/17-immich-production-cutover.md, section 9) and are not approved.
"""
import argparse, json, os, re, sys, time, statistics
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cutlib import *

ap = argparse.ArgumentParser()
ap.add_argument('--baseline', required=True, help='baseline-*.json written by preflight.py')
ap.add_argument('--source-snapshot', help='db_snapshot.py snapshot of the FROZEN source: row counts and sequence value are taken from it (the preflight baseline is older: users keep writing between preflight and freeze)')
ap.add_argument('--samples', type=int, default=20)
ap.add_argument('--min-recall-mean', type=float, default=0.95)
ap.add_argument('--min-recall-min', type=float, default=0.90)
ap.add_argument('--max-ann-ms', type=float, default=250.0)
ap.add_argument('--amcheck', action='store_true')
ap.add_argument('--skip-login', action='store_true', help='rehearsal only: skip the production-password login test')
a = ap.parse_args()
if a.skip_login and not REHEARSAL: ap.error('--skip-login is restricted to rehearsal')
base = json.loads(Path(a.baseline).read_text())['source']
src_rows = src_seq = None
if a.source_snapshot:
    _t = json.loads((Path(a.source_snapshot) / 'tables.json').read_text()); src_rows = {k: _t[v]['rows'] for k, v in (('users', 'user'), ('assets', 'asset'), ('albums', 'album'), ('libraries', 'library'), ('persons', 'person'), ('smart_search', 'smart_search'), ('face_search', 'face_search'), ('api_keys', 'api_key'))}
    src_seq = {x['sequencename']: x['last_value'] for x in json.loads((Path(a.source_snapshot) / 'sequences.json').read_text())}.get('naturalearth_countries_tmp_id_seq1')
expect_counts = src_rows or base['counts']; expect_seq = src_seq if src_seq is not None else base['seq']['last']
R = Report('validate-target')
C = TARGET

v = psql(C, 'SHOW server_version;', db='postgres')
R.check('V1', 'target is PostgreSQL 16.16', v.startswith('16.16'), v)
R.check('V2', 'PostGIS is not available in the target image', int(psql(C, "SELECT count(*) FROM pg_available_extensions WHERE name ILIKE 'postgis%';", db='postgres')) == 0)
ext = pj(C, "SELECT json_object_agg(extname,extversion) FROM pg_extension;")
R.check('V3', 'target has exactly the 8 retained extensions at validated versions', ext == EXPECTED_EXT, ext)
d = pj(C, """SELECT json_build_object('owner',pg_get_userbyid(datdba),'enc',pg_encoding_to_char(encoding),'collate',datcollate,'allow',datallowconn,
   'acl',(SELECT json_agg(json_build_array(COALESCE(g.rolname,'PUBLIC'),x.privilege_type) ORDER BY 1,2) FROM aclexplode(COALESCE(datacl,acldefault('d',datdba))) x LEFT JOIN pg_roles g ON g.oid=x.grantee),
   'size',pg_database_size(current_database())) FROM pg_database WHERE datname=current_database();""")
R.check('V4', 'database owner/encoding/collation and ACL equal the source', d['owner'] == base['db']['owner'] and d['enc'] == 'UTF8' and d['collate'] == 'en_US.utf8' and sorted(map(tuple, d['acl'])) == sorted(map(tuple, base['db']['acl'])), {k: d[k] for k in ('owner', 'enc', 'collate')})
role = pj(C, "SELECT json_build_object('super',rolsuper,'createdb',rolcreatedb,'createrole',rolcreaterole,'repl',rolreplication,'bypassrls',rolbypassrls,'login',rolcanlogin,'inherit',rolinherit) FROM pg_roles WHERE rolname='immich';")
R.check('V5', 'role immich has the same attributes as on the source (LOGIN, no superuser/createdb/createrole/replication/bypassrls)', role == base['role'], role)
pw = '' if a.skip_login else container_env(SERVER, 'DB_PASSWORD')     # exactly what the application container presents (no .env parsing)
# NOTE: inside the official postgres image 127.0.0.1 is `trust` (pg_hba), so a login over loopback proves nothing about the password.
# The login is therefore made to the container's own network address (pg_hba: host all all all scram-sha-256) and a WRONG password must be rejected.
ip = '' if a.skip_login else run(['docker', 'inspect', '-f', '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}', C]).split()[0]
p = None if a.skip_login else run(['docker', 'exec', '-e', 'PGPASSWORD', C, 'psql', '-X', '-h', ip, '-U', 'immich', '-d', DB, '-Atc', "SELECT current_user, version() LIKE '%16.16%'"], env=dict(os.environ, PGPASSWORD=pw), check=False)
bad = None if a.skip_login else run(['docker', 'exec', '-e', 'PGPASSWORD', C, 'psql', '-X', '-h', ip, '-U', 'immich', '-d', DB, '-Atc', 'SELECT 1'], env=dict(os.environ, PGPASSWORD=pw + 'x-wrong'), check=False)
R.check('V6', 'application role immich logs in over the NETWORK address with the production secret (scram) and a wrong password is rejected', True if p is None else (p.returncode == 0 and p.stdout.strip().startswith('immich|t') and bad.returncode == 2 and 'password authentication failed' in bad.stderr), 'skipped (rehearsal)' if p is None else ('login rc=%d, wrong-password rc=%d' % (p.returncode, bad.returncode)))
rights = pj(C, """SET LOCAL ROLE immich; SELECT json_build_object('tables',(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND has_table_privilege(current_user,c.oid,'SELECT') AND has_table_privilege(current_user,c.oid,'INSERT') AND has_table_privilege(current_user,c.oid,'UPDATE') AND has_table_privilege(current_user,c.oid,'DELETE')),
   'functions_missing',(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND NOT has_function_privilege(current_user,p.oid,'EXECUTE')),
   'super',(SELECT rolsuper FROM pg_roles WHERE rolname='immich'));""")
R.check('V7', 'immich has SELECT/INSERT/UPDATE/DELETE on 72 tables and can execute every public function', rights['tables'] == 72 and rights['functions_missing'] == 0 and not rights['super'], rights)
ix = pj(C, """SELECT json_build_object('invalid',(SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND NOT (i.indisvalid AND i.indisready AND i.indislive)),
   'total',(SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public'),
   'vchordrq',(SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_am am ON am.oid=c.relam WHERE am.amname='vchordrq'));""")
R.check('V8', 'indexes: 254 total, none invalid/not-ready, 2 vchordrq', ix == {'invalid': 0, 'total': 254, 'vchordrq': 2}, ix)
seq = pj(C, "SELECT json_build_object('type',data_type,'last',last_value) FROM pg_sequences WHERE schemaname='public' AND sequencename='naturalearth_countries_tmp_id_seq1';")
R.check('V9', 'identity sequence is bigint and not below the source value', seq['type'] == 'bigint' and seq['last'] >= expect_seq, seq)
cnt = pj(C, """SELECT json_build_object('users',(SELECT count(*) FROM "user"),'assets',(SELECT count(*) FROM asset),'albums',(SELECT count(*) FROM album),'libraries',(SELECT count(*) FROM library),'persons',(SELECT count(*) FROM person),'smart_search',(SELECT count(*) FROM smart_search),'face_search',(SELECT count(*) FROM face_search),'api_keys',(SELECT count(*) FROM api_key));""")
R.check('V10', 'row counts equal the FROZEN SOURCE snapshot (users, assets, albums, libraries, persons, vectors, api keys)', cnt == expect_counts, {k: (cnt[k], expect_counts[k]) for k in cnt if cnt[k] != expect_counts[k]} or 'equal (frozen source snapshot)' if src_rows else 'equal (preflight baseline)')
mig = pj(C, "SELECT json_build_object('n',count(*),'last',max(name)) FROM kysely_migrations;")
R.check('V11', 'kysely_migrations equals the source (101, same last migration)', mig == base['migrations'], mig)
R.check('V12', 'system-config JSON is byte-identical to the source', pj(C, "SELECT json_build_object('h',encode(sha256(convert_to((value::jsonb)::text,'UTF8')),'hex')) FROM system_metadata WHERE key='system-config';")['h'] == base['sys_config_sha256'])
# ---------------- vectors: index must be used and agree with the exact scan
for table, key, idx in [('smart_search', 'assetId', 'clip_index'), ('face_search', 'faceId', 'face_index')]:
    dims = pj(C, "SELECT COALESCE(json_agg(DISTINCT vector_dims(embedding)),'[]') FROM public.%s;" % table)
    nulls = int(psql(C, "SELECT count(*) FROM public.%s WHERE embedding IS NULL;" % table))
    R.check('W1-' + idx, '%s: all embeddings are vector(512), none NULL' % table, dims == [512] and nulls == 0, 'dims=%s nulls=%d' % (dims, nulls))
    ids = [r for r in psql(C, 'SELECT "%s"::text FROM public.%s WHERE embedding IS NOT NULL AND vector_norm(embedding)>0 ORDER BY md5("%s"::text) LIMIT %d;' % (key, table, key, a.samples)).splitlines() if re.fullmatch('[0-9a-f-]{36}', r)]
    rec, ms, used = [], [], True
    for i, ident in enumerate(ids):
        expr = "(SELECT embedding FROM public.%s WHERE \"%s\"='%s'::uuid)" % (table, key, ident)
        q = 'SELECT "%s"::text FROM public.%s ORDER BY embedding <=> %s LIMIT 10' % (key, table, expr)
        ann_set = 'SET LOCAL vchordrq.probes=1; SET LOCAL enable_seqscan=off; '
        exa_set = 'SET LOCAL vchordrq.probes=1; SET LOCAL enable_indexscan=off; SET LOCAL enable_indexonlyscan=off; SET LOCAL enable_bitmapscan=off; SET LOCAL enable_seqscan=on; '
        plan = json.loads(psql(C, ann_set + 'EXPLAIN (ANALYZE, FORMAT JSON) ' + q + ';'))
        ms.append(plan[0]['Execution Time']); used &= idx in json.dumps(plan)
        ann, exa = set(psql(C, ann_set + q + ';').splitlines()), set(psql(C, exa_set + q + ';').splitlines())
        rec.append(len(ann & exa) / 10)
    R.check('W2-' + idx, '%s: planner uses the index for %d sample queries' % (idx, len(ids)), len(ids) == a.samples and used)
    R.check('W3-' + idx, '%s: recall@10 vs exact scan: mean >= %.2f and min >= %.2f (PROPOSED thresholds)' % (idx, a.min_recall_mean, a.min_recall_min), bool(rec) and statistics.mean(rec) >= a.min_recall_mean and min(rec) >= a.min_recall_min, 'mean=%.3f min=%.2f' % (statistics.mean(rec), min(rec)) if rec else 'no samples')
    warm = ms[1:]      # the first query after a restore/clone is cold (page cache, index prewarm); it is reported but not judged
    R.check('W4-' + idx, '%s: ANN execution time of warm queries (all but the first) max <= %.0f ms (PROPOSED)' % (idx, a.max_ann_ms), bool(warm) and max(warm) <= a.max_ann_ms, 'cold first=%.1f ms, warm median=%.1f max=%.1f ms' % (ms[0], statistics.median(warm), max(warm)) if warm else '')
if a.amcheck:
    t = "BEGIN; SET LOCAL statement_timeout='900s'; CREATE EXTENSION amcheck; SELECT json_build_object('btree',(SELECT count(*) FROM (SELECT bt_index_check(c.oid,true) FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_am am ON am.oid=c.relam WHERE n.nspname='public' AND am.amname='btree' AND c.relpersistence<>'t') x),'heap_bad',(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN LATERAL verify_heapam(c.oid,check_toast=>true) WHERE n.nspname='public' AND c.relkind='r')); ROLLBACK;"
    r = json.loads(run(['docker', 'exec', '-i', C, 'psql', '-XqAt', '-U', 'postgres', '-d', DB, '-v', 'ON_ERROR_STOP=1'], input=t, timeout=1500).splitlines()[0])
    R.check('X1', 'amcheck (rolled-back extension): 243 btree indexes checked, 0 heap corruptions', r['heap_bad'] == 0 and r['btree'] >= 240, r)
    R.check('X2', 'amcheck extension did not remain installed', int(psql(C, "SELECT count(*) FROM pg_extension WHERE extname='amcheck';")) == 0)
sys.exit(R.finish(evidence_dir()))
