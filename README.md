# ShadowGate

Authorized fleet agent management platform. mTLS identity, atomic job queue,
signed plugin architecture, DAG orchestration, hash-chained audit log.

> This is an agent-management tool for hosts you own and administer. There is
> no covert-channel, exfiltration, or evasion code anywhere in the tree.

## Quickstart

```bash
uv sync --extra dev
uv run pytest
uv run shadowgate --help
```

## Layout

- `src/shadowgate/server/` — control-plane API, models, atomic queue, audit
- `src/shadowgate/agent/`  — executor + long-poll client
- `src/shadowgate/plugins/`— Action protocol, registry, loader, builtins
- `src/shadowgate/crypto/` — mTLS CA + ed25519 plugin signing
- `tests/`                 — exactly-once queue, audit tamper, plugins, signing

See `docs/` for architecture and the threat model.
