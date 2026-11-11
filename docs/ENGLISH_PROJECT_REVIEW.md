# English project review — private opt-in preparation

This milestone puts transcript review and clip suggestions in the mobile project
flow. It does **not** run speech recognition, enqueue preview renders or replace
the existing baseline worker. French remains experimental. The server pilot is
disabled by default and refuses staging/production configuration. Only 1–5
explicitly allowlisted app owner UUIDs can use it in development/test mode.

## Phone flow

When enabled, a project's **Review English clips** button opens a private screen:

1. Compare recognized words with the original recording.
2. Tap the last word of each complete sentence.
3. Confirm individually flagged words, or explicitly confirm all after checking.
4. Acknowledge comparison with the recording and save the review.
5. Select an English clip suggestion to read its source excerpt and timing.

The server replans from the original transcript and separate human annotations.
It preserves words, timestamps, model scores and provenance. No ASR rerun or
phone-side video/AI processing is involved. Suggestions remain human-review-only
and use the project's original requested duration, with the existing 60-second
cap. Preview generation/playback from this screen is not implemented yet; the
operator preview CLI remains the existing path for inspecting actual cuts.

The screen handles loading, no prepared transcript, network/API errors, stale-edit
conflicts and lost save responses. Explicit refresh/back controls warn about
unsaved marks; OS/stack navigation can still discard the in-memory draft. It
does not persist transcript text in phone file caches or analytics. Your existing
Gallery/source and separately saved media are unaffected by project deletion.

## Server contract and admission

- `GET /api/v1/jobs/{id}/analysis`: authenticated owner-only transcript, separate
  review, proposal and revision; `Cache-Control: private, no-store`.
- `PUT /api/v1/jobs/{id}/analysis/review`: bounded closed `{revision, review}`
  payload, explicit acknowledgement and transcript/source identity checks. A stale
  different edit returns 409; retries of the already-applied review return it.
  Writes share the existing owner-lock ordering with project/account deletion.
  Review saves are limited to 60 attempts per configured auth window per owner.
- Neither route accepts paths, executable instructions, model/engine artifacts,
  replacement transcript text or client-provided render commands.
- Private import CLI accepts only English, nonempty transcripts of at most 1,000
  words and 256 KiB. The durable accepted resumable-upload SHA-256 and the project's
  probed source duration must match. Legacy multipart-only projects without that
  accepted checksum are not eligible. Foreign/removed projects are refused.
- A separate bounded DB metadata pool admits at most 10 prepared projects per
  owner and 100 globally, serialized under the existing global capacity lock.
  This is not an unbounded metadata store or an increase to media quotas. Delete
  unneeded projects to free analysis slots. Existing identical imports preserve
  human reviews; a different transcript cannot overwrite them.

Migration `0021_project_analysis` adds one private row per prepared project.
Project/account deletion removes its transcript/review/proposal in the same
transaction; independent-journal restore replay also removes analysis for replayed
tombstones. Database backups may contain earlier transcript copies, and phone
in-memory screens/earlier exports cannot be recalled by the server. Existing
encrypted-backup/journal custody and retention policies still apply. Content
hashes bind data; they do not authenticate a reviewer or replace app ownership.

## Operator preparation after verification

**Not yet runtime-accepted.** This change had Python syntax checks, mobile
TypeScript compilation and an Android bundle build, not migration, API ownership,
deletion/restore, network or phone interaction tests. Do those before enabling
the pilot or deploying this migration onto the VPS. A green preexisting suite
alone does not cover the new review lifecycle.

Follow the existing stop-writers/verified-backup/explicit-migration upgrade process
and deploy matching API/worker tools. Startup deliberately refuses a stale schema.
For the private disposable VPS trial, the existing API `env_file` can carry:

```dotenv
ENGLISH_REVIEW_ENABLED=true
ENGLISH_REVIEW_USER_IDS=YOUR_CANONICAL_APP_OWNER_UUID
```

Keep these server settings private and restart the consuming API after changing
them. The user UUID is an app account ID, not the Linux `nextphase` UID or email.
Set `EXPO_PUBLIC_ENGLISH_REVIEW=true` only in the pilot app build and restart Metro
with a cleared cache. The public UI switch grants no API authorization. Leave
other owners and staging/production disabled.

Upload the **same recording bytes** through the app's resumable upload flow and
identify its project UUID. Use the already prepared English transcript from the
operator analysis pilot, or create one through its existing consented ASR path.
Never change transcript hashes to make mismatched media pass admission.

Using the existing private VPS `dc` Compose selector from the deployment guide:

```bash
cd ~/NextPhase-Shorts
dc exec -T api python -m app.project_analysis \
  --owner YOUR_CANONICAL_APP_OWNER_UUID \
  --project YOUR_CANONICAL_PROJECT_UUID \
  --stdin-transcript < .data/asr-pilot/english-real-analysis-1/transcript.json
```

The CLI reads bounded private stdin, uses the container's existing scoped DB
configuration and prints fixed status without transcript text/credentials. It
does not create a user, upload a source, run inference or enqueue a render. Native
development environments can instead use `scripts/import_project_analysis.py`
with `--transcript PATH` under their own existing server configuration.

Open the matching phone project, enter English review and refresh. Record actual
phone acceptance separately. Automatic contained analysis jobs, leases/cancellation,
admission/cost accounting and owned preview render jobs are still subsequent work.
