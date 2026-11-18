#!/usr/bin/env bash
# Safe handling of the temporary Immich API keys (phase 8B). SOURCE this file. It never prints a key value and never writes one anywhere.
#   keys_new_file     creates /root/.immich-cutover-keys.env with PLACEHOLDERS (0600), refuses to overwrite an existing file
#   keys_load         checks owner/mode of the file and of /root, loads the keys into THIS shell's environment (placeholders are ignored); prints names + lengths only
#   keys_verify_meta  READ-ONLY database check of api_key METADATA (name, owner, permissions; the key hash column is never selected):
#                     exactly one admin key with the 7 permissions, exactly one user key with the 3 permissions owned by a non-admin with photos+albums, and NO key with 'all'
KEYS_FILE="${KEYS_FILE:-/root/.immich-cutover-keys.env}"
KEYS_ADMIN_PERMS="job.create library.read library.statistics queue.read queue.update server.about server.statistics"
KEYS_USER_PERMS="album.read asset.read person.read"
_k_stat() { stat -c "$1" "$2" 2>/dev/null; }
keys_new_file() {
  [ ! -e "$KEYS_FILE" ] || { echo "REFUSED: $KEYS_FILE already exists (never overwritten)" >&2; return 1; }
  ( umask 077; cat > "$KEYS_FILE" <<'EOF'
# Immich cutover temporary API keys. OUTSIDE git, root:root 0600. Never paste into chat, files in the repo, or evidence.
# admin key, exactly: job.create library.read library.statistics queue.read queue.update server.about server.statistics
IMMICH_ADMIN_API_KEY=PASTE_ADMIN_KEY_HERE
# user key (account with photos and albums), exactly: album.read asset.read person.read
IMMICH_USER_API_KEY=PASTE_USER_KEY_HERE
EOF
  ); chmod 600 "$KEYS_FILE"; echo "created $KEYS_FILE (placeholders, 0600)"
}
keys_load() {
  [ -f "$KEYS_FILE" ] || { echo "KEYS FAIL: $KEYS_FILE does not exist" >&2; return 1; }
  [ "$(_k_stat %U "$KEYS_FILE")" = root ] && [ "$(_k_stat %a "$KEYS_FILE")" = 600 ] || { echo "KEYS FAIL: $KEYS_FILE must be owned by root with mode 0600 (is $(_k_stat '%U %a' "$KEYS_FILE"))" >&2; return 1; }
  [ "$(_k_stat %a /root)" = 700 ] || echo "KEYS WARN: /root is mode $(_k_stat %a /root), expected 700" >&2
  case "$KEYS_FILE" in /opt/stacks/*|/tmp/*) [ "${KEYS_TEST:-0}" = 1 ] || { echo "KEYS FAIL: the key file must live in /root, not in a repository or /tmp" >&2; return 1; };; esac
  local k v bad=0 lines
  for k in IMMICH_ADMIN_API_KEY IMMICH_USER_API_KEY; do
    lines="$(sed -n "s/^$k=//p" "$KEYS_FILE")" || { unset IMMICH_ADMIN_API_KEY IMMICH_USER_API_KEY; return 1; }
    [[ "$lines" != *$'\n'* ]] || { echo "KEYS FAIL: duplicate entry for $k" >&2; unset IMMICH_ADMIN_API_KEY IMMICH_USER_API_KEY; return 1; }
    v="${lines%$'\r'}"
    case "$v" in ""|PASTE_*) bad=1; unset "$k"; echo "KEYS INFO: $k not set (placeholder)";; *) [ "${#v}" -ge 20 ] && [ "${#v}" -le 128 ] && [ -z "${v//[A-Za-z0-9_-]/}" ] && { export "$k=$v"; echo "KEYS OK: $k loaded (length ${#v}, value not shown)"; } || { bad=1; unset "$k"; echo "KEYS FAIL: $k has an unexpected format (spaces, quotes or wrong length)" >&2; };; esac
  done
  unset v
  if [ "$bad" != 0 ]; then unset IMMICH_ADMIN_API_KEY IMMICH_USER_API_KEY; return 1; fi
  return 0
}
keys_verify_meta() {
  local PGC="${PG_SRC:-postgis}" bad=0 rows; rows="$(docker exec "$PGC" psql -X -U postgres -d immich -At -F'|' -c "SELECT k.name, u.\"isAdmin\", (SELECT count(*) FROM asset a WHERE a.\"ownerId\"=u.id AND a.\"deletedAt\" IS NULL), (SELECT count(*) FROM album_user au JOIN album al ON al.id=au.\"albumId\" WHERE au.\"userId\"=u.id AND au.role='owner' AND al.\"deletedAt\" IS NULL), (SELECT string_agg(p, ' ' ORDER BY p) FROM unnest(k.permissions) p) FROM api_key k JOIN \"user\" u ON u.id=k.\"userId\" ORDER BY k.\"createdAt\"")" || { echo "KEYS FAIL: cannot read api_key metadata" >&2; return 1; }
  echo "$rows" | awk -F'|' '{printf "INFO  key \"%s\" owner_admin=%s assets=%s albums=%s perms=[%s]\n", $1,$2,$3,$4,$5}'
  [ "$(echo "$rows" | awk -F'|' -v p="$KEYS_ADMIN_PERMS" '$2=="t" && $5==p' | wc -l)" = 1 ] && echo "PASS  exactly one admin key with the 7 permissions" || { echo "FAIL  no (or more than one) admin key with exactly: $KEYS_ADMIN_PERMS"; bad=1; }
  [ "$(echo "$rows" | awk -F'|' -v p="$KEYS_USER_PERMS" '$2=="f" && $5==p && $3>0 && $4>0' | wc -l)" = 1 ] && echo "PASS  exactly one user key with the 3 permissions on an account with photos and albums" || { echo "FAIL  no (or more than one) user key with exactly: $KEYS_USER_PERMS (non-admin owner with photos and albums)"; bad=1; }
  [ "$(echo "$rows" | awk -F'|' '$5 ~ /(^| )all( |$)/' | wc -l)" = 0 ] && echo "PASS  no key with the 'all' permission" || { echo "FAIL  a key with the 'all' permission exists (revoke it)"; bad=1; }
  [ "$bad" = 0 ]
}
