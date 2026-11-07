# Implementation Status — 2026-11-07

This is a **developer prototype**, not a production AI editor. Phase 0 engineering
validation and the server portion of Phase 1 are verified below. The owner has now
reported a successful physical Pixel upload/render/download test. This establishes
the reported Android baseline flow, not production readiness or AI functionality.

## Phase 2 increment — native Save/Share and storage admission budgets

- Replaced the combined cache-download/share button with separate Save video to
  phone and Share video actions. Save resolves the native media-library write
  before confirming success; it never opens Share. Share never saves automatically.
  Denied permission, missing/empty downloads, 401/404/network and native save errors
  do not claim success or fall back to another action. Per-screen export guard
  prevents overlapping export actions; all editing remains server-side.
- Added SDK-matched Expo Media Library 18.2.1 (declared MIT), verified its official
  SDK 54 upstream license and preserved the notice in docs/licenses/. Inventory
  regenerated to 836 records. The npm package omits a standalone license file;
  inventory points to the preserved upstream notice. Full legal/OS/transitive
  clearance remains open. Fresh npm audit is unchanged: 17 unresolved (4 high,
  12 moderate, 1 low). No paid service, billing or proprietary kit assets added.
- Save uses add/write permission where needed; Android API 33+ can add the app's
  own video without broad read permission. Native config introspection verified
  broad Android media read/location permissions blocked and iOS add-only text
  present, with no photo-library read description. Expo Go's full-access warning
  is not a claim that this app reads the gallery. Native device save is unverified.
- Migration 0008 adds nullable job/session byte budgets and per-attempt render caps.
  New admissions reserve declared/received source bytes plus two bounded render
  attempts (default 64 MiB each) against a per-account 5 GiB budget. Owner-row
  transactions prevent concurrent accepted uploads overbooking; completion swaps
  one session reservation for one job. Replay/accepted sessions remain repeat-safe
  at capacity or after a config reduction; stored caps/reservations are retained.
- New owner-only GET /api/v1/me/storage powers Account's used/reserved storage card.
  New uploads return clear 409 errors for full or unverified inventory. Failed,
  cancelled and completed jobs retain reservations until deletion media cleanup;
  aborted/expired staging retains its reservation until cleaned. These are local
  resource admission budgets, not paid credits or strict physical filesystem quotas.
- Offline `python -m app.storage --reconcile` inventories existing canonical media
  trees while API/workers are stopped. Missing/unsafe/permission-denied trees stay
  unknown and block only that owner's new uploads rather than being guessed as zero.
  Existing accounts/sessions/media are preserved; no media is deleted by inventory.
  Migration alone does not fabricate old usage; this is a required upgrade step.
- FFmpeg output is monitored and validated against its stored cap. Exceeding it
  kills the child, removes its partial artifact and fails with OUTPUT_LIMIT_EXCEEDED;
  it never silently truncates an export. Transient overshoot/temp/spooling/orphan
  files and backups still need physical/global capacity controls and retention.
- **106 backend tests passed on SQLite (25.62 s) and PostgreSQL (37.03 s)**, no skips
  in this Linux environment; one existing Starlette/httpx warning each. Covers
  legacy/resumable admission, exact replay, transfer, config reduction, cleanup
  release, unknown/offline inventory failures, four concurrent HTTP uploads,
  additive migration preservation, real oversize output failure and all prior
  deletion/auth/queue/media regressions. No multi-GiB upload/load-soak claim.
- Clean npm ci, TypeScript, **7 upload + 8 auth/API + 7 export logic tests** and
  Android Hermes export passed (1,010 modules / 2.68 MB). Offline installed-SDK
  compatibility check reports up to date; online Expo Doctor not run. Pip check,
  native config introspection and diff checks passed. Native adapters are mocked
  in client tests; Pixel save/gallery and permission/OS-storage failure tests remain.
- Real isolated HTTP smoke passed API kill/restart, auth limits/revocation,
  interrupted 51 MiB upload/resume, unchanged storage reservation after completion,
  valid 1080×1920/30fps/4.9s render/download/decode, deletion and physical cleanup
  with owner reservation released to zero. Baseline workflow 1.64 s. Ignored
  synthetic evidence: `.data/smoke-cf55070041db417fbbb78c5d9961e1ab/`.
- The isolated PostgreSQL application DB/media were backed up; migration 0008
  and offline inventory succeeded (22 records, zero unverified trees), without
  deleting media. Rebuilt Compose services passed real HTTP auth/resume/reservation
  transfer/render/download/deletion smoke (baseline 2.58 s); the external API was
  not restarted by that run.
- Review delivery: implementation `303c35c` pushed to `dev/phase-2-save-storage`.
  Automatic PR creation returned `Post https://api.github.com/graphql: Forbidden`.
  Manual review link: https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-save-storage .
  No merge/deployment was performed; remote CI not independently observed.
- See [upgrade/inventory, scope and physical acceptance](docs/SAVE_AND_STORAGE.md).
  New `npm ci` is required; custom native builds must be rebuilt for permissions.
  The OS-saved copy remains outside server deletion. No gallery save on a real
  phone, iOS device run, full privacy erasure or production disk ceiling is claimed.

## Phase 2 increment — project deletion and private-volume cleanup

- Migration `0007_project_deletion` adds nullable deletion/cleanup timestamps and an
  index. Existing accounts, sessions, jobs, attempt records and paused uploads are
  preserved; migration itself deletes no footage. No new sign-in is required.
- Owner-only DELETE `/api/v1/jobs/{id}` commits a permanent tombstone before 202.
  All prior statuses can be deleted; repeated owner requests stay repeat-safe and
  other owners receive 404. Lists/detail/download/cancel hide deleted projects.
  Claims are revoked and title/path/linked upload display metadata are scrubbed.
- Owner/job-row locks follow the worker's job→attempt lock order. Active attempts
  are cancelled, stale completion cannot publish, and legacy/session key replays
  return 410 rather than resurrecting the project. Downloads now use private/no-store.
- Worker maintenance and `python -m app.deletion` scan bounded batches of canonical
  private UUID project/staging paths. Stored source/output paths are never deletion
  targets; symlink/junction parents are refused. Failed I/O retries without logging
  customer paths; pending removal precedes successful rescans, with oldest-attempt
  ordering inside each group. Previously cleaned tombstones are rescanned for late
  artifacts. Processing cleanup waits past the original lease plus 30 seconds.
- Mobile adds explicit destructive confirmation, waits for the server's deleted
  acknowledgement and returns to My Shorts. Offline failure stays retryable. It
  attempts removal of the current app download cache and discloses local failure;
  gallery/shared/other-device copies remain. Missing project routes have a back
  action. Confirmed discard of a remotely deleted upload clears only its private
  pending copy after 404/410; network failure does not authorize local deletion.
  Library requests are invalidated on blur so a delayed old list cannot reinsert
  a deleted item after returning from project detail.
- **96 backend tests passed on SQLite (22.53 s) and PostgreSQL (31.89 s)**, no
  skips on this Linux environment; one existing Starlette/httpx warning each.
  Covers all prior media/auth/queue/upload regressions plus deletion ownership,
  all statuses, concurrent completion, a forced lock-order race, actual running
  FFmpeg termination, replay denial, retry/rescan/priority, symlink/path isolation
  and fresh/repeat/additive migration preservation. On Windows the symlink-only
  test skips if the OS lacks symlink creation privileges; other deletion tests run.
- Mobile TypeScript, **7 upload + 8 auth/API client logic tests** and Android export
  passed (1,007 modules, 2.66 MB Hermes). Doctor, pip check and diff whitespace checks
  passed. No dependency changed; the last known 17 advisories (4 high, 12 moderate,
  1 low) and 835-record inventory remain applicable, not cleared by this increment.
- Final isolated real HTTP smoke killed/restarted its API, preserved auth controls,
  resumed a partial 51 MiB upload, verified checksum/one-job completion, rendered,
  downloaded/decoded valid 1080×1920/30fps/4.9 s MP4, then deleted the synthetic
  project. Other-owner delete was denied; future downloads returned 404, key replay
  410, and CLI cleanup physically removed its source/output tree. Baseline workflow
  took 1.66 s. Ignored synthetic evidence:
  `.data/smoke-16124dc67f7649359103bc3f0d6b7d8e/`.
- The isolated Compose/PostgreSQL DB was backed up, migrated and rebuilt. Final
  real HTTP auth/resume/render/download/deletion smoke passed (baseline 2.45 s),
  followed by cleanup CLI and filesystem/DB read-back confirming both synthetic
  deleted project trees absent. That external API was not restarted by the smoke.
- Review delivery: implementation `2c2160a` pushed to `dev/phase-2-project-deletion`.
  Automatic PR creation returned `Post https://api.github.com/graphql: Forbidden`.
  Manual review link: https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-project-deletion .
  The owner subsequently merged the deletion increment into main (`c848d7c`).
  No cloud deployment was performed; remote CI not independently observed.
- Owner-reported Windows validation: 96 tests passed (43.71 s), full restart/render/
  deletion/physical-cleanup smoke passed (baseline 3.83 s), TypeScript and all 15
  prior client tests passed. The owner reported the listed Pixel deletion checks
  worked, while the old Download or share action opened Share instead of saving to
  the gallery. That was the prior cache/share behavior; the Save action above is
  new and still needs device acceptance. These are user-reported results, not cloud
  native-device tests; not every cache/OS/offline edge case was independently captured.
- Scope is known committed project/staging media, not full account/personal-data
  erasure: ID/key/fingerprint/operational tombstones and attempt metrics remain.
  Backup expiry/restore reconciliation, uncommitted orphan GC, object-store erasure,
  legal deadlines and full retention policy remain open. No paid service, AI calls,
  billing, proprietary reference-kit code or new dependency was introduced.
  See [upgrade, cleanup delay and acceptance](docs/PROJECT_DELETION.md).

## Phase 2 increment — render timing records and operator report

- Migration `0006_render_attempts` adds one durable record per newly claimed render
  attempt, transactionally with the claim. Existing users, auth sessions, completed
  paths and upload state remain intact; historical measurements are not backfilled.
- Fenced completion saves monotonic observed render wall time and successful output
  size. Cancellation records the attempt even if the worker never returns; observed
  cancellation time can be filled afterward. Lease recovery leaves crashed work
  unmeasured rather than guessing compute. Retry metrics cannot overwrite a winner.
- Added private operator CLI `python -m app.telemetry`: nearest-rank P50/P95 and
  sample counts for observed attempts, first-claim queue wait and successful job
  turnaround; states/retries/output bytes plus unknown and truncated coverage.
  Reports omit emails, tokens, IDs, paths and titles. Unexpected worker errors
  no longer log raw exception text/customer paths.
- Optional decimal hourly-rate calculation covers observed wall time only. Default
  cost stays null. It is neither CPU seconds, VM billing, full variable cost nor
  a provider charge. No provider call, provisioning or billing was introduced.
- **81 backend tests passed on SQLite (18.61 s) and PostgreSQL (22.39 s)**, no skips,
  one existing Starlette/httpx deprecation warning each. Includes unique attempt
  creation under four concurrent claimant processes, failures, cancellation, crash
  recovery, stale completion, report privacy/coverage/percentiles/rates and additive
  migration preservation. All prior media/auth/upload/queue regressions passed.
- Real HTTP smoke passed cancellation, persisted auth limits/revocation across API
  kill/restart, partial interrupted 51 MiB upload/resume, repeat-safe completion,
  render/download/whole MP4 decode and owner isolation. Baseline output was
  1080×1920, 30fps, 4.9 s; baseline workflow 1.89 s. Its aggregate report verified
  two measured successful attempts and 17,308,533 total accepted output bytes.
  Synthetic evidence (ignored): `.data/smoke-ed3af74c646c49ddbaa3496cace98a36/`.
  This tiny synthetic sample is not a production performance/cost baseline or SLA.
- Backed up and migrated the isolated Compose/PostgreSQL application DB; rebuilt
  services passed real auth/resume/render/download smoke (baseline 2.28 s). The
  external API was not restarted by that run. Its operator report confirmed two
  measured successful attempts and clearly identified 10 older/unclaimed jobs
  without attempt records. Calculation-only hourly-rate input also passed.
- Doctor, mobile TypeScript, all 6 upload + 7 auth client tests and pip check passed.
  No mobile source/dependency changed in this increment; no new native feature or
  Android bundle test is claimed. Existing 17 dependency advisories and 835-record
  inventory remain applicable and unresolved; commercial clearance still pending.
- Review delivery: implementation commit `9a500dd` pushed to
  `dev/phase-2-render-telemetry`. Automatic PR creation again returned
  `Post https://api.github.com/graphql: Forbidden`. Create the review PR at
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-render-telemetry .
  The owner subsequently merged this telemetry increment into main (`0648ed2`);
  no cloud deployment was performed. Remote CI was not independently observed.
- Owner-reported Windows/Pixel validation passed after merge: 81 backend tests
  (76.12 s), restart/resume/auth/render/telemetry smoke (baseline 2.24 s), and a new
  Pixel upload/render/download/playback. Its local report contained one successful
  28.766 s measured render, 0.088318 s first-claim wait and 7,206,440 output bytes;
  cost remained null. Thirteen older/unclaimed jobs had no attempt records, as
  expected. This is one sample/user-supplied evidence, not a performance baseline.
- See [migration, definitions and operator checks](docs/RENDER_TELEMETRY.md).
  Full tracing/exporters, CPU/GPU/peak-memory measurement, representative load/soak,
  cost ceilings, retention/deletion, object storage and verified email recovery
  remain Phase 2 work. Paid services, AI processing and billing remain disabled.

## Phase 2 increment — revocable authentication sessions

- Migration `0005_auth_sessions` adds persistent session records and shared auth
  counters. Fresh/repeat upgrades and 0004→0005 preservation of users, completed
  output paths, paused upload offsets and parts are tested on both databases.
- Access tokens require issuer/audience/subject/issued-at/expiry/random session ID
  plus an unexpired, unrevoked DB record. IDs are hashed at rest. Current-session
  logout, logout-all and authenticated password change persist across API restarts.
- Password change verifies the current scrypt password and atomically revokes all
  sessions. Login/password operations serialize on the owner row; a revoked or
  expired session is rechecked after the password-change lock. Existing password
  hashes remain valid. New passwords require 12–128 characters.
- Atomic fixed-window limits default to 5 login attempts/account, 30 login attempts
  per peer, 10 registrations/peer and 5 password attempts/account per 900 seconds.
  Successes count too. HMAC keys avoid plaintext rate-table IP/email storage;
  denied requests return Retry-After. Dummy scrypt hides the unknown-account fast
  path; registration's existing 409 enumeration behavior remains documented.
- Docker/README/API upgrade launchers disable automatic forwarded-header trust.
  Production proxy/TLS/edge configuration remains a separate reviewed boundary.
  Expired sessions/counters are cleaned by worker maintenance between renders.
- Mobile adds Change password, Sign out and Sign out all sessions, saved-session
  validation and authenticated-401 handling (including chunk requests/download).
  Serialized secure-storage writes and originating-token checks prevent delayed
  responses from deleting a newer login. Offline logout retains the credential
  until server revocation succeeds. Pending upload journals remain owner-scoped.
- **68 backend tests passed on SQLite (25.20 s) and PostgreSQL (26.31 s)**, no skips,
  with one existing Starlette/httpx deprecation warning each. Includes concurrent
  counters, JWT claim rejection, revocation scope, expiry, password and race tests,
  plus all previous queue/media/migration/upload regressions.
- Clean npm ci, **6 upload + 7 auth client logic tests**, TypeScript, offline SDK
  compatibility check and Android Hermes export passed (1,007 modules / 2.66 MB).
  These use adapters for native storage/network and are not physical-device tests.
  Pip check passed. No dependency was added; inventory remains 835 records. A fresh
  npm audit still reports **17 unresolved** (4 high, 12 moderate, 1 low).
- Isolated real HTTP smoke: killed/restarted API; revoked token remained rejected,
  valid session stayed valid and exhausted login window still returned 429.
  Password change/all-session logout passed. The same run resumed the approximately
  51 MiB source at byte 1,048,576 after partial disconnect/restart, verified SHA-256,
  completed as one job and rendered/downloaded/decoded valid 1080×1920, 30fps,
  4.9 s MP4; baseline flow took 1.51 s. Evidence (ignored, synthetic only):
  `.data/smoke-9333e84beac64e07a124d4d3af774d39/`.
- Local Compose/PostgreSQL was backed up, migrated, rebuilt and passed auth plus
  partial-disconnect/resume/one-job/render/download HTTP smoke (baseline 2.39 s);
  the externally running API was not restarted by that smoke.
- **Upgrade behavior:** old bearer tokens require one new sign-in; use the existing
  account/password to recover the same projects/pending upload. See
  [Windows upgrade and acceptance steps](docs/AUTH_SESSIONS.md).
- Review delivery: implementation commit `8482277` pushed to
  `dev/phase-2-auth-sessions`. Automatic PR creation is blocked by GitHub API
  access returning `Forbidden`; the owner can create it from
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-auth-sessions .
  The owner subsequently merged this auth increment into main (`c191c53`).
  No cloud deployment was performed.
- **Owner-reported Windows/Pixel acceptance passed 2026-11-07:** 68 backend tests
  (65.40 s), all 13 mobile client tests, TypeScript and restart/resume/render smoke
  (baseline 2.31 s). The owner confirmed the listed Pixel sign-in, current/all-session
  sign-out, password-change and upload/render/download checks all worked. These
  are user-supplied results, not device tests executed by the cloud agent.
- **Remaining gates:** verified email delivery, forgot-password recovery, refresh rotation, notices,
  admin MFA, edge abuse/body limits and production security/retention review.
  No mail credentials are configured, so no unauthenticated recovery bypass or
  simulated email verification is supplied. Phase 2 remains in progress. AI and
  billing stay disabled; no paid service/infrastructure was enabled.

## Phase 2 increment — durable resumable uploads

- Migration `0004_upload_sessions` adds owner/key-unique session records, verified
  part metadata, expiry and cleanup state. Existing jobs/download paths are retained.
- Authenticated create/get/parts/complete/abort routes provide fixed-size sequential
  SHA-256 verified chunks and authoritative DB offsets. Exact part/complete retries
  are repeat-safe; changed bytes, gaps, invalid media and cross-owner access fail.
- Unexpired uploads reserve queue capacity, shared with legacy submissions.
  Completion exchanges an existing reservation for one job, including after a
  configured limit reduction. Abort/expiry releases the slot. Legacy upload still works.
- Parts are fsynced and atomically published before their offsets commit. Completion
  rehashes every part and source, verifies size/FFprobe limits, then persists one job.
  Chunk receive deadlines bound slow requests; aborted/expired/complete staging data
  is cleaned in bounded worker maintenance batches or via `python -m app.upload_cleanup`.
- Mobile now saves a private copy plus a per-account two-slot pending journal,
  reads/hashes one bounded chunk at a time, shows acknowledged-byte progress and
  offers Pause/Resume/Discard. It rechecks server offsets after interruption/restart.
  Transfers are foreground only; app data and the saved file must remain intact.
- **47 backend tests passed on SQLite** (17.57 s) and **47 on PostgreSQL** (19.09 s),
  no skips; one existing Starlette/httpx warning each. Coverage includes concurrent
  create/parts/complete, checksum and ownership failures, request timeouts, lost
  commit acknowledgements, expiry/cleanup, invalid media and shared reservations.
- Real HTTP smoke transferred an approximately 51 MiB synthetic source in 1 MiB
  chunks, disconnected halfway through a part, forcibly killed/restarted its API,
  resumed at the last acknowledged 1,048,576 bytes, completed twice as one job,
  verified whole-source SHA-256, rendered/downloaded and decoded valid MP4 output.
  Live Compose/PostgreSQL also passed interrupted-part resume and completion/render;
  that externally running stack was not restarted by the smoke command.
- Clean npm ci, **6 mobile recovery-logic tests**, TypeScript, offline SDK check,
  Android Hermes bundle (1,004 modules / 2.65 MB) and pip check passed. The six
  client tests use native/network adapters across JS runtime restarts, not a device.
- Added SDK-compatible expo-crypto 15.0.9 (declared MIT) for bounded checksums/UUIDs;
  inventory has 835 records. Audit remains **17 unresolved** (4 high, 12 moderate, 1 low).
- **Owner-reported Windows/Pixel validation passed after merge**: 47 backend tests
  (110.87 s), six upload client tests, TypeScript, real restart/resume smoke
  (baseline 3.91 s), upload/pause/resume, saved-upload recovery, discard and download.
  These device results were supplied by the owner, not executed by the cloud agent.
- Private filesystem/shared volume only: no cloud object store, signed storage URLs,
  OS background transfer guarantees, complete retention policy or production abuse
  controls. All intensive video processing remains server-side; paid APIs and billing
  remain disabled. See `docs/RESUMABLE_UPLOADS.md` for migration/protocol/limitations.

## Prior Phase 2 increment — upload replay, cancellation and queue controls

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
- At that prior increment there were no new dependencies; the resumable-session
  work above supersedes its upload limitations. Broker, heartbeat, complete abuse
  controls, auth hardening and full retention remain outstanding. No paid services,
  billing or AI processing were activated.
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
  records 835 exact installed/locked dependency records and metadata, not legal
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
full durable broker, private cloud object storage, OS background transfers,
full account/backup/object-store erasure and retention, production observability; payments, Mobile Money, entitlements,
subscription quotas, legal/store signoffs and commercial production hosting.

## Next steps

1. Review/merge Save/Share and storage budgets; stop services, back up the actual
   DB/media, migrate 0008 and run offline storage reconciliation. Install mobile
   dependencies and perform the Pixel media-library Save/Share/storage checks in
   SAVE_AND_STORAGE.md. Never skip unknown-usage inventory by forcing zero.
2. Restore GitHub API access to create the review PR and observe remote CI.
3. Complete dependency/license review before merging for commercial use.
4. Next Phase 2 work: verified auth delivery/recovery, full retention/account/backup erasure, private
   object storage, full tracing/resource accounting and queue fairness under the master gates.
   See `docs/ROADMAP.md`; follow the later phases in `prompt.md` in order.

No paid APIs, paid infrastructure, real billing or subscription collection were
activated. Heavy rendering remains on the server; no private keys were put in mobile.
