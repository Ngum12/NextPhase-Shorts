# Phase 2: Save video, Share video and server storage budgets

## Separate native actions

Completed projects now offer **Save video to phone** and **Share video**. Save
writes the authenticated MP4 to the OS media library and reports success only
after the native save operation resolves. It does not open the share sheet. Share
opens the native share sheet and does not save to the gallery automatically.
Cancelling a share sheet is not a successful message delivery claim.

Save asks for add/write permission on iOS and legacy Android where required. On
Android 13+ (API 33+) saving an app-created video through MediaStore needs no broad
media read permission; the app skips broad library access requests. SDK 54's native
implementation confirms that its Save API supports this write path. The plugin
requests no image/video/audio read permissions and no media-location access.
Expo Go may log a general warning about full media-library access, which this
feature does not use. A physical Pixel check is still required; a JS bundle and
mocked native tests cannot establish a successful OS save.

Native permission denial, network/auth/download errors, empty files and native
save failure show errors rather than a false saved confirmation or a fallback to
Share. Sharing never falls back to saving. The current screen prevents concurrent
exports. Save uses local app cache before adding the video to the media library;
photos/OS storage availability and indexing still apply. Save does not promise
Google Photos cloud backup. Look in the phone's Photos/Gallery on-device library.
Native Android/iOS custom builds must be rebuilt to apply the plugin permissions.
Use the existing compatible SDK 54 Expo Go for the first Pixel acceptance attempt;
web exports and iOS device acceptance have not been tested.

Saving creates a separate OS-owned copy: later server project deletion cannot
remove that gallery/shared copy. The original source gallery file remains untouched.

## Conservative server admission budgets

Defaults, server-only configuration in .env:

| Setting | Default | Meaning |
|---|---|---|
| ACCOUNT_STORAGE_BYTES | 5368709120 (5 GiB) | Per-account used/reserved admission budget |
| MAX_RENDER_BYTES | 67108864 (64 MiB) | Accepted artifact limit per render attempt |

There is no payment collection, entitlement change or subscription unlock. These
are developer resource controls. Each new upload reserves **source bytes + twice
the per-attempt render cap**, covering the queue's two permitted render attempts.
The reservation is persisted on the upload session, then exchanged for the same
job reservation atomically at completion. Legacy multipart submissions use the
same owner-row admission lock. Concurrent accepted uploads cannot overbook it.
Exact key/session replays do not reserve twice and still work at capacity.

Reservation values and render caps are fixed when accepted. Existing sessions can
complete after a configuration limit reduction; a retry uses its job's stored
render cap. New admissions use the current settings. A full budget returns 409
with a clear delete/discard-and-wait message. `/api/v1/me/storage` is authenticated,
owner-scoped and reports limit, known reserved bytes, missing-inventory count and
available bytes (null if inventory is incomplete). Account displays used/reserved
MiB and explains render headroom; it is not a bill or a live disk meter.

Completed, failed and cancelled jobs keep their source/artifact reservation until
project deletion **and successful media cleanup**. Deletion acceptance alone does
not free it. Pending, aborted or expired upload sessions retain space until staging
cleanup confirms removal. Maintenance runs between renders, so capacity release
may be delayed; processing deletion also retains the previous lease delay. These
are conservative reservations, so an actual 7 MiB export can consume much more
budget due to retained source and unused render headroom.

FFmpeg output is monitored during rendering and checked before acceptance.
Oversize output aborts with OUTPUT_LIMIT_EXCEEDED and removes its partial file;
it is never silently truncated into a shorter successful video. Monitoring is
periodic, so temporary overshoot remains possible. Requested output stays <=60 s
and all intensive processing stays on server workers.

**This is not an OS/filesystem disk quota.** Multipart spooling, duplicate source
assembly, concurrent temporary files, stale/orphan artifacts, periodic overshoot,
backups and other services are outside the logical admission budget. Production
needs edge body limits, filesystem/container limits, global capacity monitoring,
retention/orphan cleanup and load/soak tests. No strict physical-disk ceiling or
complete retention/account-erasure guarantee is claimed.

## Migration and offline inventory on Windows

Stop API, worker and Expo first. Preserve both the actual DB and media backups.
The following assumes the normal local SQLite path; use your configured DB if
it differs. From the repository root after merging:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
$backup = ".data\nextphase-before-save-storage-$(Get-Date -Format yyyyMMdd-HHmmss).db"
Copy-Item .data\nextphase.db $backup
git pull
$env:PYTHONPATH = "apps/api"
.\.venv\Scripts\python.exe -m app.migrate
.\.venv\Scripts\python.exe -m app.storage --reconcile
.\.venv\Scripts\python.exe -m pytest apps/api/tests -q
.\.venv\Scripts\python.exe scripts/smoke_e2e.py
cd apps\mobile
npm ci
npm run typecheck
npm run test:uploads
npm run test:auth
npm run test:exports
```

Migration `0008_storage_budgets` adds nullable budget/cap fields. It preserves all
existing accounts/sessions/media and does not guess historical usage. The offline
inventory scans canonical private project trees without following symlinks or
stored source paths. Its budget covers observed files plus remaining attempt room,
with a source + two-attempt floor; old artifacts larger than the new cap are
counted, not deleted. Old paused sessions get their full declared-byte reservation.
Existing clean deletion tombstones need no retained-media reservation.

Until inventory is complete, **new uploads for the affected account return 409**;
existing jobs/downloads and accepted sessions remain accessible. Missing trees,
unsafe links, permissions or scan failures stay unverified, never guessed as zero.
The command commits successfully verified records, exits nonzero if any project
remains unknown and can be repeated safely while services stay stopped. Fix the
actual mount/permissions or deliberately delete an unwanted broken project and
wait for cleanup; do not force usage to zero. It deletes no media. Re-run migration
and inventory when upgrading each database/volume separately.

Compose: stop api/worker, back up PostgreSQL/media, build, run migrate, then
`docker compose run --rm --no-deps migrate python -m app.storage --reconcile`
before `docker compose up -d --wait`. Do not delete volumes to fix inventory.
Rollback requires stopped services, prior code and verified matching DB/media
backups. No new sign-in is required solely by migration 0008.

## Physical Pixel acceptance after merge (pending)

1. Install the committed mobile graph with npm ci, restart compatible Expo/USB
   forwarding/API/worker and render a disposable consented clip.
2. Tap Save video to phone. On modern Android no broad photo/video-read prompt
   should appear. Confirm the saved message, find the MP4 in Photos/Gallery and
   play it after closing the app. Save must not open Share.
3. Tap Share video. Confirm a share sheet opens; it must not request gallery read
   access or claim automatic gallery saving. Cancelling it should be harmless.
4. Check Account's server storage card. Delete the disposable project and run/wait
   for eligible cleanup; the reservation should drop while the saved gallery copy
   remains. Keep another project's download working.
5. Permission denial/OS storage-full behavior on platforms requiring permission
   and native cache/save failures still need device validation. API/network failure
   must never show a saved success. Backend tests cover reduced-budget admission
   and concurrent requests; don't lower a real account limit without noting the
   consequences for its next upload.

Email recovery, private cloud storage, full tracing/resource/cost accounting,
retention/legal/privacy review and production dependency gates remain Phase 2 work.
