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

Automated lifecycle checks now exercise SQLite and disposable PostgreSQL,
including upgrade from 0020 with existing data, source-bound import, private API
reads/writes, retry/conflict handling, concurrent edits/deletion and restore
tombstones. A real synthetic-video upload/FFprobe/import/review round-trip and
the bounded operator stdin CLI are covered. Mobile contract and mocked component
interaction checks cover review/save, stale responses, session changes and
malformed timing data. These do not replace actual phone/VPS acceptance.

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

## Existing private VPS upgrade procedure

Merge the review verification/client-hardening change first. Stop new uploads
while updating. Use the existing private `dc` selector, not a different Compose
project or a new database volume. No keys/passwords need to be shared or rotated.

### 1. Obtain a fresh verified offsite backup before rebuilding images

```bash
cd ~/NextPhase-Shorts
git pull --ff-only origin main
sudo systemctl start nextphase-backup.service
.venv/bin/python scripts/vps_maintenance.py status
```

Continue only after the latest backup reports `ok:true`,
`authenticated_readback:true`, `offsite_copy:true` and `paused:false`. If it fails,
leave the existing containers running and resolve that failure before rebuilding.
The old backup image matches the pre-upgrade database; rebuilding first can replace
that image with one that requires the new schema.

### 2. Build matching images, then pause writers for migration

Recreate the function in each new SSH session:

```bash
cd ~/NextPhase-Shorts
dc() {
  env -u VPS_DATABASE_URL -u VPS_DB_PASSWORD -u COMPOSE_PROFILES \
    -u COMPOSE_FILE -u COMPOSE_PROJECT_NAME -u COMPOSE_ENV_FILES \
    -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
    docker --host=unix:///var/run/docker.sock compose \
    --project-name nextphase-vps-trial --env-file .data/vps-trial/compose.env \
    -f compose.yaml -f compose.restore-journal.yaml \
    -f compose.private-staging.yaml -f compose.vps-trial.yaml "$@"
}
```

Run this entire block in that same VPS shell. It preserves the observed writer
selection (including mail only if it was already running) and timer activation.
Build happens while the old app runs; the application pauses for migration and
container recreation. Failure restores existing timers so alerts are not silently
left disabled; it does not attempt a blind database rollback or restart old images.

```bash
(
set -euo pipefail
sudo -v
review_backup_timer="$(systemctl is-active nextphase-backup.timer || true)"
review_monitor_timer="$(systemctl is-active nextphase-monitor.timer || true)"
review_finish() {
  review_exit=$?
  if [ "$review_backup_timer" = active ]; then sudo systemctl start nextphase-backup.timer || true; fi
  if [ "$review_monitor_timer" = active ]; then sudo systemctl start nextphase-monitor.timer || true; fi
  return "$review_exit"
}
trap review_finish EXIT
sudo systemctl stop nextphase-backup.timer
if systemctl is-active --quiet nextphase-backup.service; then
  printf '%s\n' 'Wait for the running backup service before rebuilding.' >&2
  exit 1
fi
.venv/bin/python - <<'PY'
import json, time
from pathlib import Path
state=json.loads(Path('.data/maintenance/backup-latest.json').read_text())
assert state.get('ok') and state.get('authenticated_readback') and state.get('offsite_copy')
assert 0 <= time.time()-state['completed_at'] < 900
print('Fresh authenticated offsite backup confirmed.')
PY
review_writer_text="$(.venv/bin/python -c 'import sys; sys.path.insert(0,"scripts"); from vps_maintenance import running_writers; print("\n".join(running_writers()))')"
mapfile -t review_writers <<< "$review_writer_text"
review_build_services=(api worker queue-supervisor operator-agent backup-tool migrate)
if [[ "$review_writer_text" == *mail-worker* ]]; then review_build_services+=(mail-worker); fi
dc build "${review_build_services[@]}"
sudo -v
sudo systemctl stop nextphase-monitor.timer nextphase-monitor.service
dc exec -T api python -c 'from sqlalchemy import select,func; from app.db import SessionLocal; from app.models import RenderJob; db=SessionLocal(); assert db.scalar(select(func.count()).select_from(RenderJob).where(RenderJob.status.in_(["queued","processing"])))==0, "Wait for queued/processing jobs before updating"; db.close()'
dc stop "${review_writers[@]}"
dc run --rm --no-deps migrate
dc up -d --no-deps --wait --wait-timeout 120 "${review_writers[@]}"
dc exec -T api python -c 'from app.db import engine; from app.migrate import require_current_schema; require_current_schema(engine); print("Database schema is current.")'
dc ps
)
```

If any step fails, stop and report the failing step. Do not remove volumes,
reinitialize keys, downgrade blindly or resume mismatched images. A backup made
before this migration still requires its matching restore/migration procedure.

### 3. Enable one known app owner after the updated stack is healthy

Use the existing sign-in email only to look up the UUID in the private database:

```bash
review_owner_id="$(dc exec -T api python -c '
import sys, uuid
from sqlalchemy import select
from app.db import SessionLocal
from app.models import User
with SessionLocal() as db:
    owner=db.scalar(select(User.id).where(User.email==sys.argv[1].strip().lower(),User.deleted_at.is_(None)))
if not owner or str(uuid.UUID(owner))!=owner:
    raise SystemExit("No active app account found")
print(owner)
' 'YOUR_APP_SIGN_IN_EMAIL')"
export NEXTPHASE_REVIEW_OWNER_ID="$review_owner_id"
.venv/bin/python - <<'PY'
import os, tempfile, uuid
from pathlib import Path
owner=os.environ['NEXTPHASE_REVIEW_OWNER_ID']
assert str(uuid.UUID(owner))==owner
path=Path('.data/vps-trial/server.env').absolute()
assert not any(p.is_symlink() for p in (path,*path.parents))
assert path.is_file() and path.stat().st_uid==os.getuid() and not path.stat().st_mode & 0o077
keys={'ENGLISH_REVIEW_ENABLED','ENGLISH_REVIEW_USER_IDS'}
lines=[line for line in path.read_text().splitlines() if line.split('=',1)[0].strip() not in keys]
descriptor,temporary=tempfile.mkstemp(prefix='.server-review-',dir=path.parent)
try:
    with os.fdopen(descriptor,'w') as output:
        os.fchmod(output.fileno(),0o600)
        output.write('\n'.join(lines)+f'\nENGLISH_REVIEW_ENABLED=true\nENGLISH_REVIEW_USER_IDS={owner}\n')
        output.flush();os.fsync(output.fileno())
    os.replace(temporary,path)
finally:
    Path(temporary).unlink(missing_ok=True)
print('One private English review owner configured; credentials were not printed.')
PY
unset NEXTPHASE_REVIEW_OWNER_ID
dc up -d --no-deps --wait --wait-timeout 120 api
```

Do not paste `server.env`, database credentials, bearer tokens or recovery keys
into chat. Add `EXPO_PUBLIC_ENGLISH_REVIEW=true` beside the existing API URL in
the laptop's ignored mobile `.env.local`, then restart Metro with a cleared cache.
Use the existing permitted personal network. Upload the same recording through
the app, identify its project and apply the bounded import command above. Actual
phone save/reload/conflict behavior is the final private-pilot acceptance step.
