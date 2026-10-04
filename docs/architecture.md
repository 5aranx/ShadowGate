# Architecture

```
            +-------------------+        HTTPS/mTLS         +-------------------+
 operator   |  shadowgate       |  <------------------>     |  shadowgate agent |
 dashboard  |  server (FastAPI) |                           |  (daemon)         |
            |                   |                           |   executor        |
            |  Store (sqlite)   |                           |   plugin loader   |
            |   qjobs (WAL)     |                           +-------------------+
            |  RunEngine        |
            |  AuditLog (chain) |
            +-------------------+
```

## Control-plane components

| Module | Responsibility |
|---|---|
| `server/app.py` | FastAPI surface: tokens, enroll, jobs, poll, result, runs, ui |
| `server/store.py` | One WAL sqlite connection for agents, tokens, queue, runs |
| `server/queue.py` | Atomic exactly-once claim via `UPDATE … RETURNING` |
| `server/runs.py` | DAG materialization, concurrency cap, compensation |
| `server/audit.py` | Append-only SHA-256 hash chain, tamper-evident |
| `server/orchestrator.py` | Runbook YAML, validation, cycle rejection, targeting |
| `plugins/loader.py` | Builtin + `entry_points` discovery |
| `plugins/gate.py` | ed25519 signature gate for external plugins |
| `crypto/mtls.py` | Local CA, per-agent cert issuance |
| `crypto/signing.py` | Org key generation, manifest sign/verify |

## Data flow

1. Operator mints a one-time enrollment token → agent burns it once → agent is in `agents`.
2. Operator enqueues a job (`/jobs`) or starts a runbook (`/runs`).
3. Agent long-polls `/agent/poll`; server claims that agent's next queued job atomically and returns it.
4. Agent executes the action through its signed plugin registry, posts `/agent/result`.
5. Server completes the job, updates the run state machine, and every transition is appended to the audit chain.

## Queue concurrency

`SqlQueue` claims with a single `UPDATE` constrained to `status='queued'` and
`RETURNING`, so two workers cannot claim the same row. WAL + `busy_timeout`
make multi-connection reads live. Test: `tests/test_queue.py` runs 8 threads
over 40 jobs and asserts zero duplicates.

## Plugin trust

Builtin actions ship with the package and are implicitly trusted. Third-party
actions are discovered via the `shadowgate.actions` entry-point group but are
loaded only after `plugins/gate.make_verifier` validates a signed
`shadowgate_plugin.json` manifest against the pinned org public key.

## Audit integrity

`AuditLog.append` writes `prev = sha256(last_entry)` into each JSONL line, and
`verify_chain()` recomputes the chain. Any edit, deletion, or reorder breaks
the head — tested in `tests/test_audit.py`.
