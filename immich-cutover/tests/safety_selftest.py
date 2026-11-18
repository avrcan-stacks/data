"""Offline fault injection: real step functions + real journal, mocked external operations.
No Docker executable is called. Each scenario has a fresh /tmp fixture.
"""
import copy, json, os, pathlib, shlex, subprocess, sys, tempfile
CV = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CV))
import api_checks, cutstate

sample = {'version': 'v3.3.5', 'server_statistics': dict(photos=1, videos=0, usage=1, usagePhotos=1, usageVideos=0, usage_by_user=[[1, 0, 1]]),
          'libraries': [[str(i), 1] for i in range(8)],
          'queues': {str(i): dict(active=0, waiting=0, delayed=0, failed=0, paused=0, isPaused=True) for i in range(19)},
          'albums': {'count': 1, 'asset_counts': [1]}, 'people': {'total': 1, 'hidden': 0},
          'smart': {q: dict(ids=['test-id'], cold_ms=1, warm_ms=[1]*4) for q in api_checks.SMART_QUERIES}}
receipt = dict(name='api-verify', status='PASS', fail=0, warn=0,
               items=[dict(id='Q%d'%i, status='PASS') for i in range(1, 11)], sample=sample)
results = []
def record(name, good, detail=''):
    results.append(dict(name=name, ok=bool(good), detail=detail))
    print(('PASS ' if good else 'FAIL ') + name, flush=True)

MOCKS = r'''
export CUTOVER_REHEARSAL=1 CUTOVER_ID=testhardening PG_SRC=immich-apptest-src PG_NEW=immich-apptest-db SRV=immich-apptest-server
export MOPS=immich-apptest-mops BRG=immich-apptest-brg
export REHEARSAL_SRC_CONTAINER=$PG_SRC REHEARSAL_DB_CONTAINER=$PG_NEW REHEARSAL_SERVER_CONTAINER=$SRV
export REHEARSAL_REDIS_CONTAINER=immich-apptest-redis REHEARSAL_ML_CONTAINER=immich-apptest-ml REHEARSAL_NETWORK=immich-apptest-net
export IMMICH_ADMIN_API_KEY=synthetic-admin IMMICH_USER_API_KEY=synthetic-user
export IMMICH_ENV_FILE=$EV/env EVROOT=${EV%/*} HEALTH_TIMEOUT=1 DUMP_MIN_BYTES=1 DUMP_MAX_BYTES=500000000
export BR=immich-apptest-bridge WB=$EV/bridge-work PREV_EV=$EV/previous
export CUTOVER_MANUAL_DECISION=FORWARD:$CUTOVER_ID
if [ "$STEP" = s_manual_rollback_accept_loss ]; then export CUTOVER_MANUAL_DECISION=ROLLBACK_ACCEPT_LOSS:$CUTOVER_ID; fi
source "$CV/steps.sh"
# Completely replace Docker after sourcing the rehearsal wrapper. No production token.
operation() { printf '%s\n' "$1" >> "$EV/operations"; [ "$FAIL" != "$1" ]; }
python3() {
  local args=" $* " result='' previous='' a
  case "$args" in
    *cutstate.py*)
      if [[ "$args" == *' set '* ]]; then operation journal || return 71; fi
      command python3 "$@"; return $?;;
    *api_checks.py*' check-result '*) command python3 "$@"; return $?;;
    *api_checks.py*' verify '*)
      operation api || return 72
      for a in "$@"; do [ "$previous" != --result ] || result="$a"; previous="$a"; done
      if [ "$FAIL" = api-invalid ]; then printf 'garbage' > "$result"
      elif [ "$FAIL" != api-empty ]; then cp "$EV/receipt" "$result"; fi
      return 0;;
    *api_checks.py*' baseline '*) operation baseline || return 73; cp "$EV/sample" "$EV/api-baseline.json"; return $?;;
    *api_checks.py*' queues '*) operation queues || return 74; return 0;;
    *db_snapshot.py*' snapshot '*) operation snapshot || return 75
      for a in "$@"; do [ "$previous" != --out ] || result="$a"; previous="$a"; done
      mkdir -p "$result"; for a in metadata tables sequences; do printf '{}' > "$result/$a.json"; done
      return 0;;
    *db_snapshot.py*' compare '*) operation compare || return 76; return 0;;
    *db_snapshot.py*' delta '*) operation delta || return 77; printf '{"status":"PASS"}'; return 0;;
    *validate_target.py*) operation validator || return 78; return 0;;
    *write_probe.py*) operation probe || return 79; return 0;;
    *getsecret.py*) operation secret || return 80; printf 'synthetic-password'; return 0;;
    *) command python3 "$@";;
  esac
}
docker() {
  local args=" $* "
  case "$1" in
    stop) operation stop || return 81; printf false > "$EV/running"; return 0;;
    start) operation start || return 82; return 0;;
    inspect)
      operation inspect || return 83
      case "$args" in
        *State.Health.Status*) printf healthy;;
        *State.Running*) cat "$EV/running";;
        *traefik.enable*) cat "$EV/route";;
        *immich.cutover*) printf testhardening;;
        *Mounts*) printf '%s/media' "$EV";;
        *Config.Env*) printf 'DB_HOSTNAME=%s\n' "$(cat "$EV/host")";;
        *) return 84;;
      esac;;
    run) operation bridge-run || return 95;;
    rm) operation remove-bridge || return 96;;
    logs) operation logs || return 85; printf '%s\n' 'Starting api worker' 'No schema drift detected' 'Finished running migrations' 'targetLists=1, current=1 for clip_index' 'targetLists=1, current=1 for face_index';;
    exec)
      case "$args" in
        *pg_dump*) operation dump || return 99; printf 'synthetic archive';;
        *pg_restore*) operation restore || return 86
          if [[ "$args" == *' --list '* ]]; then for ((i=0;i<1002;i++)); do printf 'toc line\n'; done; fi;;
        *sha256sum*) operation hash || return 87; printf '%064d  file\n' 0;;
        *' test '*) operation readable || return 88;;
        *) operation sql || return 89; if [[ "$args" == *'pg_stat_activity'* ]]; then printf 0; else printf 'PUBLIC|CONNECT\n'; fi;;
      esac;;
    *) operation unexpected-docker; return 99;;
  esac
}
idcf() { operation frozen-recreate || return 97; printf immich-apptest-src > "$EV/host"; }
idcd() { operation dark-recreate || return 90; }
idc() { operation recreate || return 91; printf true > "$EV/route"; printf "$PG_SRC" > "$EV/host"; printf true > "$EV/running"; }
_wait_healthy() { operation health || return 98; }
idb_up() { operation prepare || return 92; }
lb_gate_open() { operation gate || return 93; }
lb_verify() { operation backup || return 94; }
if [ "$FAIL" = missing-key ]; then unset IMMICH_ADMIN_API_KEY; fi
'''

contexts = {
    'plain': '{step}; exit $?',
    'if': 'if {step}; then exit 0; else exit $?; fi',
    'and': '{step} && exit 0; exit $?',
    'or': '{step} || exit $?; exit 0',
    'negated': 'if ! {step}; then exit 1; else exit 0; fi',
}
cases = [
    ('s_prepare_target','NONE','prepare'),
    *[('s_dump_source','FROZEN',f) for f in ('snapshot','probe','dump','journal')],
    ('s_freeze','PREPARED','stop'), ('s_freeze','PREPARED','queues'), ('s_freeze','PREPARED','baseline'),
    ('s_freeze','PREPARED','sql'), ('s_freeze','PREPARED','journal'),
    ('s_bridge_sanitize','DUMPED','dump-sha'), ('s_bridge_sanitize','DUMPED','bridge-run'), ('s_bridge_cleanup','SANITIZED','remove-bridge'),
    ('s_unfence','DARK_VERIFIED','sql'), ('s_target_reset_after_rollback','NONE','sql'),
    ('s_open_abort','OPEN_BEGIN','stop'), ('s_open_abort','OPEN_BEGIN','inspect'), ('s_open_abort','OPEN_BEGIN','journal'),
    ('s_manual_forward','HALT_MANUAL','stop'), ('s_manual_forward','HALT_MANUAL','gate'),
    ('s_manual_rollback_accept_loss','HALT_MANUAL','stop'),
] + [
    ('s_dark_launch', 'VALIDATED', f) for f in ('missing-key','api','api-invalid','api-empty','snapshot','delta','probe','health','dark-recreate','inspect','logs','sql','journal')
] + [
    ('s_restore_target','SANITIZED',f) for f in ('restore','hash','sql','journal')
] + [
    ('s_validate_target','RESTORED',f) for f in ('validator','snapshot','compare','sql','journal')
] + [
    ('s_open','DARK_VERIFIED',f) for f in ('missing-key','gate','missing-seal')
] + [
    ('s_rollback_r1','DARK_VERIFIED',f) for f in ('missing-key','stop','inspect','sql','recreate','health','start','queues','api','api-invalid','journal')
] + [('s_restore_and_validate','SANITIZED','restore'), ('s_restore_and_validate','SANITIZED','validator'),
    ('lb_verify', 'DARK_VERIFIED', 'backup'), ('s_dump_source','FROZEN','none'), ('s_dark_launch','VALIDATED','none'), ('s_open_abort','OPEN_BEGIN','none')]

for step, state, fault in cases:
    for context, pattern in contexts.items():
        with tempfile.TemporaryDirectory(prefix='immich-apptest-unit-') as tmp:
            ev = pathlib.Path(tmp)/'immich-cutover-testhardening'; ev.mkdir()
            if state != 'NONE': cutstate.set_state(ev, ['NONE'], state)
            cutstate.set_state(ev/'previous', ['NONE'], 'ROLLED_BACK')
            (ev/'env').write_text('DB_HOSTNAME=immich-apptest-src\n')
            (ev/'api-baseline.json').write_text(json.dumps(sample))
            (ev/'receipt').write_text(json.dumps(receipt)); (ev/'sample').write_text(json.dumps(sample))
            (ev/'running').write_text('true'); (ev/'route').write_text('false'); (ev/'host').write_text('immich-apptest-db')
            (ev/'source-db-acl.before').write_text('PUBLIC|CONNECT\n')
            (ev/'immich.no-postgis.dump.sha256').write_text('0'*64+'  dump\n')
            (ev/'immich.no-postgis.dump').write_bytes(b'preserve dump')
            (ev/'baseline-fixture.json').write_text('{}')
            from safety_evidence import REQUIRED
            for name in REQUIRED:
                path=ev/name; path.parent.mkdir(exist_ok=True)
                if not path.exists(): path.write_text('{"status":"PASS"}')
            import hashlib
            (ev/'immich.full.dump').write_bytes(b'preserve full dump')
            (ev/'immich.full.dump.sha256').write_text(hashlib.sha256(b'preserve full dump').hexdigest()+'  '+str(ev/'immich.full.dump')+'\n')
            (ev/'media'/'upload').mkdir(parents=True)
            (ev/'T0').write_text('2020-01-01T00:00:00Z')
            (ev/'immich.env.before').write_bytes((ev/'env').read_bytes())
            (ev/'env.before.sha256').write_text(hashlib.sha256((ev/'env').read_bytes()).hexdigest())
            (ev/'marker.dump').write_bytes(b'preserve dump')
            if step=='s_bridge_sanitize':
                (ev/'immich.no-postgis.dump').unlink()
                (ev/'immich.no-postgis.dump.sha256').unlink()
                if fault=='dump-sha': (ev/'immich.full.dump.sha256').write_text('0'*64+'  '+str(ev/'immich.full.dump')+'\n')
            if step=='s_dump_source':
                (ev/'immich.full.dump').unlink(); (ev/'immich.full.dump.sha256').unlink()
            before = (ev/'state.log').read_bytes() if (ev/'state.log').exists() else b''
            env = dict(os.environ, CV=str(CV), EV=str(ev), FAIL=fault, STEP=step)
            env.pop('CUTOVER_APPROVED',None)
            p = subprocess.run(['/bin/bash','--noprofile','--norc','-c', MOCKS+'\n'+pattern.format(step=step)],env=env,capture_output=True,text=True)
            ops = (ev/'operations').read_text().splitlines() if (ev/'operations').exists() else []
            # R1 may already have restored the public SOURCE before late API/journal failure.
            allowed_source = step == 's_rollback_r1' and fault in ('health','start','queues','api','api-invalid','journal')
            route_ok = (ev/'route').read_text() == 'false' or (allowed_source and (ev/'host').read_text() == 'immich-apptest-src')
            good = p.returncode != 0 and ((ev/'state.log').read_bytes() if (ev/'state.log').exists() else b'') == before and route_ok and (ev/'marker.dump').read_bytes() == b'preserve dump' and (step=='s_dump_source' or (ev/'immich.full.dump').read_bytes()==b'preserve full dump') and step+' OK' not in p.stdout
            # Must hit the named fault; missing key intentionally fails before any external op.
            hit = fault == 'missing-key' and 'IMMICH_ADMIN_API_KEY' in p.stderr or fault in ops or fault in ('api-invalid','api-empty') and 'api' in ops
            if step in ('s_open_abort','s_freeze') and fault != 'journal':
                good = p.returncode != 0 and cutstate.load(ev)[0] == ('ABORT_BEGIN' if step=='s_open_abort' else 'FREEZING') and route_ok and step+' OK' not in p.stdout
            if step=='s_restore_and_validate' and fault=='validator':
                good=p.returncode!=0 and cutstate.load(ev)[0]=='RESTORED' and 's_validate_target OK' not in p.stdout and route_ok
            if fault=='dump-sha': hit='FAILED' in p.stdout or 'did NOT match' in p.stderr
            if fault == 'missing-seal': hit = 'complete F8 evidence' in p.stderr
            if fault == 'none':
                hit=True
                if step=='s_dump_source':
                    good=p.returncode==0 and cutstate.load(ev)[0]=='DUMPED' and (ev/'immich.full.dump').read_bytes()==b'synthetic archive'
                elif step=='s_open_abort':
                    good=p.returncode==0 and cutstate.load(ev)[0]=='ABORT_VERIFIED' and (ev/'route').read_text()=='false'
                else: good=p.returncode==0 and cutstate.load(ev)[0]=='DARK_VERIFIED' and (ev/'dark-verified.json').exists() and (ev/'route').read_text()=='false'
            record('%s/%s/%s'%(step,fault,context),good and hit, 'rc=%s ops=%s stderr=%s'%(p.returncode,ops,p.stderr[-350:]))

# Pure data/schema/receipt tests: malformed values may never pass with exit zero.
for label, value in [('empty',None),('missing-user',{k:v for k,v in sample.items() if k!='albums'}),('empty-queues',dict(sample,queues={})),('empty-search',dict(sample,smart={})),('null-statistics',dict(sample,server_statistics={})),('control',sample)]:
    try: api_checks.validate_sample(value); accepted=True
    except (ValueError,TypeError,KeyError): accepted=False
    record('baseline-schema/'+label,accepted == (label=='control'))
with tempfile.TemporaryDirectory(prefix='immich-apptest-receipt-') as tmp:
    path=pathlib.Path(tmp)/'result'
    for label,text in [('empty',''),('malformed','garbage'),('null','null'),('missing','{}'),('false-pass',json.dumps(dict(receipt,items=[]))),('warn',json.dumps(dict(receipt,warn=1))),('control',json.dumps(receipt))]:
        path.write_text(text)
        try: api_checks.check_result(path); accepted=True
        except (ValueError,TypeError,KeyError,AttributeError): accepted=False
        record('receipt/'+label,accepted == (label=='control'))


# Key-loader failures clear both keys, even when the second key is syntactically valid.
with tempfile.TemporaryDirectory(prefix='immich-apptest-keys-') as tmp:
    keyfile=pathlib.Path(tmp)/'keys.env'
    for label,admin,user in [('missing-admin','PASTE_ADMIN','a'*32),('missing-user','a'*32,'PASTE_USER'),
                             ('invalid-admin','bad key','a'*32),('invalid-user','a'*32,'bad key'),
                             ('duplicate','a'*32+'\nIMMICH_ADMIN_API_KEY='+'b'*32,'c'*32),('control','a'*32,'b'*32)]:
        keyfile.write_text('IMMICH_ADMIN_API_KEY='+admin+'\nIMMICH_USER_API_KEY='+user+'\n');keyfile.chmod(0o600)
        script='source "$CV/keys_env.sh"; if keys_load; then exit 0; else rc=$?; [ -z "${IMMICH_ADMIN_API_KEY:-}${IMMICH_USER_API_KEY:-}" ] || exit 99; exit "$rc"; fi'
        p=subprocess.run(['/bin/bash','--noprofile','--norc','-c',script],capture_output=True,text=True,
                         env=dict(os.environ,CV=str(CV),KEYS_FILE=str(keyfile),KEYS_TEST='1'))
        record('key-loader/'+label,p.returncode==(0 if label=='control' else 1))

# HTTP errors and malformed queues must not become empty successful baselines/Redis operations.
original=api_checks.immich
for label,response in [('unauthorized',dict(status=401,json={})),('empty-queues',dict(status=200,json=[])),
                       ('invalid-queues',dict(status=200,json=[dict(name=str(i),isPaused='false',statistics={}) for i in range(19)]))]:
    api_checks.immich=lambda *args, **kwargs: response
    try: api_checks.queues(); accepted=True
    except (ValueError,RuntimeError,KeyError,TypeError): accepted=False
    record('queue-response/'+label,not accepted)
api_checks.immich=original


# F8 evidence hash binding: every changed required artifact blocks opening.
import safety_evidence
with tempfile.TemporaryDirectory(prefix='immich-apptest-seal-') as tmp:
    ev=pathlib.Path(tmp)
    for name in safety_evidence.REQUIRED:
        path=ev/name;path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(sample) if name=='api-baseline.json' else '{"status":"PASS"}')
    result=ev/'api-result.test.json';result.write_text(json.dumps(receipt))
    files={name:safety_evidence.digest(ev/name) for name in safety_evidence.REQUIRED+[result.name]}
    (ev/'dark-verified.json').write_text(json.dumps(dict(cutover_id='testhardening',target='immich-apptest-db',api_result=result.name,files=files)))
    safety_evidence.check(ev,'testhardening','immich-apptest-db');record('dark-seal/control',True)
    for name in files:
        path=ev/name;original=path.read_bytes();path.write_bytes(original+b' ')
        try: safety_evidence.check(ev,'testhardening','immich-apptest-db');accepted=True
        except ValueError: accepted=False
        finally: path.write_bytes(original)
        record('dark-seal/tampered-'+name,not accepted)
    for cid,host in [('wrong-id','immich-apptest-db'),('testhardening','wrong-db')]:
        try: safety_evidence.check(ev,cid,host);accepted=True
        except ValueError: accepted=False
        record('dark-seal/identity-'+cid+'-'+host,not accepted)

# Actual journal I/O failures must throw and leave an unverifiable journal, never success.
from unittest.mock import patch
with tempfile.TemporaryDirectory(prefix='immich-apptest-journal-') as tmp:
    ev=pathlib.Path(tmp)/'evidence'
    try:
        with patch.object(cutstate.os,'write',return_value=0): cutstate.set_state(ev,['NONE'],'PREPARED')
        accepted=True
    except OSError: accepted=False
    record('journal/short-write',not accepted and cutstate.load(ev)[0]=='CORRUPT')

if len(sys.argv)>1: pathlib.Path(sys.argv[1]).write_text(json.dumps(results,indent=1))
failed=[r for r in results if not r['ok']]
for r in failed: print('DETAIL',r)
print('%d checks, %d FAIL'%(len(results),len(failed)))
sys.exit(bool(failed))
