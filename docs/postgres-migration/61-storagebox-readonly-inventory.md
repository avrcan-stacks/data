# 61 — Storagebox Readonly Inventory

## 1. Connection Test

- **SSH command:** `ssh storagebox 'pwd; ls -la; df -h .'`
- **Status:** Successfully connected
- **Working directory:** `/home`

## 2. Capacity Overview

```text
Filesystem      Size  Used Avail Use% Mounted on
/dev/root       1.0T  128G  892G  13% /home
```

## 3. Existing Content

```text
total 24
drwxr-xr-x 3 u722659 users 4096 Nov  1 08:00 .
drwxr-xr-x 3 root    root  4096 Nov  1 07:58 ..
-rw-r--r-- 1 u722659 users  220 Nov  1 07:58 .bash_logout
-rw-r--r-- 1 u722659 users 3526 Nov  1 07:58 .bashrc
-rw-r--r-- 1 u722659 users  807 Nov  1 07:58 .profile
drwx------ 2 u722659 users 4096 Nov  1 08:00 .ssh
```

## 4. Proposed Structure

Recommended backup directory structure:

```text
/home/
└── backups/
    ├── postgres/    # For PostgreSQL dumps
    ├── postgis/     # For legacy PostGIS backups
    └── immich/      # For Immich media backups
```

## 5. Security Notes

- No existing backup directories found.
- No unexpected files detected.
- Default Hetzner permissions are restrictive (`700` for `.ssh`).
- No sensitive data exposed in the inventory.

## 6. Next Steps

1. **Approval required** for:
   - Creating `/home/backups`.
   - Setting up the initial permission structure.
2. **Recommended**:
   - Verify the SSH key rotation policy.
   - Document retention periods before implementation.

**Status:** `STORAGEBOX_INVENTORY_COMPLETE — NO_REMOTE_CHANGES`
**Timestamp:** `2026-11-18T11:15:00Z`

### Verification

- No directories or files were created or modified.
- All operations were read-only.
- No credentials or keys were exposed.
- Existing SSH configuration remains unchanged.

## Key Findings

1. 892 GB is available (13% used).
2. The Hetzner environment is clean and uses the default layout.
3. The proposed structure is feasible.
4. No immediate security concerns were detected.
