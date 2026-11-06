# Phase 2 increment: explicit migrations and fenced render attempts

This increment adds migration-managed schema and reliable DB-backed claims. It
is not the complete Phase 2 roadmap. No external queue/storage service, paid API,
billing or public deployment is enabled.

This document describes the initial lease increment. The next additive revision
`0003_submission_keys` and queue/cancel behavior are documented in
[queue controls](QUEUE_CONTROLS.md). For an already migrated database, run the
normal upgrade command after backup; do not repeat legacy adoption unnecessarily.

## Existing Windows installation: preserve your accounts and completed videos

Stop **both API and worker** with Ctrl+C before upgrading. Never run old and new
workers together. From the repository root, after merging/pulling this branch:

```powershell
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements-dev.txt
# Default local SQLite DB, with API/worker stopped:
$backup = ".data\nextphase-before-phase2-$(Get-Date -Format yyyyMMdd-HHmmss).db"
Copy-Item .data\nextphase.db $backup
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate --adopt-legacy
```

If your `.env` uses a different database location, back up that actual database
instead. Preserve the media directory too; migrations never delete footage.
`--adopt-legacy` compares the unversioned schema against a frozen Stage 1 schema
before stamping it, then upgrades. Unknown/modified schemas are rejected without
being stamped. It preserves accounts, job metadata and completed output paths.
Interrupted legacy jobs with fewer than two attempts are requeued; exhausted
ones become failed. Do not force a stamp to bypass a mismatch.

Restart API and worker normally afterward. Current schema is required at startup;
startup never creates/updates tables. Existing successes still download from their
old `job/output.mp4` path. New renders use `job/<claim-token>/output.mp4`.

For a **new empty database**, run `python -m app.migrate` before starting services.
For later versioned upgrades the same command applies; `--adopt-legacy` is not
needed. Run one migration process at a time. PostgreSQL is required for staging
and production; SQLite remains a local-development option. The migration CLI is
an explicit online upgrade command, not an offline SQL generator. Downgrades are
intentionally rejected; rollback requires stopped services, prior code and a
verified DB backup. SQLite DDL upgrades should always have a backup even when
transactional migration tooling is used.

## Docker Compose

Fresh stacks run a one-shot `migrate` service after PostgreSQL readiness and before
API startup; the worker waits for API readiness. Existing unversioned volumes
require explicit adoption first, while all old API/worker services are stopped:

```bash
docker compose stop api worker
docker compose build
# Back up the PostgreSQL database and media volume using your verified backup procedure.
docker compose run --rm migrate python -m app.migrate --adopt-legacy
docker compose up -d --wait
```

Do not delete volumes to fix migration errors. Versioned stacks use the ordinary
one-shot migration command. Managed proxy builds must include the optional CA
secret for **api, worker and migrate** in their local override; see DEVELOPMENT.md.
No secret values belong in code or migrations.

## Claim and recovery semantics

Claims compare-and-set queued → processing in one transaction. PostgreSQL also
uses SKIP LOCKED; SQLite uses the atomic conditional update with a 30-second busy
timeout. Losing claimants return no job and poll again. Order is creation time
then ID. Each claim increments the attempt counter and generates a UUID token.

The lease lasts `RENDER_TIMEOUT_SECONDS + 90` seconds; the margin covers probing
and finalization around the bounded render subprocess. Worker clocks must be
synchronized. There is no heartbeat/extension mechanism in this increment.
Expired attempts cannot complete, even before recovery runs. Recovery atomically
requeues attempt one or marks attempt two MAX_RETRIES. The DB remains the queue;
there is no exactly-once execution guarantee. Repeated rendering after a crash is
possible, but stale attempts cannot overwrite accepted DB results or winner files.

Every render writes into its token-specific directory. Finalization requires the
same active token, processing status and an unexpired lease. A losing completion
removes only its own output. A database outage can still terminate a worker;
Compose restarts it. Hard-killed renders may leave attempt directories/partial
files, so retention/janitor work remains open. There is no submit idempotency key,
user fairness, cancellation, durable broker, per-user quota or production sandbox
yet. Existing render errors remain terminal rather than retrying arbitrary media.

## Validation

Run the normal suite on SQLite. To repeat against an isolated PostgreSQL database:

```bash
NEXTPHASE_TEST_DATABASE_URL=postgresql+psycopg://nextphase:localdev@127.0.0.1:5544/nextphase_test PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests -q
```

Use only a disposable database whose name ends `_test`; the suite adds test rows.
Migration tests create and remove their own PostgreSQL schemas. The fixture never
uses the application database by default. CI runs both database variants.

Coverage includes fresh/repeat upgrades and model/schema equivalence, legacy
preservation and unknown-schema rejection, stale-version startup checks, staging
SQLite rejection, four simultaneous claimant processes / 12 jobs, bounded retry,
a process exiting immediately after claim, expired-token rejection, stale output
isolation and legacy downloads. The live smoke now migrates its isolated database
before launching API and worker. It still validates real rendering and download.

Revision `0004_upload_sessions` is covered by [resumable uploads](RESUMABLE_UPLOADS.md).
