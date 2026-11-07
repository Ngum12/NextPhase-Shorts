# NextPhase Shorts — Stage 1 Starter Repository

**Your Personal AI Shorts Editor** — future commercial product. First milestone is a **functional cloud-style upload/render prototype**, not a finished AI editor.

> **Codex:** Read [`prompt.md`](prompt.md) **first**, followed by `docs/`, then run tests and proceed Phase 0 -> Phase 1. `prompt.md` defines the full implementation phases through commercial launch.

## What works right now

- Expo/React Native screens: sign in/register, home, Create Short, six future style choices, My Shorts, job polling and owner-authenticated download/share.
- FastAPI: email/password login, revocable bearer sessions, current/all-session sign-out, password change and shared auth limits, project listing, upload validation, 10-minute source/300-MiB cap, 60-second requested output hard limit, private download route.
- Dedicated worker: basic FFmpeg 1080×1920 MP4, up to 30 fps, from the **first** requested seconds of footage; status queued/processing/succeeded/failed/cancelled. The worker runs on a server or your dev PC; never on the phone.
- SQLite local development or Docker PostgreSQL, backend tests and GitHub Actions starter.

## Not yet built (don't mistake labels for finished features)

**No real AI highlight extraction, automatic captions, effects, animated carousels, different editing styles, privacy-compliant commercial hosting, payments, Mobile Money billing, subscription quotas, production hardened auth, production cloud deployment yet.** Six style names are visible but render the same plain baseline. This is deliberately transparent.

## Step 1 — Run local or Docker backend

### Recommended: Docker Desktop

From repo root:

```bash
cp .env.example .env
# Replace JWT_SECRET with a random string. For development only; never commit .env.
docker compose up --build -d
curl http://localhost:8000/health
```

The API listens on port 8000, worker automatically polls queued jobs, PostgreSQL is internal to Docker. To see logs:

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

For Android emulator use `EXPO_PUBLIC_API_URL=http://10.0.2.2:8000`. For iOS simulator use `http://localhost:8000`. For a **physical phone** use your computer's LAN IP and allow the firewall, e.g. `http://192.168.x.x:8000`. **Only for development on a trusted network.** Real production must use HTTPS + domain and reverse proxy. Verify Expo Go/SDK compatibility or build an Expo development client when needed.

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

- [Full Codex build contract](prompt.md)
- [System architecture](docs/ARCHITECTURE.md)
- [What costs money / API options](docs/COSTS_AND_KEYS.md)
- [License audit](docs/LICENSE_AUDIT.md)
- [Security gates](docs/SECURITY.md)

For migration 0005, one-time re-login, authentication limits and physical-device
acceptance, see [auth sessions](docs/AUTH_SESSIONS.md). Email verification, secure
recovery and session refresh remain pending; no email service is enabled.

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
