# Phase 2 package 5 — capacity, cleanup, restore and security review

## Implemented boundary

Migration **0019_global_capacity** creates one SQL admission mutex and shared
in-flight upload reservations. It does not change accounts, sessions, media,
consent, upload offsets, prior job outcomes or pricing. PostgreSQL is the staging
DB; SQLite remains a development adapter. No paid service, billing, AI, email
sender or public deployment is activated by this package.

New admissions hold owner lock first, then the global mutex. SQL counts all owners'
queued/processing jobs and unexpired upload sessions; includes retained job and
uncleaned upload byte reservations, and refuses new work when inventory is unknown.
An admitted session swaps its existing reservation for one job even if limits are
subsequently lowered. Same-key valid replays survive capacity limits. Deletion,
cancellation and successful cleanup reduce the applicable counts without creating
new capacity reservations. Bytes are released only under the existing cleanup
rules, not merely because a job failed or the user clicked Delete.

Defaults (server-only settings):

| Setting | Default | Meaning |
|---|---:|---|
| API_REQUEST_CONCURRENCY | 8 | Per-process active HTTP requests; wait asynchronously up to 30s to avoid DB-pool/thread starvation; then 503/Retry-After |
| GLOBAL_ACTIVE_LIMIT | 100 | Shared active jobs plus live upload sessions |
| GLOBAL_PROCESSING_LIMIT | 2 | Shared processing claims, including stuck claims until fenced recovery |
| GLOBAL_STORAGE_BYTES | 50 GiB | Logical retained/admitted storage reservation ceiling |
| INGRESS_LIMIT | 4 | Shared raw multipart/part requests in progress |
| GLOBAL_INGRESS_BYTES | 1 GiB | Shared temporary intake reservation ceiling |
| INGRESS_TIMEOUT_SECONDS | 600 | Total body-read deadline, not a general thread/process cancellation promise |
| MIN_FREE_DISK_BYTES | 128 MiB | Local storage free-space floor |
| OBSERVATION_RETENTION_DAYS | 7 | Operational span/stopped-worker retention, allowed 1–30 days |

Tune these below real allocated disk/DB/CPU/provider capacity before staging. The
logical budget is **not** an S3 quota, complete physical inventory, disk partition,
provider billing cap or guarantee that every paused upload can resume immediately.
Do not enlarge it simply to silence a refusal. The physical free-space guard covers
the configured local media/scratch filesystem; other mounts, provider stores and
external writers need their own quotas/alerts. Request limits do not replace an
edge connection/body/rate/TLS policy or stop every denial of service.

## Upload-body and intake protection

ASGI body limits run **before multipart parsing**: legacy source cap plus 64KiB
form overhead; parts at configured chunk size; other POST/PUT/PATCH JSON bodies at
64KiB. Both Content-Length and actual received bytes are checked; malformed/duplicate
lengths fail safely. Chunked/missing-length input still has a real byte cap. Header
limits and transport parsing remain server/edge responsibilities.

Multipart/part receivers reserve twice their bounded declared size (or maximum
when length is absent) to cover parser/staging copies. Multiple API replicas share
SQL intake count/bytes; ordinary JSON control requests use bounded per-process
execution. Space is checked before intake and worker claims; full/unknown capacity
returns fixed retryable 503 messages without secrets. Unauthenticated large upload
requests are also bounded, but can occupy the small intake pool until deadline;
reviewed edge/auth abuse controls remain essential.

Normal completion/error/cancellation releases intake reservations. A process crash
or DB outage can leave a reservation; it **stays charged** after its recorded body
bound plus 120s rather than silently assuming its writer is gone. The monitor
reports stale reservations. Recovery requires stopping **all API writers** and
reviewing orphan media/staging before:

```powershell
docker compose stop api
docker compose run --rm --no-deps api python -m app.capacity --release-stale --writers-stopped
docker compose up -d api
```

The explicit flag is an operator assertion, not distributed process detection.
This releases stale metadata only, never deletes footage. Inventory/retention
preview remains separately required where media ownership/state is uncertain.

## Decoder output bounds

Required Linux mode now grants write/read/truncate access to **one precreated
partial output file**, instead of an entire attempt directory. Landlock denies
creating arbitrary sibling scratch files. The launcher sets hard RLIMIT_FSIZE to
the stored render byte cap (maximum 512MiB); probe children have zero file-write
size budget. These bounds supplement CPU/time/PID/memory controls and narrow
filesystem/network permissions. Oversize attempts fail rather than silently trim.

The existing host check additionally tests writing the allowed file and refusing
creation of a sibling. Unsupported kernels still fail closed. Actual RLIMIT_FSIZE
is tested on Linux here; this managed host still cannot run Landlock/cgroup strict
acceptance. A supported-host hostcheck **and actual FFmpeg render** are required
for this narrower policy. Native Windows development is not equivalent protection.
Shared kernel, runtime read paths and trusted publisher/S3 client remain part of
the threat model; this is not VM isolation or a kernel-exploit certification.

## Retention and erasure scope

| Data | Implemented policy | Limit / remaining gate |
|---|---|---|
| Valid saved projects | Retain until explicit deletion; no surprise age expiry | User-facing policy/legal signoff still required |
| Deleted project/account media | Immediate access/claim revocation; bounded retryable cleanup after old writer hard bounds and signed capability deadlines | In-flight remote writes/copies, versions/backups and stopped maintenance do not have a universal erase SLA |
| Terminal upload staging | Bounded cleanup/rescan; keep reservation until verified cleanup | Direct capabilities may remain usable until expiry |
| Unknown/stale orphans | Offline preview, >=24h grace, reviewed digest, stopped-writer apply only | No unsafe online unreferenced-file deletion |
| Trace observations | Delete <=1000 old rows per maintenance pass after default seven days | Separate transaction, not lossless audit; stopped services delay cleanup |
| Stopped worker pulses | Same bounded age cleanup | Crash records without stopped_at retained for operator review; no claim of universal metadata GC |
| Job/attempt/cost/rights/grant/deletion tombstones | Preserved to protect replay, accounting and cleanup fences | Full personal-data/legal retention and backup erasure are OPEN; not full GDPR erasure |
| Device saves/shares and recipient/provider copies | Outside server deletion | Disclosure/user/provider controls required |

Maintenance runs in the queue supervisor or native worker. No arbitrary personal
media was deleted during implementation; tests use original synthetic fixtures.

## Tested backup restoration

`scripts/capacity_exercise.py` creates its **own** PostgreSQL container, API, workers,
synthetic accounts and media; it never accepts an existing server/DB/media target.
It stops all its writers, takes pg_dump custom-format plus media copy, hashes the
files, restores into a **new** PostgreSQL database, removes/replaces only its own
original media tree, and verifies prior auth, exact output hash, deleted-project
inaccessibility and a fresh render after restoration. Its container/volume and
processes are removed on exit; private synthetic backup/report artifacts remain
ignored under `.data/capacity-exercise-*` for review.

This is a consistent local restore proof, not an offsite disaster-recovery SLA or
a backup encryption/authenticity service. SHA-256 detects changed data against a
trusted manifest; it does not authenticate an attacker-replaced backup/manifest.
Real backups contain private account/session/operational data and must be encrypted,
access controlled, tested and expired under an approved policy. Protect encryption
and mail key rings separately; losing mail keys can make envelopes unreadable.

Production restore runbook: stop all writers/dispatch; back up the active PostgreSQL
DB and all media/staging namespaces consistently; retain version/config/key refs;
verify manifest before restoring into an isolated new target with compatible paths;
run migrations/inventory/host checks; **reapply deletion/revocation requests received
after the snapshot from a separately protected current journal before any user
access**; invalidate sessions if credentials/deletion state is uncertain; verify
owner isolation/known downloads/new render/monitoring; then approve cutover. Never
restore over the only live copy, run blind tar extraction, or activate mail/billing.
The independent post-snapshot journal/offsite/encrypted restore is an unresolved
production privacy gate; this prototype cannot reconstruct missing later requests.

## Load and soak evidence

The exercise opens **100 simultaneous HTTP session submissions** from 100 synthetic
accounts against a disposable PostgreSQL API. With global active limit 64 it expects
64 unique admissions and 36 retryable capacity refusals, checks same-key replays
and other-owner denial, aborts/cleans those sessions, then runs real FFmpeg cycles
with two worker processes and three rotating owners. Requests are bounded to eight
active API executions; 100 submissions are not 100 DB transactions or renderers.

```bash
.venv/bin/python scripts/capacity_exercise.py --soak-seconds 600
```

The recorded ten-minute steady workload uses two-second synthetic landscape/audio
clips and render/download/delete checks. CI repeats a 30-second version; the full
suite separately tests 60-second exports, cancellation, retry, malformed media,
capabilities and ownership. This is not a production peak-throughput result,
24-hour soak, representative real-device codec/HDR corpus or a hostile-code audit.
Those remain the staging/security acceptance plan, not silently marked passed.

## Upgrade and focused owner check

Stop API/worker/supervisor and back up the **active PostgreSQL database and media**
using the existing backup procedure. Pull the reviewed merge; rebuild images (the
installer is pinned to reviewed pip 26.3), run the updated hostcheck, and continue
only if ready true:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
git pull --ff-only
docker compose build worker
docker compose run --rm --no-deps worker python -m app.worker_hostcheck
docker compose up --build -d
```

Migration 0019 runs before startup. Existing budgeted media needs no re-inventory;
if the aggregate reports unknown records, stop all writers and use the existing
`python -m app.storage --reconcile` procedure; never guess unknown usage as zero.
Run one Pixel upload/render/save/playback and:

```powershell
docker compose exec -T worker python -m app.monitoring --check
```

Share the coarse report, not private backups/keys/logs/trace files. No npm reinstall
or repeat manual backend suite is needed. The dependency/privacy/security risk
review remains [SECURITY_REVIEW_2026-11-08.md](SECURITY_REVIEW_2026-11-08.md); this
package does not declare a public launch safe.
