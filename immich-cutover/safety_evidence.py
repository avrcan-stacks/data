"""Bind the successful F8 API receipt and database evidence to this attempt.
A journal state on its own cannot authorize opening (including historical F8 false successes).
"""
import hashlib, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from api_checks import check_result

REQUIRED = ['api-baseline.json', 'dark-delta.json', 'write-probe-dark.json',
            'dst2/metadata.json', 'dst2/tables.json', 'dst2/sequences.json',
            'compare.json', 'freeze-gap-proof.json', 'immich.full.dump.sha256', 'immich.no-postgis.dump.sha256']

def digest(path):
    if not path.is_file() or path.is_symlink() or not path.stat().st_size:
        raise ValueError('missing, empty or symlinked evidence: '+path.name)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(ev, cid, host):
    seal = json.loads((ev/'dark-verified.json').read_text())
    if seal.get('cutover_id') != cid or seal.get('target') != host:
        raise ValueError('dark evidence belongs to another attempt or database')
    files = seal['files']
    result = seal['api_result']
    if not isinstance(result, str) or '/' in result or not result.startswith('api-result.'):
        raise ValueError('invalid API receipt path')
    if set(files) != set(REQUIRED+[result]):
        raise ValueError('incomplete dark evidence seal')
    for name, sha in files.items():
        if digest(ev/name) != sha: raise ValueError('dark evidence changed: '+name)
    check_result(ev/result)
    for name in ('compare.json', 'dark-delta.json', 'freeze-gap-proof.json'):
        if json.loads((ev/name).read_text()).get('status') != 'PASS':
            raise ValueError('database evidence is not PASS: '+name)


if __name__ == '__main__':
    action, directory, cid, host = sys.argv[1:5]
    ev = Path(directory).resolve()
    if action == 'seal':
        result = Path(sys.argv[5]).resolve()
        if result.parent != ev: raise ValueError('API receipt outside evidence directory')
        names = REQUIRED+[result.name]
        seal = dict(cutover_id=cid, target=host, api_result=result.name, files={n:digest(ev/n) for n in names})
        # Refuse replacing a prior successful seal. The step archives it before a retry.
        with open(ev/'dark-verified.json', 'x', opener=lambda p,f: os.open(p,f,0o600)) as out:
            json.dump(seal,out,indent=1)
    elif action != 'check': raise ValueError('unknown command')
    check(ev,cid,host)
