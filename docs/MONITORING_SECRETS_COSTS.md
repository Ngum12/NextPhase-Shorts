# Phase 2 package 4 — monitoring, secret files and measured cost coverage

This increment adds private operator tooling, not a public monitoring endpoint,
customer billing, AI processing or a paid monitoring integration. No automatic
network exporter, mail sender, external collector, cloud vault or funds are activated.
Output remains server-rendered 9:16 and at most 60 seconds.

## Upgrade and focused acceptance

Stop native API/worker/supervisor processes. Back up the **active** database and
media; the Docker PostgreSQL database is separate from `.data/nextphase.db`.
For Docker, follow the backup/restore guidance for the PostgreSQL deployment; a
copy of the old SQLite file is not a PostgreSQL backup. Pull the reviewed merge,
then `docker compose up --build -d` applies additive migration **0018** before
starting API/workers. Do not use `down --volumes` to upgrade. Keep mail sending off.
Native development uses the existing venv, `PYTHONPATH=apps/api`, `python -m
app.migrate`, then restarts its processes. No new Python/npm dependency is required.

Run one ordinary Pixel upload/render/save, then from the repo root:

```powershell
docker compose exec -T worker python -m app.monitoring --check
```

Share only that aggregate JSON report; it omits account/project/trace IDs, titles,
paths, provider endpoints, recipient details and secret values. Historical jobs
without observations stay unknown. `status: ok` covers evaluated alert rules,
**not** complete cost coverage or production/security acceptance. The owner need
not manually repeat the full regression suite.

## Trace model and OpenTelemetry interoperability

The API creates its own random 128-bit trace and 64-bit span IDs, returns
`X-Trace-ID`, and records only fixed media-route stage names. It ignores untrusted
incoming traceparent/baggage/headers. A successful admission stores trace/parent
IDs transactionally with the job; the queue message still contains only a generation
UUID. Every retry uses the job trace with its own attempt span. Downloads bind to
the same trace only after authorization. Existing historical jobs remain nullable;
workers use their canonical job UUID as a deterministic fallback trace.

Earlier resumable-part requests retain their own request traces/aggregate bytes;
per-job attribution is not fabricated before admission. Measurements are bounded
to 32 stage rows per recorder. Stages: HTTP upload/control/
download, attempt, source fetch/probe, encode, output probe and output publish.
Start/end Unix nanoseconds, monotonic wall duration and outcome are recorded.
No filename, raw URL/query, user ID, request body/header, prompt, token, transcript,
exception message or stack trace enters this sink. Third-party/edge/host logs and
operators remain outside a universal redaction guarantee. Uvicorn raw access logging
is disabled by the API; fixed JSON request completion events replace it. Worker
JSON events carry active trace/span IDs. Logs and trace IDs are private metadata.

```powershell
docker compose exec -T worker python -m app.monitoring --format otlp --output /tmp/nextphase-traces.json
docker compose cp worker:/tmp/nextphase-traces.json .data/nextphase-traces.json
```

Choose a new filename for later exports. Output is create-only UTF-8 with POSIX
mode 0600, refuses overwrite/symlinks, and prints only a confirmation. Protect the
Windows destination using current-user NTFS permissions. `/tmp` exports disappear
on container recreation. Delete disposable exports after review under your approved
retention policy. No trace bodies are uploaded as CI artifacts.

The file uses **OTLP/HTTP JSON `resourceSpans`/`scopeSpans`/`spans`**, hexadecimal IDs,
protobuf JSON decimal strings for 64-bit timestamps/integers, typed attributes and
fixed service/scope. It can be POSTed to an approved collector's `/v1/traces` using
`application/json`; collector authentication, TLS, storage and sending require a
separate reviewed deployment. This package exports a real protocol document; it
has not deployed or independently tested an external collector. The default window
is 24 hours, maximum 744; `--limit` is 1–10000. Export refuses silent truncation.
Read-only exports are repeatable and can duplicate spans when reimported.

Trace commits are separate from business transactions and best effort: telemetry
failure must not undo an accepted job/download. A hard kill can lose buffered spans.
Fixed `observation_write_unavailable`/`observation_state_unavailable` warnings and
missing-attempt coverage expose gaps. This is not lossless audit logging, sampling
of every process, a complete distributed provider trace or progress percentage.

## Resource measurements

Linux encoder `/proc/<child>/stat` samples record CPU seconds **lower bounds** and
maximum **sampled** RSS, at the existing approximately 250ms supervision cadence.
Short/unsupported/failed observations can be missing; values are never relabeled
exact CPU or true peak memory. Probe and storage stages have wall timings. QA
records a frame-count estimate from validated duration × fixed 30 fps and average
encode throughput from that estimate/encode wall duration; not FFmpeg progress or
instantaneous FPS. No GPU/AI work is used by this baseline and no GPU/AI meter is
invented. A worker crash retains unknown time, and retries have distinct attempts.

## Cost units and unknowns

Without an explicit rate card every monetary value is **null**, never “free.”
The units are retained and can be repriced with approved real rates later:

- worker hours: measured attempt wall seconds / 3600, summed across retries;
- storage GiB-days: known original/successful-output bytes × time after recorded
  storage/admission until observed project cleanup completion, clipped to the window;
- API egress GiB: ASGI body bytes handed to the server, including repeated downloads,
  not TCP ACKs or proof of a client saving the bytes;
- storage read/write GiB: successful worker source fetch/output publication bytes.

Known artifact lifetime is an accounting approximation of the physical interval;
cleanup may remove a file earlier within its transaction. Originals are measured
atomically at new admission, outputs after fenced success. Old media is not
backfilled from reservations; records without measurements are explicitly counted.
A telemetry failure after success can leave unknown output coverage. Interrupted
network transfers may have billable partial bytes that this meter cannot observe.

**Excluded/unknown:** direct signed GET/PUT traffic (issuing a capability is not a
transfer), staging/unaccepted/orphan/backup/versioned objects and metadata, failed
storage traffic, API/database/broker/idle worker compute, provider request fees,
taxes/discounts and unsampled decoder resources. Provider access/billing exports
and physical inventory are required to close total-cost coverage at staging;
this increment cannot infer these from the mobile app or broker.

Synthetic calculation-only card, **not a quote or current provider price**:

```json
{"version":1,"currency":"USD","rates":{"worker_hour":"1.00","storage_gib_day":"0.01","api_egress_gib":"0.10","storage_read_gib":"0.00","storage_write_gib":"0.00"}}
```

All five values must be finite nonnegative decimal strings. Explicit zero means
operator-entered zero, not a guessed free tier. Only USD is supported here. Store
an approved card privately and mount/copy it into the operator container before
using `--rates /path/to/rates.json`. Reports show component estimates, sample-counted
per-job **partial window** P50/P95, unknown coverage and truncation. Do not price
subscriptions or calculate gross margins from this tiny prototype sample.

## Alerts and metrics

```powershell
docker compose exec -T worker python -m app.monitoring --check
docker compose exec -T worker python -m app.monitoring --format prometheus
```

Prometheus text contains bounded fixed labels, no project/owner/trace cardinality.
All windowed values are gauges, not lifetime monotonic counters. Local alert checks
cover no fresh workers, expired/missing claims, skew/truncation, oldest queue wait
(default 300s), recent terminal failures (default five), measurement truncation,
and optional observed-cost threshold (`--rates ... --cost-alert-usd ...`). With a
cost threshold, missing rates/known coverage gaps also require attention. The
operations failure window is at most seven days even if the cost window is longer.

Exit **0**: evaluated checks clear; **1**: attention; **2**: unavailable/invalid
configuration/export bounds. Invalid argparse options also return 2. No process
recovery, deletion or lease mutation is performed. Schedule this command in the
approved host/collector tooling and route nonzero exits to the operator; no external
alert delivery or scheduler is installed here. Thresholds are conservative local
checks, not calibrated SLOs. The cost threshold is an **alert on partial observed
cost**, never a provider billing stop or total infrastructure ceiling. Global
admission/capacity and staging's approved hard ceiling remain packages 5–6.

## Secret management and rotation

Server settings now support either a value or a mounted file, never both:
`JWT_SECRET`, `DATABASE_URL`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY`,
`QUEUE_PASSWORD`, `RESEND_API_KEY`, `AUTH_MAIL_ENCRYPTION_KEYS`, each with `_FILE`.
Files are at most 16KiB, one UTF-8 line (terminal newlines allowed), regular,
non-symlink/non-junction; POSIX denies world permissions and group write/execute
(0600 or group-readable 0640/0440). Parent directories must be operator-controlled;
this is not a defense against a malicious host administrator replacing parents.
Do not use FIFOs, log values, or store files in media/Git/mobile. Secret values are
not copied into process environment variables or decoder environments by the loader.

Mount read-only files from an approved secret manager/runtime and grant only the
necessary service access. Local env/env_file remains supported for development.
Compose's existing default PostgreSQL password/env files are **development-only**;
this does not magically convert them into a cloud vault or production credential.
The monitor reports only source type (`file`, `environment`, `unset`), never values,
hashes/fingerprints or private file paths. Restart every consumer after rotating;
cached settings are not silently reloaded mid-job.

Rotation procedure: back up DB/media and encrypted-mail key ring privately; stop
or drain writers; prepare replacement in the secret manager/private file atomically;
restart API/workers/supervisor/mail sender as applicable; verify readiness and a
synthetic authorized operation; retire the old provider credential only after
all consumers switch. Provider/IAM revocation and external audit are operator tasks.

- JWT secret: deliberate all-session reset; old access signatures, refresh hashes,
  action bindings and auth limit HMAC keys stop matching. Users sign in again with
  existing passwords; accounts/media remain. Do not promise seamless rotation or
  delete old DB account/media records. Existing refresh/action windows expire under
  ordinary maintenance. Never switch while a lost-response refresh is being recovered.
- Mail encryption: retain old decrypt keys while placing the new key first, use
  the existing bounded re-encryption CLI in EMAIL_DELIVERY.md, verify zero old-key
  envelopes before retiring old keys. Loss of keys fails affected mail closed.
- Broker: drain/stop dispatch consumers and supervisor, change the private server
  config and matching client secret together, restart/validate AOF + authentication;
  DB reconciliation recovers signals. Do not flush queues or publish passwords.
- S3/database/Resend: provision a least-privilege replacement outside chat, roll
  consumers and test before revoking old credentials. Namespace identity changes
  can block historical media; follow PRIVATE_OBJECT_STORAGE.md instead of claiming
  a newly empty bucket proves erasure. Keep real sending disabled during routine QA.

The tests cover rejected secret files, loaded values not entering the environment,
ambiguity, access revocation under a changed JWT secret and preservation of the
account; prior mail rotation tests remain. They do not claim provider/IAM rotation
or automatic secret-manager provisioning. No secrets need to be pasted into chat.
