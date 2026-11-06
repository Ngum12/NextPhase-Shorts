# Implementation Status — 2026-11-06

This is a **developer prototype**, not a production AI editor. Phase 0 engineering
validation and the server portion of Phase 1 are verified below. The owner has now
reported a successful physical Pixel upload/render/download test. This establishes
the reported Android baseline flow, not production readiness or AI functionality.

## Phase 2 increment — upload replay, cancellation and queue controls

- Added migration `0003_submission_keys`, retaining prior rows/downloads. Optional
  owner-scoped Idempotency-Key plus server-side source/settings fingerprint prevents
  duplicate accepted jobs on replay; changed requests under a key return 409.
- Added owner-only queued/processing cancellation, terminal cancelled status,
  repeated-cancel safety, lease revocation and cooperative FFmpeg kill/reaping.
  Completed/failed jobs cannot be cancelled. No cancelled output is downloadable.
- Configurable defaults: max three active jobs and one processing job per owner.
  Short owner-row transactions protect admission and claimant capacity checks.
  Replay is checked before queue capacity; full queue returns 429/Retry-After.
- Mobile preserves the current form's submission key across network failures,
  guards double taps, adds a confirmation/cancel action and stops terminal polling.
  Native interaction recheck remains outstanding for these new controls.
- **33 tests passed on SQLite** (18.33 s) and **33 on PostgreSQL** (17.84 s), no skips,
  one existing Starlette/httpx deprecation warning each. Includes simultaneous
  same-key/different-key submissions and same-owner worker races, cleanup/conflicts,
  cross-owner/terminal cancellation, fencing, a real FFmpeg termination test and
  preserving/replaying an accepted upload after a lost commit acknowledgement.
- Live isolated SQLite smoke passed queued cancellation, upload replay, full render,
  owner-only download and decode (4.9 s, 1080x1920/30 fps H.264/AAC, 1.92 s workflow).
  Rebuilt/migrated Compose PostgreSQL passed queued cancellation with worker paused,
  then the replay/render/download smoke with worker restarted (1.88 s workflow).
- Mobile TypeScript and Android Hermes export passed (992 modules / 2.59 MB).
  Remote CI and physical Pixel testing of these new interactions remain unverified.
- No new dependencies; 17 mobile audit findings remain unresolved. No paid services,
  billing or AI processing activated. This is still a Phase 2 increment, not full
  production queueing/security: no broker, heartbeat, persistent upload session,
  resumable transfer, global upload reservation, auth hardening or retention janitor.
  See `docs/QUEUE_CONTROLS.md` for protocol, limits and migration instructions.
- Owner reports the prior Windows migration passed, all 22 prior tests and the
  migrated smoke passed (2.39 s), and both old/new Pixel downloads worked afterward.
  Those are user-supplied prior-increment results, not tests of this new increment.

## Prior Phase 2 increment — migrations and worker reliability

- Explicit Alembic `0001_baseline` / `0002_job_leases` upgrades. API/worker startup
  checks the version and never creates tables. Checked legacy adoption preserves
  users/completed job paths and rejects unknown schemas. Existing deployments must
  stop services and back up before running the migration; see `docs/PHASE_2_MIGRATIONS.md`.
- Atomic queued → processing compare-and-set claims; PostgreSQL SKIP LOCKED;
  UUID tokens and expiry fence completion and keep each attempt's artifacts separate.
- Expired first attempt requeues; expired second attempt fails with MAX_RETRIES.
  A stale worker cannot publish over a retry or delete the winner's output.
- PostgreSQL required for staging/production. Compose runs a one-shot migration
  before API readiness and worker startup. SQLite remains local development only.
- **22 tests passed on SQLite** (10.61 s) and **22 passed on PostgreSQL** (11.16 s),
  no skips; one existing Starlette/httpx deprecation warning on each run. Tests
  include four claimant processes / 12 jobs, a process crash immediately after
  claiming, stale-token/output rejection, bounded retries, legacy downloads,
  fresh/repeat migration, model/schema equivalence and data preservation.
- Migration-aware live SQLite smoke passed (4.9 s export, 1080x1920/30 fps,
  H.264/AAC, full decode and owner isolation; 1.50 s workflow time). Compose build,
  one-shot migration, repeated startup and PostgreSQL live smoke also passed.
- Mobile TypeScript passed; no mobile source/dependency changes in this increment.
- CI now defines SQLite and PostgreSQL test variants; remote CI remains unobserved.
- **At that increment**, submission idempotency/cancellation were still pending;
  broker, heartbeat, full fairness, billing quotas, storage/resumable uploads, auth hardening,
  full telemetry or retention janitor yet. Claims have bounded leases, not
  exactly-once execution; hard-killed attempts can leave orphan files.

## Implemented and verified

- FastAPI registration/login and signed bearer sessions, scrypt password hashes.
- Per-user job listing/detail/download, UUID storage paths, validated uploads.
- Source cap 600 seconds / 300 MiB; requested output 5–60 seconds.
- Separate polling worker, bounded stale-job retries and terminal render failures.
- Server FFmpeg first-seconds trim/letterbox to 1080x1920, 30 fps, H.264/AAC MP4.
- Six future styles remain explicitly unavailable; no style-dependent effects.
- SQLite native development and Docker API/worker/PostgreSQL startup and live E2E.
- Expo SDK 54 dependencies aligned (React Native 0.81.5; React/React DOM 19.1.0),
  committed npm lockfile, clean `npm ci`, TypeScript and Android Hermes bundle.
- Docker source permissions repaired for unprivileged execution, API HTTP healthcheck
  and worker readiness ordering. Optional build-time CA secret supports the managed
  TLS proxy without disabling verification or putting the CA into image layers.
- Phase 0 ADR, dependency/trust graph, threat model, service contract, work queue,
  metadata inventory and reproducible demo commands in `docs/` and README.
- Mobile preview copy now states baseline processing and avoids promising secure
  transport on the plain-HTTP development API.

## Current validation record

Executed on Python 3.12.14, Node 24.22.1 / npm 11.9.0, FFmpeg 7.1.5.

| Command / check | Actual outcome |
|---|---|
| `python3 scripts/doctor.py` | Python, Node/npm, FFmpeg/ffprobe and Docker found |
| Baseline backend suite before changes | 9 passed |
| `PYTHONPATH=apps/api .venv/bin/python -m pytest apps/api/tests -q` | **14 passed**, 8.44 s; no skips; one Starlette/httpx deprecation warning |
| Added regression coverage | Empty/bad/unsupported uploads, unknown style, blank title, byte-limit cleanup, >600 s source, login/invalid sessions, terminal worker failures, two-attempt stale recovery |
| Actual 60-second render with audio | Passed: 1080x1920, duration >=59 and <=60.00 s; existing >60 request/render rejection tests also passed |
| `.venv/bin/python scripts/smoke_e2e.py` | Real HTTP + isolated SQLite API/worker; queued → processing → succeeded; 1080x1920/30 fps H.264/AAC, 4.9 s; full decode and owner isolation passed; 1.44 s measured workflow time |
| Docker Compose build and `up -d --wait` | Passed after proxy CA trust and source permission fixes; API/DB readiness and separate worker verified |
| Smoke against Docker/PostgreSQL API on port 8002 | Same full workflow passed; queued → processing → succeeded; 4.9 s output, 2.43 s measured workflow time |
| `npm ci --no-audit --no-fund` | Clean lockfile install passed, no forced/legacy peer resolution |
| `npm run typecheck` | Passed |
| `EXPO_OFFLINE=1 npx expo install --check` | Installed SDK metadata reports dependencies up to date; online Expo Doctor not run |
| Android `expo export` | Passed: 989 modules, 2.58 MB Hermes bundle; not an APK/device test |
| `.venv/bin/python -m pip check` | No broken requirements |
| GitHub Actions | Workflow updated for lockfile, Expo check, Android bundle and live smoke; remote CI not yet observed |

Smoke output MP4, reports and logs are kept in ignored `.data/smoke-*`; Android
bundle/assets are in ignored `apps/mobile/.expo/android-export`. Only synthetic
video patterns and a generated sine tone were used. Report timings are single
local runs, source generation excluded, and are not production benchmarks or SLAs.
Byte/source-limit tests exercise the configured handler boundary using a small
limit/mock probe; no 300-MiB fixture or actual >10-minute upload was transferred.

## Follow-up validation after Pixel report

- Clean npm ci, mobile TypeScript and offline SDK compatibility check: passed.
- Android Hermes export: passed, 992 modules / 2.59 MB; does not verify safe-area appearance on hardware.
- Backend regression suite: 14 passed in 10.01 s, one existing Starlette/httpx deprecation warning.
- Live isolated API/worker smoke: queued → processing → succeeded, 1080x1920/30 fps,
  4.9-second H.264/AAC output, full decode and owner isolation passed (1.54 s measured).
- Dependency inventory regenerated for the targeted PostCSS update; current audit
  reports 17 remaining findings. No blanket override, forced resolution or Expo SDK change.
- Owner's Windows results: 14 tests passed in 81.51 s and live smoke passed in 2.69 s,
  followed by successful TypeScript/Android bundle checks and physical Pixel download.
  These are user-supplied results, not remotely executed by this agent.

## Remaining blockers and acceptance limits

- **Android evidence and limits:** owner-reported Pixel test passed using Expo Go
  for SDK 54 on Windows with USB `adb reverse` (ports 8000 and 8081). The supplied
  result screenshot shows documentary, requested 15 s, actual 11.7 s, SUCCEEDED;
  the owner confirmed download worked. Home/style-list screenshots were supplied.
  Exact Pixel model, Android build, media provenance and independent probe of that
  downloaded file were not captured. iOS remains untested. The owner subsequently confirmed the safe-area fix and
  a repeated upload/render/download check all worked on the Pixel.
- **Dependency findings:** current audit reproduced 18 findings (5 high). A targeted
  PostCSS 8.5.32 override reduces this to 17 (4 high, 12 moderate, 1 low), preserving
  Expo SDK 54. Remaining findings are unresolved; see `docs/DEPENDENCY_SECURITY.md`.
- **Commercial license clearance is pending:** `docs/dependency-inventory.json`
  records 834 exact installed/locked dependency records and metadata, not legal
  approval, complete OS/container SBOM or an attribution bundle. Reference ZIPs
  are absent; their original licenses were not independently reinspected. No code
  or assets from them were imported. See `docs/LICENSE_AUDIT.md` and Phase 0 audit.
- **GitHub PR API access:** the actual `gh api` repository request returned
  Forbidden. Existing HTTPS Git read access works. `api.github.com` was added to
  the environment configuration draft; saving the draft does not apply runtime
  access. Review/save the setting and publish as the environment UI requires.
  The development branch `dev/phase-0-1-validation` was committed and pushed successfully.
  `gh pr create --draft` then failed with `Post https://api.github.com/graphql: Forbidden`;
  no PR was created. A review description is prepared in `/tmp/nextphase-pr-body.md`.
  Retry PR creation after API access is applied; Git push access alone is insufficient.
- Python requirements remain version ranges; the inventory records this machine,
  while the mobile lockfile pins npm resolution. No production security
  certification or complete dependency vulnerability review is claimed.

## Not implemented

AI highlights/director integration, ASR/captions, intelligent reframing, motion/3D,
B-roll and six style engines; hardened auth/account lifecycle;
full durable broker, private cloud storage, resumable upload,
retention/deletion, production observability; payments, Mobile Money, entitlements,
quotas, legal/store signoffs and commercial production hosting.

## Next steps

1. Review/merge this Phase 2 increment; stop services and back up the actual Windows
   DB before the documented checked migration, then repeat the Pixel workflow.
2. Restore GitHub API access to create the review PR and observe remote CI.
3. Complete dependency/license review before merging for commercial use.
4. Next Phase 2 work: durable upload sessions/resumability and auth hardening,
   then retention/telemetry and further queue fairness, according to the master gates.
   See `docs/ROADMAP.md`; follow the later phases in `prompt.md` in order.

No paid APIs, paid infrastructure, real billing or subscription collection were
activated. Heavy rendering remains on the server; no private keys were put in mobile.
