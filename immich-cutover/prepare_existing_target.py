"""F2 for an already-created role/database: READ ONLY SQL, then one gated journal append.
Never starts a container, creates a role/database/extension or changes a password.
Production policy is pinned to the reviewed second-attempt evidence. No receipt replay.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cutlib as cl
import cutstate
import db_snapshot
import write_probe

HERE = Path(__file__).resolve().parent
PROD_POLICY = HERE / 'policies/f2-20261115t150714z.json'


def require(ok, name):
    if ok is not True:
        raise RuntimeError('HALT: ' + name)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def canonical_mounts(mounts):
    # Preserve every field, duplicates and nested values; ignore list order only.
    return sorted(json.dumps(m, sort_keys=True, separators=(',', ':')) for m in mounts)


def signature(c):
    return dict(id=c['Id'], started=c['State']['StartedAt'], restarts=c['RestartCount'],
                running=c['State']['Running'], mounts=canonical_mounts(c['Mounts']),
                networks=sorted(c['NetworkSettings']['Networks']),
                config_hash=hashlib.sha256(json.dumps(c['Config'], sort_keys=True).encode()).hexdigest())


def inspect(name):
    return json.loads(cl.run(['docker', 'inspect', name]))[0]


def real_path(p):
    p = Path(p)
    require(p.is_absolute() and p.exists() and p.resolve() == p, 'missing/noncanonical path')
    require(not any(x.is_symlink() for x in [p, *p.parents]), 'symlink path')
    return p


def read_json(path):
    return json.loads(real_path(path).read_text())


def db_identity(container, name):
    require(re.fullmatch(r'[A-Za-z0-9_]+', name) is not None, 'database identifier')
    return cl.pj(container, "SELECT json_build_object('oid',oid,'owner',pg_get_userbyid(datdba),"
                 "'acl',datacl::text,'encoding',pg_encoding_to_char(encoding),"
                 "'collate',datcollate,'ctype',datctype) FROM pg_database WHERE datname='%s';" % name, db='postgres')


def empty_database(container):
    return cl.pj(container, """SELECT json_build_object(
      'relations',(SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'),
      'functions',(SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
         WHERE n.nspname NOT IN ('pg_catalog','information_schema')),
      'schemas',(SELECT json_agg(nspname ORDER BY nspname) FROM pg_namespace
         WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema'),
      'extensions',(SELECT json_object_agg(extname,extversion) FROM pg_extension),
      'extra_objects',((SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace
         WHERE n.nspname NOT LIKE 'pg_%' AND n.nspname<>'information_schema') +
       (SELECT count(*) FROM pg_collation c JOIN pg_namespace n ON n.oid=c.collnamespace WHERE n.nspname NOT LIKE 'pg_%') +
       (SELECT count(*) FROM pg_conversion c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname NOT LIKE 'pg_%') +
       (SELECT count(*) FROM pg_operator o JOIN pg_namespace n ON n.oid=o.oprnamespace WHERE n.nspname NOT LIKE 'pg_%') +
       (SELECT count(*) FROM pg_foreign_server) + (SELECT count(*) FROM pg_event_trigger) + (SELECT count(*) FROM pg_default_acl)));
""")


def check_empty(value):
    require(isinstance(value,dict) and type(value.get('relations')) is int and type(value.get('functions')) is int and type(value.get('extra_objects')) is int and value == dict(relations=0, functions=0, schemas=['public'], extensions={'plpgsql': '1.0'}, extra_objects=0), 'target not empty template0 database')


def check_role(value, expected):
    require(value == expected and value['login'] is True and value['inherit'] is True
            and all(value[k] is False for k in ('super','createdb','createrole','repl','bypass'))
            and type(value['memberships']) is int and value['memberships'] == 0 and value['scram'] is True, 'role identity/privileges/SCRAM verifier')


def check_login(good, bad):
    require(good.returncode == 0 and good.stdout.strip() == 'immich', 'positive SCRAM login')
    require(bad.returncode == 2 and 'password authentication failed' in bad.stderr, 'negative SCRAM control inconclusive/accepted')


def check_rights(value):
    require(isinstance(value,dict) and all(type(value.get(k)) is bool for k in ('connect','create','temp','usage','schema_create')) and value == dict(connect=True, create=True, temp=True, usage=True, schema_create=True,
                          schema_owner='pg_database_owner'), 'effective database/schema rights')


def check_platform(value):
    require(value['version'] == '160016' and type(value['postgis']) is int and value['postgis'] == 0 and value['encryption'] == 'scram-sha-256'
            and 'vchord' in value['preload'].split(',') and value['available'] == cl.EXPECTED_EXT,
            'PG16.16/extensions/preload/password encryption')
    rules = value['hba']
    require(isinstance(rules, list) and bool(rules), 'HBA rules missing')
    hosts = [r for r in rules if r['type'].startswith('host')]
    require(any(r['address'] == 'all' and r['auth_method'] == 'scram-sha-256' for r in hosts)
            and all(r['auth_method'] == 'scram-sha-256' or r['address'] in ('127.0.0.1','::1') for r in hosts)
            and all(r['error'] is None for r in rules), 'network HBA not SCRAM')


def backup_verify(p):
    # lb_verify alone tolerates absent manifests. Demand the F0 pair first.
    ev, home = Path(p['ev']), Path(p['home'])
    for f in (ev/'CUTOVER_ID', ev/'local-backup/cutover-id', home/'CUTOVER_ID'):
        require(real_path(f).read_text() == p['id'] + '\n', 'F0 identity')
    a, b = ev/'local-backup/app-backup.sha256', home/'app-backup/SHA256SUMS'
    manifest = real_path(a).read_text()
    require(manifest == real_path(b).read_text() and re.fullmatch(r'[0-9a-f]{64}  immich-db-backup-[A-Za-z0-9._-]+\.sql\.gz\n', manifest) is not None, 'F0 manifests')
    name = manifest.split()[1]
    original = real_path(Path(p['app_backups'])/name)
    require(0 <= datetime.datetime.now().timestamp()-original.stat().st_mtime < 26*3600, 'F0 age >=26h or future')
    # Pass paths as positional arguments, never interpolate shell text; no approval token.
    env = dict(os.environ)
    for k in ('CUTOVER_APPROVED','LB_BACKUP_ONLY_APPROVED','LB_TEST','LB_MDSTAT'):
        env.pop(k, None)
    env.update(CUTOVER_ID=p['id'], EV=p['ev'], LB_ROOT=str(home.parent), IMMICH_BACKUPS=p['app_backups'])
    cl.run(['/bin/bash','--noprofile','--norc','-c',
            'source "$1/local_backup.sh" || exit "$?"; lb_verify || exit "$?"', 'f2-f0', str(HERE)], env=env, timeout=600)
    cl.run(['gzip','-t',str(original)], timeout=300)
    cl.run(['gzip','-t',str(real_path(home/'app-backup'/name))], timeout=300)


def validate(p, out, emit=print):
    def passed(name):
        emit('PASS ' + name)
    require(os.environ.get('CUTOVER_ID') == p['id'] and os.environ.get('EV') == p['ev'], 'attempt identity')
    require(cl.TARGET == p['target'] and cl.SERVER == p['server'] and cl.SOURCE == p['source'], 'container profile')
    for path in (p['ev'], p['prev_ev'], p['home']): real_path(path)
    require(cutstate.load(p['ev'])[0] == 'NONE', 'journal must be NONE')
    previous = cutstate.load(p['prev_ev'])
    require(previous[0] == 'ROLLED_BACK' and previous[1] == p['prev_tip'] and len(previous[2]) == p['prev_entries'], 'previous ROLLED_BACK chain')
    require(not (Path(p['ev'])/'T_open').exists(), 'T_open present')
    for path, h in p['protected'].items():
        require(digest(real_path(path)) == h, 'protected evidence/configuration changed')
    passed('identity, journals, immutable evidence/configuration')
    backup_verify(p); passed('F0 lb_verify, age, gzip and identity')
    observed = {}
    for name, expected in p['containers'].items():
        c = inspect(name); observed[name] = c
        require(signature(c) == expected and c['State']['Running'] is True
                and c['State'].get('Health',{}).get('Status','none') in ('healthy','none'), 'container configuration/health changed: '+name)
    server_env = observed[p['server']]['Config']['Env']
    require('DB_HOSTNAME='+p['source'] in server_env and 'DB_DATABASE_NAME=immich' in server_env
            and 'DB_USERNAME=immich' in server_env, 'production server source configuration')
    target = observed[p['target']]
    require(target['HostConfig']['PortBindings'] in ({}, None) and not target['NetworkSettings']['Ports'].get('5432/tcp'), 'target published ports')
    networks = target['NetworkSettings']['Networks']
    require(list(networks) == [p['network']] and bool(networks[p['network']]['IPAddress']), 'target network')
    passed('containers, canonical mounts, network, source configuration, Redis identity')
    platform = cl.pj(p['target'], """SELECT json_build_object('version',current_setting('server_version_num'),
      'postgis',(SELECT count(*) FROM pg_available_extensions WHERE name ILIKE 'postgis%'),
      'encryption',current_setting('password_encryption'),'preload',current_setting('shared_preload_libraries'),
      'available',(SELECT json_object_agg(name,default_version) FROM pg_available_extensions WHERE name IN
       ('plpgsql','cube','earthdistance','pg_trgm','unaccent','uuid-ossp','vector','vchord')),
      'hba',(SELECT json_agg(x) FROM (SELECT type,address,auth_method,error FROM pg_hba_file_rules ORDER BY rule_number) x));""", db='postgres')
    check_platform(platform); passed('PG16.16, available extensions, no PostGIS, SCRAM HBA/preload')
    role = cl.pj(p['target'], """SELECT json_build_object('oid',oid,'login',rolcanlogin,'inherit',rolinherit,
      'super',rolsuper,'createdb',rolcreatedb,'createrole',rolcreaterole,'repl',rolreplication,'bypass',rolbypassrls,
      'memberships',(SELECT count(*) FROM pg_auth_members WHERE member=r.oid),
      'scram',COALESCE(rolpassword LIKE 'SCRAM-SHA-256$%',false)) FROM pg_authid r WHERE rolname='immich';""", db='postgres')
    check_role(role, p['role']); passed('existing role identity, no escalation, SCRAM verifier')
    require(db_identity(p['target'],'immich') == p['new_identity'], 'new database OID/owner/ACL/encoding/locale')
    require(p['new_identity']['owner'] == 'immich' and p['new_identity']['encoding'] == 'UTF8'
            and p['new_identity']['collate'] == p['new_identity']['ctype'] == 'en_US.utf8'
            and p['new_identity']['oid'] != p['archive_identity']['oid'], 'database owner/locale/identity')
    check_empty(empty_database(p['target']))
    rights = cl.pj(p['target'], """SET LOCAL ROLE immich; SELECT json_build_object(
       'connect',has_database_privilege('immich','immich','CONNECT'),
       'create',has_database_privilege('immich','immich','CREATE'),
       'temp',has_database_privilege('immich','immich','TEMP'),
       'usage',has_schema_privilege('immich','public','USAGE'),
       'schema_create',has_schema_privilege('immich','public','CREATE'),
       'schema_owner',(SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname='public'));""")
    check_rights(rights); passed('empty template0 target, exact identity, effective rights')
    pw = cl.container_env(p['server'],'DB_PASSWORD')
    require(isinstance(pw,str) and bool(pw), 'empty application secret')
    args = ['docker','exec','-e','PGPASSWORD',p['target'],'psql','-XqAt','-h',networks[p['network']]['IPAddress'],
            '-U','immich','-d','immich','-v','ON_ERROR_STOP=1','-c','BEGIN READ ONLY; SELECT current_user; ROLLBACK;']
    good = cl.run(args, env=dict(os.environ,PGPASSWORD=pw),check=False)
    bad = cl.run(args, env=dict(os.environ,PGPASSWORD=pw+'x-wrong-control'),check=False)
    check_login(good,bad); del pw; passed('network SCRAM positive rc0 / negative rc2 auth failure')
    require(db_identity(p['target'],p['archive']) == p['archive_identity'], 'archive identity/ACL/locale')
    db_snapshot.snapshot(p['target'],out/'archive-snapshot',db=p['archive'])
    for name in ('metadata.json','tables.json','sequences.json'):
        require(read_json(out/'archive-snapshot'/name) == read_json(Path(p['archive_snapshot'])/name), 'archive content/metadata/sequence changed')
    write_probe.capture(p['target'],p['archive'],out/'archive-probe.json')
    require(write_probe.check(p['archive_probe'],str(out/'archive-probe.json'),set())['status'] == 'PASS', 'archive writes/restart/stat reset')
    passed('archive full snapshot and strict no-write evidence')
    # Re-read the live boundaries immediately before returning to journal commit.
    check_empty(empty_database(p['target']))
    require(cl.pj(p['target'],"SELECT to_json(count(*)) FROM pg_stat_activity WHERE datname IN ('immich','%s') AND pid<>pg_backend_pid();" % p['archive'],db='postgres') == 0, 'unexpected target/archive clients')
    for name, expected in p['containers'].items():
        require(signature(inspect(name)) == expected, 'container changed during F2')
    for path,h in p['protected'].items(): require(digest(real_path(path)) == h, 'protected file changed during F2')
    require(cutstate.load(p['ev'])[0] == 'NONE', 'journal changed during checks')
    passed('final emptiness, zero clients, configuration/evidence and journal recheck')


def authorize(p, prepare):
    if cl.REHEARSAL:
        require(all(p[k].startswith('immich-apptest-') for k in ('target','source','server','network')), 'isolated names')
        for k in ('ev','prev_ev','home','app_backups','archive_snapshot','archive_probe'):
            require(str(real_path(p[k])).startswith('/tmp/immich-apptest-'), 'isolated paths')
        for path in p['protected']: require(str(real_path(path)).startswith('/tmp/immich-apptest-'), 'isolated protected path')
        require(all(n.startswith('immich-apptest-') for n in p['containers']), 'isolated container signature')
    elif prepare:
        require(os.environ.get('CUTOVER_APPROVED') == p['id'], 'F2 needs separate production approval')


def execute(p, out, prepare, validator=validate, journal=cutstate.set_state):
    authorize(p, prepare)
    validator(p, out)
    # A fresh durable check receipt is written BEFORE the journal, never replayed.
    with (out/'checks.json').open('x') as f:
        json.dump(dict(status='CHECKS_PASSED',cutover_id=p['id'],requested_prepare=prepare,
                       utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),f,indent=1)
        f.flush(); os.fchmod(f.fileno(),0o600); os.fsync(f.fileno())
    directory = os.open(out,os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(directory)
    finally: os.close(directory)
    if prepare:
        require(cutstate.load(p['ev'])[0] == 'NONE', 'journal before commit')
        require(journal(p['ev'], ['NONE'], 'PREPARED', 'existing role/database verified; no DDL') == 0, 'PREPARED write failed')
        require(cutstate.load(p['ev'])[0] == 'PREPARED', 'PREPARED readback failed')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--policy',type=Path,default=PROD_POLICY)
    ap.add_argument('--prepare',action='store_true',help='requires separate approval; writes PREPARED only after live validation')
    a = ap.parse_args()
    try:
        if not cl.REHEARSAL: require(a.policy.resolve() == PROD_POLICY.resolve(), 'production policy override refused')
        p = read_json(a.policy)
        authorize(p,a.prepare)  # reject before creating evidence
        out = Path(tempfile.mkdtemp(prefix='f2-existing-',dir=real_path(p['ev'])))
        os.chmod(out,0o700)
        execute(p,out,a.prepare)
        print('F2 existing target PASS; '+('PREPARED' if a.prepare else 'read-only validation'))
        return 0
    except Exception as e:
        # Never echo subprocess output or args: errors may originate in secret loading.
        print(str(e) if isinstance(e,RuntimeError) and str(e).startswith('HALT:') else 'HALT: evidence/SQL/Docker/validation failure',file=sys.stderr)
        return 1

if __name__ == '__main__': sys.exit(main())
