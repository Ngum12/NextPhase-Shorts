# Phase 2: project deletion and private-volume cleanup

Project detail now has a confirmed **Delete project** action for queued, processing,
completed, failed and cancelled projects. It is not account deletion or a complete
retention/erasure policy. No paid APIs, infrastructure or billing are enabled.

## Contract and races

`DELETE /api/v1/jobs/{id}` requires the owner's valid bearer. It returns 202 with
`{"status":"deleted","media_cleanup":"scheduled"}` only after committing a
permanent tombstone. Repeat owner requests return 202; unknown/other-owner IDs
return the same 404, and unauthenticated requests return 401.

In the deletion transaction the project becomes terminal `deleted`, its claim and
lease are revoked, active attempts become cancelled, its title/source/output path
are cleared, and linked completed upload sessions become deleted with scrubbed
file names/titles/source checksums. The active-job slot is released. List/detail,
cancel and download endpoints hide it (404). New downloads include private/no-store
cache headers. A download/request already authenticated or transferring may finish;
previously saved/shared copies cannot be recalled.

A stale worker cannot publish after deletion: completion requires the still-active
processing status and claim token. Owner-row admission/claim/deletion transactions
serialize; deletion also locks the job before its attempts to match worker lock order; completion's conditional update determines the winner against deletion.
The renderer cooperatively stops FFmpeg on its next ownership check. Old legacy
idempotency keys and related upload session replays return 410 rather than creating
a replacement project. A new intentional upload must use a new key.

## File removal and retry

The request removes server access immediately; **202 does not mean bytes have
already been erased**. The worker runs bounded cleanup batches between renders,
at most once per minute; a long render can delay maintenance. Operators can run:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.deletion
```

For Compose: `docker compose exec -T api python -m app.deletion`.

Queued/terminal projects are eligible immediately. When a processing lease exists,
cleanup waits until that original lease expiry plus 30 seconds, even if the worker
stops sooner. With default settings that is up to approximately 22 minutes after
claim, plus maintenance delay. This allows bounded render/probe work and Windows
open files to close. It is not a guaranteed erasure deadline.

Cleanup derives only canonical UUID paths under the configured private storage
root: the owner's project tree and its linked upload staging trees. It never trusts
stored source/output paths. Symlink/junction parents are rejected; a symlink leaf
is removed without following its target. Storage is trusted app-owned infrastructure;
this is not protection against a hostile administrator racing filesystem mutation.
Permission/open-file failures retain a retryable tombstone and do not log paths.
Attempts are timestamped so failed jobs do not monopolize a batch indefinitely.

Successful scans remove linked part metadata and mark staging cleaned. Pending removals take priority over previously successful scans. Tombstones
are rescanned in oldest-attempt order within each group, so late
stale artifacts can be removed again. media_deleted_at records the last successful
scan, not a promise that a paused process can never recreate an inaccessible file.
There is no restoration endpoint and no automatic tombstone expiry in this slice.

## What remains and what does not get deleted

The tombstone retains owner/job IDs, submission keys/fingerprints, timing/size/style
metadata and attempt metrics to block retries and preserve operational accounting.
These linked records still require a retention policy. Telemetry output-byte totals
are historical accepted bytes, not current storage usage. This feature does not
claim complete personal-data removal or GDPR certification.

Original gallery files, OS/shared/download copies outside the app, other devices,
backups/snapshots, uncommitted orphan uploads, logs and physical disk blocks are not
erased by project deletion. Known committed project/staging trees are the cleanup
scope. Backup expiry/restore reconciliation, orphan GC, secure object-store erasure,
account deletion and legal retention deadlines remain open.

Mobile requests explicit confirmation and waits for the 202/deleted response before
leaving the screen. Offline/failure keeps the page for retry; repeating a request
is safe after a lost acknowledgement. It attempts to remove this phone's app-managed
download cache; failure is disclosed. Saved gallery/shared copies remain. A stale
project URL shows an unavailable/back action instead of an endless loader. If a
saved pending upload belongs to a remotely deleted project, Resume fails safely;
confirmed Discard can remove its private copy after a 404/410, never on a network
failure. The original gallery file is untouched.

## Windows upgrade and acceptance

Stop API, worker and Expo. Back up the actual configured database and media, then:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
$backup = ".data\nextphase-before-deletion-$(Get-Date -Format yyyyMMdd-HHmmss).db"
Copy-Item .data\nextphase.db $backup
git pull
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
.\.venv\Scripts\python.exe scripts/smoke_e2e.py
cd apps\mobile
npm run typecheck
npm run test:uploads
npm run test:auth
```

Migration `0007_project_deletion` adds nullable timestamps/index only. Existing
accounts/sessions/jobs/uploads stay intact; migration itself deletes no media and
does not require a new sign-in. No mobile dependencies changed. Do not run old/new
workers together; downgrade requires stopped services, prior code and a verified
backup. Restoring a pre-deletion backup can resurrect metadata/media, so reconcile
later deletion requests before any future production restore.

Restart services/USB forwarding/SDK 54 Expo normally. Physical Pixel acceptance
is pending for this increment; use a newly created disposable test project:

1. Download/play it. Open Delete project, choose Keep project; it must remain.
2. Confirm deletion; return to My Shorts, refresh, and confirm it stays absent.
   Another project must still download; the original gallery video must remain.
3. Delete a queued/processing disposable project. It must disappear and never
   return as succeeded; do not expect immediate disk removal during its lease.
4. Disconnect USB before submitting Delete; an error must leave the project visible.
   Reconnect/reverse ports and retry. Run the cleanup CLI for eligible projects.

Automated tests cover ownership, all statuses, repeatability, download/list hiding,
stale claims, real FFmpeg termination, forced completion/deletion lock races, key/session replay, cleanup retry/rescan,
path isolation, linked staging and migration preservation. The real HTTP smoke
creates/deletes only its own synthetic project and verifies filesystem removal in
its isolated database. Existing-device acceptance is user-reported, not automated.
A Windows symlink-only test skips if OS privileges prohibit creating symlinks;
normal derived-path/deletion tests still run. Native confirmation, navigation,
cache permissions and offline interactions still need the physical check above.
