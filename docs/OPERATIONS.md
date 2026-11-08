# Operational visibility in the developer preview

Package 3 adds a separate claim supervisor and durable dispatch operator snapshot;
see [QUEUE_RELIABILITY.md](QUEUE_RELIABILITY.md). Process-liveness pulses described
here remain independent of actual claim renewal and do not prove render progress.

This increment adds private operator snapshots, process liveness and structured
worker events. It does not activate an external monitoring service, public admin
console, alert delivery, paid infrastructure or AI. All intensive rendering remains
on the server, with the existing 9:16 and 60-second output limits.

## Upgrade first

Migration **0013_worker_pulses** adds only worker metadata; it does not alter
accounts, jobs, paths, rights records or pending-upload offsets. Stop API and
workers, back up the database/media using the existing runbook, pull, migrate and
restart updated server processes. No pip/npm dependency or mobile/native change.
Keep every server terminal's existing private S3 settings if enabled.

Windows, from the repository root:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
$backup = ".data\nextphase-before-operations-$(Get-Date -Format yyyyMMdd-HHmmss).db"
Copy-Item .data\nextphase.db $backup
git pull
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
.\.venv\Scripts\python.exe scripts/smoke_e2e.py
```

For a PostgreSQL installation, use its verified PostgreSQL backup process instead
of the SQLite copy command. Do not copy a live SQLite file or change real job lease
timestamps. Old workers must be restarted: they cannot publish these new pulses.
The existing strict Docker cgroup guard remains enabled; migration does not solve
unsupported host limits. See WORKER_RESILIENCE.md before Docker deployment.

## Liveness versus readiness

- GET `/health` is unchanged: API process liveness and the truthful baseline label.
- GET `/ready` checks database connectivity/current schema. It returns 200 with
  `{"ok":true,"service":"nextphase-shorts"}` or 503 with `ok:false`, always no-store.
  Exceptions/schema/credentials are not returned. Compose API health now uses it.
- Readiness does not check worker capacity, provider reachability or successful
  rendering. During worker restarts the API can still accept durable queued jobs.
  Probes use the existing database driver/pool timeouts; production timeout/edge
  controls and overload validation remain necessary.

No `/metrics`, public operations route or worker-list endpoint is introduced.

## Private operator commands

Use the same database settings as the API, from a trusted server terminal:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.operations
.\.venv\Scripts\python.exe -m app.operations --check
.\.venv\Scripts\python.exe -m app.telemetry
```

On Linux use `PYTHONPATH=apps/api .venv/bin/python -m app.operations`. In a configured
Docker deployment use `docker compose exec api python -m app.operations`.

`app.operations` reports:

- All current nondeleted job counts by state, oldest queued/processing age, expired
  processing leases and processing rows missing a deadline. Deleted projects are
  excluded even when their retained attempt history proves successful rendering.
- Attempt states for attempts **started** in the selected window, plus fixed failure
  codes for failed jobs **finished** in it. Unknown stored labels become `other`,
  never arbitrary database text. Default window 24 hours; `--hours` allows 1–168.
- Recent worker records: fresh, stale, stopped, clock-skew count and sampled phases.
  Default `--worker-limit 1000`, maximum 10,000; overflow is explicitly truncated
  and prevents an `ok` result. Worker records outside the window are not counted.

Reports contain no emails, user/job/worker IDs, titles, filenames, source paths,
URLs, receipt keys or credentials. They require local server/database access;
there is no client-side privileged token. Protect stored reports and server logs.
Full aggregate SQL cost at scale still needs measurement; row caps apply to worker
record fetching, not a promise of constant-time database aggregates.

Without `--check`, a successfully produced attention report exits zero. With it,
exit 0 means no listed issues, 1 means attention (no fresh workers, expired/missing
claims, skew or incomplete worker coverage), and 2 means unavailable DB/schema or
invalid CLI arguments. Unavailable output is sanitized JSON. `ok` is not an SLA,
a guarantee of forward progress or a production capacity measurement. Ages/counts
are a multi-query observation and may change during reporting; no queue mutations
or automatic retries/deletions are triggered by this command.

The existing `app.telemetry` remains the timing/optional partial compute-estimate
report. No provider charges or CPU/GPU billing measurement was added.

## What a worker heartbeat means

Each updated worker process registers a random ID, timestamps, interval and sampled
phase in `worker_pulses`; it stores no hostname, PID, user or media reference.
A separate thread writes every `WORKER_HEARTBEAT_SECONDS` (default 10, allowed 1–60)
using its own short database session, including while foreground rendering runs.
Freshness allows `3 * advertised_interval + 15` seconds (45 seconds by default).
Future timestamps beyond five seconds are flagged as clock skew, not healthy.

Heartbeat liveness does **not** renew a job lease or prove that rendering advances.
A hung main loop can still have a live heartbeat; inspect queue age, phases, lease
expiry and failure events too. Existing fenced leases/retry limits remain authoritative.
DB write failures leave the last timestamp unchanged, log a safe event and retry
on the next tick. DB outages make the operator CLI unavailable rather than falsely
claiming a full worker outage.

Orderly exit stops the thread and marks the record stopped. Hard kills cannot
record shutdown; the record remains apparently fresh until its deadline, then
stale. Windows `Popen.terminate()` is a hard kill; the smoke does not claim graceful
Windows SIGTERM behavior. Old stopped/crashed metadata is retained; the report's
window bounds visibility, not storage retention. Bounded metadata retention and
external watchdog/heartbeat delivery guarantees remain future work.

## Structured worker events

New worker lifecycle, render outcomes, database retry, heartbeat failure and lease
recovery events are JSON records with schema version, UTC timestamp, level,
component and a fixed event/message. Optional fields are narrowly validated opaque
job/worker UUIDs, durations, phase or bounded recovery counts. Arbitrary payloads,
URLs, titles, tokens and exception text are rejected. Heartbeats do not log every
successful tick. Correlation UUIDs are operational data; do not publish raw logs.

Legacy maintenance/third-party output may remain plain text. This is not a complete
OpenTelemetry exporter, distributed tracing setup, global log-redaction guarantee,
log rotation policy or alerting service. Review logging/retention before public use.

## Validation and operator checks

The isolated HTTP smoke verifies readiness, live worker reporting, queue counters,
advanced heartbeat timestamps and structured render events. After stopping only its
own writers, it checks stopped state (POSIX), a synthetic expired lease and CLI exit
1. It advances only the stopped fixture report's observation clock 200 seconds to
check stale-worker classification; it never edits a real job or claims a real waiting
interval. The S3 smoke repeats these checks through direct uploads and real rendering.
`operations_smoke.py` refuses databases outside the disposable SQLite smoke fixture.

After upgrade, start the API/worker and run `/ready` plus `app.operations`. With an
active updated worker expect fresh >=1; if it is stopped, no_fresh_workers is expected.
Run one upload/render/save, inspect its completion event and verify queued work
settles. Confirm old projects and paused uploads remain available. Physical Pixel,
strict Docker-host and sustained load/soak acceptance remain separate checks.
