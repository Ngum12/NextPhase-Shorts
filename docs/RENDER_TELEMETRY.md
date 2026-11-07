# Phase 2: render measurements and operator cost estimates

This increment measures the existing baseline renderer. It adds no AI, editing
effects, paid service or billing. No new dependencies or reference-kit assets.

## Upgrade on Windows

Stop API, worker and Expo. Back up the actual configured database and media
before pulling; these commands assume the default SQLite location:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
$backup = ".data\nextphase-before-telemetry-$(Get-Date -Format yyyyMMdd-HHmmss).db"
Copy-Item .data\nextphase.db $backup
git pull
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
.\.venv\Scripts\python.exe scripts/smoke_e2e.py
```

Migration `0006_render_attempts` adds an attempt table and indexes. It preserves
users, auth sessions, completed video paths and resumable uploads. No new sign-in
is required solely by this migration. No historical attempt timings are invented.
Do not run old/new workers together. Downgrade requires stopped services, prior
code and a verified database backup; never delete volumes to fix an upgrade.

For Compose: stop api/worker, back up PostgreSQL and media, build, run one migration
process (`docker compose run --rm migrate`), then `docker compose up -d --wait`.

Restart API/worker/Expo normally; keep the API's `--no-proxy-headers` flag and USB
forwarding. Upload/render/download one consented video on the Pixel. Then at the
repo root, in a terminal with PYTHONPATH set:

```powershell
.\.venv\Scripts\python.exe -m app.telemetry
# Optional calculation with YOUR verified allocated-worker hourly rate:
.\.venv\Scripts\python.exe -m app.telemetry --days 7 --hourly-rate 0.25 --currency USD
```

The 0.25 value is illustrative, not a provider quote or a configured charge.
The CLI does not provision resources, charge users or contact providers. Omit
--hourly-rate unless you know the relevant rate; cost then stays null, not zero.
The isolated smoke uses a temporary database, so its jobs do not appear in the
normal database report. Its own telemetry-report.json is under the printed
ignored .data/smoke-* evidence directory. After a real app render the normal DB
report should contain a succeeded attempt, positive output bytes and timing samples.

For Compose use `docker compose exec -T api python -m app.telemetry`. This is an
operator CLI using privileged DB access, not an unauthenticated metrics endpoint.
Do not publish its output as a customer dashboard or public health response.

## What is measured

- Each new claim inserts one attempt in the same transaction as the job claim.
  Attempts retain their own identity/number across retries. Old completions cannot
  overwrite a new attempt's metrics. Claim IDs never appear in aggregate reports.
- Success/failure timings are saved atomically with fenced job completion.
  Wall time uses a monotonic clock around rendering/probing/verification; it is
  **not CPU/GPU seconds**, peak memory or billable VM uptime. Output bytes refer
  only to an accepted successful artifact, not storage GB-days or egress.
- Cancellation is recorded in the cancel transaction even if the worker crashes.
  When the worker returns it records its observed wall time. Lease recovery marks
  an unfinished attempt lease_lost without guessing consumed compute from a lease.
  Unknown durations remain null; known failed/cancelled work is included in costs.
- First-claim queue wait uses job-created→claim timestamps. Retried claims are not
  mislabelled as pure queue time. Successful job turnaround uses job-created→finish
  and includes queue/retries; it excludes phone upload and download time. UTC wall
  clocks must be synchronized; negative clock deltas clamp to zero.
- P50/P95 use nearest-rank and explicit sample counts. Empty distributions are null.
  A tiny synthetic sample is not a production latency benchmark or SLA.
- Cost = sum(observed attempt wall seconds) × operator hourly rate / 3600, with
  decimal arithmetic and eight decimal places. It excludes unknown/crashed work,
  idle time, API/database, storage, network, GPU and AI/provider charges. It is a
  partial allocated-slot estimate, never an invoice, complete cost or gross margin.

## Window, coverage and privacy

Default window is seven days (allowed 1–365). Jobs are selected by creation time,
attempts by start time. Each table is independently bounded to the newest 10,000
rows (`--limit`, allowed 1–100000). `truncated=true` means the report is incomplete;
use a smaller window or a later warehouse/reporting pipeline before capacity or
pricing decisions. Long jobs can straddle windows; job and attempt cohorts differ.
`jobs_without_attempt_records` means no attempt in this sampled window, not proof
that a job never ran. `unmeasured_attempts` includes live, crashed and direct-test
completions without a duration. Never interpret a missing sample as free compute.

Reports include counts/distributions and totals, never emails, bearer/claim tokens,
user/job IDs, source paths, titles or exception text. Worker unexpected-error logs
keep a fixed message and server job ID instead of raw customer-path tracebacks.
No public aggregate API or secret-bearing exporter was added. The telemetry table
is private operational metadata; retention/deletion policy still needs definition.

## Remaining Phase 2 gates

Realistic rights-cleared load/soak datasets, peak memory and CPU/GPU measurements,
structured trace/export integration, worker heartbeats, dashboards/alerts, measured
resource/cost ceilings, full attempt recovery accounting and production SLOs remain.
This does not replace a durable broker, object storage, deletion/retention controls,
verified email recovery, security review, dependency/license clearance or consent.
All intensive editing stays on the server; exports remain 9:16 and <=60 seconds.

The owner subsequently reported Windows/Pixel acceptance passed: 81 backend tests,
full smoke and a playable new app render. One measured attempt (28.766 s, 7,206,440
output bytes) confirms recording on that setup; it is not a representative benchmark.
