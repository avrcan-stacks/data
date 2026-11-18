"""Rehearsal wrapper for the docker CLI: applies the production guard and appends the argv to $CUTOVER_AUDIT, then executes the real docker.
Used by steps.sh only when CUTOVER_REHEARSAL=1 (shell function `docker`)."""
import os, shutil, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import cutlib
args = ['docker'] + sys.argv[1:]
try:
    cutlib.guard(args)
except PermissionError as e:
    sys.stderr.write(str(e) + '\n'); sys.exit(97)
cutlib.audit(args)
real = shutil.which('docker')
os.execv(real, ['docker'] + sys.argv[1:])
