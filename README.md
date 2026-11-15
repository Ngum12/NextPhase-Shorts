# NextPhase Shorts — Stage 1 Starter Repository

**Your Personal AI Shorts Editor** — future commercial product. First milestone is a **functional cloud-style upload/render prototype**, not a finished AI editor.

> **Codex:** Read [`prompt.md`](prompt.md) **first**, followed by `docs/`, then run tests and proceed Phase 0 -> Phase 1. `prompt.md` defines the full implementation phases through commercial launch.

## What works right now

- Expo/React Native screens: sign in/register, home, Create Short, six future style choices, My Shorts, job polling and owner-authenticated download/share.
- FastAPI: email/password login, revocable bearer sessions, current/all-session sign-out, password change and shared auth limits, project listing, upload validation, 10-minute source/300-MiB cap, 60-second requested output hard limit, private download route.
- Dedicated worker: basic FFmpeg 1080×1920 MP4, up to 30 fps, from the **first** requested seconds of footage; status queued/processing/succeeded/failed/cancelled. The worker runs on a server or your dev PC; never on the phone.
- SQLite local development or Docker PostgreSQL, backend tests and GitHub Actions starter.

## Not yet built (don't mistake labels for finished features)

**Autonomous semantic highlight/story direction, advanced effects, animated carousels, distinct editing style engines, commercial hosting, payments, Mobile Money billing, subscription quotas and production security/release acceptance remain planned.** Six style names are visible but render the same plain baseline. This is deliberately transparent.

The private English review pilot can render selected reviewed excerpts and optional
[clean phrase captions](docs/CLEAN_CAPTION_PREVIEWS.md). New opt-in uploads can use the [automatic English analysis pilot](docs/AUTOMATIC_ENGLISH_ANALYSIS.md).
The [automatic Short draft flow](docs/AUTOMATIC_CLIP_DRAFTS.md) can now choose and
render a private excerpt without mandatory sentence marks or individual word
confirmations. Detailed transcript review remains optional; watch the finished
clip before sharing. Selection is heuristic, not verified story understanding.
This remains an owner-restricted prototype, not a public release.

Reviewed previews also offer optional [centered portrait framing](docs/PORTRAIT_FRAMING.md).
Fit remains the default; fill crops outer details and requires watching the result.
This is fixed center cropping, not automatic speaker tracking.

The [polished-video workspace](docs/POLISHED_VIDEO.md) combines reviewed-caption
text/timing corrections, fixed appearance choices, optional voice leveling and a
local preset into one render flow. It needs a saved English review and human recording comparison. Automatic
transcription is a separate opt-in pilot; face tracking remains planned.

## Step 1 — Run local or Docker backend

### Recommended: Docker Desktop

From repo root:

```bash
cp .env.example .env
# Replace JWT_SECRET with a random string. For development only; never commit .env.
python scripts/configure_queue.py
docker compose build worker
docker compose run --rm --no-deps worker python -m app.worker_hostcheck
# Continue only when the strict host report says ready: true.
docker compose up --build -d
curl http://localhost:8000/health
```

The API listens on port 8000; a Valkey/Arq worker consumes durable dispatch requests,
with PostgreSQL job authority and a separate queue supervisor. Compose requires
an unprivileged cgroup v2/Landlock-capable Linux host; unsupported hosts fail closed.
Native DB development remains available below. To see logs:

```bash
docker compose logs -f api worker
```

Stop:

```bash
docker compose down
```

To run without Docker, install FFmpeg and Python 3.12, then from repo root:

```bash
cp .env.example .env
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r apps/api/requirements-dev.txt
mkdir -p .data
PYTHONPATH=apps/api python -m app.migrate
PYTHONPATH=apps/api uvicorn app.main:app --reload --port 8000 --no-proxy-headers
# Separate terminal, from same repo root and same venv:
PYTHONPATH=apps/api python -m app.worker
```

On Windows, in PowerShell replace the `PYTHONPATH=apps/api COMMAND` syntax with `$env:PYTHONPATH='apps/api'; COMMAND`, or use WSL.

Existing installations: stop API/worker and back up first. An unversioned Stage 1
database requires a checked `python -m app.migrate --adopt-legacy` upgrade; see
[Phase 2 migration instructions](docs/PHASE_2_MIGRATIONS.md), including Windows commands.
Fresh Compose stacks run migrations automatically before API startup; existing
unversioned Compose volumes need explicit adoption first.

### Quick API check

```bash
curl -s http://localhost:8000/api/v1/styles
# API docs: http://localhost:8000/docs
```

Register via `/api/v1/auth/register` in `/docs` and use its bearer token for `/api/v1/jobs` upload. No AI keys are needed.

## Step 2 — Run Android / iOS app

```bash
cd apps/mobile
cp .env.local.example .env.local
npm ci  # installs the committed Expo-compatible dependency graph
npm start
```

For Android emulator use `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000`. For iOS simulator use `http://localhost:8000`. For a **physical Pixel**, prefer USB `adb reverse tcp:8000 tcp:8000` plus the Metro port and use `http://127.0.0.1:8000`. Docker binds the API to loopback by default. LAN access requires an explicit trusted development binding and firewall review. Real production must use HTTPS + domain and reverse proxy. Verify Expo Go/SDK compatibility or build an Expo development client when needed.

1. Create account / sign in.
2. Create Short -> choose your own short sample video -> acknowledge upload rights/server processing -> choose a style (future marker) -> 15, 30, 45 or 60 s maximum -> upload.
3. Observe queued/processing status; refresh or see auto-poll.
4. Tap Save video to phone for the media library, or Share video for the share sheet; both use authenticated server download.

The mobile app **does not render** the video. It may use network/battery for file transfers and video playback.

## Step 3 — Tests and doctor

```bash
python scripts/doctor.py
python -m pip install -r apps/api/requirements-dev.txt
PYTHONPATH=apps/api python -m pytest apps/api/tests -q
cd apps/mobile && npm run typecheck
```

The included test suite generates a 2-second FFmpeg video pattern and checks a 1080x1920 MP4. No paid API needed.

### Resumable uploads

Create Short now saves a private copy and uploads checksum-verified chunks. Pause
and Resume preserve committed progress; reopening New Short can recover the saved
intent after an app restart. Discard releases a partial upload's reserved slot.
This requires app data/the saved file to remain intact and does not provide OS
background transfers. See [resumable upload setup and checks](docs/RESUMABLE_UPLOADS.md).

### Retry and queue controls

Upload sessions from the mobile form reuse an owner-scoped submission key when retried.
Queued/processing projects have a **Cancel render** action. By default an owner
can have three active jobs and one processing job; full queues return a clear
error. Cancellation stops publication even if it races a render. See
[queue controls and upgrade instructions](docs/QUEUE_CONTROLS.md) for details.

### Reproducible server smoke demo

From the repository root with FFmpeg/ffprobe installed:

```bash
.venv/bin/python scripts/smoke_e2e.py
# Or test an already running API + worker (creates synthetic test accounts/jobs):
.venv/bin/python scripts/smoke_e2e.py --base-url http://localhost:8000
```

The default starts isolated API/worker subprocesses with a temporary SQLite DB,
generates five seconds of video/audio, uploads, polls, downloads, checks owner
isolation, probes H.264/AAC 1080x1920/30 fps and fully decodes the result. It stops
only its own processes. Logs, output and report go to an ignored `.data/smoke-*`
directory; no real footage or credentials are committed. This proves the server
path, not Android UI behavior. Run without Python's `-O` option so assertions run.

For local Metro in restricted networks, use
`EXPO_NO_TYPESCRIPT_SETUP=1 EXPO_OFFLINE=1 npm start -- --localhost`.
Run `npm run typecheck` separately; offline mode is not a compatibility check.
For managed Docker builds behind a TLS-inspecting proxy, see
[development validation](docs/DEVELOPMENT.md).

## Important boundaries

- Stage 1 jobs are **not smart clips**. They select the first N seconds and letterbox/pad for vertical; changing the style does not yet change visual effects. Codex will implement true style engines in later phases.
- You must review both platform payment policies before offering Mobile Money subscriptions through Android/iOS apps; a standalone compliant web checkout is a separate surface. No checkout code is active.
- Uploaded NextPhase Editor V1, Carousel Kit and Motion Carousels skills are **not included** because reuse and commercial SaaS licensing require individual verification. In particular, NextPhase Editor V1 prohibits repackaging the kit as a paid product. This original scaffold has no copies of them.
- Never commit `.env`, API keys, real footage or mobile output files. Do not deploy this prototype publicly until hardening stages in `prompt.md` are complete.

## Owner starter actions

1. Create a **private** GitHub repository and push the unzipped starter.
2. Connect GitHub repo to Codex.
3. Tell Codex: **“Read `prompt.md` in full. Execute Phase 0 and Phase 1, repair failures, run end-to-end Android + FFmpeg smoke test, keep all 60-second/server-render/license/payment gates. Then progress sequentially without enabling billing or paid APIs.”**
4. Supply only consented short sample media when requested; put it in secure test storage rather than public git.
5. Optional later: pay for actual cloud CPU/GPU rendering and secure object storage. For now, Docker/local dev costs no software subscription fees.

## More details

- [Experimental operator transcript/planning pilot](docs/ANALYSIS_PILOT.md):
  manual-fixture review and an optional local ASR adapter; no running-app activation
  or verified speech-recognition quality is claimed.
- [Current private-VPS acceptance and remaining gates](docs/PHASE_2_ACCEPTANCE_2026-11-11.md).

- [Full Codex build contract](prompt.md)
- [System architecture](docs/ARCHITECTURE.md)
- [What costs money / API options](docs/COSTS_AND_KEYS.md)
- [License audit](docs/LICENSE_AUDIT.md)
- [Security gates](docs/SECURITY.md)

For migration 0005, one-time re-login, authentication limits and physical-device
acceptance, see [auth sessions](docs/AUTH_SESSIONS.md). Email verification, secure
recovery delivery remain pending; no email service is enabled. Refresh rotation
is implemented and owner-reported Pixel checks passed; see [session refresh](docs/SESSION_REFRESH.md).

Migration 0006 records render-attempt timings and output sizes. Operators can run
`PYTHONPATH=apps/api python -m app.telemetry` for sample-counted P50/P95 and optional
partial cost estimates. See [measurement definitions and upgrade](docs/RENDER_TELEMETRY.md).

Project details now offer confirmed owner-only deletion. Access is revoked when
the request commits; private-volume files are removed by retryable cleanup, with
active renders deferred past their old lease. See [deletion scope and upgrade](docs/PROJECT_DELETION.md).

Save and Share are now separate native actions. Per-account server storage
admission budgets require migration 0008 and an offline inventory for existing
media. See [upgrade, native permissions and budget definitions](docs/SAVE_AND_STORAGE.md).

New uploads now require a recorded rights/server-processing acknowledgement.
Server container/codec/pixel/frame-rate checks and file-only FFmpeg input protocols
are restricted; old paused uploads can reconfirm without losing progress. See
[consent/media profile and migration 0009](docs/UPLOAD_CONSENT_AND_MEDIA.md).

Optional private S3-compatible originals/results and short-lived signed download
links are implemented behind `MEDIA_BACKEND=s3`. Local storage remains the default;
normal mobile Save/Share stays API-authenticated. See [configuration, migration
0010, local S3 smoke and remaining limits](docs/PRIVATE_OBJECT_STORAGE.md).

Direct signed chunk uploads are now opt-in with `DIRECT_UPLOADS_ENABLED=true` and
S3 storage. The API verifies and seals each chunk before acknowledging progress;
existing sessions and default local uploads retain their prior path. See
[migration 0011, protections and validation](docs/DIRECT_UPLOADS.md).

Worker upload expiration is now bounded and owner-locked. A separate preview-first
offline tool inventories/removes aged recognized orphans and unreferenced stale
attempts while retaining valid projects. See [retention and safety limits](docs/RETENTION.md).

### Account deletion

Account → Delete account disables sessions and schedules durable server-media cleanup.
Lost responses can be recovered from the sign-in screen. This excludes backups,
operational records and saved/shared phone copies. Back up and run migration 0012
before restarting. See [upgrade and disposable-account checks](docs/ACCOUNT_DELETION.md).

### Worker resilience

Claims now rotate across eligible accounts and expired-lease recovery is bounded.
Linux decoder children have parent-death/CPU limits and reduced environments. The
Compose worker requires enforced cgroup v2 CPU/memory/PID caps and fails startup if
unsupported. No migration or dependency change; see [upgrade and host acceptance](docs/WORKER_RESILIENCE.md).

### Operational visibility

Migration 0013 adds independent worker liveness pulses. `/ready` checks API DB/schema
readiness; private `python -m app.operations` reports backlog, expired claims, recent
failures and observed worker states. Worker events use validated JSON fields. No
public metrics/admin endpoint or paid monitoring service. See [upgrade and checks](docs/OPERATIONS.md).

### Local authentication recovery preview

Migration 0014 adds expiring one-use password-reset/email-proof actions. Delivery is
disabled by default; an explicit private local-file inbox is available only for
development/testing. No SMTP/provider, real-world email-owner verification or
verification enforcement was activated. Forgot password/Account screens show this
state honestly. See [upgrade and disposable-account QA](docs/AUTH_RECOVERY.md).

### Remaining Phase 2 scope

Follow the [fixed six-package checklist](docs/PHASE_2_CHECKLIST.md) in order.
Package 1 adds short access tokens, rotating refresh credentials, family revocation
and durable mobile retry. Back up and migrate **0015** before restarting. Existing
access-only logins need a new sign-in to enable refresh. No paid service, real email
or billing is enabled. See [upgrade and focused Pixel check](docs/SESSION_REFRESH.md).

Package 2 implements opt-in Resend delivery, an encrypted durable outbox and
verified-email upload policy. Default delivery/enforcement remain disabled; the
owner reports inbox/verification/reset/Pixel acceptance passed; production privacy
and provider-terms review remain open. Stop/back up, install updated Python
requirements and migrate **0016** before restarting. A private setup helper keeps
keys out of chat/history/Git and leaves sending off. See [email delivery runbook](docs/EMAIL_DELIVERY.md).

Package 3 adds free local Valkey/Arq dispatch, renewable bounded claims, retry/dead
letters and strict decoder filesystem/network isolation. Back up and migrate
**0017** before restarting; install updated Python requirements. The managed cloud
host cannot pass required containment; the owner supplied a passing Docker Desktop
host report and confirmed the focused Pixel render/save/playback checks after PR #22.
See [queue upgrade and the one host check](docs/QUEUE_RELIABILITY.md).

Package 4 adds private trace/metrics exports, local alert evaluation, mounted secret
files and explicit measured-cost coverage. See [monitoring, secrets and costs](docs/MONITORING_SECRETS_COSTS.md).

Package 5 adds shared capacity/intake limits, pre-parser upload caps, bounded
operational cleanup and a disposable load/backup-restore drill. See
[capacity/security runbook](docs/CAPACITY_SECURITY.md) and the
[explicit security/privacy launch blockers](docs/SECURITY_REVIEW_2026-11-08.md).

Package 6 preparation resolves the mobile advisory graph with Expo SDK 58 and
reviewed tool patches. Use an SDK 58-compatible Expo Go client. See
[upgrade and remaining staging gates](docs/STAGING_BLOCKERS.md). Zero npm findings
is not production/security/legal signoff.


Package 6 backup safety adds an opt-in independent encrypted local journal and
explicit offline restore/release gate. Protected restores require fresh password
recovery and reapply post-snapshot deletions; back up and migrate **0020** first,
then explicitly bind the current stopped source before protected snapshots.
API staging/production now requires the journal. Local Docker activation uses the
reviewed `compose.restore-journal.yaml` overlay; preserve its independent volume
when restoring DB/media. See [setup, automated proof and remaining offsite gates](docs/RESTORE_JOURNAL.md).


### One consolidated Phase 2 acceptance build

The remaining backup/TLS/operations/review software is now grouped into one
[consolidated build and acceptance runbook](docs/CONSOLIDATED_ACCEPTANCE.md).
`python scripts/consolidated_acceptance.py` runs one Linux/CI report for encrypted
recovery, real certificate-verified HTTPS/render/download, private operator delivery,
budget admission gates and external approval gaps. Windows owners use the single
reviewed `scripts/activate_private_staging.ps1` after merging. No mobile reinstall
or repeated phone test suite is needed. Local software acceptance does not approve
public hosting, real provider costs, offsite custody or legal/provider signoff.

### Preparing a new VPS

The [VPS preparation and migration runbook](docs/VPS_DEPLOYMENT.md) provides a
dedicated disposable Linux trial with fresh credentials, private loopback ports,
one-render limits and `scripts/vps_trial.py accept --synthetic`. It preserves the
working PC installation. This is private host acceptance preparation; trusted
public HTTPS, private cloud storage, offsite recovery and external approvals
remain required before an actual hosted release.

Private English automatic analysis: [AUTOMATIC_ENGLISH_ANALYSIS.md](docs/AUTOMATIC_ENGLISH_ANALYSIS.md)
describes opt-in uploads, queued server transcription, transcript review and
suggestions, plus the single existing-model VPS activation command. English
recordings up to three minutes only; actual protected inference/phone acceptance
remains an operator check. The prototype UI is unchanged in scope.

Reviewed clip selection: [CLIP_SELECTION.md](docs/CLIP_SELECTION.md) covers
diverse source-range alternatives, nearby transcript context and immutable
plan-bound review revisions. It is a transparent local selection improvement,
not semantic AI or a final interface redesign.

Audio timing: [AUDIO_TIMING_GUIDE.md](docs/AUDIO_TIMING_GUIDE.md) describes delayed
audio alignment and optional low-volume passage guidance for new automatic
English analyses. Existing reviewed projects remain unchanged; quiet-energy
estimates are informational and require playback review.

Visual changes: [SCENE_CHANGE_GUIDE.md](docs/SCENE_CHANGE_GUIDE.md) describes optional
server-side sampled visual-transition guidance for new private English analyses.
It helps review boundaries without changing source ranges, word timing or voice;
it is not semantic scene understanding or automatic cutting.


Optional private **Create with Gemini** can find up to three contiguous passages
across the complete English transcript, then map them to validated original word
boundaries. Older clients retain shortlist selection. Explicit transcript/timing
sharing consent, a server-only key and free-tier development gates are required;
failures fall back to the standard selector. See [setup and app test steps](docs/GEMINI_CLIP_SELECTION.md).
