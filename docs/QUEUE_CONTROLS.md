# Phase 2 increment: retry-safe uploads, cancellation and queue limits

## Upgrade and manual device check

Stop API and worker, back up the actual database/media, pull the merged branch,
install requirements, and run `PYTHONPATH=apps/api python -m app.migrate`.
This applies additive revision `0003_submission_keys` to the already versioned
Phase 2 database; `--adopt-legacy` is not needed again. Keep old/new workers from
running together. Existing users, jobs and old downloads are retained. Restart
API, worker and Expo (clear Metro cache). See PHASE_2_MIGRATIONS.md for Windows.

On the Pixel, confirm an old download and a new successful render still work.
To check queued cancellation reliably, stop just the worker, submit a short
consented test video, open the queued job and choose **Cancel render**, then
confirm. Restart the worker and verify the job stays CANCELLED and offers no
download. Processing cancellation may race completion: a completed job remains
SUCCEEDED and cannot be cancelled. The new UI controls require device recheck;
Android bundle/typecheck alone do not verify interactions.

## Submission contract

`POST /api/v1/jobs` accepts optional `Idempotency-Key` (8–128 ASCII letters,
digits, underscores or hyphens). Keys are scoped to the authenticated owner and
persist on the job without automatic expiry. Legacy clients without keys can
still submit, subject to queue limits. A unique DB index protects the owner/key
pair, including concurrent requests and separate API processes.

The server hashes source bytes while streaming to private storage, then hashes
that digest with the normalized title, style, desired duration and file extension.
Same key + same fingerprint returns the original job with HTTP 200 and
`Idempotency-Replayed: true`; a new submission returns 201. A changed fingerprint
under the same key returns 409. Original filename and multipart encoding are not
part of identity. Replays return the current job state, including cancelled/failed;
they never silently create a retry job. Invalid media/request fields still fail
validation before replay. A lost response can be retried using the same key.

Replays currently transfer and validate the entire source again; this is
submission idempotency, not resumable uploads or a byte-transfer optimization.
Rejected/replayed requests remove their temporary second source. If a new job's
COMMIT acknowledgement is lost, its input is deliberately retained because the
commit outcome is uncertain; a future janitor must handle orphan sources.

Mobile keeps a random non-secret key in memory for the current form's file URI,
name/size and editing settings. Double taps are guarded and network failures
reuse the key. Changing the form creates a new intent/key. Keys do not survive
form unmount/app restart; persistent upload sessions remain future work. No video
hashing, rendering or other heavy processing is introduced on the phone.

## Cancellation contract

`POST /api/v1/jobs/{id}/cancel` requires owner auth. Queued/processing jobs become
terminal `cancelled`; their lease token is revoked and final result fields cleared.
Repeated cancellation returns the same state and finished timestamp. Unknown or
another owner's job returns 404; missing auth returns 401; succeeded/failed jobs
return 409. Download of a cancelled job returns 409.

The DB state changes immediately. FFmpeg checks ownership/cancellation every
250 ms while encoding and is killed/reaped when ownership is lost. DB latency,
scheduling and an in-flight ffprobe (bounded to 30 s) can delay physical shutdown;
this is not an immediate-stop guarantee. A final ownership check and token-fenced
DB update prevent publication if cancellation won the race. Cancelled jobs never
requeue during lease recovery. Source media is retained for future retention
policy; cancellation is not account/project deletion. Hard-killed processes may
still leave orphan artifacts.

## Limits and concurrency

Defaults (validated at startup):

```dotenv
MAX_ACTIVE_JOBS_PER_USER=3
MAX_PROCESSING_JOBS_PER_USER=1
```

Both must be positive integers, and processing cannot exceed active. All API and
worker processes must use the same limits. Active means queued or processing;
terminal jobs do not count. Lowering limits never deletes or cancels existing jobs;
new admissions/claims wait until the owner is below capacity. Admission locks the owner row and checks for replay
before checking capacity, so a legitimate replay works even when the queue is
full. Exceeding capacity returns 429, actionable text and `Retry-After: 5`.

Claims select the oldest eligible owner's queued job, skip PostgreSQL locked
owners and recheck processing capacity under the owner lock. SQLite serializes
short owner-write transactions. Upload reads/probes and render I/O hold no owner
lock. Cancellation uses the same owner lock; completion/recovery update job rows
atomically. Tests exercise same-owner parallel submissions and claims on both DBs.
Cancelled encoders can briefly overlap replacement work while shutting down.

This is bounded per-user concurrency, not weighted round-robin fairness, a global
worker cap, request rate limiting or billing quotas. It does not bound concurrent
multipart buffering/upload disk I/O before admission; edge body limits and upload
reservations are still required before public deployment.

## Validation scope

The suite tests replay/mismatch and source cleanup, owner scope, key validation,
replay at full capacity, terminal cancellation, expired-worker fencing, FFmpeg
termination/partial cleanup, four simultaneous same-key submissions, four unique
submissions competing for three slots, and four workers competing for one owner's
processing slot. The real HTTP smoke checks queued cancellation before starting
its isolated worker, upload replay, owner isolation, successful H.264/AAC export,
full decode and rejection of cancellation after success. No paid services or
new third-party dependencies are introduced. The 17 mobile audit findings remain.
