# Threat model

ShadowGate is meant to be run **only** on infrastructure you own and have been
authorized to administer. It is designed to make unauthorized use hard.

## Assets

- Agent identity keys (`ca.key`, agent certs, org signing key)
- The job queue and task results (may contain host metadata)
- The audit log's integrity

## Trust boundaries

- Agent certs are issued per agent by the local CA and pinned at enrollment;
  re-enrollment requires a fresh one-time token.
- Enrollment tokens are single-use and expire; a second use of a burned token is
  rejected with 403.
- Plugin loads are gated by org signature; an unsigned or tampered manifest is
  rejected before the action object is even imported.

## Explicit non-goals / guardrails

- **No remote shell execution plugin.** Actions are narrow, declared
  data-fetchers (`system_info`, `disk_health`, `file_fetch`, `service_status`).
- **No obfuscation, no traffic hiding, no persistence mechanisms, no
  exfiltration channel.** Any PR introducing these is rejected.
- Agents only ever pull work that names their own agent id (`claim_next(agent_id=…)`).

## Failure modes

| Failure | Handling |
|---|---|
| Duplicate HTTP delivery of a result | Queue row already terminal → idempotent `complete` |
| Worker crash mid-job | Row stays `running`; operator surface for re-queue (future) |
| Audit log tampered | `verify_chain()` returns false; head hash mismatch |
| Compromised plugin package | Signature gate blocks load unless org key also compromised |
| Enrollment token reuse | Burned token rejected; agent can't re-enroll |

## Reporting

If you find a way this gives an unauthorized party control of an agent, open an
issue — that's a high-severity bug.
