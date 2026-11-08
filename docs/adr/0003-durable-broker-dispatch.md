# ADR 0003 — Valkey/Arq dispatch with PostgreSQL job authority

Status: implemented for package 3 review; strict processing-host acceptance open.

The owner delegated the queue choice. Use free self-hosted **Valkey 8.1.11** with
**Arq 0.28.0**. PostgreSQL retains job/attempt state, owner-turn scheduling,
admission budgets and fenced immutable output references. Valkey supplies durable
dispatch delivery; an encrypted/authenticated business payload is unnecessary
because dispatch contains only an internal generation UUID and fixed function name.
It carries no media path, account identity, user text, credentials or executable plan.

A dispatch request means **drain one eligible fair job**, not assign a particular
customer's job to a FIFO broker slot. This preserves the existing owner scheduler.
API admission commits a QueueSignal with the job. A bounded supervisor publishes
signals with stable IDs and reconciles pending work every two seconds. The worker
does not poll PostgreSQL while idle; Arq consumes the broker queue. Periodic outbox/
lease reconciliation remains intentional. A 60-second stale-signal threshold
repairs lost broker state; this is not an instantaneous outage-recovery guarantee.

Each consumer processes at most one job at a time. It completes its signal only
after the DB records a terminal/retry outcome or a durable no-eligible-work decision.
Arq acknowledges afterward. Duplicate/stale signals are inert. Retry outcomes
remain durable queued work and get another signal when due. Signal completion is
not a claim that the signal's originating job itself succeeded. The DB is the
authority for customer status, output ownership, attempts and eventual recovery.

Use JSON-only serialization with a strict fixed envelope; never Arq's default
pickle. Require authenticated broker access, AOF appendfsync always, no eviction,
bounded connections and queue size via memory failure, immutable pinned image and
private storage. Stage/production requires verified TLS. No HA, lossless storage
hardware, exactly-once execution or public production readiness is claimed.

Resource/isolation acceptance is independent of broker delivery. Strict workers
and decoder callers must be unprivileged, have finite enforced cgroup v2 limits,
and pass actual Landlock/seccomp canaries. Shared-kernel isolation is not a VM or
security certification. The managed test host lacks Landlock and finite worker
cgroups; its successful development broker flow does not close that host gate.

Alternatives remain operational options, not parallel implementations: a DB-only
adapter stays for native development/tests; Redis/Celery or RabbitMQ would add
another implementation/migration path. Valkey's BSD license and the existing
Python async stack fit this commercial project's free local foundation. Provider
hosting, costs, production secrets/ACLs/HA and disaster-recovery acceptance remain
subject to later package gates and owner approval for paid resources.
