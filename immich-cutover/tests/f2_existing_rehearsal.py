"""Real PG16.16 isolated F2 rehearsal; synthetic data/secrets only, no production mounts.
Creates only immich-apptest-* containers on a private internal network. Leaves evidence.
"""
import datetime,gzip,hashlib,json,os
from pathlib import Path
import subprocess,sys,tempfile,time
CV=Path(__file__).resolve().parents[1]
root=Path(tempfile.mkdtemp(prefix='immich-apptest-f2-'))
case=root.name
names={k:case+'-'+k for k in ('db','server','source')};network=case+'-net'
results=[];created=[]
image='immich-db-local:16.16-bookworm-vector0.8.2-vchord1.1.1'
pw='synthetic-F2-$-quote-test'
for n in ('data','backups','app','home','old'): (root/n).mkdir(mode=0o700)
ev=root/'backups/immich-cutover-isolatedf2';ev.mkdir(mode=0o700)
env=dict(os.environ,CUTOVER_REHEARSAL='1',CUTOVER_ID='isolatedf2',EV=str(ev),PG_SRC=names['source'],PG_NEW=names['db'],SRV=names['server'],MOPS='',BRG='',
 REHEARSAL_SRC_CONTAINER=names['source'],REHEARSAL_DB_CONTAINER=names['db'],REHEARSAL_SERVER_CONTAINER=names['server'],
 REHEARSAL_REDIS_CONTAINER=case+'-redis',REHEARSAL_ML_CONTAINER=case+'-ml',REHEARSAL_NETWORK=network,
 CUTOVER_AUDIT=str(root/'audit.jsonl'),PYTHONDONTWRITEBYTECODE='1')
for k in ('CUTOVER_APPROVED','LB_BACKUP_ONLY_APPROVED'):env.pop(k,None)
os.environ.update(env)
sys.path.insert(0,str(CV));import prepare_existing_target as f2,cutstate,db_snapshot,write_probe,cutlib

def run(args,**kw):
    # Setup/teardown also gets the rehearsal guard. No production names/paths.
    cutlib.guard(args)
    p = subprocess.run(args,text=True,capture_output=True,**kw)
    if p.returncode:
        (root/'setup-error.txt').write_text(p.stderr)
        raise RuntimeError('isolated setup command failed; stderr in setup-error.txt')
    return p
def record(name,ok):
    results.append(dict(name=name,ok=bool(ok)));print(('PASS ' if ok else 'FAIL ')+name,flush=True)
    (root/'results.json').write_text(json.dumps(results,indent=1))
    if not ok:raise RuntimeError('rehearsal assertion failed: '+name)
def sql(text,db='postgres'):
    return run(['docker','exec','-i',names['db'],'psql','-XqAt','-U','postgres','-d',db,'-v','ON_ERROR_STOP=1'],input=text).stdout.strip()
def shell(context,label,success):
    # A separate isolated EV per test; production journal is never an argument.
    local_ev=root/'backups'/('immich-cutover-'+label);local_ev.mkdir(mode=0o700)
    (local_ev/'local-backup').mkdir(mode=0o700)
    for rel in ('CUTOVER_ID','local-backup/cutover-id','local-backup/app-backup.sha256'):
        (local_ev/rel).write_bytes((ev/rel).read_bytes())
    p2=dict(policy,ev=str(local_ev));pp=root/('policy-'+label+'.json');pp.write_text(json.dumps(p2,indent=1))
    env2=dict(env,EV=str(local_ev),CV=str(CV),F2_EXISTING_POLICY=str(pp))
    call={'direct':'s_prepare_existing_target; rc=$?', 'if':'if s_prepare_existing_target; then rc=0; else rc=$?; fi',
          'and':'s_prepare_existing_target && true; rc=$?', 'or':'s_prepare_existing_target || rc=$?; rc=${rc:-0}',
          'not':'if ! s_prepare_existing_target; then rc=1; else rc=0; fi'}[context]
    proc=subprocess.run(['/bin/bash','--noprofile','--norc','-c','source "$CV/steps.sh" || exit 91\n'+call+'\nprintf "CALL_RC=%s\\n" "$rc"\n'],env=env2,capture_output=True,text=True)
    (root/(label+'.out')).write_text(proc.stdout+proc.stderr)
    state=cutstate.load(local_ev)[0]
    record(label, (proc.returncode==0 and 'CALL_RC=0' in proc.stdout and state=='PREPARED') if success else ('CALL_RC=0' not in proc.stdout and state=='NONE'))
    return local_ev

try:
    run(['docker','network','create','--internal',network])
    run(['docker','run','-d','--pull','never','--name',names['db'],'--network',network,'--restart','no','--memory','768m','--cpus','1',
         '--mount','type=bind,src='+str(root/'data')+',dst=/var/lib/postgresql/data',
         '--mount','type=bind,src='+str(root/'backups')+',dst=/backups',
         '-e','POSTGRES_PASSWORD=synthetic-superuser','-e','POSTGRES_HOST_AUTH_METHOD=scram-sha-256',
         '-e','POSTGRES_INITDB_ARGS=--encoding=UTF8 --locale=en_US.utf8',
         '--health-cmd','pg_isready -U postgres -d postgres','--health-interval','1s','--health-retries','90',
         image,'postgres','-c','shared_preload_libraries=vchord','-c','shared_buffers=64MB'])
    created.append(names['db'])
    for k in ('source','server'):
        run(['docker','run','-d','--pull','never','--name',names[k],'--network',network,'--restart','no','--memory','64m',
             '--health-cmd','true','--health-interval','1s','--entrypoint','sleep',
             '-e','DB_HOSTNAME='+names['source'],'-e','DB_DATABASE_NAME=immich','-e','DB_USERNAME=immich','-e','DB_PASSWORD='+pw,
             image,'infinity'])
        created.append(names[k])
    for _ in range(90):
        if all(f2.inspect(n)['State'].get('Health',{}).get('Status')=='healthy' for n in created):break
        time.sleep(1)
    record('isolated containers healthy',all(f2.inspect(n)['State'].get('Health',{}).get('Status')=='healthy' for n in created))
    # Fixture DDL belongs solely to the temporary synthetic cluster, never F2 itself.
    sql("CREATE ROLE immich LOGIN INHERIT PASSWORD '"+pw+"'; CREATE DATABASE immich OWNER immich TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'en_US.utf8' LC_CTYPE 'en_US.utf8';")
    sql(';'.join('CREATE EXTENSION "'+n+'"' for n in ('cube','earthdistance','pg_trgm','unaccent','uuid-ossp','vector','vchord'))+';',db='immich')
    sql(';'.join('CREATE TABLE public.t%02d(id integer primary key, value text); ALTER TABLE public.t%02d OWNER TO immich; INSERT INTO public.t%02d VALUES (1,\'synthetic\')'%(i,i,i) for i in range(72))+';',db='immich')
    sql("CREATE SEQUENCE public.fixture_seq AS bigint; ALTER SEQUENCE public.fixture_seq OWNER TO immich; SELECT nextval('public.fixture_seq');",db='immich')
    before_id=f2.db_identity(names['db'],'immich')
    db_snapshot.snapshot(names['db'],root/'before-snapshot')
    write_probe.capture(names['db'],'immich',root/'before-probe.json')
    archive='immich_failed_isolatedf2_'
    sql('ALTER DATABASE immich RENAME TO '+archive+"; CREATE DATABASE immich OWNER immich TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'en_US.utf8' LC_CTYPE 'en_US.utf8';")
    cutstate.set_state(root/'old',['NONE'],'ROLLED_BACK','synthetic previous attempt')
    home=root/'home/isolatedf2';(home/'app-backup').mkdir(parents=True,mode=0o700)
    filename='immich-db-backup-isolated-v3.3.5-pg16.16.sql.gz';backup=root/'app'/filename
    with gzip.open(backup,'wb') as f:f.write(b'-- synthetic application backup\n')
    (home/'app-backup'/filename).write_bytes(backup.read_bytes())
    manifest=f2.digest(backup)+'  '+filename+'\n'
    (ev/'local-backup').mkdir(mode=0o700)
    for f in (ev/'CUTOVER_ID',ev/'local-backup/cutover-id',home/'CUTOVER_ID'):f.write_text('isolatedf2\n')
    for f in (ev/'local-backup/app-backup.sha256',home/'app-backup/SHA256SUMS'):f.write_text(manifest)
    # Let PostgreSQL's stats collector settle before comparing the no-write probe.
    time.sleep(1)
    write_probe.capture(names['db'],archive,root/'before-probe.json')
    config=root/'configuration.marker';config.write_text('unchanged synthetic config\n')
    policy=dict(id='isolatedf2',ev=str(ev),prev_ev=str(root/'old'),prev_tip=cutstate.load(root/'old')[1],prev_entries=1,
                home=str(home),app_backups=str(root/'app'),target=names['db'],source=names['source'],server=names['server'],network=network,
                archive=archive,archive_identity=before_id,new_identity=f2.db_identity(names['db'],'immich'),
                role=dict(oid=sql("SELECT oid FROM pg_roles WHERE rolname='immich'"),login=True,inherit=True,super=False,createdb=False,createrole=False,repl=False,bypass=False,memberships=0,scram=True),
                containers={n:f2.signature(f2.inspect(n)) for n in created},protected={str(config):f2.digest(config)},archive_snapshot=str(root/'before-snapshot'),archive_probe=str(root/'before-probe.json'))
    (root/'policy.json').write_text(json.dumps(policy,indent=1))
    for context in ('direct','if','and','or','not'):shell(context,'positive-'+context,True)
    sql('ALTER ROLE immich CREATEDB');shell('if','negative-role',False);sql('ALTER ROLE immich NOCREATEDB')
    sql('CREATE TABLE contamination(id integer)',db='immich');shell('and','negative-not-empty',False);sql('DROP TABLE contamination',db='immich')
    sql("CREATE TYPE contamination AS ENUM ('x')",db='immich');shell('if','negative-extra-type',False);sql('DROP TYPE contamination',db='immich')
    sql('REVOKE CREATE ON SCHEMA public FROM pg_database_owner',db='immich');shell('or','negative-rights',False);sql('GRANT CREATE ON SCHEMA public TO pg_database_owner',db='immich')
    sql('ALTER DATABASE immich OWNER TO postgres');shell('not','negative-owner',False);sql('ALTER DATABASE immich OWNER TO immich')
    config.write_text('changed');shell('if','negative-config',False);config.write_text('unchanged synthetic config\n')
    original=(home/'app-backup/SHA256SUMS').read_text();(home/'app-backup/SHA256SUMS').write_text('invalid\n');shell('or','negative-F0',False);(home/'app-backup/SHA256SUMS').write_text(original)
    # A genuine archive write must HALT, even if all identity/role checks still pass.
    sql("UPDATE t00 SET value='changed'",db=archive);shell('if','negative-archive-write',False)
    record('base isolated EV remains NONE',cutstate.load(ev)[0]=='NONE')
    record('no production approval token','CUTOVER_APPROVED' not in os.environ)
    record('all Docker audit resources isolated',all(not any(a in cutlib.PROD_NAMES for a in json.loads(line)['argv']) for line in (root/'audit.jsonl').read_text().splitlines()))
finally:
    for n in reversed(created):run(['docker','rm','-f',n])
    run(['docker','network','rm',network])
    print('EVIDENCE '+str(root),flush=True)
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(str(root))
print('RESULT',sum(x['ok'] for x in results),'/',len(results))
