#!/usr/bin/env bash
# Offline self-test of the cutover tooling. Touches NO container and NO production resource: it uses the stored phase 4-5 evidence
# (source snapshot of 14 Nov, restored-copy snapshot, application deltas) as fixtures.
set -euo pipefail
cd "$(dirname "$0")/.."
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
O=/opt/stacks/data/backups/immich-restore-test-20261114t152235z-1bb3b8
N=/opt/stacks/data/backups/immich-apptest-20261114t225542z-b30ca6/snap
mkdir -p "$T/src" "$T/dst"
cp "$O/source.metadata.json" "$T/src/metadata.json"; cp "$O/source.tables.json" "$T/src/tables.json"
echo '[{"sequencename":"naturalearth_countries_tmp_id_seq1","data_type":"bigint","last_value":4274}]' > "$T/src/sequences.json"
cp "$N/Bpre/metadata.json" "$N/Bpre/tables.json" "$T/dst/"; cp "$T/src/sequences.json" "$T/dst/sequences.json"
ok()   { echo "PASS  $1"; }
bad()  { echo "FAIL  $1"; exit 1; }
python3 -I db_snapshot.py compare --source "$T/src" --target "$T/dst" >/dev/null && ok "compare: restored copy equals source (72 tables, metadata, sequence)" || bad "positive compare"
t() { rm -rf "$T/x"; cp -r "$T/dst" "$T/x"; python3 -I - "$T/x" "$1" <<'PY'
import json, sys
d, case = sys.argv[1], sys.argv[2]
if case == 'hash':
    p = d + '/tables.json'; t = json.load(open(p)); t['asset']['sha256'] = '0' * 64; json.dump(t, open(p, 'w'))
elif case == 'sequence':
    p = d + '/sequences.json'; s = json.load(open(p)); s[0]['data_type'] = 'integer'; json.dump(s, open(p, 'w'))
elif case == 'index':
    p = d + '/metadata.json'; m = json.load(open(p))
    for x in m['indexes']:
        if x['name'] == 'face_index': x['definition'] = x['definition'].replace('lists = [1]', 'lists = [2]')
    json.dump(m, open(p, 'w'))
elif case == 'postgis':
    p = d + '/metadata.json'; m = json.load(open(p)); m['extensions'].append({'name': 'postgis', 'version': '3.6.2', 'owner': 'postgres', 'schema': 'public'}); json.dump(m, open(p, 'w'))
elif case == 'seqlow':
    p = d + '/sequences.json'; s = json.load(open(p)); s[0]['last_value'] = 10; json.dump(s, open(p, 'w'))
PY
python3 -I db_snapshot.py compare --source "$T/src" --target "$T/x" >/dev/null 2>&1; }
for c in hash sequence index postgis seqlow; do if t $c; then bad "compare must FAIL for tampered: $c"; else ok "compare fails on tampered: $c"; fi; done
python3 -I db_snapshot.py delta --before "$N/B0" --after "$N/B1" >/dev/null && ok "delta: startup changes only allowed tables" || bad "delta positive"
if python3 -I db_snapshot.py delta --before "$N/B0" --after "$N/B3" --allow session >/dev/null 2>&1; then bad "delta must FAIL outside allow-list"; else ok "delta fails outside allow-list"; fi
if python3 -I api_checks.py queues pause >/dev/null 2>&1; then bad "queues pause must refuse without --execute"; else ok "queues pause refuses without --execute"; fi
if python3 -I api_checks.py job backup-database >/dev/null 2>&1; then bad "job must refuse without --execute"; else ok "job backup-database refuses without --execute"; fi
if CUTOVER_REHEARSAL=1 REHEARSAL_DB_CONTAINER=postgis REHEARSAL_SERVER_CONTAINER=immich_server python3 -I -c "import sys; sys.path.insert(0,'.'); import cutlib" >/dev/null 2>&1; then bad "rehearsal must refuse production names"; else ok "rehearsal mode refuses production container names"; fi
python3 -I -m py_compile cutlib.py preflight.py db_snapshot.py validate_target.py api_checks.py && ok "all scripts compile" || bad compile

# ---- phase 7B: state journal and write probe (pure logic, no container)
python3 -I - <<'PY' && ok "state journal + write probe logic (transitions, tamper detection, rollback/abort gates, probe verdicts)" || bad "7B logic"
import json, os, subprocess, sys, tempfile
from pathlib import Path
sys.path.insert(0, '.')
import cutstate, write_probe
d = Path(tempfile.mkdtemp()); ev = d / 'ev'
def S(to, frm, note=''): return cutstate.set_state(ev, frm.split(','), to, note)
assert cutstate.load(ev)[0] == 'NONE'
assert S('FREEZING', 'NONE,PREPARED') == 0 and S('FROZEN', 'FREEZING') == 0
assert S('RESTORED', 'SANITIZED') == 5, 'a step whose predecessor state is not current must be refused'
assert cutstate.main(['x', 'can-rollback', str(ev)]) == 0
for st, frm in (('DUMPED', 'FROZEN'), ('SANITIZED', 'DUMPED'), ('RESTORED', 'SANITIZED'), ('VALIDATED', 'RESTORED'), ('DARK_VERIFIED', 'VALIDATED'), ('OPEN_BEGIN', 'DARK_VERIFIED'), ('ENV_CHANGED', 'OPEN_BEGIN')):
    assert S(st, frm) == 0, st
assert cutstate.main(['x', 'can-rollback', str(ev)]) == 3, 'R1 must be refused in a partially opened state'
assert cutstate.main(['x', 'can-abort', str(ev)]) == 0
for st, frm in (('RECREATING', 'ENV_CHANGED'), ('RECREATED', 'RECREATING'), ('ROUTE_LIVE', 'RECREATED'), ('AUX_STARTED', 'ROUTE_LIVE')):
    assert S(st, frm) == 0 and cutstate.main(['x', 'can-abort', str(ev)]) == 0 and cutstate.main(['x', 'can-rollback', str(ev)]) == 3
assert S('RESUMING', 'AUX_STARTED') == 0 and S('OPEN_CONFIRMED', 'RESUMING') == 0
assert cutstate.main(['x', 'can-abort', str(ev)]) == 3 and cutstate.main(['x', 'can-rollback', str(ev)]) == 3, 'past the point of no return nothing is automatic'
# tamper detection: every manipulation is CORRUPT (= HALT), never a silent downgrade of the state
import shutil
def corrupt(fn):
    t = d / 'tmp'; shutil.rmtree(t, ignore_errors=True); shutil.copytree(ev, t); fn(t); r = cutstate.load(t)[0]; return r == 'CORRUPT'
assert corrupt(lambda t: (t / 'state').write_text('DARK_VERIFIED ' + 'a' * 64 + '\n')), 'state file rewritten'
assert corrupt(lambda t: (t / 'state').unlink()), 'state file deleted'
assert corrupt(lambda t: (t / 'state.log').unlink()), 'log deleted'
assert corrupt(lambda t: (t / 'state.log').write_text('\n'.join((t / 'state.log').read_text().splitlines()[:-1]) + '\n')), 'last entry cut'
assert corrupt(lambda t: (t / 'state.log').write_text((t / 'state.log').read_text().replace('"ROUTE_LIVE"', '"ENV_CHANGED"', 1))), 'entry edited'
t = d / 'tmp'; shutil.rmtree(t, ignore_errors=True); shutil.copytree(ev, t); (t / 'state').write_text('DARK_VERIFIED x\n')
assert cutstate.set_state(t, ['DARK_VERIFIED'], 'OPEN_BEGIN') == 6 and cutstate.main(['x', 'can-rollback', str(t)]) == 6, 'a corrupt journal must neither transition nor allow rollback'
# write probe verdicts
base = {'postmaster_start': 't0', 'stats_reset': 'never', 'tables': {'asset': [1, 2, 3], 'system_metadata': [5, 5, 0], 'session': [0, 0, 0]}, 'sequences': {'s1': 10}}
def P(name, obj): (d / name).write_text(json.dumps(obj)); return str(d / name)
def verdict(after, allow={'system_metadata'}):
    return write_probe.check(P('b.json', base), P('a.json', after), allow)['status'] if after is not None else write_probe.check(P('b.json', base), str(d / 'missing.json'), allow)['status']
import copy, io, contextlib
def V(after, allow={'system_metadata'}):
    with contextlib.redirect_stdout(io.StringIO()): return verdict(after, allow)
assert V(copy.deepcopy(base)) == 'PASS'
x = copy.deepcopy(base); x['tables']['system_metadata'] = [9, 9, 0]; assert V(x) == 'PASS', 'start-up tables are allowed'
x = copy.deepcopy(base); x['tables']['session'] = [1, 0, 0]; assert V(x) == 'FAIL', 'a new session = a login = a user write'
x = copy.deepcopy(base); x['tables']['asset'] = [1, 2, 4]; assert V(x) == 'FAIL'
x = copy.deepcopy(base); x['sequences']['s1'] = 11; assert V(x) == 'FAIL', 'nextval of a rolled-back insert'
x = copy.deepcopy(base); x['postmaster_start'] = 't1'; assert V(x) == 'FAIL'
x = copy.deepcopy(base); x['stats_reset'] = 'later'; assert V(x) == 'FAIL'
assert V(None) == 'UNKNOWN', 'missing probe is not proof'
x = copy.deepcopy(base); del x['sequences']; assert V(x) == 'UNKNOWN'
PY
bash tests/local_backup_selftest.sh >/dev/null 2>&1 && ok "local backup gate + backup-only approval selftest (46 checks, synthetic /tmp data)" || bad "local backup selftest"
python3 -I -m py_compile cutstate.py write_probe.py && ok "7B scripts compile bash -n steps.sh" && bash -n steps.sh || bad compile7b
python3 -I tests/safety_selftest.py > "$T/safety.out" 2>&1 && ok "explicit failure propagation, API receipts, keys and conditional Bash contexts" || { cat "$T/safety.out"; bad "safety hardening"; }
python3 -I -m py_compile safety_evidence.py && ok "F8 evidence seal compiles" || bad "seal compile"
python3 -I tests/f2_existing_selftest.py > "$T/f2-existing.out" 2>&1 && ok "existing-target F2: failures block PREPARED, including conditional Bash callers" || { cat "$T/f2-existing.out"; bad "existing-target F2"; }
rm -rf __pycache__; echo "ALL OFFLINE CHECKS PASSED"
