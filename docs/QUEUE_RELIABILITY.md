# Phase 2 package 3 — durable queue and worker supervision

## What is implemented and what is blocked

Valkey/Arq dispatch, transactional signals, bounded reconciliation, renewable
fenced claims with absolute deadlines, transient retry/backoff and explicit dead
letters are implemented. Strict mode adds per-decoder filesystem/network isolation
and requires actual unprivileged cgroup-limited Linux execution. Database mode
remains the default for native development; Compose now selects Valkey with strict
guards for API/worker. Paid services, AI, email sending and billing are not enabled.

**The managed cloud host cannot pass strict host acceptance:** Landlock version
query returns ENOSYS and the Docker daemon has cgroup driver none; observed limits
are outer/shared rather than per-worker. Required mode refuses this host. We did
not disable its production guards or count the development flow as that proof.
Package 3 stays open until a supported host passes the focused check and review/CI.

## Upgrade and the one host check

Stop API/render/queue-supervisor processes, back up DB and media, pull the reviewed
merge, install Python requirements and migrate **0017**. Existing jobs/media/
accounts/uploads/consent and fixed two-attempt storage reservations are preserved.
Active legacy claims keep their existing lifetime bound; old failures become
dead-letter records labeled LEGACY_FAILURE without copying private error strings.

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
git pull --ff-only
.\.venv\Scripts\python.exe -m pip install -r apps/api/requirements-dev.txt
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe scripts/configure_queue.py
docker compose build worker
docker compose run --rm --no-deps worker python -m app.worker_hostcheck
```

The helper prints no password, preserves existing credentials and creates private
ignored `.data/queue-private/` files. Host directory is 0700 on POSIX; the broker
configuration is readable through its single-file container mount. Protect the
folder with current-user NTFS permissions on Windows. Never upload/print/commit
client.json, client.env or valkey.conf. No resource starts merely by preparing them.

The check must report **ready: true** with all three fields enforced: unprivileged
user, cgroup limits, filesystem/network isolation. It reads actual cgroup files and
runs real isolated read/write/network canaries. It does not require API/broker/DB
to be running and does not process customer media. If false, stop at this host
gate; do not set flags false or relabel APP_ENV to claim production readiness.
Share only the coarse report. We can interpret it; no infrastructure choice or
secret needs to be supplied. A modern supported Linux kernel/configuration and
cgroup v2 runtime are required; Docker's version string alone does not prove them.

When the host passes, `docker compose up --build -d` starts DB, durable broker,
migrations, API, queue supervisor and worker. Worker limits remain CPU <=2,
memory <=2 GiB and PIDs <=128; API has declared CPU 1/memory 1 GiB/PIDs 128 and
uses the same strict decoder startup checks. Broker is UID 999, read-only root,
capabilities dropped, persistent data volume, authenticated loopback port 6380,
64-MiB internal no-eviction limit; kernel limits still need real host acceptance.
Default Compose credentials/networking are development setup, not public hosting.

## Native development adapter

For functional Windows development only, start the local free queue with:

```powershell
docker compose up -d queue
```

Load the private client settings separately in API, render-worker and supervisor
windows, preserving the existing storage/DB configuration:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
(Get-Content .data\queue-private\client.json -Raw | ConvertFrom-Json).PSObject.Properties |
    ForEach-Object { [Environment]::SetEnvironmentVariable($_.Name, [string]$_.Value, "Process") }
$env:PYTHONPATH = "apps/api"
```

Start the usual API; `python -m app.worker` now selects the Arq consumer. A separate
terminal runs `python -m app.queue_supervisor`. Keep email sending disabled unless
separately authorized. Do not mount Docker sockets into application containers or
forward port 6380 to the phone. Pixel uses API/Metro and optional local S3 ports
as before. Native Windows is a development adapter, not strict Linux acceptance.

Do not mix DB and broker workers intentionally. Fences protect publication if a
stray development worker exists, but production workers reject database mode or
missing required resource/sandbox flags. Stage/production broker requires TLS
with hostname/certificate verification; configure role-scoped credentials/ACLs,
backups and approved certificates before public deployment. No paid host is created.

## Dispatch and ACK contract

Admission commits a job and QueueSignal together. The supervisor claims signals
under owner-first locks, publishes stable generation IDs outside DB locks, then
records broker acceptance under a lease fence. Lost responses may repeat enqueue;
Arq deduplicates the stable ID. No input uses pickle: only fixed render_next,
one canonical UUID, no kwargs, bounded JSON envelope. Broker compromise cannot
submit shell commands or a media URL through this protocol.

A signal requests **one fair drain iteration**. The SQL scheduler retains owner
turns/FIFO/per-account processing limits; the signal origin does not force a
specific customer's job ahead of another. A worker completes the signal after
a durable terminal/retry/no-work outcome. Arq acknowledges after function return.
Pending/retried jobs remain in SQL and receive another signal when due. This is
at-least-once dispatch with fenced publication, not exactly-once computation.

Reconciliation examines <=100 eligible missing/completed/stale signals per pass,
publishes <=100, closes <=100 terminal signals and recovers <=100 expired claims.
Healthy old signals cannot starve missing newer ones. Lost broker state gets a
new generation after 60 seconds, not instant recovery. No worker/broker outage
can turn an accepted upload into a falsely successful result. Only SQL references
to verified attempt-specific artifacts determine downloads. Signals/dead letters
are private metadata retained with their job; broader retention belongs to package 5.

Valkey uses AOF appendfsync always and noeviction; clients verify those settings.
Messages/results/health keys have bounded lifetimes and results are not retained.
The 64-MiB data limit fails writes instead of discarding jobs; SQL reconciliation
remains the recovery source. This is single-node local durability, not HA or a
power-loss/storage-hardware guarantee. Observed local image startup warned about
host memory overcommit; no global sysctl was changed. Review host persistence/
memory/failover under package 5/6 load and disaster recovery gates.

## Supervision, retries and erasure deadlines

Default claim lease is 45 seconds, renewed every 10 seconds. Renewal requires the
same live token/status and unexpired lease; it never revives an expired/cancelled/
superseded claim or moves past the absolute render/probe/storage budget. Process
liveness pulses are still separate from ownership/progress. DB loss cannot be
acknowledged as durable completion. Cancellation and stop fence publication and
tear down decoder groups; hard worker death waits for the short lease to expire.

Only transient storage/internal failures automatically requeue, with default
five-second backoff, inside the existing **two render attempts** and reserved
output budget. Invalid media/output-limit failures terminate immediately. Exhausted
claims or terminal failures record a durable dead letter; CLI does not silently
grant unlimited manual retries. Old tokens cannot overwrite winners.

Short leases are not cleanup lifetime bounds. Each attempt records its original
hard deadline; project/account deletion consider running/lost/cancelled attempt
deadlines before scheduling removal, including a recovered older claim. Revocation
is immediate; physical removal may wait. Trusted control-process/remote-store
in-flight writes cannot be universally recalled by a DB token; provider IAM/lifetime
and stopped-writer orphan/version/backup cleanup limits still apply. This does not
claim perfect physical erasure of an indefinitely suspended privileged sender.

## Decoder boundary

Strict Linux launchers retain parent-death kill, CPU/core/open-file limits,
credential stripping, closed inherited FDs and null stdin. Before FFmpeg/FFprobe,
Landlock ABI >=3 permits one input and private output attempt directory plus
immutable runtime files; other tenant files/app secrets are inaccessible. Seccomp
denies sockets/network operations and selected escape/inspection/mount/io_uring
syscalls, checks architecture and rejects x32 ABI. Filesystem and syscall policies
are inherited across descendants. No-new-privileges prevents elevation.

This shares a kernel and immutable runtime read trees, not a VM or a penetration-
test certification. Keep runtime trees free of customer data/secrets; retain read-
only unprivileged containers with no Docker socket or host admin mounts. Successful
guards on a host do not prove the absence of kernel/codec exploits. Actual stricter
host acceptance, load/security review and deployment privacy remain explicit gates.

## Automated checks and operator snapshot

```bash
PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests -q
.venv/bin/python scripts/smoke_e2e.py
.venv/bin/python scripts/smoke_broker_queue.py
.venv/bin/python scripts/smoke_broker_queue.py --s3
PYTHONPATH=apps/api .venv/bin/python -m app.queue_supervisor --report
```

The broker proof uses a disposable authenticated loopback Valkey, checks exact
accepted JSON after SIGKILL/restart/AOF recovery, then runs actual Arq/supervisor/
HTTP upload/resume/queue/render/download and existing auth/deletion/retention
proofs. --s3 adds real private local object storage/direct uploads. It removes
only its own container/config. These standalone development fixtures explicitly
disable strict host requirements and real email; they are not production-host
acceptance. Unsupported Landlock tests verify refusal rather than reporting an
isolation pass. Linux seccomp network denial is exercised independently.

Private report shows unpublished/unfinished signals and dead-letter counts, not
addresses, credentials or media paths. Full tracing/export/alerts remain package 4.
After review and supported-host acceptance, one Pixel upload/render/save is the
focused app check; repeated manual backend/mobile suites are unnecessary.

## Remaining capacity boundary

The decoder filesystem policy is not a per-job disk quota. Existing output-size
checks do not guarantee containment of hostile scratch-file growth. Global disk
budgets, capacity/soak and broader deployment/security acceptance remain in the
fixed later packages; this increment does not declare production readiness.
