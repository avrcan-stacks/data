"""Explicit cutover state journal (phase 7B). Replaces "does the file T_open exist" as the only evidence of the point of no return.

  python3 -I cutstate.py get    <EV>                         -> prints the current state (NONE | <STATE> | CORRUPT); exit 0 / 6 (corrupt)
  python3 -I cutstate.py set    <EV> --from A,B --to C [--note TEXT]   -> appends a transition; exit 5 if the current state is not in --from, 6 if corrupt
  python3 -I cutstate.py verify <EV>                         -> verifies the whole hash chain; exit 0 / 6
  python3 -I cutstate.py can-rollback <EV>                   -> exit 0 only for states in which the scripted rollback R1 is allowed
  python3 -I cutstate.py can-abort    <EV>                   -> exit 0 only for the partially opened states (s_open_abort may run its evidence checks)

Files in <EV> (0600): state.log = one JSON object per line, each carrying sha256 of the previous raw line (a broken or edited chain is CORRUPT);
state = "<STATE> <sha256 of the last log line>" (must agree with the log). Anything unexpected is CORRUPT, and CORRUPT means HALT: no automatic action.
"""
import fcntl, hashlib, json, os, sys, time
from pathlib import Path

STATES = ['PREPARED', 'FREEZING', 'FROZEN', 'DUMPED', 'SANITIZED', 'RESTORED', 'VALIDATED', 'DARK_VERIFIED',
          'OPEN_BEGIN', 'ENV_CHANGED', 'RECREATING', 'RECREATED', 'ROUTE_LIVE', 'AUX_STARTED', 'RESUMING', 'OPEN_CONFIRMED',
          'ABORT_BEGIN', 'ABORT_VERIFIED', 'HALT_MANUAL', 'ROLLED_BACK', 'ROLLED_BACK_LOSS_ACCEPTED']
ROLLBACK_OK = {'FREEZING', 'FROZEN', 'DUMPED', 'SANITIZED', 'RESTORED', 'VALIDATED', 'DARK_VERIFIED', 'ABORT_VERIFIED'}
# states in which the application may already have been reachable by users (or may have written to the new database): only s_open_abort, with proof, may leave them
ABORTABLE = {'OPEN_BEGIN', 'ENV_CHANGED', 'RECREATING', 'RECREATED', 'ROUTE_LIVE', 'AUX_STARTED', 'ABORT_BEGIN'}
PAST_PONR = {'RESUMING', 'OPEN_CONFIRMED'}      # queue workers resumed on the new database: nothing can prove "no write" any more


def _sha(b): return hashlib.sha256(b).hexdigest()


def load(ev):
    """returns (state, last_sha, entries); state is 'NONE', a state name, or 'CORRUPT'"""
    log, st = Path(ev) / 'state.log', Path(ev) / 'state'
    if not log.exists() and not st.exists(): return 'NONE', '', []
    if not (log.exists() and st.exists()): return 'CORRUPT', '', []
    prev, entries = '', []
    try:
        for i, raw in enumerate(log.read_bytes().splitlines(keepends=True)):
            e = json.loads(raw)
            if e.get('seq') != i + 1 or e.get('prev') != prev or e.get('state') not in STATES: return 'CORRUPT', '', entries
            if i > 0 and e.get('from') != entries[-1]['state']: return 'CORRUPT', '', entries
            entries.append(e); prev = _sha(raw)
        name, sha = st.read_text().split()
    except Exception:
        return 'CORRUPT', '', entries
    if not entries or name != entries[-1]['state'] or sha != prev: return 'CORRUPT', '', entries
    return name, prev, entries


def set_state(ev, frm, to, note=''):
    ev = Path(ev); ev.mkdir(parents=True, exist_ok=True, mode=0o700)
    with open(ev / '.state.lock', 'a') as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        cur, prev, entries = load(ev)
        if cur == 'CORRUPT': print('CORRUPT state journal in %s: HALT (no automatic action)' % ev, file=sys.stderr); return 6
        if cur not in frm: print('STATE VIOLATION: cannot go %s -> %s (allowed from: %s)' % (cur, to, ','.join(frm)), file=sys.stderr); return 5
        if to not in STATES: print('unknown state ' + to, file=sys.stderr); return 5
        e = {'seq': len(entries) + 1, 'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'from': cur if entries else 'NONE', 'state': to, 'note': note, 'prev': prev}
        raw = (json.dumps(e, sort_keys=True) + '\n').encode()
        fd = os.open(ev / 'state.log', os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            if os.write(fd, raw) != len(raw): raise OSError('short journal write: HALT')
            os.fsync(fd)
        finally: os.close(fd)
        tmp = ev / '.state.tmp'; tmp.write_text('%s %s\n' % (to, _sha(raw))); os.chmod(tmp, 0o600); os.replace(tmp, ev / 'state')
        # Both files must reach durable storage before reporting success.
        with open(ev / 'state', 'rb') as state_file: os.fsync(state_file.fileno())
        directory = os.open(ev, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
        if load(ev)[0] != to: raise OSError('journal read-back differs: HALT')
    return 0


def main(argv):
    cmd, ev = argv[1], argv[2]
    if cmd == 'get':
        s = load(ev)[0]; print(s); return 6 if s == 'CORRUPT' else 0
    if cmd == 'verify':
        s = load(ev)[0]; print(s); return 6 if s == 'CORRUPT' else 0
    if cmd == 'set':
        a = argv[3:]; frm = a[a.index('--from') + 1].split(',') if '--from' in a else []; to = a[a.index('--to') + 1]; note = a[a.index('--note') + 1] if '--note' in a else ''
        return set_state(ev, frm, to, note)
    s = load(ev)[0]
    if cmd == 'can-rollback': print(s); return 0 if s in ROLLBACK_OK else (6 if s == 'CORRUPT' else 3)
    if cmd == 'can-abort': print(s); return 0 if s in ABORTABLE else (6 if s == 'CORRUPT' else 3)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
