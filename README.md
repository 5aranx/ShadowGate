# ShadowGate

Authorized fleet agent-management platform. mTLS identity, an atomic job
queue, a signed plugin architecture, DAG runbook orchestration, and a
hash-chained audit log. Linux-first, Python 3.12+.

> This is an agent-management tool for hosts you own and administer. There is
> no covert-channel, exfiltration, or evasion code anywhere in the tree.

## Features

- **Agent identity** — one-time enrollment tokens, per-agent mTLS certs
- **Atomic queue** — `UPDATE … RETURNING` exactly-once dispatch (SQLite WAL)
- **Plugin system** — builtin actions plus ed25519-signed third-party plugins
  loaded via `shadowgate.actions` entry points
- **Runbooks** — YAML DAGs with cycle validation, fan-out, per-run concurrency
  caps, and compensating steps on failure
- **Audit** — append-only SHA-256 chain; any edit breaks verification
- **Dashboard** — server-rendered Jinja2 + HTMX at `/ui`

## Quickstart

```bash
uv sync --extra dev
uv run pytest                 # 12 passing
uv run ruff check src tests   # clean
uv run mypy                   # strict, clean
uv run uvicorn shadowgate.server.app:app --port 8080
```

Then:

```bash
TOKEN=$(curl -s -X POST localhost:8080/tokens | jq -r .token)
curl -X POST localhost:8080/enroll -d "{\"agent_id\":\"a1\",\"token\":\"$TOKEN\",\"tags\":\"linux\"}" \
  -H 'Content-Type: application/json'
curl -X POST localhost:8080/jobs -d '{"agent_id":"a1","action":"system_info"}' \
  -H 'Content-Type: application/json'
open http://localhost:8080/ui
```

## Layout

```
src/shadowgate/
  server/   app, store, queue, runs, orchestrator, audit
  agent/    executor, long-poll client
  plugins/  Action protocol, registry, loader, gate, builtins
  crypto/   mTLS CA, ed25519 signing
  cli/      `shadowgate` entry point
  web/      templates + static
docs/       architecture.md, threat-model.md
examples/   runbooks/*.yaml
tests/      queue concurrency, audit tamper, plugins, signing, runs
```

## Plugin example

```python
# inside your package, pyproject.toml:
# [project.entry-points."shadowgate.actions"]
# disk_health = "mypkg:DiskHealthAction"
```

Ship a `shadowgate_plugin.json` manifest signed with the org ed25519 key, and
the gate will load it; otherwise it's dropped before import.

## CI

`.github/workflows/ci.yml` runs ruff, mypy --strict, and pytest on every push.
