# Migration rules

- Work only on this host (dedicated server).
- Never delete production data unless explicitly instructed. If reset is needed, ask first.
- Use Docker container named `postgis`.
- Dumps are located in `/opt/stacks/data/backups/`.
- Prefer safe, repeatable steps: verify -> apply -> verify.
- Log commands you run and paste key outputs.
