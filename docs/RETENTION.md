# Retention maintenance and preview-first orphan cleanup

This increment does not delete saved projects by age. Automatic project expiry,
account/backup erasure and a production retention policy still require separate
implementation/review. Existing output invariants (9:16, <=60 s) and server-only
processing are unchanged. No paid service or dependency is added.

## Automatic maintenance of known resources

The worker still runs maintenance between renders, roughly every 60 seconds:

- Expire upload sessions whose recorded lifetime elapsed. Expiration now selects
  at most 100 records per pass and takes the same owner lock used by completion,
  rechecking status/deadline before changing it. A call limit of 1–1000 is allowed.
- Clean terminal upload staging, respecting direct-PUT expiry and namespace checks.
  Failed cleanup stays pending; direct terminal sessions are rescanned for late writes.
- Clean explicitly deleted projects after their original lease safety window.
  Storage budget is released only after known project/staging removal succeeds.

Expired/discarded uploads cannot resume as active sessions. A valid, unexpired
paused upload remains protected, regardless of file age. Completed, failed,
cancelled or queued **projects** are retained until their existing delete flow is
used. This is not a new customer retention deadline or an account-erasure promise.

## Unknown media and stale attempts

A missing DB row alone does not prove a file is abandoned: a request may be writing
before committing its job. Therefore **unknown-orphan removal is an offline
operator action**, never an unattended worker/bucket lifecycle rule in this build.
Preview may run online; apply requires all API/worker/client/storage writers stopped.
The storage service itself stays running for S3 access. Close/finish outstanding
PUTs and wait for capabilities to expire; stopping Metro alone does not stop a
running phone upload. The offline flag is an operator assertion, not automatic
proof that distributed writers are stopped. Do not apply against a stale restored
DB until backup/media reconciliation is complete.

The tool recognizes only canonical server UUID layouts in the configured media
root, or S3 `media/` and `uploads/` prefixes. Eligible groups are:

- Recognized media/upload trees for a **known owner** whose entity ID has no job or
  upload-session row and is not referenced by any job source/output or remote part.
- Noncurrent failed/cancelled/lease-lost attempt artifacts in a terminal project,
  with a matching attempt record and no source/output/part reference. Current
  claim tokens, active jobs, winners and source files remain protected.

Every file/directory in a local candidate must be at least **24 hours** old by
both modification/change timestamps. S3 uses server LastModified. Grace can be
increased to one year but cannot be lowered below 24 hours through the CLI.
Unknown owners, formats, directory shapes, symlinks/junctions, hardlinked/special
files and unreadable trees are skipped. No arbitrary client path or filename is a
deletion target. Nonversioned private buckets only; versioned/suspended buckets are
refused. Namespace changes and stored-namespace mismatches protect remote attempts.

Scans visit at most 10,000 entries by default (maximum 50,000), with at most 100
S3 pages per prefix. Truncated, failed or nonprogressing listings cannot be applied.
These are operation/entry bounds, not a guaranteed wall-clock/DB query deadline.

## Preview, review, then apply

From repo root with the correct server environment and current schema:

```powershell
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe -m app.retention --backend local
```

Default output is aggregate counts/bytes, skipped reasons, completeness and a
`digest`. It changes nothing. `--details` additionally exposes canonical operational
UUID paths/object keys and metadata; keep such reports private and out of Git.
No titles, emails, secret values or signed URLs are included. To inspect S3, load
its existing private server settings and select `--backend s3`; no bucket/policy
is created. Do not enable/configure paid storage without owner approval.

After reviewing a complete preview, stop all writers, back up DB/media and run:

```powershell
.\.venv\Scripts\python.exe -m app.retention --backend local --apply --offline --expect-digest '<digest from preview>'
```

Use the same backend/grace/scan limit for both commands. Apply takes a **fresh scan**
and compares the digest, which binds candidates/metadata to the DB/store/root and
scan parameters. It does not execute a supplied JSON manifest. New references,
changed data/settings or incomplete scans refuse apply before removal. Local
ancestors/metadata and remote HEAD ETag/length/time are checked again; S3 deletes
only exact reviewed keys, never a whole bucket or unreviewed prefix. Apply rechecks
DB protection immediately before each group. These checks do not make apply safe
against concurrent hostile filesystem/provider writers; the offline requirement
is essential. S3 HEAD/list times are normalized to whole seconds to accommodate
HTTP Last-Modified precision; ETag and length remain independent checks.

Exit 0: complete preview or successful apply. Exit 1: one or more group removals
failed (a group may be partly removed). Exit 2: unsafe options, changed/incomplete
plan or unavailable inventory. Review a fresh preview after failures; partial local
removal may make a directory young and defer its next cleanup until the grace
passes. No raw provider exceptions/customer paths enter the default summary.

Orphan/stale-attempt cleanup does not alter job/session rows, rights, claims,
telemetry or reservations. Those are conservative admission budgets, not a count
of physical bytes; orphan objects have no valid reservation to release. Known
upload/project cleanup retains its existing budget-release rules. Saved gallery,
shared and backup copies are outside this tool's scope.

## Upgrade and validation

No schema migration, dependency install or mobile change is required solely for
this increment. Pull/restart the worker to use bounded expiration. Start with a
preview; do not run apply merely because the software was upgraded.

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
git pull
$env:PYTHONPATH = 'apps/api'
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
.\.venv\Scripts\python.exe scripts/smoke_e2e.py
# Optional disposable local S3/direct + retention proof; requires Docker:
.\.venv\Scripts\python.exe scripts/smoke_object_store.py
```

The smoke's retention fixture runs only after its own API/worker stop, against its
own temporary SQLite DB/storage and, for S3, its disposable local bucket. A test
clock advances two days to exercise the minimum grace without waiting 24 hours;
this is synthetic correctness evidence, not proof of an observed two-day retention
period. It removes introduced orphans and verifies known sources survive. Actual
source/render/download/expiry checks precede the offline fixture. Production
provider/IAM, scan scale, native filesystem variants and formal legal retention
remain unverified. Do not run this internal fixture against the normal app DB.
