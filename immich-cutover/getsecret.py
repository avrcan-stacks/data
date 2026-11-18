"""Prints the value of KEY exactly as the running CONTAINER received it (what Compose resolved from env_file/quoting/interpolation).

    export NEWPW="$(python3 -I getsecret.py immich_server DB_PASSWORD)"

The value is written to stdout only (for command substitution) - never to a file or a log. Use it instead of parsing .env with sed/cut:
special characters ($ ' " # \\ space =) are then irrelevant because the application receives the very same string.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from cutlib import container_env
if len(sys.argv) != 3:
    sys.exit('usage: getsecret.py CONTAINER KEY')
sys.stdout.write(container_env(sys.argv[1], sys.argv[2]))
