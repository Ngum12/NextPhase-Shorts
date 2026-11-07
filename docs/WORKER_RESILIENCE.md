# Worker resilience and containment in the developer preview

The DB poller remains the current queue. This increment strengthens fair claims,
recovery and process limits; it does not finish Phase 2 or introduce a broker,
production deployment, paid service or AI editing.

## Fair turns and bounded recovery

Eligible accounts are ordered by their most recent recorded attempt claim, with
never-served accounts first, then oldest queued work and account ID for ties.
Within an account, oldest creation time/job ID still wins. Existing durable attempt
records supply the scheduling history, including failures/retries/deleted projects;
no migration or in-memory rotation state is required. Each retry consumes a turn.
Per-account processing limits and disabled-account guards still apply. PostgreSQL
locks an eligible owner with SKIP LOCKED; SQLite retains transactional admission.
This is account-turn fairness, not equal CPU time, priority billing, or Sybil defense.
New accounts and busy/locked owners can alter ordering. Query cost with large
histories and representative multi-worker fairness/load remain deployment gates.

Recovery selects at most 100 expired jobs per pass (internal maximum 1,000), ordered
by deadline/ID. PostgreSQL skips locked rows. Completion and recovery keep the same
job-before-attempt lock order and recheck expiry/state. A first lost attempt requeues;
a second fails with MAX_RETRIES. Unexpired leases remain protected. No exactly-once
execution, immediate crash detection, broker ACK, heartbeat or lease renewal is
claimed. Hard crashes wait for the existing bounded lease (render timeout plus
90 seconds local / 300 seconds S3). Cancellation/deletion can revoke earlier.

SIGINT/SIGTERM stops new claims and asks active rendering to stop. After decoder
teardown, only the matching processing claim's lease is expired for recovery.
Shutdown consumes an attempt; it never grants unlimited retries or overwrites a
newer claim/terminal state. Storage I/O may delay signal handling until its bounded
operation returns; a supervisor may hard kill after its grace period. Transactional
DB failures during the loop are logged without raw details and retried after the
poll interval. Startup configuration/schema/bucket failures still fail explicitly.

## Decoder process boundary

FFmpeg and FFprobe receive a small environment allowlist: executable/system paths,
temporary paths and locale, not JWT/DB/S3/provider/proxy credentials. Python module
search overrides and user-site paths are not inherited by the Linux launcher.
Commands remain fixed server-generated argument lists, with the existing file-only
protocol/container/codec profile, allocation/thread checks and output validation.
FFmpeg stderr is discarded rather than accumulating unbounded data or leaking
private source paths. FFprobe returns only selected metadata; diagnostics are discarded.

On Linux, an isolated Python launcher sets PR_SET_PDEATHSIG(SIGKILL), rechecks its
parent, disables core dumps, caps open files at 128 and CPU seconds at
`ceil(operation_timeout * 2 + 30)`, then execs the decoder. CPU limits are aggregate
process CPU time, not a VM billing metric. Wall timeout, output byte monitoring and
claim checks remain separate. POSIX rendering runs in its own process group, killed
and reaped on timeout/cancellation/exit. Fixed FFmpeg does not normally spawn children;
parent-death enforcement does not promise containment of arbitrary malicious forks.

Windows standalone development retains direct decoder execution, the environment
allowlist, wall/output/thread bounds and cooperative cancellation. Linux parent-death,
CPU rlimit and process-group enforcement tests are explicitly skipped on Windows.
A hard-killed Windows worker can leave FFmpeg running: use Docker Linux for deployment,
or inspect/stop only that worker's orphan process before restarting. This increment
does not implement Windows Job Objects or a native Windows production sandbox.

## Docker profile and fail-closed startup

Compose worker: unprivileged image user, init/reaping, read-only root, no capabilities,
no-new-privileges, writable media volume, 64-MiB /tmp, two CPUs, 2-GiB RAM, 128 PIDs,
15-second stop grace. `WORKER_REQUIRE_LIMITS=true` is set explicitly for this service.
Its startup requires readable cgroup v2 limits at or below those CPU/memory/PID caps.
Missing, unlimited or excessive values fail before DB/queue work. Container limits
cover the worker service; API ingestion, host disk, provider costs and total replica
allocation need their own controls. The shared media volume remains readable to the
worker: this is not per-tenant filesystem or network isolation against a decoder exploit.

Standalone defaults `WORKER_REQUIRE_LIMITS=false` for local Windows/Linux development.
Do not turn the Compose guard off to disguise unsupported production limits. Use a
host/runtime with functioning cgroup v2 delegation. Custom smaller caps must still
support realistic inputs; OOM/killed workers recover via leases rather than success.
Cgroup v1 hosts require a future reviewed implementation, not silent fallback.

**Cloud validation limitation:** this managed Docker daemon reports cgroup driver
`none` and memory/CPU/PID support false. Inside a disposable container it exposes
outer limits (32 GiB, four CPUs, unlimited PIDs). Rendering, UID 1000, read-only root,
zero effective capabilities and no-new-privileges were verified; the requested
worker cgroup caps could not be enforced here. The startup guard must reject this
runtime. This is not evidence that resource ceilings are enforced on another host.
Docker Desktop/Linux host acceptance remains required before using the strict profile.

## Upgrade and acceptance

No schema, dependency, mobile UI or native change. Existing migration 0012 remains
current, and accounts/projects/pending uploads/rights records are preserved. Stop
native API/worker before pulling and restarting updated server code. Keep existing
server-only S3 settings and USB forwarding where used.

From repository root on Windows:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
git pull
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
.\.venv\Scripts\python.exe scripts/smoke_e2e.py
cd apps\mobile
npm run typecheck
```

For Linux Docker, build and check enforcement before starting the service:

```bash
docker compose build worker
docker compose run --rm --no-deps worker python -c 'from app.worker_limits import require_worker_limits; require_worker_limits()'
# Only after this succeeds; recreate API too to apply its updated FFprobe launcher.
docker compose up --build -d
```

After restart, check old projects, one new upload/render/save, cancellation, and a
second account's queue access. Do not manually change real DB lease timestamps.
Use `python scripts/smoke_worker_recovery.py` for the disposable crash proof: it
kills its own claimant, advances only that synthetic expired lease, starts another
worker and validates a real 1080×1920 MP4 plus stale-result fencing. It is also run
by the normal isolated HTTP and disposable S3 smokes. Test reports live under
ignored `.data/worker-recovery-*`. No production waiting-period observation claimed.

Automated burst coverage submits 100 synthetic jobs across ten accounts with up to
16 requests in flight, verifies exactly three admissions per account and 70 quota
refusals, and drains three fair rounds. It does not establish 100 simultaneously
active render workers, a long soak, hostile-code isolation, latency SLAs or capacity
for real public traffic. Physical Pixel and strict Docker-host acceptance of this
increment remain outstanding until supplied by the owner.

## Windows smoke cleanup correction

The owner reported WinError 32 after the crash/restart checks passed: idle SQLite
connections in the helper's SQLAlchemy pool prevented TemporaryDirectory cleanup.
The helper now disposes that engine before directory cleanup on both success and
exception paths. Its success report is written only after the temporary tree is
actually gone, with `temporary_cleanup=passed`. This changes only disposable test
cleanup, not account databases, queue behavior or media handling. Native Windows
rerun remains necessary; Linux regression tests simulate refusal while handles remain.
