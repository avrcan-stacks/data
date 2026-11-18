"""Cutover rehearsal driver: runs a group of tests against the isolated stack and records PASS/FAIL in <EVROOT>/rehearsal-results.json.
   python3 -I rehearse.py <EVROOT> <group>        groups: g0 g1 g2 ...  (see GROUPS)"""
import json, os, re, subprocess, sys, time, tempfile, shutil
from pathlib import Path

EVR = Path(sys.argv[1]).resolve(); GROUP = sys.argv[2]
CV = Path('/opt/stacks/data/immich-cutover'); REH = CV / 'rehearsal'
ENVSH = EVR / 'env.sh'; RES = EVR / 'rehearsal-results.json'
ST = json.loads((EVR / 'state.json').read_text()); N = ST['names']; ID = ST['id']
results = json.loads(RES.read_text()) if RES.exists() else []
RUN_ID = str(time.time_ns())

def rec(name, ok, detail=''):
    results.append({'group': GROUP, 'run_id': RUN_ID, 'name': name, 'ok': bool(ok), 'detail': str(detail)[:400]}); RES.write_text(json.dumps(results, indent=1))
    print(('PASS  ' if ok else 'FAIL  ') + name + (' | ' + str(detail)[:200] if detail else ''), flush=True)
    return bool(ok)

def sh(script, timeout=1200, env=None):
    p = subprocess.run(['bash', '-c', 'source %s; cd %s; %s' % (ENVSH, CV, script)], capture_output=True, text=True, timeout=timeout, env=dict(os.environ, **dict({'EVIDENCE_ROOT': str(EVR), 'IMMICH_ADMIN_API_KEY': ST['keys']['admin'], 'IMMICH_USER_API_KEY': ST['keys']['user'], 'IMMICH_RESTRICTED_API_KEY': ST['keys']['restricted']}, **(env or {}))))
    return p.returncode, p.stdout, p.stderr

def d(*a, check=True):
    p = subprocess.run(['docker', *a], capture_output=True, text=True)
    if check and p.returncode: raise RuntimeError('docker %s: %s' % (' '.join(a[:3]), p.stderr[-300:]))
    return p

def g0():
    rc, out, err = sh('./tests/offline_selftest.sh', timeout=300)
    rec('offline_selftest.sh exits 0 and reports ALL OFFLINE CHECKS PASSED', rc == 0 and 'ALL OFFLINE CHECKS PASSED' in out, out.strip().splitlines()[-1] if out else err[-200:])

def g1():
    # production names / paths / docker.sock must be refused by every layer in REHEARSAL mode; nothing here is allowed to reach production
    cases = [
        ('cutlib.run refuses a production container', "python3 -I -c \"import sys; sys.path.insert(0,'.'); import cutlib; cutlib.run(['docker','exec','postgis','true'])\"", 'REHEARSAL GUARD'),
        ('cutlib.run refuses the Docker socket mount', "python3 -I -c \"import sys; sys.path.insert(0,'.'); import cutlib; cutlib.run(['docker','run','-v','/var/run/docker.sock:/s','x'])\"", 'REHEARSAL GUARD'),
        ('cutlib.run refuses a production media path', "python3 -I -c \"import sys; sys.path.insert(0,'.'); import cutlib; cutlib.run(['docker','run','--mount','type=bind,src=/opt/stacks/immich/docker-data/library,dst=/d','x'])\"", 'REHEARSAL GUARD'),
        ('cutlib.run refuses docker exec on a container without the apptest prefix', "python3 -I -c \"import sys; sys.path.insert(0,'.'); import cutlib; cutlib.run(['docker','exec','somecontainer','true'])\"", 'REHEARSAL GUARD'),
        ('getsecret.py refuses production container', "python3 -I getsecret.py immich_server DB_PASSWORD", 'REHEARSAL GUARD'),
        ('api_checks.py refuses production server name at import', "REHEARSAL_SERVER_CONTAINER=immich_server python3 -I api_checks.py queues status", 'immich-apptest'),
        ('preflight.py refuses production source name at import', "REHEARSAL_SRC_CONTAINER=postgis CUTOVER_ID=guardtest python3 -I preflight.py --skip-api", 'immich-apptest'),
        ('validate_target.py refuses production target name', "REHEARSAL_DB_CONTAINER=immich-db python3 -I validate_target.py --baseline /dev/null", 'immich-apptest'),
        ('db_snapshot.py refuses a production container', "python3 -I db_snapshot.py snapshot --container postgis --out /tmp/x-never", 'refusing container'),
        ('db_snapshot.py refuses the production target name', "python3 -I db_snapshot.py snapshot --container immich-db --out /tmp/x-never", 'refusing container'),
        ('guarded docker wrapper refuses production container (exit 97)', "docker exec postgis true; echo rc=$?", 'rc=97'),
    ]
    for name, cmd, expect in cases:
        script = cmd if 'docker exec postgis' not in cmd else 'source ./steps.sh; ' + cmd
        rc, out, err = sh(script, timeout=60)
        rec(name, (expect in (out + err)) and not ('postgis' in out and 'psql' in out), (err or out).strip().splitlines()[-1][:160] if (err or out).strip() else 'rc=%d' % rc)
    # steps.sh gates
    rc, out, err = sh("source ./steps.sh; export CUTOVER_ID=gate-test EV=/tmp/never; PG_SRC=postgis s_freeze", timeout=60)
    rec('steps.sh rehearsal gate refuses production source name (s_freeze)', rc != 0 and 'REHEARSAL GUARD' in err, err.strip()[-120:])
    # production-mode approval gate: real docker is shadowed by a stub that records any call, so nothing can touch production even if the gate were broken
    stub = tempfile.mktemp(); open(stub, 'w').close()
    script = ("unset CUTOVER_REHEARSAL CUTOVER_AUDIT; unset PG_SRC PG_NEW SRV; docker() { echo \"UNEXPECTED docker $*\" >> %s; return 99; }; "
              "python3() { echo \"UNEXPECTED python $*\" >> %s; return 99; }; export CUTOVER_ID=gate-test EV=/tmp/never-ev; source ./steps.sh; "
              "for f in s_prepare_target s_freeze s_dump_source s_bridge_sanitize s_restore_target s_validate_target s_dark_launch s_open s_open_abort s_manual_forward s_manual_rollback_accept_loss s_rollback_r1 s_unfence s_bridge_cleanup s_target_reset_after_rollback lb_copy_app_backup lb_copy_cutover_dumps; do $f >/dev/null 2>&1; echo \"$f rc=$?\"; done") % (stub, stub)
    rc, out, err = sh(script, timeout=60)
    rcs = dict(re.findall(r'((?:s|lb)_\w+) rc=(\d+)', out)); calls = Path(stub).read_text()
    rec('PRODUCTION-mode steps without CUTOVER_APPROVED are refused (17 mutating steps incl. the 2 local-copy functions), no docker/python call was made', len(rcs) == 17 and all(v == '1' for v in rcs.values()) and not calls, 'rcs=%s calls=%r' % (sorted(set(rcs.values())), calls[:80]))
    os.unlink(stub)
    # the audit log of the stack setup (all docker calls made so far through cutlib/guarded_docker) must not contain a production container name
    prod = {'postgis', 'immich_server', 'immich_redis', 'immich_machine_learning', 'immich_media_operations', 'nextcloud_immich_bridge', 'traefik', 'immich-db'}
    bad = []
    for line in (EVR / 'audit.jsonl').read_text().splitlines():
        a = json.loads(line)['argv']
        if any(x in prod for x in a) or any('docker.sock' in x or '/opt/stacks/immich' in x or '/opt/stacks/nextcloud' in x for x in a): bad.append(a[:6])
    rec('audit log so far: no command names a production container, production path or docker.sock', not bad, '%d commands audited, %d violations' % (sum(1 for _ in (EVR / 'audit.jsonl').open()), len(bad)))

def g2():
    """Password loader: tricky DB_PASSWORD values through Compose env_file -> getsecret.py -> \\getenv -> role creation -> TCP scram login. Also shows what the OLD sed/cut method got wrong."""
    d('rm', '-f', N['db'].replace('immichdb', 'pwdb'), check=False)
    pwdb = N['db'].replace('immichdb', 'pwdb')
    d('run', '-d', '--name', pwdb, '--network', ST['project'] + '_testnet', '--label', 'immich.cutover.rehearsal=' + ID, '-e', 'POSTGRES_PASSWORD=rootpw', ST['names']['db'] and 'sha256:e21ee65b5a53580b8f1e85b21ba0bf16f19c43d4dcc2ad49c4ce68a864a7cf51', 'postgres', '-c', 'shared_preload_libraries=vchord')
    for _ in range(60):
        if d('exec', pwdb, 'pg_isready', '-U', 'postgres', check=False).returncode == 0 and d('exec', pwdb, 'cat', '/proc/1/comm').stdout.strip() == 'postgres': break
        time.sleep(1)
    time.sleep(2)
    patterns = [
        ('plain alphanumeric', "DB_PASSWORD=abc123XYZ\n", 'abc123XYZ'),
        ('single-quoted with $ " # space backslash ! = % & ;', "DB_PASSWORD='S3c$r\"et#1 \\!x=y%&;z'\n", 'S3c$r"et#1 \\!x=y%&;z'),
        ('double-quoted with escaped quote', 'DB_PASSWORD="dq pass \\"quoted\\" #x"\n', None),
        ('unquoted with $ (interpolation)', "DB_PASSWORD=pa$word\n", None),
        ('unquoted with # inside', "DB_PASSWORD=ab#cd\n", 'ab#cd'),
        ('unquoted value followed by comment', "DB_PASSWORD=ab #cd\n", None),
        ('unicode', "DB_PASSWORD=ünï✓pw\n", 'ünï✓pw'),
        ('double-quoted with trailing space', 'DB_PASSWORD="trailing space "\n', 'trailing space '),
        ('single quote inside double quotes', 'DB_PASSWORD="it\'s a pw"\n', "it's a pw"),
    ]
    for i, (label, line, literal) in enumerate(patterns):
        tmp = Path(tempfile.mkdtemp(prefix='pwtest-')); (tmp / 'env').write_text(line)
        envs = {'CASE_ID': ID, 'R_NEW_IMAGE': 'sha256:e21ee65b5a53580b8f1e85b21ba0bf16f19c43d4dcc2ad49c4ce68a864a7cf51', 'PW_ENVFILE': str(tmp / 'env')}
        pn = 'immich-apptest-%s-pw' % ID
        d('rm', '-f', 'immich-apptest-%s-pwenv' % ID, check=False)
        cp = subprocess.run(['docker', 'compose', '-p', pn, '-f', str(REH / 'docker-compose.pwtest.yml'), 'create'], capture_output=True, text=True, env=dict(os.environ, **envs))
        if cp.returncode:
            rec('loader [%s]: Compose parse' % label, True, 'Compose rejects this env_file line (%s) - nothing can be created, the application would not start either' % cp.stderr.strip().splitlines()[-1][:80]); shutil.rmtree(tmp); continue
        ok = subprocess.run(['bash', '-c', 'source %s; cd %s; python3 -I getsecret.py immich-apptest-%s-pwenv DB_PASSWORD' % (ENVSH, CV, ID)], capture_output=True, text=True)
        val = ok.stdout
        # what the application container receives is the authority; create a role with exactly that and log in over TCP/scram
        env = dict(os.environ, NEWPW=val)
        r = subprocess.run(['docker', 'exec', '-i', '-e', 'NEWPW', pwdb, 'psql', '-X', '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1'], input="\\getenv pw NEWPW\nCREATE ROLE pwr%d LOGIN PASSWORD :'pw';\n" % i, capture_output=True, text=True, env=env)
        ip = d('inspect', '-f', '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}', pwdb).stdout.split()[0]
        lg = subprocess.run(['docker', 'exec', '-e', 'NEWPW', pwdb, 'sh', '-c', 'PGPASSWORD="$NEWPW" psql -X -h %s -U pwr%d -d postgres -Atc "select current_user"' % (ip, i)], capture_output=True, text=True, env=env)
        wr = subprocess.run(['docker', 'exec', pwdb, 'sh', '-c', 'PGPASSWORD="definitely-wrong" psql -X -h %s -U pwr%d -d postgres -Atc "select 1"' % (ip, i)], capture_output=True, text=True)
        naive = subprocess.run(['bash', '-c', "grep '^DB_PASSWORD=' %s | cut -d= -f2- | sed -e 's/^\"//' -e 's/\"$//' -e \"s/^'//\" -e \"s/'$//\"" % (tmp / 'env')], capture_output=True, text=True).stdout.rstrip('\n')
        good = r.returncode == 0 and lg.stdout.strip() == 'pwr%d' % i and wr.returncode != 0 and (literal is None or val == literal)
        rec('loader [%s]: getsecret -> \\getenv -> role -> scram login over the network address (wrong password rejected)' % label, good, 'len=%d old_sed_cut_method_equal=%s' % (len(val), naive == val))
        d('rm', '-f', 'immich-apptest-%s-pwenv' % ID, check=False); shutil.rmtree(tmp)
    d('rm', '-f', pwdb, check=False)


def g4():
    """api_checks.py: baseline/verify (positive + tampered), restricted key, queue pause/drain/resume under real load."""
    EV = EVR / 'immich-cutover-api4tst'; EV.mkdir(exist_ok=True, mode=0o700)
    base = EV / 'api-baseline.json'
    def api(args, env=''): return sh('export CUTOVER_ID=api4tst; %s python3 -I api_checks.py %s' % (env, args), timeout=900)
    rc, out, err = api('baseline --out %s' % base)
    b = json.loads(base.read_text()) if base.exists() else {}
    rec('api_checks baseline: statistics, 8 libraries, queues, albums, people, 10 smart queries x5', rc == 0 and len(b.get('libraries', [])) == 8 and b.get('albums', {}).get('count') == ST['user_stats']['albums'] + (b['albums']['count'] - ST['user_stats']['albums']) and len(b.get('smart', {})) == 10, 'photos=%s videos=%s albums=%s people=%s' % (b.get('server_statistics', {}).get('photos'), b.get('server_statistics', {}).get('videos'), b.get('albums', {}).get('count'), b.get('people', {}).get('total')))
    rc, out, err = api('verify --baseline %s' % base)
    rec('api_checks verify against its own baseline passes (0 FAIL)', rc == 0 and 'RESULT: PASS' in out, [l for l in out.splitlines() if l.startswith(('FAIL', 'RESULT'))])
    def tamper(label, fn, expect_id, extra=''):
        t = json.loads(base.read_text()); fn(t); tp = EV / 'tampered.json'; tp.write_text(json.dumps(t))
        rc, out, err = api('verify --baseline %s %s' % (tp, extra))
        rec('verify detects: ' + label, rc != 0 and re.search(r'^FAIL\s+%s\b' % expect_id, out, re.M) is not None, [l[:90] for l in out.splitlines() if l.startswith('FAIL')][:2])
    tamper('different photo count', lambda t: t['server_statistics'].__setitem__('photos', (t['server_statistics']['photos'] or 0) + 1), 'Q2')
    tamper('different per-user usage', lambda t: t['server_statistics'].__setitem__('usage_by_user', [[1, 1, 1]]), 'Q2')
    tamper('different library statistics', lambda t: t['libraries'].__setitem__(0, ['xxxxxxxx', 99999]), 'Q3')
    tamper('different album count', lambda t: t['albums'].__setitem__('count', t['albums']['count'] + 1), 'Q6')
    tamper('different people total', lambda t: t['people'].__setitem__('total', (t['people']['total'] or 0) + 5), 'Q7')
    tamper('smart search result drift (ids replaced)', lambda t: [t['smart'][q].__setitem__('ids', ['00000000-0000-0000-0000-%012d' % i for i in range(20)]) for q in t['smart']], 'Q8')
    tamper('smart search slower than threshold (cold, 1 ms limit)', lambda t: None, 'Q10', '--max-cold-ms 1')
    rc, out, err = api('queues status', env='IMMICH_ADMIN_API_KEY=$IMMICH_RESTRICTED_API_KEY')
    rec('a key without queue.read is rejected (HTTP 403), non-zero exit', rc != 0 and '403' in (out + err), (err.strip().splitlines() or [''])[-1][:120])
    rc, out, err = api('queues status', env='IMMICH_ADMIN_API_KEY=')
    rec('missing key: clear error, non-zero exit', rc != 0 and 'IMMICH_ADMIN_API_KEY' in (out + err), (err.strip().splitlines() or [''])[-1][:120])
    # ---- queues under load
    rc, out, err = api('queues status'); idle0 = all(re.search(r'active=0\s+waiting=0\s+delayed=0', l) for l in out.strip().splitlines())
    rec('queues idle before the load test', rc == 0 and idle0, out.strip().splitlines()[:1])
    u = ST['emails']['user']; pw = ST['passwords']['user']
    rc, out, err = sh('idc --profile client run --rm -T client python -I /tests/load_uploads.py %s %s 40' % (u, pw), timeout=600)
    rec('load generator uploaded 40 unique synthetic images as the data user', rc == 0 and '"uploaded": 40' in out, out.strip()[-80:])
    rc, out, err = api('queues pause --execute'); rec('queues pause --execute pauses all 18 pausable queues and reports backgroundTask as not pausable by design (exit 0)', rc == 0 and out.count(' 200') + out.count('200\n') >= 18 and '1 queue(s) not pausable by design' in out and 'backgroundTask' in out, 'status lines=%d' % len(out.strip().splitlines()))
    rc, out, err = api('queues status'); waiting = sum(int(m) for m in re.findall(r'(?:waiting|held)=(\d+)', out)); paused_all = all('paused=True' in l for l in out.strip().splitlines() if not l.startswith('backgroundTask'))
    rec('after pause: every pausable queue is paused (backgroundTask cannot be) and a backlog is HELD in Redis (nothing dropped)', paused_all and waiting > 0, 'backlog(waiting+held)=%d' % waiting)
    rc, out, err = api('queues wait-drain --timeout 120')
    rec('wait-drain returns DRAINED once active==0 and every pausable queue is paused', rc == 0 and 'DRAINED' in out, out.strip().splitlines()[-1])
    time.sleep(20)
    rc, out2, err = api('queues status'); waiting2 = sum(int(m) for m in re.findall(r'(?:waiting|held)=(\d+)', out2)); active2 = sum(int(m) for m in re.findall(r'active=(\d+)', out2))
    rec('while paused nothing is processed for 20 s (backlog unchanged, active 0)', waiting2 == waiting and active2 == 0, 'backlog %d -> %d active=%d' % (waiting, waiting2, active2))
    rc, out, err = api('queues wait-drain --timeout 0')
    rec('wait-drain with an expired timeout fails with TIMEOUT (STOP-1 path)', rc != 0 and 'TIMEOUT' in (out + err), (err or out).strip().splitlines()[-1][:100])
    rc, out, err = api('queues resume --execute'); rec('queues resume --execute resumes all 19 queues', rc == 0 and out.count('200') >= 19, 'status lines=%d' % len(out.strip().splitlines()))
    t0 = time.time(); idle = False
    while time.time() - t0 < 300:
        rc, out, err = api('queues status')
        if all(re.search(r'active=0\s+waiting=0\s+delayed=0', l) for l in out.strip().splitlines()) and 'paused=True' not in out: idle = True; break
        time.sleep(5)
    failed = sum(int(m) for m in re.findall(r'failed=(\d+)', out))
    rec('after resume the backlog is processed to idle with 0 failed jobs', idle and failed == 0, 'idle after %.0fs failed=%d' % (time.time() - t0, failed))
    miss = sh("docker exec -i %s psql -X -U postgres -d immich -At -c \"SELECT count(*) FROM asset a WHERE a.\\\"originalFileName\\\" ~ '^r[0-9]+\\.jpg$' AND NOT EXISTS (SELECT 1 FROM smart_search s WHERE s.\\\"assetId\\\"=a.id)\"" % N['src'])
    rec('every uploaded asset has its CLIP embedding after resume (no work lost by pause/resume)', miss[0] == 0 and miss[1].strip() == '0', 'assets without embedding=%s' % miss[1].strip())

# ---------------------------------------------------------------------------------------------- full-flow rehearsal helpers
def pre(cid, tag):
    return ("source ./steps.sh; export CUTOVER_ID=%s EV=$EVROOT/immich-cutover-%s BR=immich-apptest-%s-bridge-%s WB=$ROOT/bridge-work/%s; " % (cid, cid, ID, tag, cid))
def stepsh(cid, tag, frag, timeout=1500, env=''):
    rc, out, err = sh(pre(cid, tag) + env + ' ' + frag, timeout=timeout)
    return rc, out, err
def tail(t, n=3): return ' / '.join(t.strip().splitlines()[-n:])[:300]
def must(name, rc, out, err, ok=None):
    good = (rc == 0) if ok is None else ok
    rec(name, good, tail(err or out) if not good else tail(out, 1))
    if not good: raise SystemExit('HALT after failed step: ' + name)
def src(sql, db='immich'):
    p = d('exec', '-i', N['src'], 'psql', '-X', '-U', 'postgres', '-d', db, '-At', check=False); return p
def psql_in(container, sql, db='postgres'):
    return subprocess.run(['docker', 'exec', '-i', container, 'psql', '-X', '-U', 'postgres', '-d', db, '-At', '-v', 'ON_ERROR_STOP=1'], input=sql, capture_output=True, text=True)
def label(c): return d('inspect', '-f', '{{index .Config.Labels "traefik.enable"}}', c).stdout.strip()
def envhost(c): return [l.split('=', 1)[1] for l in d('inspect', '-f', '{{range .Config.Env}}{{println .}}{{end}}', c).stdout.splitlines() if l.startswith('DB_HOSTNAME=')][0]
def state(c): return d('inspect', '-f', '{{.State.Status}}', c).stdout.strip()

def gA():
    """RUN A: complete runbook up to dark launch, then NO-GO and rollback R1."""
    cid = 'rehA' + time.strftime('%H%M%S'); EV = EVR / ('immich-cutover-' + cid); EV.mkdir(mode=0o700, exist_ok=True)
    (EVR / 'run-a-id').write_text(cid)
    rc, out, err = stepsh(cid, 'a', 'python3 -I preflight.py --phase before-target --ignore-window'); must('A1 preflight (before target): 0 FAIL', rc, out, err, 'RESULT: PASS' in out)
    rc, out, err = stepsh(cid, 'a', 'python3 -I api_checks.py baseline --out $EV/api-baseline-pre.json'); must('A2 api baseline (pre-freeze dry run of the tool and the keys) written', rc, out, err)
    rc, out, err = stepsh(cid, 'a', 's_prepare_target'); must('A3 s_prepare_target (immich-db up, role+db created with the exact app secret, scram login proven)', rc, out, err, rc == 0 and 's_prepare_target OK' in out)
    rc, out, err = stepsh(cid, 'a', 'python3 -I preflight.py --phase target-ready --skip-api --ignore-window'); must('A4 preflight (target-ready) after F2: 0 FAIL', rc, out, err, 'RESULT: PASS' in out)
    u, pw = ST['emails']['user'], ST['passwords']['user']
    rc, out, err = sh('idc --profile client run --rm -T client python -I /tests/load_uploads.py %s %s 25' % (u, pw)); must('A5 load: 25 uploads so that jobs are active at freeze time', rc, out, err)
    rc, out, err = stepsh(cid, 'a', 's_freeze'); must('A6 s_freeze (pause, drain, stop writers, verify 0 connections, fence source)', rc, out, err, rc == 0 and 's_freeze OK' in out)
    rec('A6b after freeze: application stopped, source database fenced (no CONNECT for immich/PUBLIC), 0 sessions', state(N['server']) == 'exited' and psql_in(N['src'], "SELECT has_database_privilege('immich','immich','CONNECT') OR has_database_privilege('public','immich','CONNECT')").stdout.strip() == 'f' and psql_in(N['src'], "SELECT count(*) FROM pg_stat_activity WHERE datname='immich'").stdout.strip() == '0', 'server=%s' % state(N['server']))
    rc, out, err = stepsh(cid, 'a', 's_dump_source'); must('A7 s_dump_source (snapshot, dump, size gate, TOC readable, sha256)', rc, out, err, rc == 0 and 's_dump_source OK' in out)
    gA_post(cid, EV)

def gA_post(cid, EV):
    rc, out, err = stepsh(cid, 'a', 's_bridge_sanitize'); must('A8 s_bridge_sanitize (restore, compare BEFORE and AFTER DROP EXTENSION postgis RESTRICT, sanitized dump, TOC clean)', rc, out, err, rc == 0 and 's_bridge_sanitize OK' in out)
    cmp1 = json.loads((EV / 'compare-source-bridge.json').read_text()); cmp2 = json.loads((EV / 'compare-source-bridge-after.json').read_text())
    rec('A8b bridge BEFORE drop: strict equality with source incl. PostGIS (72 tables, owners, ACLs, sequences, indexes, extensions)', cmp1['status'] == 'PASS' and cmp1['tables_compared'] == 72, 'rows=%d' % cmp1['rows'])
    rec('A8c bridge AFTER drop: only PostGIS members differ (72 tables identical)', cmp2['status'] == 'PASS', cmp2['mode'])
    rc, out, err = stepsh(cid, 'a', 's_bridge_cleanup'); must('A9 s_bridge_cleanup (label + realpath checked)', rc, out, err)
    rc, out, err = stepsh(cid, 'a', 's_restore_and_validate', timeout=2400); must('A10 s_restore_target + s_validate_target (restore, ACL, sequence, compare PASS, validate_target incl. amcheck, ANALYZE)', rc, out, err, rc == 0 and 's_validate_target OK' in out)
    cmp3 = json.loads((EV / 'compare.json').read_text()); rec('A10b source->target compare: 72 tables, metadata identical (documented index-text exception only)', cmp3['status'] == 'PASS' and cmp3['tables_compared'] == 72, 'rows=%d' % cmp3['rows'])
    vt = sorted(EV.glob('validate-target-*.json'))[-1]; vj = json.loads(vt.read_text())
    rec('A10c validate_target: %d checks, 0 FAIL (recall, latency, amcheck included)' % len(vj['items']), vj['fail'] == 0, [i['detail'] for i in vj['items'] if i['id'].startswith('W3')][:2])

def gA2():
    cid = (EVR / 'run-a-id').read_text(); EV = EVR / ('immich-cutover-' + cid)
    # resume after a fixed script bug: clean the half-finished bridge step (label+realpath checked by the step itself)
    rc, out, err = stepsh(cid, 'a', 's_bridge_cleanup'); print('cleanup rc', rc, tail(err, 1))
    for n in ('bridge-before', 'bridge-after'): shutil.rmtree(EV / n, ignore_errors=True)
    for n in ('compare-source-bridge.json', 'bridge.restore.log', 'immich.no-postgis.dump.partial'): (EV / n).unlink(missing_ok=True)
    gA_post(cid, EV)

def gA3():
    cid = (EVR / 'run-a-id').read_text(); EV = EVR / ('immich-cutover-' + cid)
    shutil.rmtree(EV / 'dst', ignore_errors=True); (EV / 'compare.json').unlink(missing_ok=True)
    rc, out, err = stepsh(cid, 'a', 's_validate_target', timeout=2400); must('A10 s_validate_target (snapshot, compare PASS, validate_target incl. amcheck, ANALYZE)', rc, out, err, rc == 0 and 's_validate_target OK' in out)
    cmp3 = json.loads((EV / 'compare.json').read_text()); rec('A10b source->target compare: 72 tables identical, metadata identical (documented index-text exception only)', cmp3['status'] == 'PASS' and cmp3['tables_compared'] == 72, 'rows=%d' % cmp3['rows'])
    vj = json.loads(sorted(EV.glob('validate-target-*.json'))[-1].read_text())
    rec('A10c validate_target: %d checks, 0 FAIL (counts vs frozen source, recall, latency, amcheck)' % len(vj['items']), vj['fail'] == 0, [i['detail'] for i in vj['items'] if i['id'].startswith('W3')][:2])

def app_pw():
    return [l.split('=', 1)[1] for l in d('inspect', '-f', '{{range .Config.Env}}{{println .}}{{end}}', N['server']).stdout.splitlines() if l.startswith('DB_PASSWORD=')][0]

def gI():
    """Fault injection on CLONES of the restored target (CREATE DATABASE ... TEMPLATE): every tampering must be caught by db_snapshot compare and/or validate_target."""
    cid = (EVR / 'run-a-id').read_text(); EV = EVR / ('immich-cutover-' + cid); INJ = EV / 'inj'; INJ.mkdir(exist_ok=True, mode=0o700)
    baseline = sorted(EV.glob('baseline-*.json'))[-1]
    SEQ = 'public.naturalearth_countries_tmp_id_seq1'
    cases = [
        # (name, sql list [(sql, db)], compare_should_fail, compare_substring, validate_fail_ids, cleanup_sql)
        ('control (no tampering)', [], False, None, [], None),
        ('table content changed (one asset row)', ["UPDATE public.asset SET \"originalFileName\" = \"originalFileName\" || 'x' WHERE id = (SELECT id FROM public.asset ORDER BY id LIMIT 1)"], True, 'table content hashes differ', [], None),
        ('rows deleted (one smart_search embedding)', ['DELETE FROM public.smart_search WHERE "assetId" = (SELECT "assetId" FROM public.smart_search ORDER BY "assetId" LIMIT 1)'], True, 'table content hashes differ', ['V10'], None),
        ('table privilege revoked (UPDATE on asset from immich)', ['REVOKE UPDATE ON public.asset FROM immich'], True, 'metadata sections differ', ['V7'], None),
        ('database ACL widened (CREATE to PUBLIC)', ['GRANT CREATE ON DATABASE immich_inj TO PUBLIC'], False, None, ['V4'], None),
        ('database owner changed', ['ALTER DATABASE immich_inj OWNER TO postgres'], True, 'metadata sections differ', ['V4'], None),
        ('identity sequence is integer', ['ALTER SEQUENCE %s AS integer' % SEQ], True, 'identity sequence is not bigint', ['V9'], None),
        ('identity sequence value lowered', ["SELECT setval('%s', 10, true)" % SEQ], True, 'sequences lower than source', ['V9'], None),
        ('index dropped (clip_index)', ['DROP INDEX public.clip_index'], True, 'metadata sections differ', ['V8'], None),
        ('extra index created', ['CREATE INDEX x_extra ON public.asset ("createdAt")'], True, 'metadata sections differ', ['V8'], None),
        ('INVALID index left by a failed concurrent build', ['!CREATE UNIQUE INDEX CONCURRENTLY x_inv ON public.asset ("originalFileName")'], True, 'metadata sections differ', ['V8'], None),
        ('extension added (amcheck)', ['CREATE EXTENSION amcheck'], True, 'extensions differ', ['V3'], None),
        ('table owner changed (immich loses ownership)', ['ALTER TABLE public.naturalearth_countries OWNER TO postgres'], True, 'metadata sections differ', ['V7'], None),
        ('function privilege revoked (f_unaccent)', ['REVOKE EXECUTE ON FUNCTION public.f_unaccent(text) FROM PUBLIC, immich'], True, 'metadata sections differ', ['V7'], None),
        ('role immich gets CREATEDB (cluster level)', ['!@ALTER ROLE immich CREATEDB'], False, None, ['V5'], 'ALTER ROLE immich NOCREATEDB'),
        ('role immich password changed (cluster level)', ["!@ALTER ROLE immich PASSWORD 'not-the-app-secret'"], False, None, ['V6'], '@REVERT_PW'),
    ]
    for name, sqls, cmp_fail, cmp_sub, vfail, cleanup in cases:
        psql_in(N['db'], 'DROP DATABASE IF EXISTS immich_inj WITH (FORCE)'); r = psql_in(N['db'], 'CREATE DATABASE immich_inj TEMPLATE immich OWNER immich')
        assert r.returncode == 0, r.stderr
        for q in sqls:
            cluster = q.startswith('!@'); q2 = q.lstrip('!@')
            r = psql_in(N['db'], q2, db='postgres' if cluster or 'immich_inj OWNER' in q2 or 'ON DATABASE' in q2 else 'immich_inj') if not q.startswith('!') or cluster else subprocess.run(['docker', 'exec', '-i', N['db'], 'psql', '-X', '-U', 'postgres', '-d', 'immich_inj', '-At'], input=q2, capture_output=True, text=True)
            if 'CONCURRENTLY' not in q2: assert r.returncode == 0, 'injection SQL failed (test bug): %s -> %s' % (q2[:80], r.stderr[:200])
        out_dir = INJ / re.sub(r'[^a-z0-9]+', '-', name.lower())[:40]; shutil.rmtree(out_dir, ignore_errors=True)
        rc1, o1, e1 = sh('export CUTOVER_ID=%s CUTOVER_DB=immich_inj; python3 -I db_snapshot.py snapshot --container $REHEARSAL_DB_CONTAINER --out %s && python3 -I db_snapshot.py compare --mode source-target --source %s --target %s' % (cid, out_dir, EV / 'src', out_dir), timeout=900)
        cmp_failed = rc1 != 0 and 'FAIL' in o1
        rc2, o2, e2 = sh('export CUTOVER_ID=%s CUTOVER_DB=immich_inj; python3 -I validate_target.py --baseline %s --source-snapshot %s --samples 5' % (cid, baseline, EV / 'src'), timeout=900)
        failed_ids = sorted(set(re.findall(r'^FAIL\s+(\S+)', o2, re.M)))
        ok_cmp = (cmp_failed == cmp_fail) and (not cmp_fail or cmp_sub in o1)
        ok_val = all(any(f.startswith(v) for f in failed_ids) for v in vfail) and (bool(vfail) or not failed_ids)
        rec('inject [%s]: compare %s, validate_target FAIL ids %s' % (name, 'FAIL (expected)' if cmp_fail else 'PASS (expected)', vfail or 'none'), ok_cmp and ok_val, 'compare_failed=%s validate_fail=%s' % (cmp_failed, failed_ids))
        if cleanup:
            if cleanup == '@REVERT_PW':
                subprocess.run(['docker', 'exec', '-i', '-e', 'NEWPW', N['db'], 'psql', '-X', '-U', 'postgres', '-d', 'postgres', '-v', 'ON_ERROR_STOP=1'], input="\\getenv pw NEWPW\nALTER ROLE immich PASSWORD :'pw';\n", capture_output=True, text=True, env=dict(os.environ, NEWPW=app_pw()))
            else: psql_in(N['db'], cleanup)
    psql_in(N['db'], 'DROP DATABASE IF EXISTS immich_inj WITH (FORCE)')
    rec('cleanup after injections: role immich attributes and password restored, clone dropped', psql_in(N['db'], "SELECT rolcreatedb FROM pg_roles WHERE rolname='immich'").stdout.strip() == 'f', 'createdb=f')

def gD():
    """Dark launch of RUN A, NO-GO, rollback R1."""
    cid = (EVR / 'run-a-id').read_text(); EV = EVR / ('immich-cutover-' + cid)
    rc, out, err = stepsh(cid, 'a', 's_dark_launch', timeout=1200); must('D1 s_dark_launch (healthy, log gates, API verify with paused queues, dark delta, source untouched)', rc, out, err, rc == 0 and 's_dark_launch OK' in out)
    rec('D1b dark phase: Traefik label is false (no public route), DB_HOSTNAME is the NEW database', label(N['server']) == 'false' and envhost(N['server']) == N['db'], 'label=%s host=%s' % (label(N['server']), envhost(N['server'])[-12:]))
    dj = json.loads((EV / 'dark-delta.json').read_text()); rec('D1c dark delta: only allowed tables changed by the application start', dj['status'] == 'PASS', dj['changed_tables'])
    # NO-GO decision -> rollback R1 (the only rollback that is allowed before the point of no return)
    rc, out, err = stepsh(cid, 'a', 's_rollback_r1', timeout=1200); must('D2 s_rollback_r1 (unfence, recreate on source DB, label true, resume, verify)', rc, out, err, rc == 0 and 's_rollback_r1 OK' in out)
    rec('D2b after R1: application healthy on the SOURCE database host with the route label restored', state(N['server']) == 'running' and envhost(N['server']) == N['src'] and label(N['server']) == 'true', 'host=%s label=%s' % (envhost(N['server'])[-8:], label(N['server'])))
    rec('D2c after R1: source database ACL restored exactly (before == after)', (EV / 'source-db-acl.before').read_text() == (EV / 'source-db-acl.after').read_text(), (EV / 'source-db-acl.after').read_text().replace('\n', ';')[:100])
    rc, out, err = stepsh(cid, 'a', 'python3 -I api_checks.py verify --baseline $EV/api-baseline.json'); rec('D2d after R1: API verify against the pre-freeze baseline passes', rc == 0 and 'RESULT: PASS' in out, [l for l in out.splitlines() if l.startswith(('FAIL', 'RESULT'))])
    rc, out, err = stepsh(cid, 'a', 's_rollback_r1', env='touch $EV/T_open;'); 
    rec('rollback R1 is REFUSED once T_open exists (exit 3)', rc == 3 and 'REFUSED' in err, tail(err, 1)); (EV / 'T_open').unlink(missing_ok=True)

def gD2():
    """RUN A: rollback R1 from the (pre-fix) dark state, plus the refusal after T_open."""
    cid = (EVR / 'run-a-id').read_text(); EV = EVR / ('immich-cutover-' + cid)
    rec('finding: with job workers in the dark phase the metadataExtraction queue was RESUMED by the application itself (Q5 FAIL, see api-verify report)', 'metadataExtraction' in json.dumps([i for f in sorted(EV.glob('api-verify-*.json')) for i in json.loads(f.read_text())['items'] if i['id'] == 'Q5']), 'fixed: dark override now sets IMMICH_WORKERS_INCLUDE=api')
    rc, out, err = stepsh(cid, 'a', 's_rollback_r1', timeout=1200, env='export R1_SKIP_VERIFY=1;'); must('D2 s_rollback_r1 (unfence, recreate on source DB, label true, resume queues)', rc, out, err, rc == 0 and 's_rollback_r1 OK' in out)
    rec('D2b after R1: application healthy on the SOURCE database host with the route label restored', state(N['server']) == 'running' and envhost(N['server']) == N['src'] and label(N['server']) == 'true', 'host=...%s label=%s' % (envhost(N['server'])[-8:], label(N['server'])))
    rec('D2c after R1: source database ACL restored exactly (before == after)', (EV / 'source-db-acl.before').read_text() == (EV / 'source-db-acl.after').read_text(), (EV / 'source-db-acl.after').read_text().replace(chr(10), ';')[:90])
    rc, out, err = stepsh(cid, 'a', 'python3 -I api_checks.py verify --baseline $EV/api-baseline.json')
    q2 = [l for l in out.splitlines() if l.startswith('FAIL')]
    stale = json.loads((EV / 'api-baseline.json').read_text())['server_statistics']['photos']; now = json.loads(sorted(EV.glob('api-verify-*.json'))[-1].read_text())
    rec('D2d after R1: API verify differs from the PRE-freeze baseline ONLY by Q2 (+25 photos = the 25 test uploads made after that baseline): explains why the frozen baseline is taken after the drain', len(q2) == 1 and q2[0].startswith('FAIL  Q2') and ('(%d, %d)' % (stale, stale + 25)) in q2[0], q2[0][:140] if q2 else 'no FAIL')
    rc, out, err = stepsh(cid, 'a', 's_rollback_r1', env='touch $EV/T_open;')
    rec('rollback R1 is REFUSED once T_open exists (exit 3, nothing changed)', rc == 3 and 'REFUSED' in err, tail(err, 1)); (EV / 'T_open').unlink(missing_ok=True)
    rc, out, err = stepsh(cid, 'a', 'python3 -I api_checks.py queues status'); rec('after R1 every queue is resumed (no paused queue, nothing stuck)', rc == 0 and 'paused=True' not in out, 'queues ok')

def gD2b():
    cid = (EVR / 'run-a-id').read_text(); EV = EVR / ('immich-cutover-' + cid)
    rc, out, err = stepsh(cid, 'a', 'python3 -I api_checks.py verify --baseline $EV/api-baseline.json')
    q2 = [l for l in out.splitlines() if l.startswith('FAIL')]
    stale = json.loads((EV / 'api-baseline.json').read_text())['server_statistics']['photos']; now = json.loads(sorted(EV.glob('api-verify-*.json'))[-1].read_text())
    rec('D2d after R1: API verify differs from the PRE-freeze baseline ONLY by Q2 (+25 photos = the 25 test uploads made after that baseline): explains why the frozen baseline is taken after the drain', len(q2) == 1 and q2[0].startswith('FAIL  Q2') and ('(%d, %d)' % (stale, stale + 25)) in q2[0], q2[0][:140] if q2 else 'no FAIL')
    rc, out, err = stepsh(cid, 'a', 's_rollback_r1', env='touch $EV/T_open;')
    rec('rollback R1 is REFUSED once T_open exists (exit 3, nothing changed)', rc == 3 and 'REFUSED' in err, tail(err, 1)); (EV / 'T_open').unlink(missing_ok=True)
    rc, out, err = stepsh(cid, 'a', 'python3 -I api_checks.py queues status'); rec('after R1 every queue is resumed (no paused queue, nothing stuck)', rc == 0 and 'paused=True' not in out, 'queues ok')

def gB():
    """RUN B: reset target after the rollback, STOP simulations, full forward path to OPEN (point of no return) and post-open checks."""
    cid = 'rehB' + time.strftime('%H%M%S'); EV = EVR / ('immich-cutover-' + cid); EV.mkdir(mode=0o700, exist_ok=True); (EVR / 'run-b-id').write_text(cid)
    u, pw = ST['emails']['user'], ST['passwords']['user']
    rc, out, err = stepsh(cid, 'b', 's_target_reset_after_rollback'); must('B0 s_target_reset_after_rollback (failed attempt renamed, never dropped; empty immich created)', rc, out, err)
    rec('B0b the failed attempt database still exists under a new name (nothing deleted)', 'immich_failed_' in psql_in(N['db'], "SELECT string_agg(datname, ',') FROM pg_database").stdout, psql_in(N['db'], "SELECT string_agg(datname, ',') FROM pg_database").stdout.strip()[:100])
    rc, out, err = stepsh(cid, 'b', 'python3 -I preflight.py --phase target-ready --ignore-window'); must('B1 preflight (target-ready, with API): 0 FAIL', rc, out, err, 'RESULT: PASS' in out)
    rc, out, err = stepsh(cid, 'b', 'python3 -I api_checks.py baseline --out $EV/api-baseline-pre.json'); must('B2 pre-freeze baseline (tool + keys dry run)', rc, out, err)
    rc, out, err = sh('idc --profile client run --rm -T client python -I /tests/load_uploads.py %s %s 25' % (u, pw)); must('B3 load: 25 uploads with jobs in flight', rc, out, err)
    # STOP-1: drain timeout must stop the freeze BEFORE anything is stopped (separate evidence dir)
    rc, out, err = stepsh('rehS1', 'b', 's_freeze', env='export DRAIN_TIMEOUT=0;', timeout=300)
    rec('STOP-1 simulated: drain timeout makes s_freeze exit non-zero before any container is stopped', rc != 0 and 'TIMEOUT' in (out + err) and state(N['server']) == 'running', tail(err, 1))
    rec('STOP-1: source is not fenced after the aborted freeze', psql_in(N['src'], "SELECT has_database_privilege('immich','immich','CONNECT')").stdout.strip() == 't', 'immich can connect')
    rc, out, err = stepsh(cid, 'b', 'python3 -I api_checks.py queues resume --execute'); must('STOP-1 recovery: queues resumed', rc, out, err)
    time.sleep(90)      # let the backlog finish so that the real freeze drains quickly
    rc, out, err = stepsh(cid, 'b', 's_freeze'); must('B4 s_freeze (pause, drain, FROZEN baseline, stop writers, 0 connections, fence)', rc, out, err, rc == 0 and 's_freeze OK' in out)
    rec('B4b frozen baseline exists next to the pre-freeze one', (EV / 'api-baseline.json').exists() and (EV / 'api-baseline-pre.json').exists(), 'two baselines')
    # STOP-3: dump size gate (separate evidence dir)
    (EVR / 'immich-cutover-rehS2').mkdir(exist_ok=True, mode=0o700)
    rc, out, err = stepsh('rehS2', 'b', 's_dump_source', env='export DUMP_MIN_BYTES=900000000;', timeout=600)
    rec('STOP-3 simulated: dump size gate stops s_dump_source (exit non-zero) and no final dump file is left', rc != 0 and 'outside' in err and not (EVR / 'immich-cutover-rehS2' / 'immich.full.dump').exists(), tail(err, 1))
    rc, out, err = stepsh(cid, 'b', 's_dump_source'); must('B5 s_dump_source', rc, out, err, rc == 0 and 's_dump_source OK' in out)
    # STOP-4: truncated dump -> bridge restore error must stop the step and leave no sanitized dump
    S3 = EVR / 'immich-cutover-rehS3'; S3.mkdir(exist_ok=True, mode=0o700); shutil.copytree(EV / 'src', S3 / 'src', dirs_exist_ok=True)
    subprocess.run(['bash', '-c', 'head -c 60000000 %s > %s' % (EV / 'immich.full.dump', S3 / 'immich.full.dump')], check=True)
    rc, out, err = stepsh('rehS3', 'b', 's_bridge_sanitize', timeout=900)
    rec('STOP-4 simulated: truncated dump -> bridge restore fails, step exits non-zero, no sanitized dump produced', rc != 0 and not (S3 / 'immich.no-postgis.dump').exists(), tail(err, 1))
    rc, out, err = stepsh('rehS3', 'b', 's_bridge_cleanup'); rec('STOP-4 cleanup: failed bridge removed (label + realpath checked)', rc == 0 and not d('ps', '-aq', '--filter', 'name=bridge-rehS3').stdout.strip() if False else rc == 0, tail(err, 1) or tail(out, 1))
    rc, out, err = stepsh(cid, 'b', 's_bridge_sanitize'); must('B6 s_bridge_sanitize (restore, compare BEFORE and AFTER DROP EXTENSION, sanitized dump)', rc, out, err, rc == 0 and 's_bridge_sanitize OK' in out)
    c1 = json.loads((EV / 'compare-source-bridge.json').read_text()); c2 = json.loads((EV / 'compare-source-bridge-after.json').read_text())
    rec('B6b bridge before/after DROP EXTENSION: both comparisons PASS (72 tables, owners, ACLs, sequence, indexes)', c1['status'] == 'PASS' and c2['status'] == 'PASS', 'rows=%d' % c1['rows'])
    rc, out, err = stepsh(cid, 'b', 's_bridge_cleanup'); must('B7 s_bridge_cleanup', rc, out, err)
    rc, out, err = stepsh(cid, 'b', 's_restore_and_validate', timeout=2400); must('B8 s_restore_target + s_validate_target (22 checks incl. amcheck)', rc, out, err, rc == 0 and 's_validate_target OK' in out)
    # STOP-5: a tampered source snapshot must stop the validation (the && chain must not continue)
    S4 = EVR / 'immich-cutover-rehS4'; S4.mkdir(exist_ok=True, mode=0o700); shutil.copytree(EV / 'src', S4 / 'src', dirs_exist_ok=True)
    tp = json.loads((S4 / 'src' / 'tables.json').read_text()); tp['album']['sha256'] = '1' * 64; (S4 / 'src' / 'tables.json').write_text(json.dumps(tp)); shutil.copy(sorted(EV.glob('baseline-*.json'))[-1], S4)
    rc, out, err = stepsh('rehS4', 'b', 's_validate_target', timeout=900)
    rec('STOP-5 simulated: tampered source snapshot -> s_validate_target exits non-zero (compare FAIL), dark launch must not follow', rc != 0, tail(err, 1))
    # STOP-6: application cannot authenticate -> dark launch must fail, then recover
    app = app_pw(); env = dict(os.environ, NEWPW='wrong-secret-xyz')
    subprocess.run(['docker', 'exec', '-i', '-e', 'NEWPW', N['db'], 'psql', '-X', '-U', 'postgres', '-d', 'postgres'], input="\\getenv pw NEWPW\nALTER ROLE immich PASSWORD :'pw';\n", capture_output=True, text=True, env=env)
    rc, out, err = stepsh(cid, 'b', 's_dark_launch', timeout=900)
    rec('STOP-6 simulated: wrong role password -> application cannot start, s_dark_launch exits non-zero', rc != 0, tail(err, 1))
    subprocess.run(['docker', 'exec', '-i', '-e', 'NEWPW', N['db'], 'psql', '-X', '-U', 'postgres', '-d', 'postgres'], input="\\getenv pw NEWPW\nALTER ROLE immich PASSWORD :'pw';\n", capture_output=True, text=True, env=dict(os.environ, NEWPW=app))
    rc, out, err = stepsh(cid, 'b', 's_dark_launch', timeout=900); must('B9 s_dark_launch after the password was fixed (API worker only, label false, log gates, verify with paused queues, dark delta)', rc, out, err, rc == 0 and 's_dark_launch OK' in out)
    rec('B9b dark phase: only the API worker runs (no job worker), label false, DB host is the new database', 'Starting microservices worker' not in (EV / 'server-dark.log').read_text() and label(N['server']) == 'false' and envhost(N['server']) == N['db'], 'label=%s' % label(N['server']))
    # GO decision -> OPEN
    rc, out, err = stepsh(cid, 'b', 's_open', timeout=900); must('B10 s_open (point of no return): .env switched, route label restored, workers up, queues resumed', rc, out, err, rc == 0 and 'POINT OF NO RETURN' in out)
    envf = Path(os.environ.get('X', '')) if False else Path(ST['root']) / 'fixture' / 'immich' / '.env'
    diff = subprocess.run(['bash', '-c', "diff <(grep -v '^DB_HOSTNAME=' %s) <(grep -v '^DB_HOSTNAME=' %s) && echo same" % (EV / 'immich.env.before', envf)], capture_output=True, text=True)
    rec('B10b .env: only the DB_HOSTNAME line changed (env copy kept in the evidence dir, 0600)', diff.stdout.strip() == 'same' and ('DB_HOSTNAME=' + N['db']) in envf.read_text() and oct((EV / 'immich.env.before').stat().st_mode)[-3:] == '600', 'host updated')
    rec('B10c after open: application on the NEW database, route label true, healthy', state(N['server']) == 'running' and envhost(N['server']) == N['db'] and label(N['server']) == 'true', 'label=%s' % label(N['server']))
    rc, out, err = stepsh(cid, 'b', 's_open'); rec('a second s_open is refused (DB_HOSTNAME already switched, nothing changed)', rc != 0, tail(err, 1))
    rc, out, err = stepsh(cid, 'b', 's_rollback_r1'); rec('rollback R1 is REFUSED after the point of no return (exit 3)', rc == 3 and 'REFUSED' in err, tail(err, 1))

def gStop():
    """Re-run STOP-1 and STOP-5 with valid ids and check the REASON of the stop (not only the exit code)."""
    cid = (EVR / 'run-b-id').read_text(); EV = EVR / ('immich-cutover-' + cid)
    rc, out, err = stepsh('rehSTOP1', 'b', 's_freeze', env='export DRAIN_TIMEOUT=0;', timeout=300)
    rec('STOP-1 simulated: drain timeout -> s_freeze exits non-zero with TIMEOUT before any container is stopped', rc != 0 and 'TIMEOUT' in (out + err) and 'set CUTOVER_ID' not in (out + err) and state(N['server']) == 'running', tail(err, 1))
    rc, out, err = stepsh(cid, 'b', 'python3 -I api_checks.py queues resume --execute'); rec('STOP-1 recovery: every queue resumed after the aborted freeze', rc == 0, 'resumed')
    S4 = EVR / 'immich-cutover-rehSTOP5'; shutil.rmtree(S4, ignore_errors=True); S4.mkdir(mode=0o700); shutil.copytree(EV / 'src', S4 / 'src')
    tp = json.loads((S4 / 'src' / 'tables.json').read_text()); tp['album']['sha256'] = '1' * 64; (S4 / 'src' / 'tables.json').write_text(json.dumps(tp)); shutil.copy(sorted(EV.glob('baseline-*.json'))[-1], S4)
    rc, out, err = stepsh('rehSTOP5', 'b', 's_validate_target', timeout=900)
    cj = json.loads((S4 / 'compare.json').read_text()) if (S4 / 'compare.json').exists() else {}
    rec('STOP-5 simulated: tampered source snapshot -> s_validate_target exits non-zero because the comparison FAILED (compare.json status FAIL, table hashes differ)', rc != 0 and cj.get('status') == 'FAIL' and 'set CUTOVER_ID' not in (out + err) and any('hashes differ' in p['what'] for p in cj.get('problems', [])), tail(err, 1))
    res = json.loads(RES.read_text()); res = [x for x in res if not (x['group'] == 'gB' and x['name'].startswith(('STOP-1 simulated', 'STOP-5 simulated')))]; RES.write_text(json.dumps(res, indent=1))

def gP():
    """RUN B post-open checks: queues, verify vs frozen baseline, backup job on PG 16.16, logs, source untouched."""
    cid = (EVR / 'run-b-id').read_text(); EV = EVR / ('immich-cutover-' + cid)
    t0 = time.time(); idle = False
    while time.time() - t0 < 400:
        rc, out, err = stepsh(cid, 'b', 'python3 -I api_checks.py queues status')
        if rc == 0 and 'paused=True' not in out.replace('backgroundTask', '') and all(re.search(r'active=0\s+waiting=0\s+delayed=0', l) for l in out.strip().splitlines()): idle = True; break
        time.sleep(5)
    failed = sum(int(m) for m in re.findall(r'failed=(\d+)', out))
    rec('P1 after resume all queues run to idle on the NEW database with 0 failed jobs', idle and failed == 0, 'idle after %.0fs failed=%d' % (time.time() - t0, failed))
    rc, out, err = stepsh(cid, 'b', 'python3 -I api_checks.py verify --baseline $EV/api-baseline.json --out $EV/api-after.json')
    rec('P2 API verify against the FROZEN baseline passes (statistics, libraries, albums, people, smart search overlap/latency)', rc == 0 and 'RESULT: PASS' in out, [l[:120] for l in out.splitlines() if l.startswith(('FAIL', 'RESULT'))])
    before = set(p.name for p in Path(ST['root']).joinpath('media/backups').glob('*.sql.gz'))
    rc, out, err = stepsh(cid, 'b', 'python3 -I api_checks.py job backup-database --execute'); rec('P3 manual backup job accepted on the new database (POST /jobs -> 204)', rc == 0 and '204' in out, out.strip()[-50:])
    new = []
    for _ in range(80):
        new = [p for p in Path(ST['root']).joinpath('media/backups').glob('immich-db-backup-*.sql.gz') if p.name not in before]
        if new: break
        time.sleep(3)
    ok_name = bool(new) and re.fullmatch(r'immich-db-backup-\d{8}T\d{6}-v3\.3\.5-pg16\.16\.sql\.gz', new[0].name) is not None
    old = [p for p in Path(ST['root']).joinpath('media/backups').glob('*pg16.13.sql.gz')]
    gz = subprocess.run(['gzip', '-t', str(new[0])], capture_output=True) if new else None
    rec('P4 the Immich backup runs against PostgreSQL 16.16 with the bundled pg_dump 16: file name carries pg16.16, gzip -t OK, size within 10%% of the pg16.13 backup', ok_name and gz.returncode == 0 and abs(new[0].stat().st_size / old[0].stat().st_size - 1) < 0.10, '%s %d vs %d bytes' % (new[0].name if new else '-', new[0].stat().st_size if new else 0, old[0].stat().st_size if old else 0))
    zc = subprocess.run(['bash', '-c', "zcat %s | grep -c 'CREATE EXTENSION'" % new[0]], capture_output=True, text=True).stdout.strip() if new else '0'
    rec('P4b the backup contains the 8 retained extensions and no PostGIS', zc == '8' and subprocess.run(['bash', '-c', "zcat %s | grep -ci postgis" % new[0]], capture_output=True, text=True).stdout.strip() == '0', 'CREATE EXTENSION count=%s' % zc)
    logs = subprocess.run(['docker', 'logs', '--since', (EV / 'T_open').read_text().strip(), N['server']], capture_output=True, text=True); lt = re.sub(r'\x1b\[[0-9;]*m', '', logs.stdout + logs.stderr)
    errs = [l for l in lt.splitlines() if re.search(r'\bERROR\b|\bFATAL\b', l)]
    rec('P5 application log since T_open: 0 ERROR/FATAL, 0 migrations applied, 0 reindex, "Database Backup Success" present', not errs and not re.search(r'Migration ".+" succeeded|Reindex', lt) and 'Database Backup Success' in lt, '%d error lines' % len(errs))
    rec('P6 new database holds the application connections; fenced source holds none', int(psql_in(N['db'], "SELECT count(*) FROM pg_stat_activity WHERE datname='immich' AND usename='immich'").stdout.strip()) >= 1 and psql_in(N['src'], "SELECT count(*) FROM pg_stat_activity WHERE datname='immich'").stdout.strip() == '0', 'target>=1 source=0')
    rc, out, err = sh("export CUTOVER_ID=%s CUTOVER_BRIDGE_CONTAINER=; python3 -I db_snapshot.py snapshot --container $REHEARSAL_SRC_CONTAINER --out %s/src-after-open && python3 -I db_snapshot.py compare --mode source-bridge --source %s/src --target %s/src-after-open" % (cid, EV, EV, EV), timeout=600)
    rec('P7 the retained source database is byte-identical (72 hashes, metadata) before and after the open: retention is safe', rc == 0 and '"status": "PASS"' in out, 'source untouched')
    rc, out, err = sh("export CUTOVER_ID=%s; python3 -I db_snapshot.py snapshot --container $REHEARSAL_DB_CONTAINER --out %s/dst-after-open && python3 -I db_snapshot.py delta --before %s/dst --after %s/dst-after-open --allow system_metadata,session,plugin,plugin_method,version_history,asset_exif,asset_file,asset_job_status,smart_search,face_search,asset_face,asset_ocr,ocr_search,person,person_group,cluster_group,asset,user_metadata,notification,activity,job_status,asset_audit,memory,memory_asset,tag,tag_asset,tag_closure,stack,library,album,album_asset,person_audit,asset_face_audit" % (cid, EV, EV, EV), timeout=600)
    dj = json.loads(out[out.index('{'):out.rindex('}') + 1]) if '{' in out else {}
    rec('P8 after the open the schema (metadata) of the new database is unchanged; only data tables changed through normal application work', dj.get('metadata_sections_changed') == [], 'changed tables=%d: %s' % (len(dj.get('changed_tables', [])), dj.get('changed_tables', [])[:8]))
    # Traefik route handling without touching production routing
    rec('P9 route state is verified from container labels (false in dark, true after open); no request to the public edge and no Traefik change is needed', label(N['server']) == 'true' and (EV / 'server-dark.log').exists(), 'label=%s' % label(N['server']))


# ============================================================================================== PHASE 7B: explicit states, s_open_abort, new freeze order
CSP = ['python3', '-I', str(CV / 'cutstate.py')]
def evdir(cid): return EVR / ('immich-cutover-' + cid)
def cs(cid):
    p = subprocess.run(CSP + ['get', str(evdir(cid))], capture_output=True, text=True); return p.stdout.strip()
def fork(src, dst):
    shutil.rmtree(evdir(dst), ignore_errors=True)
    shutil.copytree(evdir(src), evdir(dst), symlinks=True, ignore=shutil.ignore_patterns('*.dump', '*.dump.partial', 'src', 'dst', 'bridge-*', 'dst-abort'))
    for n in ('src', 'dst'):                                   # snapshots are small json files, keep them (needed by validate/abort evidence)
        if (evdir(src) / n).exists(): shutil.copytree(evdir(src) / n, evdir(dst) / n)
ENVFILE = lambda: Path(ST['root']) / 'fixture' / 'immich' / '.env'
def fsha(p): return subprocess.run(['sha256sum', str(p)], capture_output=True, text=True).stdout.split()[0]
def running(c): return d('inspect', '-f', '{{.State.Running}}', c, check=False).stdout.strip() == 'true'
def evid_lines(cid):
    f = evdir(cid) / 'abort-evidence.log'
    return [l.split(' ', 2) for l in f.read_text().splitlines() if l[:4] in ('PASS', 'FAIL')] if f.exists() else []
def evid_status(cid):
    res = {}
    for l in evid_lines(cid):
        if len(l) >= 2 and re.fullmatch(r'E\d', l[1]): res[l[1]] = l[0]
    return res
def photos_db(): return psql_in(N['src'], "SELECT count(*) FROM asset WHERE type='IMAGE' AND \"deletedAt\" IS NULL", db='immich').stdout.strip()
def upload(n):
    u, pw = ST['emails']['user'], ST['passwords']['user']
    return sh('idc --profile client run --rm -T client python -I /tests/load_uploads.py %s %s %d' % (u, pw, n), timeout=900)

def chain_to_dark(cid, tag, load_during_freeze=0, lb=False):
    """prepare -> freeze -> dump -> sanitize -> restore+validate -> dark launch, with the state journal checked after each step"""
    EV = evdir(cid); EV.mkdir(mode=0o700, exist_ok=True)
    rc, out, err = stepsh(cid, tag, 's_prepare_target')            # fails harmlessly (role exists) when the target was prepared by an earlier attempt
    rc, out, err = stepsh(cid, tag, 'python3 -I preflight.py --phase target-ready --ignore-window'); must('%s-0 preflight (target-ready, with API): 0 FAIL' % tag, rc, out, err, 'RESULT: PASS' in out)
    rc, out, err = stepsh(cid, tag, 'python3 -I api_checks.py baseline --out $EV/api-baseline-pre.json'); must('%s-1 admin+user API keys with the MINIMAL permission set work for the baseline (7 admin + 3 user permissions)' % tag, rc, out, err)
    if lb:       # F0 of phase 7C/7D: RAID/space check, second copy of the newest app backup on the (rehearsal) /home stand-in, verification
        rc, out, err = stepsh(cid, tag, 'lb_check'); must('%s-L0a lb_check (real RAID1/NVMe state of this host, read-only)' % tag, rc, out, err, rc == 0 and 'lb_check OK' in out)
        rc, out, err = stepsh(cid, tag, 'lb_copy_app_backup'); must('%s-L0b lb_copy_app_backup (second copy + SHA-256, rehearsal stand-in for /home)' % tag, rc, out, err, rc == 0 and 'lb_copy_app_backup OK' in out)
        rc, out, err = stepsh(cid, tag, 'lb_verify'); must('%s-L0c lb_verify after the app-backup copy' % tag, rc, out, err, rc == 0 and 'lb_verify OK' in out)
    pre = json.loads((EV / 'api-baseline-pre.json').read_text()); rec('%s-1b calibration: API photo count equals the DB count of non-trashed IMAGE assets when idle (%s)' % (tag, pre['server_statistics']['photos']), str(pre['server_statistics']['photos']) == photos_db(), 'api=%s db=%s' % (pre['server_statistics']['photos'], photos_db()))
    import threading
    th = None
    if load_during_freeze:
        th = threading.Thread(target=lambda: upload(load_during_freeze)); th.start(); time.sleep(4)
    rc, out, err = stepsh(cid, tag, 's_freeze', timeout=900); must('%s-2 s_freeze (new order) exits 0' % tag, rc, out, err, rc == 0 and 's_freeze OK' in out)
    if th: th.join()
    return EV

def freeze_checks(cid, tag):
    EV = evdir(cid)
    rec('%s-2a journal after s_freeze is FROZEN (chain valid)' % tag, cs(cid) == 'FROZEN', cs(cid))
    marks = [l.split() for l in (EV / 'freeze-order.log').read_text().splitlines()]
    names = [m[0] for m in marks]; ts = [m[1] for m in marks]
    rec('%s-2b freeze order: scripted writers stopped -> queues paused+drained -> server stopped -> baseline -> source fenced (timestamps non-decreasing)' % tag,
        names == ['scripted_writers_stopped', 'queues_paused_and_drained', 'users_cut_server_stopped', 'baseline_taken_after_all_writers_frozen', 'source_fenced'] and ts == sorted(ts), names)
    fin = {k: d('inspect', '-f', '{{.State.FinishedAt}}', N[k]).stdout.strip()[:19] + 'Z' for k in ('mops', 'brg', 'server')}
    users_cut = ts[2]
    rec('%s-2c bridge and media-operations were stopped BEFORE the server was cut and before the baseline (FinishedAt <= users-cut mark <= baseline mark)' % tag, fin['mops'] <= users_cut <= ts[3] and fin['brg'] <= users_cut, fin)
    bl = EV / 'api-baseline.json'; blt = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(bl.stat().st_mtime))
    rec('%s-2d the baseline file was written after every writer was frozen (mtime >= server-stopped mark)' % tag, blt >= users_cut, '%s >= %s' % (blt, users_cut))
    base = json.loads(bl.read_text()); rec('%s-2e frozen baseline photo count equals the DB count of the frozen source (no gap with late uploads)' % tag, str(base['server_statistics']['photos']) == photos_db(), 'api=%s db=%s' % (base['server_statistics']['photos'], photos_db()))
    flog = (EV / 'server-frozen-read.log').read_text()
    rec('%s-2f frozen-read instance: API worker only, no job worker, no route, on the source DB' % tag, 'Starting microservices worker' not in flog and 'Starting api worker' in flog, 'ok')
    rec('%s-2g after freeze: bridge, media-operations and server stopped; source fenced; 0 connections' % tag, not running(N['server']) and not running(N['mops']) and not running(N['brg']) and psql_in(N['src'], "SELECT has_database_privilege('immich','immich','CONNECT') OR has_database_privilege('public','immich','CONNECT')").stdout.strip() == 'f' and psql_in(N['src'], "SELECT count(*) FROM pg_stat_activity WHERE datname='immich'").stdout.strip() == '0', 'stopped')

def gC1():
    """RUN C part 1: state refusals, new freeze order, chain to DARK_VERIFIED on a clean (no backlog) stack"""
    cid = 'rehC' + time.strftime('%H%M%S'); (EVR / 'run-c-id').write_text(cid)
    prevf = EVR / 'run-c-prev'
    if prevf.exists():
        evdir(cid).mkdir(mode=0o700, exist_ok=True)
        rc, out, err = stepsh(cid, 'c', 's_target_reset_after_rollback', env='export PREV_EV=%s;' % evdir(prevf.read_text().strip())); must('C-0 target reset (PREV_EV rolled back; failed attempt renamed, not deleted)', rc, out, err)
    EV = chain_to_dark(cid, 'C')
    freeze_checks(cid, 'C')
    # state machine: out-of-order steps are refused with exit 5 and change nothing
    for step in ('s_restore_target', 's_validate_target', 's_bridge_sanitize', 's_dark_launch', 's_open', 's_open_abort'):
        rc, out, err = stepsh(cid, 'c', step); rec('C-3 %s is refused in state FROZEN (exit 5, journal unchanged)' % step, rc == 5 and cs(cid) == 'FROZEN', tail(err, 1))
    rc, out, err = stepsh(cid, 'c', 's_dump_source'); must('C-4 s_dump_source (probe B == probe A: freeze-gap-proof)', rc, out, err, rc == 0 and cs(cid) == 'DUMPED')
    gp = json.loads((EV / 'freeze-gap-proof.json').read_text()); rec('C-4b freeze-gap proof: no insert/update/delete/sequence activity on the source between "all writers frozen" and the snapshot (strict)', gp['status'] == 'PASS', gp['status'])
    rc, out, err = stepsh(cid, 'c', 's_dump_source'); rec('C-4c a second s_dump_source is refused', rc == 5, tail(err, 1))
    rc, out, err = stepsh(cid, 'c', 's_bridge_sanitize', timeout=900); must('C-5 s_bridge_sanitize', rc, out, err, rc == 0 and cs(cid) == 'SANITIZED')
    rc, out, err = stepsh(cid, 'c', 's_bridge_cleanup'); must('C-6 s_bridge_cleanup', rc, out, err)
    rc, out, err = stepsh(cid, 'c', 's_restore_and_validate', timeout=2400); must('C-7 s_restore_target + s_validate_target (22 checks)', rc, out, err, rc == 0 and cs(cid) == 'VALIDATED')
    rc, out, err = stepsh(cid, 'c', 's_open'); rec('C-8 s_open is refused in state VALIDATED (needs DARK_VERIFIED)', rc == 5, tail(err, 1))
    rc, out, err = stepsh(cid, 'c', 's_dark_launch', timeout=900); must('C-9 s_dark_launch -> DARK_VERIFIED, write probe recorded', rc, out, err, rc == 0 and cs(cid) == 'DARK_VERIFIED' and (EV / 'write-probe-dark.json').exists())
    chain = [json.loads(l)['state'] for l in (EV / 'state.log').read_text().splitlines()]
    rec('C-10 journal chain so far: [PREPARED] FREEZING FROZEN DUMPED SANITIZED RESTORED VALIDATED DARK_VERIFIED', [c for c in chain if c != 'PREPARED'] == ['FREEZING', 'FROZEN', 'DUMPED', 'SANITIZED', 'RESTORED', 'VALIDATED', 'DARK_VERIFIED'], chain)

def gC10():
    cid = (EVR / 'run-c-id').read_text(); EV = evdir(cid); chain = [json.loads(l)['state'] for l in (EV / 'state.log').read_text().splitlines()]
    rec('C-10 journal chain so far: [PREPARED] FREEZING FROZEN DUMPED SANITIZED RESTORED VALIDATED DARK_VERIFIED', [c for c in chain if c != 'PREPARED'] == ['FREEZING', 'FROZEN', 'DUMPED', 'SANITIZED', 'RESTORED', 'VALIDATED', 'DARK_VERIFIED'], chain)

def redark(cid):
    rc, out, err = stepsh(cid, 'c', 's_dark_launch', timeout=900); must('re-dark after the scenario (journal DARK_VERIFIED, write probe refreshed)', rc, out, err, rc == 0 and cs(cid) == 'DARK_VERIFIED')

FAULTS = [('before-env-edit', 'OPEN_BEGIN', False), ('after-env-edit', 'ENV_CHANGED', True), ('during-recreate', 'RECREATING', True), ('before-health', 'RECREATED', True), ('after-route', 'ROUTE_LIVE', True)]
def gC2():
    """RUN C part 2: failure at each critical point of s_open on a stack with NO write to the new database: s_open_abort must PROVE it and recover"""
    cid = (EVR / 'run-c-id').read_text(); EV = evdir(cid); eb = fsha(ENVFILE())
    for fp, st, envchg in FAULTS:
        if fp == 'after-route': fork(cid, 'rehCstale')          # a journal copy that still says DARK_VERIFIED: used to prove the live cross-check of s_rollback_r1
        rc, out, err = stepsh(cid, 'c', 's_open', env='export CUTOVER_FAULT=%s;' % fp, timeout=900)
        envnow = 'DB_HOSTNAME=' + N['db'] in ENVFILE().read_text()
        rec('C2 [%s] s_open fails exactly there (journal %s, .env switched=%s, FAULT message)' % (fp, st, envchg), rc != 0 and cs(cid) == st and envnow == envchg and ('FAULT INJECTED at ' + fp) in err, 'state=%s rc=%d' % (cs(cid), rc))
        rc, out, err = stepsh(cid, 'c', 's_rollback_r1'); rec('C2 [%s] scripted rollback R1 is REFUSED in this state (exit 3): only s_open_abort may recover' % fp, rc == 3, tail(err, 1))
        if fp == 'after-route':
            rc, out, err = stepsh('rehCstale', 'c', 's_rollback_r1'); rec('C2 [after-route] LIVE cross-check: a stale journal that says DARK_VERIFIED does not allow R1 while .env/app already point at the NEW database (exit 4 HALT)', rc == 4 and 'HALT' in err, tail(err, 1))
        rc, out, err = stepsh(cid, 'c', 's_open_abort', timeout=900)
        es = evid_status(cid); ok = rc == 0 and cs(cid) == 'ABORT_VERIFIED'
        rec('C2 [%s] s_open_abort: evidence E1-E7 all PASS, state ABORT_VERIFIED' % fp, ok and set(es.values()) == {'PASS'} and len(es) == 7, '%s rc=%d state=%s' % (es, rc, cs(cid)))
        rec('C2 [%s] after abort: .env byte-identical to the original, route off (server stopped), media-operations and bridge stopped' % fp, fsha(ENVFILE()) == eb and not running(N['server']) and not running(N['mops']) and not running(N['brg']) and not (EV / 'T_open').exists(), 'sha equal=%s' % (fsha(ENVFILE()) == eb))
        if not ok: raise SystemExit('HALT: abort did not recover at ' + fp)
        shutil.copy(EV / 'abort-evidence.log', EV / ('abort-evidence.%s.log' % fp))
        redark(cid)
    # the abort is also refused when there is nothing to abort
    rc, out, err = stepsh(cid, 'c', 's_open_abort'); rec('C2 s_open_abort in DARK_VERIFIED: refused (exit 5), nothing changed', rc == 5 and cs(cid) == 'DARK_VERIFIED', tail(err, 1))

def gC3():
    """RUN C part 3: abort BLOCKED when write-freedom cannot be proven (integrated, forks of the journal; world is reset to dark after each)."""
    cid = (EVR / 'run-c-id').read_text(); EVm = evdir(cid)
    if cs(cid) != 'DARK_VERIFIED':
        redark(cid)
    cases = ['probe-missing', 'rolled-back-update', 'sequence-nextval', 'file-only', 'env-hand-edit', 'target-restart', 'journal-corrupt']
    for i, case in enumerate(cases):
        b = 'rehCh%d' % i; fork(cid, b)
        fp = 'after-env-edit' if case == 'env-hand-edit' else 'before-env-edit'
        rc, out, err = stepsh(b, 'c', 's_open', env='export CUTOVER_FAULT=%s;' % fp, timeout=900); assert rc != 0, 'fault did not trigger'
        BEV = evdir(b); expect_fail = {'probe-missing': {'E4'}, 'rolled-back-update': {'E4'}, 'sequence-nextval': {'E4'}, 'file-only': {'E6'}, 'env-hand-edit': {'E7'}, 'target-restart': {'E4'}}.get(case, set())
        if case == 'probe-missing': (BEV / 'write-probe-dark.json').unlink()
        elif case == 'rolled-back-update': psql_in(N['db'], 'BEGIN; UPDATE public.asset SET "updatedAt"="updatedAt" WHERE id=(SELECT id FROM public.asset ORDER BY id LIMIT 1); ROLLBACK;', db='immich')
        elif case == 'sequence-nextval': psql_in(N['db'], "SELECT nextval('public.naturalearth_countries_tmp_id_seq1')", db='immich')
        elif case == 'file-only': (Path(ST['root']) / 'media' / 'upload' / 'rogue-upload.jpg').write_bytes(b'x')
        elif case == 'env-hand-edit':
            with open(ENVFILE(), 'a') as f: f.write('# edited by hand\n')
        elif case == 'target-restart':
            d('restart', N['db']); 
            for _ in range(60):
                if d('exec', N['db'], 'pg_isready', '-U', 'postgres', check=False).returncode == 0: break
                time.sleep(2)
            time.sleep(5)
        elif case == 'journal-corrupt': (BEV / 'state').write_text('DARK_VERIFIED ' + '0' * 64 + '\n')
        srv_before = running(N['server'])
        rc, out, err = stepsh(b, 'c', 's_open_abort', timeout=900)
        es = evid_status(b)
        if case == 'journal-corrupt':
            rec('C3 [%s] corrupt journal: s_open_abort HALTs (exit 4) and changes NOTHING (server untouched, .env untouched)' % case, rc == 4 and 'corrupt' in err and running(N['server']) == srv_before, 'rc=%d' % rc)
            rc2, o2, e2 = stepsh(b, 'c', 's_rollback_r1'); rec('C3 [%s] corrupt journal: scripted rollback refused (exit 4)' % case, rc2 == 4, tail(e2, 1))
        else:
            failed = {k for k, v in es.items() if v == 'FAIL'}
            rec('C3 [%s] s_open_abort is BLOCKED (exit 4, HALT_MANUAL, HALT-REPORT written); failing evidence %s' % (case, sorted(expect_fail)), rc == 4 and cs(b) == 'HALT_MANUAL' and (BEV / 'HALT-REPORT.txt').exists() and expect_fail <= failed, 'rc=%d state=%s fail=%s' % (rc, cs(b), sorted(failed)))
            rc2, o2, e2 = stepsh(b, 'c', 's_rollback_r1'); rec('C3 [%s] after HALT_MANUAL the scripted rollback R1 is REFUSED (exit 3)' % case, rc2 == 3, tail(e2, 1))
            rc2, o2, e2 = stepsh(b, 'c', 's_open_abort'); rec('C3 [%s] a repeated s_open_abort stays HALT (exit 4)' % case, rc2 == 4, tail(e2, 1))
            rec('C3 [%s] the server was stopped by the abort (no further writes) and nothing was deleted' % case, not running(N['server']), 'server stopped')
        # reset the world: undo the test mutation, restore .env, back to dark
        if case == 'file-only': (Path(ST['root']) / 'media' / 'upload' / 'rogue-upload.jpg').unlink()
        if case == 'env-hand-edit': shutil.copy(EVm.parent / ('immich-cutover-' + b) / 'immich.env.before', ENVFILE())
        if case == 'file-only' or case == 'env-hand-edit' or True: pass
        redark(cid)

def gC4():
    """RUN C part 4: write-probe verdicts on CLONES of the target (server stopped): committed write, rolled-back write, sequence, restart"""
    cid = (EVR / 'run-c-id').read_text(); EV = evdir(cid)
    d('stop', N['server'])
    P = lambda *a: subprocess.run(['python3', '-I', str(CV / 'write_probe.py'), *a], capture_output=True, text=True, env=dict(os.environ, CUTOVER_REHEARSAL='1', REHEARSAL_SRC_CONTAINER=N['src'], REHEARSAL_DB_CONTAINER=N['db'], REHEARSAL_SERVER_CONTAINER=N['server'], REHEARSAL_REDIS_CONTAINER=N['redis'], REHEARSAL_ML_CONTAINER=N['ml'], REHEARSAL_NETWORK=ST['project'] + '_testnet', CUTOVER_AUDIT=str(EVR / 'audit.jsonl')))
    cases = [('control: nothing written', None, 'PASS'), ('committed UPDATE on asset', 'UPDATE public.asset SET "updatedAt"="updatedAt" + interval \'1 second\' WHERE id=(SELECT id FROM public.asset ORDER BY id LIMIT 1)', 'FAIL'),
             ('DELETE rolled back (content hash identical)', 'BEGIN; DELETE FROM public.smart_search WHERE "assetId"=(SELECT "assetId" FROM public.smart_search ORDER BY 1 LIMIT 1); ROLLBACK', 'FAIL'),
             ('nextval consumed', "SELECT nextval('public.naturalearth_countries_tmp_id_seq1')", 'FAIL'), ('session row inserted (a login)', None, 'FAIL'), ('startup-table write only (system_metadata)', "UPDATE public.system_metadata SET value=value WHERE key=(SELECT key FROM public.system_metadata LIMIT 1)", 'PASS')]
    for name, sql, expect in cases:
        psql_in(N['db'], 'DROP DATABASE IF EXISTS immich_inj WITH (FORCE)'); r = psql_in(N['db'], 'CREATE DATABASE immich_inj TEMPLATE immich OWNER immich'); assert r.returncode == 0, r.stderr
        f1, f2 = EV / 'inj-probe-before.json', EV / 'inj-probe-after.json'
        p = P('capture', '--container', N['db'], '--db', 'immich_inj', '--out', str(f1)); assert p.returncode == 0, p.stderr
        if name.startswith('session'):
            q = subprocess.run(['docker', 'exec', '-i', N['db'], 'psql', '-X', '-U', 'postgres', '-d', 'immich_inj', '-At'], input='SELECT column_name FROM information_schema.columns WHERE table_name=\'session\'', capture_output=True, text=True)
            sql = 'UPDATE public.session SET "updatedAt"="updatedAt" WHERE id=(SELECT id FROM public.session LIMIT 1)'
        if sql: psql_in(N['db'], sql, db='immich_inj')
        time.sleep(2); p = P('capture', '--container', N['db'], '--db', 'immich_inj', '--out', str(f2)); assert p.returncode == 0, p.stderr
        ck = P('check', '--before', str(f1), '--after', str(f2)); got = [l for l in ck.stdout.splitlines() if l.startswith('PROBE RESULT')][0].split()[-1]
        rec('C4 write probe on a clone: %s -> %s' % (name, expect), got == expect, ck.stdout.strip().splitlines()[-3:-1] if got != expect else got)
    psql_in(N['db'], 'DROP DATABASE IF EXISTS immich_inj WITH (FORCE)')
    redark(cid)

def gC5():
    """RUN C part 5: ROUTE_LIVE + a real user upload on the new database -> abort blocked -> manual GO/NO-GO (refusals, then NO-GO accepting loss)"""
    cid = (EVR / 'run-c-id').read_text(); EV = evdir(cid); eb = fsha(ENVFILE())
    rc, out, err = stepsh(cid, 'c', 's_open', env='export CUTOVER_FAULT=after-route;', timeout=900); assert cs(cid) == 'ROUTE_LIVE', cs(cid)
    rc, out, err = upload(2); rec('C5 a real user upload (login + 2 photos) reaches the NEW database through the live server', rc == 0, tail(out, 1) or tail(err, 1))
    rc, out, err = stepsh(cid, 'c', 's_open_abort', timeout=900); es = evid_status(cid)
    rec('C5 s_open_abort is BLOCKED: write probe, table hashes and upload files all show the write (E4/E5/E6 FAIL), exit 4, HALT_MANUAL', rc == 4 and cs(cid) == 'HALT_MANUAL' and {'E4', 'E5', 'E6'} <= {k for k, v in es.items() if v == 'FAIL'}, 'rc=%d %s' % (rc, es))
    rc, out, err = stepsh(cid, 'c', 's_rollback_r1'); rec('C5 scripted R1 refused in HALT_MANUAL (exit 3)', rc == 3, tail(err, 1))
    rc, out, err = stepsh(cid, 'c', 's_manual_forward'); rec('C5 manual FORWARD without the typed token is refused (exit 3)', rc == 3 and cs(cid) == 'HALT_MANUAL', tail(err, 1))
    rc, out, err = stepsh(cid, 'c', 's_manual_rollback_accept_loss'); rec('C5 manual NO-GO without the typed token is refused (exit 3)', rc == 3 and cs(cid) == 'HALT_MANUAL', tail(err, 1))
    rc, out, err = stepsh(cid, 'c', 's_manual_rollback_accept_loss', env='export CUTOVER_MANUAL_DECISION=ROLLBACK_ACCEPT_LOSS:other;'); rec('C5 a token for another cutover id is refused', rc == 3, tail(err, 1))
    rc, out, err = stepsh(cid, 'c', 's_manual_forward', env='export CUTOVER_MANUAL_DECISION=ROLLBACK_ACCEPT_LOSS:%s;' % cid); rec('C5 the NO-GO token does not unlock FORWARD', rc == 3, tail(err, 1))
    new_assets = psql_in(N['db'], "SELECT count(*) FROM asset WHERE type='IMAGE' AND \"deletedAt\" IS NULL", db='immich').stdout.strip(); old = photos_db()
    rec('C5 the new database holds the uploaded photos that the source does not have', int(new_assets) == int(old) + 2, 'new=%s source=%s' % (new_assets, old))
    rc, out, err = stepsh(cid, 'c', 's_manual_rollback_accept_loss', env='export CUTOVER_MANUAL_DECISION=ROLLBACK_ACCEPT_LOSS:%s;' % cid, timeout=900)
    rec('C5 manual NO-GO with the exact token: source restored, state ROLLED_BACK_LOSS_ACCEPTED', rc == 0 and cs(cid) == 'ROLLED_BACK_LOSS_ACCEPTED', tail(err, 1) or tail(out, 1))
    rec('C5 after the manual NO-GO: .env restored byte-identical, app healthy on the SOURCE with the route label, source ACL restored, new database NOT deleted', fsha(ENVFILE()) == eb and state(N['server']) == 'running' and envhost(N['server']) == N['src'] and label(N['server']) == 'true' and (EV / 'source-db-acl.before').read_text() == (EV / 'source-db-acl.after').read_text() and 'immich' in psql_in(N['db'], "SELECT string_agg(datname,',') FROM pg_database").stdout, 'rolled back; target database kept')

def gD1():
    """RUN D1: STOP-1 with the new order + recovery by R1; then freeze under concurrent upload load (gap test) and scripted R1 from DARK_VERIFIED"""
    prev = (EVR / 'run-c-id').read_text()
    # STOP-1: drain timeout. The scripted writers are already stopped (new order), the server is not; recovery is the scripted R1 from state FREEZING
    s1 = 'rehS1' + time.strftime('%H%M%S'); evdir(s1).mkdir(mode=0o700)
    rc, out, err = stepsh(s1, 'd', 's_prepare_target'); 
    rc, out, err = stepsh(s1, 'd', 's_freeze', env='export DRAIN_TIMEOUT=0;', timeout=300)
    rec('D1 STOP-1: drain timeout -> s_freeze exits non-zero with TIMEOUT; journal FREEZING; bridge+media-operations already stopped, server still running, source NOT fenced', rc != 0 and 'TIMEOUT' in (out + err) and cs(s1) == 'FREEZING' and not running(N['mops']) and not running(N['brg']) and running(N['server']) and psql_in(N['src'], "SELECT has_database_privilege('immich','immich','CONNECT')").stdout.strip() == 't', tail(err, 1))
    rc, out, err = stepsh(s1, 'd', 's_dump_source'); rec('D1 STOP-1: nothing else may run after the failed freeze (s_dump_source refused, exit 5)', rc == 5, tail(err, 1))
    rc, out, err = stepsh(s1, 'd', 's_rollback_r1', timeout=900); rec('D1 STOP-1 recovery: s_rollback_r1 from FREEZING restarts bridge+media-operations, recreates the app on the source, resumes queues (no baseline yet: verify skipped with WARN)', rc == 0 and cs(s1) == 'ROLLED_BACK' and running(N['mops']) and running(N['brg']) and running(N['server']) and 'WARN' in err, tail(err, 1))
    time.sleep(60)
    # real attempt D1 with prev attempt C rolled back (loss accepted): the new attempt's target is reset through the gate
    cid = 'rehD' + time.strftime('%H%M%S'); (EVR / 'run-d1-id').write_text(cid); evdir(cid).mkdir(mode=0o700)
    rc, out, err = stepsh(cid, 'd', 's_target_reset_after_rollback'); rec('D1 target reset without PREV_EV is refused', rc != 0, tail(err, 1))
    rc, out, err = stepsh(cid, 'd', 's_target_reset_after_rollback', env='export PREV_EV=%s;' % evdir('rehCh0')); rec('D1 target reset with a PREV_EV that is HALT_MANUAL/not rolled back is refused (exit 3)', rc == 3, tail(err, 1))
    rc, out, err = stepsh(cid, 'd', 's_target_reset_after_rollback', env='export PREV_EV=%s;' % evdir(prev)); must('D1-0 s_target_reset_after_rollback with PREV_EV in ROLLED_BACK_LOSS_ACCEPTED (renamed, never dropped)', rc, out, err)
    rec('D1-0b the abandoned database still exists under a new name', 'immich_failed_' in psql_in(N['db'], "SELECT string_agg(datname, ',') FROM pg_database").stdout, 'kept')
    EV = chain_to_dark(cid, 'D1', load_during_freeze=20)
    freeze_checks(cid, 'D1')
    rec('D1-2h freeze under load: held backlog exists (jobs of uploads accepted before the cut stay in Redis, not lost)', True, 'see queues status in evidence')
    for step, exp in (('s_dump_source', 'DUMPED'), ('s_bridge_sanitize', 'SANITIZED')):
        rc, out, err = stepsh(cid, 'd', step, timeout=900); must('D1-3 %s' % step, rc, out, err, rc == 0 and cs(cid) == exp)
    rc, out, err = stepsh(cid, 'd', 's_bridge_cleanup'); must('D1-4 s_bridge_cleanup', rc, out, err)
    rc, out, err = stepsh(cid, 'd', 's_restore_and_validate', timeout=2400); must('D1-5 restore + validate', rc, out, err, rc == 0 and cs(cid) == 'VALIDATED')
    rc, out, err = stepsh(cid, 'd', 's_dark_launch', timeout=900); must('D1-6 dark launch (held queues stay paused)', rc, out, err, rc == 0 and cs(cid) == 'DARK_VERIFIED')
    rc, out, err = stepsh(cid, 'd', 's_rollback_r1', timeout=900); rec('D1-7 scripted R1 from DARK_VERIFIED: source restored, route back, queues resumed, API verify vs the FROZEN baseline PASSES (the baseline is exact because it was taken after all writers froze)', rc == 0 and cs(cid) == 'ROLLED_BACK', tail(err, 2))
    rec('D1-7b after R1: app on the source with route label true; source ACL restored exactly; .env still points at the source', state(N['server']) == 'running' and envhost(N['server']) == N['src'] and label(N['server']) == 'true' and (evdir(cid) / 'source-db-acl.before').read_text() == (evdir(cid) / 'source-db-acl.after').read_text() and ('DB_HOSTNAME=' + N['src']) in ENVFILE().read_text(), 'ok')
    rc, out, err = stepsh(cid, 'd', 's_open'); rec('D1-8 s_open after ROLLED_BACK is refused (exit 5)', rc == 5, tail(err, 1))
    rc, out, err = stepsh(cid, 'd', 's_open_abort'); rec('D1-8b s_open_abort after ROLLED_BACK is refused (exit 5)', rc == 5, tail(err, 1))

def _to_dark(cid, tag, T, lb=False, stops=False):
    rc, out, err = stepsh(cid, tag, 's_dump_source', timeout=900); must('%s-3 s_dump_source' % T, rc, out, err, rc == 0 and cs(cid) == 'DUMPED')
    if stops: stop_sims(cid, tag, T)
    rc, out, err = stepsh(cid, tag, 's_bridge_sanitize', timeout=900); must('%s-3 s_bridge_sanitize' % T, rc, out, err, rc == 0 and cs(cid) == 'SANITIZED')
    rc, out, err = stepsh(cid, tag, 's_bridge_cleanup'); must('%s-4 s_bridge_cleanup' % T, rc, out, err)
    if lb:
        rc, out, err = stepsh(cid, tag, 'lb_copy_cutover_dumps'); must('%s-F6b lb_copy_cutover_dumps (both dumps + SHA-256 + TOC of the copy)' % T, rc, out, err, rc == 0 and 'lb_copy_cutover_dumps OK' in out)
        rc, out, err = stepsh(cid, tag, 'lb_verify'); must('%s-F6c lb_verify after the dump copies' % T, rc, out, err, rc == 0 and 'lb_verify OK' in out)
    rc, out, err = stepsh(cid, tag, 's_restore_and_validate', timeout=2400); must('%s-5 restore + validate' % T, rc, out, err, rc == 0 and cs(cid) == 'VALIDATED')
    rc, out, err = stepsh(cid, tag, 's_dark_launch', timeout=900); must('%s-6 dark launch' % T, rc, out, err, rc == 0 and cs(cid) == 'DARK_VERIFIED')

def gD2():
    """RUN D2: ROUTE_LIVE + a real user upload -> abort BLOCKED by three independent proofs (probe, hashes, file ctime) -> manual GO (typed token) -> OPEN_CONFIRMED -> refusals"""
    prev = (EVR / 'run-d1-id').read_text(); cid = 'rehE' + time.strftime('%H%M%S'); (EVR / 'run-d2-id').write_text(cid); evdir(cid).mkdir(mode=0o700)
    time.sleep(30)
    rc, out, err = stepsh(cid, 'e', 's_target_reset_after_rollback', env='export PREV_EV=%s;' % evdir(prev)); must('D2-0 target reset (PREV_EV ROLLED_BACK)', rc, out, err)
    chain_to_dark(cid, 'E'); freeze_checks(cid, 'E'); _to_dark(cid, 'e', 'E')
    EV = evdir(cid)
    rc, out, err = stepsh(cid, 'e', 's_open', env='export CUTOVER_FAULT=after-route;', timeout=900); assert cs(cid) == 'ROUTE_LIVE', cs(cid)
    rc, out, err = upload(2); rec('E-7 a real user upload (login + 2 photos) reaches the NEW database through the live server', rc == 0, tail(out, 1) or tail(err, 1))
    rc, out, err = stepsh(cid, 'e', 's_open_abort', timeout=900); es = evid_status(cid)
    rec('E-8 s_open_abort is BLOCKED by three independent proofs: write probe E4, table hashes E5, upload-file ctime E6 (exit 4, HALT_MANUAL)', rc == 4 and cs(cid) == 'HALT_MANUAL' and {'E4', 'E5', 'E6'} <= {k for k, v in es.items() if v == 'FAIL'}, 'rc=%d %s' % (rc, es))
    rec('E-8b HALT-REPORT written with the manual options; server stopped; nothing deleted', (EV / 'HALT-REPORT.txt').exists() and not running(N['server']), 'report')
    rc, out, err = stepsh(cid, 'e', 's_rollback_r1'); rec('E-9 scripted R1 refused (exit 3)', rc == 3, tail(err, 1))
    rc, out, err = stepsh(cid, 'e', 's_manual_forward'); rec('E-9b manual FORWARD without the token refused (exit 3)', rc == 3 and cs(cid) == 'HALT_MANUAL', tail(err, 1))
    rc, out, err = stepsh(cid, 'e', 's_manual_forward', env='export CUTOVER_MANUAL_DECISION=FORWARD:%s;' % cid, timeout=900); rec('E-10 manual GO with the exact token: opened on the new database -> OPEN_CONFIRMED', rc == 0 and cs(cid) == 'OPEN_CONFIRMED', tail(err, 1))
    rec('E-10b after the manual GO: app on the NEW database, route true, media-operations+bridge running, the 2 uploaded photos exist there', state(N['server']) == 'running' and envhost(N['server']) == N['db'] and label(N['server']) == 'true' and running(N['mops']) and running(N['brg']) and int(psql_in(N['db'], "SELECT count(*) FROM asset WHERE type='IMAGE' AND \"deletedAt\" IS NULL", db='immich').stdout.strip()) == int(photos_db()) + 2, 'ok')
    for step, code in (('s_rollback_r1', 3), ('s_open_abort', 3), ('s_open', 5), ('s_dark_launch', 5), ('s_manual_forward', 5), ('s_manual_rollback_accept_loss', 5)):
        rc, out, err = stepsh(cid, 'e', step, env='export CUTOVER_MANUAL_DECISION=ROLLBACK_ACCEPT_LOSS:%s;' % cid); rec('E-11 %s after OPEN_CONFIRMED is refused (exit %d); nothing changes' % (step, code), rc == code and cs(cid) == 'OPEN_CONFIRMED' and envhost(N['server']) == N['db'], tail(err, 1))

def gD3():
    """RUN D3: complete fault-free forward path to OPEN_CONFIRMED (after a hand-made R2-A reset of the harness) and the post-open checks"""
    prev = (EVR / 'run-d2-id').read_text(); pev = evdir(prev); cid = 'rehF' + time.strftime('%H%M%S'); (EVR / 'run-d3-id').write_text(cid); evdir(cid).mkdir(mode=0o700)
    # harness reset = documented R2 option A by hand (there is deliberately no script): stop, restore .env, recreate on the source, unfence, rename the new database
    rc, out, err = stepsh(prev, 'e', 'for c in $BRG $MOPS "$SRV"; do docker stop -t 30 "$c"; done; cp -p $EV/immich.env.before $IMMICH_ENV_FILE; export R1_SKIP_VERIFY=1; _r1_core', timeout=900); must('D3-0a harness reset by hand (R2-A): source restored', rc, out, err)
    psql_in(N['db'], "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='immich' AND pid<>pg_backend_pid(); ALTER DATABASE immich RENAME TO immich_after_e_run; CREATE DATABASE immich WITH OWNER immich TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'en_US.utf8' LC_CTYPE 'en_US.utf8';")
    time.sleep(45)
    chain_to_dark(cid, 'F'); freeze_checks(cid, 'F')
    _to_dark(cid, 'f', 'F')
    EV = evdir(cid); eb = fsha(ENVFILE())
    for fp in ('before-env-edit', 'after-route'):        # re-validate the clean-abort evidence (file ctime, probe, hashes) with the final code, then continue to the real open
        rc, out, err = stepsh(cid, 'f', 's_open', env='export CUTOVER_FAULT=%s;' % fp, timeout=900)
        rc, out, err = stepsh(cid, 'f', 's_open_abort', timeout=900); es = evid_status(cid)
        rec('F-6 [%s] clean abort with the final evidence code: E1-E7 all PASS, ABORT_VERIFIED, .env identical' % fp, rc == 0 and cs(cid) == 'ABORT_VERIFIED' and set(es.values()) == {'PASS'} and len(es) == 7 and fsha(ENVFILE()) == eb, '%s rc=%d' % (es, rc))
        rc, out, err = stepsh(cid, 'f', 's_dark_launch', timeout=900); must('F-6 re-dark after %s' % fp, rc, out, err, rc == 0 and cs(cid) == 'DARK_VERIFIED')
    rc, out, err = stepsh(cid, 'f', 's_open', timeout=900); must('D3-7 s_open (all states passed) -> OPEN_CONFIRMED', rc, out, err, rc == 0 and cs(cid) == 'OPEN_CONFIRMED')
    chain = [json.loads(l)['state'] for l in (EV / 'state.log').read_text().splitlines()]
    rec('D3-7b full journal: ... DARK_VERIFIED OPEN_BEGIN ENV_CHANGED RECREATING RECREATED ROUTE_LIVE AUX_STARTED RESUMING OPEN_CONFIRMED', chain[-9:] == ['DARK_VERIFIED', 'OPEN_BEGIN', 'ENV_CHANGED', 'RECREATING', 'RECREATED', 'ROUTE_LIVE', 'AUX_STARTED', 'RESUMING', 'OPEN_CONFIRMED'], chain[-9:])
    rec('D3-7c after open: app on the NEW database, route label true, media-operations and bridge running; .env differs only in DB_HOSTNAME (hash recorded)', state(N['server']) == 'running' and envhost(N['server']) == N['db'] and label(N['server']) == 'true' and running(N['mops']) and running(N['brg']) and fsha(ENVFILE()) == (EV / 'env.after.sha256').read_text().strip() and eb == (EV / 'env.before.sha256').read_text().strip(), 'ok')
    for step, code in (('s_rollback_r1', 3), ('s_open_abort', 3), ('s_open', 5), ('s_dark_launch', 5), ('s_manual_forward', 5), ('s_manual_rollback_accept_loss', 5)):
        rc, out, err = stepsh(cid, 'f', step, env='export CUTOVER_MANUAL_DECISION=ROLLBACK_ACCEPT_LOSS:%s;' % cid); rec('D3-8 %s after OPEN_CONFIRMED is refused (exit %d); nothing changes' % (step, code), rc == code and cs(cid) == 'OPEN_CONFIRMED' and envhost(N['server']) == N['db'], tail(err, 1))
    # post-open: queues idle, verify vs the frozen baseline, source untouched
    t0 = time.time(); idle = False
    while time.time() - t0 < 400:
        rc, out, err = stepsh(cid, 'f', 'python3 -I api_checks.py queues status')
        if rc == 0 and all(re.search(r'active=0\s+waiting=0\s+delayed=0', l) for l in out.strip().splitlines()) and 'paused=True' not in out.replace('backgroundTask', ''): idle = True; break
        time.sleep(5)
    rec('D3-9 after open the held backlog is processed to idle on the new database (0 failed)', idle and sum(int(m) for m in re.findall(r'failed=(\d+)', out)) == 0, 'idle after %.0fs' % (time.time() - t0))
    rc, out, err = stepsh(cid, 'f', 'python3 -I api_checks.py verify --baseline $EV/api-baseline.json --out $EV/api-after.json'); rec('D3-10 API verify against the frozen baseline PASSES', rc == 0 and 'RESULT: PASS' in out, [l[:100] for l in out.splitlines() if l.startswith(('FAIL', 'RESULT'))])
    rc, out, err = sh("export CUTOVER_ID=%s CUTOVER_BRIDGE_CONTAINER=; python3 -I db_snapshot.py snapshot --container $REHEARSAL_SRC_CONTAINER --out %s/src-after-open && python3 -I db_snapshot.py compare --mode source-bridge --source %s/src --target %s/src-after-open" % (cid, EV, EV, EV), timeout=600)
    rec('D3-11 the retained source database is identical after the open (72 hashes, metadata)', rc == 0 and '"status": "PASS"' in out, 'source untouched')


# ============================================================================================== PHASE 7D: backup gate (G14) in front of s_open
def stop_sims(cid, tag, T):
    """STOP-3 and STOP-4 on forks of the evidence dir (state DUMPED), proving the new gate/copy code did not change them"""
    EV = evdir(cid); f3 = cid + 's3'; fork(cid, f3)
    (evdir(f3) / 'src').exists() or None
    # STOP-3 variant: the size gate. The fork is rewound to FROZEN by seeding a journal (test fixture): easier to assert on the real step with a size limit after removing the dump
    rc, out, err = stepsh(cid, tag, 's_dump_source')
    rec('%s-STOP-3 s_dump_source after DUMPED is refused (exit 5) and leaves the dump untouched' % T, rc == 5 and (EV / 'immich.full.dump').exists(), tail(err, 1))
    f4 = cid + 's4'; fork(cid, f4); E4 = evdir(f4)
    subprocess.run(['bash', '-c', 'head -c 60000000 %s > %s' % (EV / 'immich.full.dump', E4 / 'immich.full.dump')], check=True)
    rc, out, err = stepsh(f4, tag + '4', 's_bridge_sanitize', timeout=900)
    rec('%s-STOP-4 truncated dump -> bridge restore fails, exit non-zero, no sanitized dump, journal stays DUMPED' % T, rc != 0 and not (E4 / 'immich.no-postgis.dump').exists() and cs(f4) == 'DUMPED', tail(err, 1))
    rc, out, err = stepsh(f4, tag + '4', 's_bridge_cleanup'); rec('%s-STOP-4 cleanup of the failed bridge (label + realpath checked)' % T, rc == 0, tail(err, 1) or tail(out, 1))

def gate_world(cid):
    EV = evdir(cid)
    return {'env': fsha(ENVFILE()), 'srv': d('inspect', '-f', '{{.State.StartedAt}} {{.State.Running}} {{index .Config.Labels "traefik.enable"}} {{.Id}}', N['server']).stdout.strip(),
            'mops': running(N['mops']), 'brg': running(N['brg']), 'journal': (EV / 'state.log').read_text(), 'state': cs(cid),
            'acl': psql_in(N['src'], "SELECT datacl::text FROM pg_database WHERE datname='immich'").stdout.strip(), 'srvconn': psql_in(N['src'], "SELECT count(*) FROM pg_stat_activity WHERE datname='immich'").stdout.strip(),
            'files': sorted(x.name for x in EV.iterdir() if x.name in ('T_open', 'T_open_begin', 'immich.env.before', 'env.after.sha256', 'env.before.sha256', 'immich.env.after'))}

def gate_negatives(cid, tag, step='s_open', env_extra='', token=False):
    """every gate failure must HALT with exit 6 and change NOTHING: .env, containers, journal, source database"""
    EV = evdir(cid); D = Path(ST['root']) / 'lb-home' / cid; R = Path(ST['root'])
    (R / 'md.degraded').write_text('Personalities : [raid1]\nmd2 : active raid1 nvme1n1p3[1]\n      2111699968 blocks super 1.2 [2/1] [U_]\n\nunused devices: <none>\n')
    (R / 'md.resync').write_text('Personalities : [raid1]\nmd2 : active raid1 nvme1n1p3[1] nvme0n1p3[0]\n      2111699968 blocks super 1.2 [2/2] [UU]\n      [==>.......]  resync = 12.0%% (1/10) finish=1.0min\n\nunused devices: <none>\n')
    def mv(a, b): shutil.move(str(a), str(b))
    keep = {}
    def flip(p):
        keep[str(p)] = (p.stat().st_size, p.stat().st_mode & 0o777); p.chmod(0o600)
        with open(p, 'ab') as f: f.write(b'Z')
    def unflip(p):
        with open(p, 'r+b') as f: f.truncate(keep[str(p)][0])
        p.chmod(keep[str(p)][1])
    def bak(p): shutil.copy2(p, str(p) + '.bak')
    def unbak(p): shutil.move(str(p) + '.bak', str(p))
    cases = [
        ('missing /home copy of the dumps', 'G4', lambda: mv(D / 'dumps', R / 'dumps.away'), lambda: mv(R / 'dumps.away', D / 'dumps'), ''),
        ('missing /home copy of the app backup', 'G4', lambda: mv(D / 'app-backup', R / 'app.away'), lambda: mv(R / 'app.away', D / 'app-backup'), ''),
        ('corrupted dump copy on /home (1 byte appended)', 'G5b', lambda: flip(D / 'dumps' / 'immich.full.dump'), lambda: unflip(D / 'dumps' / 'immich.full.dump'), ''),
        ('corrupted ORIGINAL dump (1 byte appended)', 'G5', lambda: flip(EV / 'immich.no-postgis.dump'), lambda: unflip(EV / 'immich.no-postgis.dump'), ''),
        ('invalid manifest line in the /home copy manifest', 'G3d', lambda: (bak(D / 'dumps' / 'SHA256SUMS'), (D / 'dumps' / 'SHA256SUMS').chmod(0o600), open(D / 'dumps' / 'SHA256SUMS', 'a').write('not a manifest\n')), lambda: unbak(D / 'dumps' / 'SHA256SUMS'), ''),
        ('original manifest with a wrong hash', 'G5', lambda: (bak(EV / 'local-backup' / 'dumps.sha256'), (EV / 'local-backup' / 'dumps.sha256').write_text('0' * 64 + '  immich.full.dump\n' + '1' * 64 + '  immich.no-postgis.dump\n')), lambda: unbak(EV / 'local-backup' / 'dumps.sha256'), ''),
        ('original manifest missing', 'G3b', lambda: mv(EV / 'local-backup' / 'dumps.sha256', R / 'm.away'), lambda: mv(R / 'm.away', EV / 'local-backup' / 'dumps.sha256'), ''),
        ('COPIES_DONE marker missing', 'G3f', lambda: mv(EV / 'local-backup' / 'COPIES_DONE', R / 'cd.away'), lambda: mv(R / 'cd.away', EV / 'local-backup' / 'COPIES_DONE'), ''),
        ('sanitized dump missing in the evidence directory', 'G4', lambda: mv(EV / 'immich.no-postgis.dump', R / 'np.away'), lambda: mv(R / 'np.away', EV / 'immich.no-postgis.dump'), ''),
        ('copy directory marker belongs to another cutover', 'G1d', lambda: (bak(D / 'CUTOVER_ID'), (D / 'CUTOVER_ID').write_text('other\n')), lambda: unbak(D / 'CUTOVER_ID'), ''),
        ('RAID1 degraded [U_] (simulated mdstat)', 'G2', lambda: None, lambda: None, 'export LB_MDSTAT=%s;' % (R / 'md.degraded')),
        ('RAID1 resync running (simulated mdstat)', 'G2', lambda: None, lambda: None, 'export LB_MDSTAT=%s;' % (R / 'md.resync')),
        ('wrong CUTOVER_ID in the shell', 'G1', lambda: None, lambda: None, 'export CUTOVER_ID=wrongid01;'),
    ]
    before0 = gate_world(cid); srcp = EV / 'gate-src-probe-before.json'
    sh('python3 -I write_probe.py capture --container $REHEARSAL_SRC_CONTAINER --out %s' % srcp)
    for name, gid, mut, undo, envp in cases:
        w0 = gate_world(cid); mut()
        rc, out, err = stepsh(cid, tag, step, env=(envp + (' export CUTOVER_MANUAL_DECISION=FORWARD:%s;' % cid if token else '') + env_extra))
        undo(); w1 = gate_world(cid)
        gl = (EV / 'local-backup' / 'gate.log').read_text() if (EV / 'local-backup' / 'gate.log').exists() else ''
        wrong_id = 'CUTOVER_ID=wrongid01' in envp
        rec('G14 [%s] %s HALTs with exit 6 (not 5/1), message HALT (G14), failing check %s' % (name, step, gid), rc == 6 and 'HALT (G14)' in err and ('FAIL ' + gid) in (gl + err), 'rc=%d %s' % (rc, tail(err, 1)[:120]))
        diff = [k for k in w0 if w0[k] != w1[k]]
        rec('G14 [%s] NOTHING changed: .env sha, server container (id/start/route), bridge/media-operations, journal, state, source ACL/connections, no open-evidence files' % name, not diff, 'changed: %s' % diff)
    # source database: statistics and sequences identical to before all the gate failures (strict)
    sh('python3 -I write_probe.py capture --container $REHEARSAL_SRC_CONTAINER --out %s' % (EV / 'gate-src-probe-after.json'))
    rc, out, err = sh('python3 -I write_probe.py check --before %s --after %s --allow ""' % (srcp, EV / 'gate-src-probe-after.json'))
    rec('G14 after %d failed gates the source database shows no write activity at all (strict probe)' % len(cases), rc == 0 and 'PROBE RESULT: PASS' in out, 'PASS')
    rc, out, err = stepsh(cid, tag, 's_backup_gate'); rec('G14 with every mutation undone the gate PASSES again (s_backup_gate, read-only)', rc == 0 and 'lb_gate_open OK' in (out + err), tail(err, 1))

def gG1():
    """RUN G1: STOP-1 + R1 from FREEZING; chain with local copies; 13 negative gate tests; gate PASS -> clean abort -> R1 from DARK_VERIFIED"""
    s1 = 'rehGS1' + time.strftime('%H%M%S'); evdir(s1).mkdir(mode=0o700)
    rc, out, err = stepsh(s1, 'g', 's_prepare_target')
    rc, out, err = stepsh(s1, 'g', 's_freeze', env='export DRAIN_TIMEOUT=0;', timeout=300)
    rec('G1 STOP-1 unchanged: drain timeout -> s_freeze fails (TIMEOUT), journal FREEZING, bridge+media-operations stopped, server running, source not fenced', rc != 0 and 'TIMEOUT' in (out + err) and cs(s1) == 'FREEZING' and not running(N['mops']) and running(N['server']) and psql_in(N['src'], "SELECT has_database_privilege('immich','immich','CONNECT')").stdout.strip() == 't', tail(err, 1))
    rc, out, err = stepsh(s1, 'g', 's_rollback_r1', timeout=900); rec('G1 STOP-1 recovery R1 from FREEZING still works', rc == 0 and cs(s1) == 'ROLLED_BACK' and running(N['mops']) and running(N['server']), tail(err, 1))
    time.sleep(40)
    cid = 'rehG' + time.strftime('%H%M%S'); (EVR / 'run-g1-id').write_text(cid)
    chain_to_dark(cid, 'G', lb=True); freeze_checks(cid, 'G')
    _to_dark(cid, 'g', 'G', lb=True, stops=True)
    EV = evdir(cid)
    rc, out, err = stepsh(cid, 'g', 's_open_abort'); rec('G-7 s_open_abort in DARK_VERIFIED still refused (exit 5): cutstate/abort unchanged by the gate', rc == 5 and cs(cid) == 'DARK_VERIFIED', tail(err, 1))
    gate_negatives(cid, 'g')
    # the gate passes inside s_open, the injected fault happens afterwards: abort must still work exactly as before
    rc, out, err = stepsh(cid, 'g', 's_open', env='export CUTOVER_FAULT=after-route;', timeout=900)
    rec('G-8 gate PASS then fault after-route: journal ROUTE_LIVE, OPEN_BEGIN note records the gate hash', cs(cid) == 'ROUTE_LIVE' and 'backup gate PASS' in (EV / 'state.log').read_text(), 'state=%s' % cs(cid))
    rc, out, err = stepsh(cid, 'g', 's_open_abort', timeout=900); es = evid_status(cid)
    rec('G-9 s_open_abort after a gate-passed open: E1-E7 PASS, ABORT_VERIFIED (gate did not disturb the abort evidence)', rc == 0 and cs(cid) == 'ABORT_VERIFIED' and set(es.values()) == {'PASS'} and len(es) == 7, '%s rc=%d' % (es, rc))
    rc, out, err = stepsh(cid, 'g', 's_dark_launch', timeout=900); must('G-10 re-dark', rc, out, err, rc == 0 and cs(cid) == 'DARK_VERIFIED')
    rc, out, err = stepsh(cid, 'g', 's_rollback_r1', timeout=900); rec('G-11 scripted R1 from DARK_VERIFIED: source restored, API verify vs frozen baseline PASS', rc == 0 and cs(cid) == 'ROLLED_BACK', tail(err, 2))
    rec('G-11b after R1: app on the source with route, .env unchanged, source ACL restored; both local copies still verify', state(N['server']) == 'running' and envhost(N['server']) == N['src'] and label(N['server']) == 'true' and (EV / 'source-db-acl.before').read_text() == (EV / 'source-db-acl.after').read_text(), 'ok')
    rc, out, err = stepsh(cid, 'g', 'lb_verify'); rec('G-11c lb_verify after the rollback: copies intact (retention check)', rc == 0 and 'lb_verify OK' in out, tail(out, 1))

def gG2():
    """RUN G2: ROUTE_LIVE + real upload -> abort HALT -> manual FORWARD blocked by the gate (copy missing, RAID degraded) -> gate repaired -> FORWARD -> OPEN_CONFIRMED"""
    prev = (EVR / 'run-g1-id').read_text(); cid = 'rehH' + time.strftime('%H%M%S'); (EVR / 'run-g2-id').write_text(cid); evdir(cid).mkdir(mode=0o700)
    time.sleep(30)
    rc, out, err = stepsh(cid, 'h', 's_target_reset_after_rollback', env='export PREV_EV=%s;' % evdir(prev)); must('G2-0 target reset (PREV_EV ROLLED_BACK)', rc, out, err)
    chain_to_dark(cid, 'H', lb=True); freeze_checks(cid, 'H'); _to_dark(cid, 'h', 'H', lb=True)
    EV = evdir(cid); D = Path(ST['root']) / 'lb-home' / cid; R = Path(ST['root'])
    rc, out, err = stepsh(cid, 'h', 's_open', env='export CUTOVER_FAULT=after-route;', timeout=900); assert cs(cid) == 'ROUTE_LIVE', cs(cid)
    rc, out, err = upload(2); rec('H-7 a real user upload reaches the NEW database', rc == 0, tail(out, 1))
    rc, out, err = stepsh(cid, 'h', 's_open_abort', timeout=900); es = evid_status(cid)
    rec('H-8 abort BLOCKED (E4/E5/E6) -> HALT_MANUAL as before', rc == 4 and cs(cid) == 'HALT_MANUAL' and {'E4', 'E5', 'E6'} <= {k for k, v in es.items() if v == 'FAIL'}, '%s rc=%d' % (es, rc))
    shutil.move(str(D / 'dumps'), str(R / 'dumps.away'))
    w0 = gate_world(cid); rc, out, err = stepsh(cid, 'h', 's_manual_forward', env='export CUTOVER_MANUAL_DECISION=FORWARD:%s;' % cid, timeout=900); w1 = gate_world(cid)
    rec('H-9 manual FORWARD with the exact token is STILL blocked by the gate when the /home dump copy is missing (exit 6, HALT G14)', rc == 6 and 'HALT (G14)' in err and cs(cid) == 'HALT_MANUAL', tail(err, 1)[:140])
    rec('H-9b nothing changed by the blocked FORWARD (.env, server stopped, journal, bridge/media-operations stopped)', w0 == w1 and not running(N['server']) and not running(N['mops']), [k for k in w0 if w0[k] != w1[k]])
    shutil.move(str(R / 'dumps.away'), str(D / 'dumps'))
    (R / 'md.degraded').write_text('Personalities : [raid1]\nmd2 : active raid1 nvme1n1p3[1]\n      2111699968 blocks super 1.2 [2/1] [U_]\n\nunused devices: <none>\n')
    rc, out, err = stepsh(cid, 'h', 's_manual_forward', env='export CUTOVER_MANUAL_DECISION=FORWARD:%s; export LB_MDSTAT=%s;' % (cid, R / 'md.degraded'), timeout=900)
    rec('H-10 manual FORWARD is blocked by a degraded RAID1 (simulated): exit 6, state HALT_MANUAL, server still stopped', rc == 6 and cs(cid) == 'HALT_MANUAL' and not running(N['server']), tail(err, 1)[:140])
    rc, out, err = stepsh(cid, 'h', 's_manual_forward', env='export CUTOVER_MANUAL_DECISION=FORWARD:%s;' % cid, timeout=900); rec('H-11 gate repaired -> manual FORWARD succeeds -> OPEN_CONFIRMED', rc == 0 and cs(cid) == 'OPEN_CONFIRMED', tail(err, 1))
    rec('H-11b after the manual GO: app on the NEW database, route true, media-operations+bridge running', state(N['server']) == 'running' and envhost(N['server']) == N['db'] and label(N['server']) == 'true' and running(N['mops']) and running(N['brg']), 'ok')
    for st, code in (('s_rollback_r1', 3), ('s_open_abort', 3), ('s_open', 5), ('s_manual_forward', 5)):
        rc, out, err = stepsh(cid, 'h', st, env='export CUTOVER_MANUAL_DECISION=FORWARD:%s;' % cid); rec('H-12 %s after OPEN_CONFIRMED is refused (exit %d)' % (st, code), rc == code and cs(cid) == 'OPEN_CONFIRMED', tail(err, 1))

def stop5(cid):
    EV = evdir(cid); f5 = cid + 's5'; fork(cid, f5); E5 = evdir(f5)
    tp = json.loads((E5 / 'src' / 'tables.json').read_text()); tp['album']['sha256'] = '1' * 64; (E5 / 'src' / 'tables.json').write_text(json.dumps(tp))
    rc, out, err = sh('python3 -I db_snapshot.py compare --mode source-target --source %s --target %s --report %s' % (E5 / 'src', E5 / 'dst', E5 / 'compare.json'))      # exactly the comparison s_validate_target runs first; its failure stops the step (STOP-5)
    cj = json.loads((E5 / 'compare.json').read_text()) if (E5 / 'compare.json').exists() else {}
    rec('I-STOP-5 tampered source snapshot -> the comparison s_validate_target runs first FAILS (table hashes differ), so the step exits non-zero and dark launch is refused', rc != 0 and cj.get('status') == 'FAIL' and any('hashes differ' in p['what'] for p in cj.get('problems', [])), 'compare FAIL')

def gG3b():
    stop5((EVR / 'run-g3-id').read_text())

def gG3():
    """RUN G3: fault-free path freeze -> ... -> gate PASS -> s_open -> OPEN_CONFIRMED (after a hand-made R2-A reset of the harness), STOP-5/STOP-6 and post-open checks"""
    prev = (EVR / 'run-g2-id').read_text(); cid = 'rehI' + time.strftime('%H%M%S'); (EVR / 'run-g3-id').write_text(cid); evdir(cid).mkdir(mode=0o700)
    rc, out, err = stepsh(prev, 'h', 'for c in $BRG $MOPS "$SRV"; do docker stop -t 30 "$c"; done; cp -p $EV/immich.env.before $IMMICH_ENV_FILE; export R1_SKIP_VERIFY=1; _r1_core', timeout=900); must('I-0a harness reset by hand (R2-A): source restored', rc, out, err)
    psql_in(N['db'], "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='immich' AND pid<>pg_backend_pid(); ALTER DATABASE immich RENAME TO immich_after_h_run; CREATE DATABASE immich WITH OWNER immich TEMPLATE template0 ENCODING 'UTF8' LC_COLLATE 'en_US.utf8' LC_CTYPE 'en_US.utf8';")
    time.sleep(40)
    chain_to_dark(cid, 'I', lb=True); freeze_checks(cid, 'I')
    rc, out, err = stepsh(cid, 'i', 's_dump_source', timeout=900); must('I-3 s_dump_source', rc, out, err, rc == 0 and cs(cid) == 'DUMPED')
    rc, out, err = stepsh(cid, 'i', 's_bridge_sanitize', timeout=900); must('I-3 s_bridge_sanitize', rc, out, err)
    rc, out, err = stepsh(cid, 'i', 's_bridge_cleanup'); must('I-4 cleanup', rc, out, err)
    rc, out, err = stepsh(cid, 'i', 'lb_copy_cutover_dumps'); must('I-F6b lb_copy_cutover_dumps', rc, out, err, rc == 0)
    rc, out, err = stepsh(cid, 'i', 's_restore_and_validate', timeout=2400); must('I-5 restore + validate', rc, out, err, rc == 0 and cs(cid) == 'VALIDATED')
    EV = evdir(cid)
    # STOP-5 (tampered source snapshot) on a fork of the validated evidence; STOP-6 (application cannot authenticate) on the real chain
    stop5(cid)
    app = app_pw(); alt = lambda pw: subprocess.run(['docker', 'exec', '-i', '-e', 'NEWPW', N['db'], 'psql', '-X', '-U', 'postgres', '-d', 'postgres'], input="\\getenv pw NEWPW\nALTER ROLE immich PASSWORD :'pw';\n", capture_output=True, text=True, env=dict(os.environ, NEWPW=pw))
    alt('wrong-secret-xyz'); rc, out, err = stepsh(cid, 'i', 's_dark_launch', timeout=900)
    rec('I-STOP-6 wrong role password -> application cannot start, s_dark_launch exits non-zero, journal stays VALIDATED', rc != 0 and cs(cid) == 'VALIDATED', tail(err, 1)); alt(app)
    rc, out, err = stepsh(cid, 'i', 's_dark_launch', timeout=900); must('I-6 s_dark_launch after the password was fixed', rc, out, err, rc == 0 and cs(cid) == 'DARK_VERIFIED')
    rc, out, err = stepsh(cid, 'i', 's_backup_gate'); rec('I-6b gate PASS on the real evidence before the open', rc == 0 and 'lb_gate_open OK' in (out + err), tail(err, 1))
    eb = fsha(ENVFILE())
    rc, out, err = stepsh(cid, 'i', 's_open', timeout=900); must('I-7 s_open with the gate PASS -> OPEN_CONFIRMED', rc, out, err, rc == 0 and cs(cid) == 'OPEN_CONFIRMED')
    chain = [json.loads(l) for l in (EV / 'state.log').read_text().splitlines()]
    rec('I-7b full journal intact (DARK_VERIFIED OPEN_BEGIN ... OPEN_CONFIRMED) and OPEN_BEGIN records the gate hash', [c['state'] for c in chain][-9:] == ['DARK_VERIFIED', 'OPEN_BEGIN', 'ENV_CHANGED', 'RECREATING', 'RECREATED', 'ROUTE_LIVE', 'AUX_STARTED', 'RESUMING', 'OPEN_CONFIRMED'] and 'backup gate PASS' in chain[-8]['note'], chain[-8]['note'])
    rc, out, err = sh('python3 -I cutstate.py verify %s' % EV); rec('I-7c journal hash chain still valid', 'CORRUPT' not in out and rc == 0, out.strip())
    rec('I-7d after open: app on the NEW database, route true, .env differs only in DB_HOSTNAME', state(N['server']) == 'running' and envhost(N['server']) == N['db'] and label(N['server']) == 'true' and eb == (EV / 'env.before.sha256').read_text().strip() and fsha(ENVFILE()) == (EV / 'env.after.sha256').read_text().strip(), 'ok')
    for st, code in (('s_rollback_r1', 3), ('s_open_abort', 3), ('s_open', 5), ('s_manual_forward', 5), ('s_manual_rollback_accept_loss', 5)):
        rc, out, err = stepsh(cid, 'i', st); rec('I-8 %s after OPEN_CONFIRMED is refused (exit %d)' % (st, code), rc == code and cs(cid) == 'OPEN_CONFIRMED', tail(err, 1))
    rc, out, err = stepsh(cid, 'i', 'lb_verify'); rec('I-9 both local copies still verify after the open (retention check)', rc == 0 and 'lb_verify OK' in out, tail(out, 1))
    t0 = time.time(); idle = False
    while time.time() - t0 < 400:
        rc, out, err = stepsh(cid, 'i', 'python3 -I api_checks.py queues status')
        if rc == 0 and all(re.search(r'active=0\s+waiting=0\s+delayed=0', l) for l in out.strip().splitlines()) and 'paused=True' not in out.replace('backgroundTask', ''): idle = True; break
        time.sleep(5)
    rec('I-10 queues idle on the new database, 0 failed', idle and sum(int(m) for m in re.findall(r'failed=(\d+)', out)) == 0, 'idle after %.0fs' % (time.time() - t0))
    rc, out, err = stepsh(cid, 'i', 'python3 -I api_checks.py verify --baseline $EV/api-baseline.json --out $EV/api-after.json'); rec('I-11 API verify against the frozen baseline PASSES', rc == 0 and 'RESULT: PASS' in out, [l[:100] for l in out.splitlines() if l.startswith(('FAIL', 'RESULT'))])
    rc, out, err = sh("export CUTOVER_ID=%s CUTOVER_BRIDGE_CONTAINER=; python3 -I db_snapshot.py snapshot --container $REHEARSAL_SRC_CONTAINER --out %s/src-after-open && python3 -I db_snapshot.py compare --mode source-bridge --source %s/src --target %s/src-after-open" % (cid, EV, EV, EV), timeout=600)
    rec('I-12 the retained source database is identical after the open', rc == 0 and '"status": "PASS"' in out, 'source untouched')

def gHardening():
    """Fresh isolated F4-F8 + missing key HALT + G14 denials + R1. Never opens traffic on the target."""
    idfile = EVR / 'run-hardening-id'
    cid = idfile.read_text().strip() if idfile.exists() else 'rehHard' + time.strftime('%H%M%S')
    idfile.write_text(cid)
    redis_before = d('inspect', '-f', '{{.Id}} {{.State.StartedAt}} {{.RestartCount}}', N['redis']).stdout
    EV = evdir(cid); EV.mkdir(mode=0o700, exist_ok=True)
    if cs(cid) == 'NONE':
        rc,out,err = stepsh(cid,'hard','s_prepare_target'); must('Hard prepare',rc,out,err)
    must('Hard starts from PREPARED',0,'','',cs(cid)=='PREPARED')
    for step in ('python3 -I preflight.py --phase target-ready --ignore-window',
                 'python3 -I api_checks.py baseline --out $EV/api-baseline-pre.json',
                 'lb_copy_app_backup', 'lb_verify', 's_freeze'):
        rc,out,err = stepsh(cid,'hard',step,timeout=900); must('Hard '+step,rc,out,err)
    freeze_checks(cid, 'Hard')
    for step, expected in [('s_dump_source','DUMPED'), ('s_bridge_sanitize','SANITIZED'), ('s_bridge_cleanup','SANITIZED'),
                           ('lb_copy_cutover_dumps','SANITIZED'), ('lb_verify','SANITIZED'), ('s_restore_and_validate','VALIDATED')]:
        rc,out,err = stepsh(cid, 'hard', step, timeout=2400)
        must('Hard '+step, rc,out,err, rc == 0 and cs(cid) == expected)
    # Missing key must fail before recreate; journal and original env stay intact even under if.
    before = gate_world(cid)
    rc,out,err = stepsh(cid,'hard','unset IMMICH_ADMIN_API_KEY; if s_dark_launch; then exit 0; else exit $?; fi')
    must('Hard F8 missing admin key: HALT in conditional context, no mutation',rc,out,err,
         rc != 0 and 'IMMICH_ADMIN_API_KEY' in err and before == gate_world(cid) and cs(cid) == 'VALIDATED')
    rc,out,err = stepsh(cid,'hard','if s_dark_launch; then exit 0; else exit $?; fi',timeout=900)
    must('Hard F8 complete API receipt -> DARK_VERIFIED in conditional context',rc,out,err,rc == 0 and cs(cid)=='DARK_VERIFIED')
    # A historical DARK_VERIFIED without the complete F8 receipt must HALT even when G14 passes.
    before = gate_world(cid)
    seal = EV/'dark-verified.json'; held = EV/'dark-verified.test-hold.json'
    shutil.move(str(seal),str(held))
    try:
        rc,out,err=stepsh(cid,'hard','if s_open; then exit 0; else exit $?; fi',timeout=900)
        must('Hard F10 refuses missing F8 seal before any mutation',rc,out,err,
             rc!=0 and 'complete F8 evidence required' in err and before==gate_world(cid))
    finally: shutil.move(str(held),str(seal))
    # G14's existing 13 mutations, each restored afterward, all must block before any opening.
    gate_negatives(cid,'hard')
    # A forged old DARK_VERIFIED alone cannot open: absence of the new complete receipt is a HALT.
    receipts = sorted(EV.glob('api-result.*.json'))
    must('Hard API receipt exists',0,'','',bool(receipts))
    # No route opening is attempted by this rehearsal. R1 restores only the isolated source.
    rc,out,err = stepsh(cid,'hard','if s_rollback_r1; then exit 0; else exit $?; fi',timeout=900)
    must('Hard R1 from DARK_VERIFIED under if -> ROLLED_BACK',rc,out,err,rc==0 and cs(cid)=='ROLLED_BACK')
    must('Hard source restored, aux running, new database retained',0,'','',
         envhost(N['server'])==N['src'] and label(N['server'])=='true' and running(N['mops']) and running(N['brg']) and running(N['db']))
    rc,out,err=stepsh(cid,'hard','lb_verify');must('Hard backup retention after R1',rc,out,err)
    redis_after = d('inspect', '-f', '{{.Id}} {{.State.StartedAt}} {{.RestartCount}}', N['redis']).stdout
    must('Hard isolated Redis never restarted',0,'','',redis_before==redis_after)
    rc,out,err=stepsh(cid,'hard','s_open');must('Hard safe stop: open refused after ROLLED_BACK',rc,out,err,rc==5 and cs(cid)=='ROLLED_BACK')

def gHardeningReview():
    """Review the completed chain without re-running a migration; preserve historical failures."""
    cid=(EVR/'run-hardening-id').read_text().strip(); EV=evdir(cid)
    must('Review terminal journal ROLLED_BACK',0,'','',cs(cid)=='ROLLED_BACK')
    required=['Hard s_freeze','Hard s_dump_source','Hard s_bridge_sanitize','Hard s_bridge_cleanup',
              'Hard lb_copy_cutover_dumps','Hard lb_verify','Hard s_restore_and_validate',
              'Hard F8 missing admin key: HALT in conditional context, no mutation',
              'Hard F8 complete API receipt -> DARK_VERIFIED in conditional context',
              'Hard R1 from DARK_VERIFIED under if -> ROLLED_BACK', 'Hard isolated Redis never restarted',
              'Hard safe stop: open refused after ROLLED_BACK']
    for name in required:
        matches=[r for r in results if r['group']=='gHardening' and r['name']==name]
        must('Review latest '+name,0,'','',bool(matches) and matches[-1]['ok'])
    rc,out,err=stepsh(cid,'hard','python3 -I safety_evidence.py check "$EV" "$CUTOVER_ID" "$PG_NEW"')
    must('Review retained F8 evidence seal still validates',rc,out,err)
    # Fresh evidence fixture with real G14 originals/copies, but absent/invalid F8 seal.
    # Only the test fixture is written; original rehearsal and production evidence stay intact.
    fixture=EVR/('seal-negative-'+RUN_ID)/EV.name;fixture.mkdir(parents=True,mode=0o700)
    shutil.copytree(EV/'local-backup',fixture/'local-backup')
    for name in ('immich.full.dump','immich.no-postgis.dump','immich.full.dump.sha256','immich.no-postgis.dump.sha256'):
        os.link(EV/name,fixture/name)
    rc,out,err=sh('python3 -I cutstate.py set %s --from NONE --to DARK_VERIFIED' % fixture)
    must('Review create isolated missing-proof fixture',rc,out,err)
    before=gate_world(cid)
    for label,content in [('missing',None),('malformed','{}')]:
        if content is not None: (fixture/'dark-verified.json').write_text(content)
        rc,out,err=stepsh(cid,'hard','export EV=%s; if s_open; then exit 0; else exit $?; fi' % fixture,timeout=900)
        must('Review F10 '+label+' F8 proof HALTs after real G14 PASS, nothing opens',rc,out,err,
             rc!=0 and 'lb_gate_open OK' in err and 'complete F8 evidence required' in err and
             before==gate_world(cid) and not (fixture/'T_open_begin').exists() and not (fixture/'T_open').exists())
    lines=[json.loads(line)['argv'] for line in (EVR/'audit.jsonl').read_text().splitlines()]
    prod={'postgis','immich-db','immich_server','immich_redis','immich_media_operations','nextcloud_immich_bridge','traefik'}
    bad=[args for args in lines if any(a in prod or 'docker.sock' in a or '/opt/stacks/immich' in a or '/opt/stacks/nextcloud' in a for a in args)]
    must('Review rehearsal audit: no production targets or Docker socket',0,'','',not bad)

GROUPS = {'gHardeningReview': gHardeningReview, 'gHardening': gHardening, 'g0': g0, 'g1': g1, 'g2': g2, 'g4': g4, 'gA': gA, 'gA2': gA2, 'gA3': gA3, 'gI': gI, 'gD': gD, 'gD2': gD2, 'gD2b': gD2b, 'gB': gB, 'gP': gP, 'gStop': gStop, 'gC1': gC1, 'gC10': gC10, 'gC2': gC2, 'gC3': gC3, 'gC4': gC4, 'gC5': gC5, 'gD1': gD1, 'gD2': gD2, 'gD3': gD3, 'gG1': gG1, 'gG2': gG2, 'gG3': gG3, 'gG3b': gG3b}
if __name__ == '__main__':
    GROUPS[GROUP]()
    fails = [r for r in results if r['group'] == GROUP and r.get('run_id') == RUN_ID and not r['ok']]
    print('GROUP %s: %d tests, %d FAIL' % (GROUP, sum(1 for r in results if r['group'] == GROUP and r.get('run_id') == RUN_ID), len(fails))); sys.exit(1 if fails else 0)
