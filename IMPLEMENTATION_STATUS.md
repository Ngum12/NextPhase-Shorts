# Implementation Status — 2026-11-08

This is a **developer prototype**, not a production AI editor. Phase 0 engineering
validation and the server portion of Phase 1 are verified below. The owner has now
reported a successful physical Pixel upload/render/download test. This establishes
the reported Android baseline flow, not production readiness or AI functionality.

## Phase 2 package 2 — optional Resend delivery and verified-email policy

- Implementation on `dev/phase-2-email-delivery`, based on confirmed merge
  **f200dc3**. Owner selected Resend, reports `auth.techskillnow.com`/DKIM/Forge
  records verified in Ireland and a sending-only API key prepared privately.
  No key was shared with this environment. Dashboard/DNS verification is an owner
  report, not an independent real-provider/inbox acceptance observation.
- **Real sending remains disabled by default and no real email was sent here.**
  No paid API/infrastructure, subscription billing or AI activated. Optional Resend
  adapter uses fixed HTTPS origin, verified TLS, no redirects, bounded IO/reply
  handling and a stable per-outbox idempotency key with a frozen message body.
  Provider terms/current free limits/Forge/idempotency behavior could not be checked
  from this environment (provider-site proxy Forbidden); account review remains.
- Migration **0016_email_outbox** adds method-tagged actions, encrypted outbox and
  persistent attempt budgets. It preserves legacy local proof meaning/accounts/
  passwords/sessions/uploads/jobs/media. Action hash and encrypted envelope commit
  atomically; no best-effort background gap for real delivery. No plaintext proof
  or recipient is stored in outbox columns; existing users.email remains account
  data. Envelope binding/expiry/credentials/deletion are checked before dispatch.
- Separate mail sender: owner-first locks, 90-second fenced leases, crash recovery,
  <=5 attempts, backoff/Retry-After, permanent failure states and no raw provider
  errors/log payloads. Network calls hold no owner lock. Concurrent senders share
  UTC day/month caps and one reservation/second. Defaults 20/day, 500/month; QA
  helper 5/day, 20/month, one owned recipient. Reservations/retries/crashes count
  conservatively, not provider billing units. Other apps' quota is not included.
- Accepted/terminal ciphertext is removed immediately; <=1,000-row maintenance
  wipes expired payloads and removes metadata after expiry plus one day. Existing
  render auth maintenance also cleans mail. CLI supports private aggregate reports,
  cleanup and bounded/cursor-based key re-encryption. Separate Fernet key ring,
  backup/rotation procedure; loss of keys fails those messages closed. No wall-clock
  purge SLA while processes are stopped; provider copies/backups/inboxes are outside
  this cleanup. Password/reset/deletion cancel queued/claimed mail transactionally;
  an already in-flight send may arrive, but its proof is revoked and completion fenced.
- Opt-in `AUTH_REQUIRE_VERIFIED_EMAIL` gates multipart upload/session creation/
  parts/completion/direct grants/commits. Only method `resend` from an accepted
  outbox establishes trusted verification. Local proofs cannot be promoted or
  redeemed across channels. Login/refresh/recovery/deletion, existing-project
  reads/downloads and abort/discard remain available; previously queued renders
  may finish. Default preview policy remains false until reviewed real-channel QA.
- Mobile distinguishes disabled/local/real delivery, avoids claiming delivery
  from generic request acceptance, displays actual verification state and blocks
  upload/resume with a route to confirmation when policy requires it. Paused upload
  state is preserved. No permission/native module/mobile key added.
- Baseline **264 tests passed (49.15 s)**. Final **294 backend tests passed on
  SQLite (57.25 s) and PostgreSQL (70.62 s)**; no skips, one existing Starlette/
  httpx warning each. Covers atomic encrypted issuance/failure, secret-free generic
  requests, concurrent/stale claims, exact retry bodies/keys, network/4xx/5xx/rate
  failures, caps/clock reversal/max attempts, payload/key/expiry cleanup, reset/
  deletion races and refresh revocation, trusted-upload routes and additive legacy
  proof migration. Extended existing live decoder check separately passed: new
  RESEND_API_KEY/AUTH_MAIL_ENCRYPTION_KEYS are stripped from child environments.
- **63 mobile logic tests**, TypeScript and Android Hermes export passed:
  **1,016 modules / 2.73 MB**. Offline Expo check reports dependencies up to date,
  with its explicit offline-validation limitation; this is not a new registry audit.
  Doctor/pip consistency/diff checks passed. Compose email profile parses correctly;
  it was not deployed or claimed to have enforced production host limits.
- Full local HTTP upload/resume/queue/server-render/download/operations/deletion/
  retention/crash/auth regressions passed: 1080×1920/30 fps/4.9 s, baseline **2.00 s**.
  Evidence: `.data/smoke-731512b82ea541daad99303c41783f70/`. Separate real HTTP API
  plus mail-process fixture restarted API before sending, killed sender after mock
  provider acceptance, advanced only its stopped disposable lease and recovered
  the exact message. Verification admission, one-use reset/all refresh revocation,
  other-owner isolation, ciphertext removal and secret-free logs passed. **Transport
  was local MockTransport only, not Resend.** Private temp data was removed.
  Evidence: `.data/email-delivery-smoke-0e9f3487bb2946168505e337cc71b6a5/` (standalone
  earlier proof `.data/email-delivery-smoke-e29b097bd18b443d817c9b9c39881d2f/`).
- Private S3/direct-upload full regression also passed, same valid output, baseline
  **8.02 s** includes signed-link expiry wait; staging/original/output cleanup and
  separate mock email proof passed. Evidence:
  `.data/nextphase-s3-smoke-126d8547688f/workflow/` and
  `.data/email-delivery-smoke-d0fd93af96374bfbbc0c1902c708d117/`.
  Normal smokes force real email/enforcement off regardless of inherited settings;
  full smoke/CI includes the explicit disposable mock proof.
- Added pinned cryptography **50.0.2**, installed cffi **2.1.1**/pycparser **3.12**;
  packaged license notices preserved and metadata inventory regenerated to **846**.
  No restricted reference-kit code/assets. Existing last-known 17 npm advisories,
  full dependency/OS/wheel audit and legal/privacy signoff remain open; metadata
  review is not commercial production clearance.
- Private setup helper uses a hidden terminal key prompt, preserves encryption
  keys, atomically saves ignored local configuration and leaves sending/policy off.
  Upgrade requires Python requirements installation, backup/migration 0016 and
  restart. Runbook [EMAIL_DELIVERY.md](docs/EMAIL_DELIVERY.md) specifies one owned-
  inbox Pixel verification/reset/upload/save check under conservative free-plan
  caps, then restores disabled preview settings. No repeated manual test suite
  requested. Remote CI/actual provider/inbox/Pixel/privacy acceptance remain pending;
  package 2 is **not closed** and package 3 has not been started. Production cgroup
  host enforcement remains open and was not bypassed. No production deployment.
- Delivery: implementation **7e12d27** pushed to `dev/phase-2-email-delivery`.
  GitHub GraphQL returned **Forbidden** creating the review PR; no PR or merge was
  performed here. Manual review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-email-delivery

## Owner acceptance and package 2 preparation

- Confirmed upstream main **f200dc3**, merge of PR **#20** (session refresh).
  Owner reports all five focused Pixel checks passed: fresh sign-in, app reopen,
  access renewal after the 70-second check, upload/resume/render/save, and sign-out/
  sign-in. These are owner-supplied device results, not independent observations.
- Package 1 local automated proof remains 264 SQLite/264 PostgreSQL tests, 61
  client logic tests, TypeScript/Android export and full HTTP/private-S3 workflows.
  Remote CI lookup returned GitHub API **Forbidden**; its status is unobserved,
  not passed. This gate remains explicit rather than being silently dropped.
- Started `dev/phase-2-email-delivery` from the confirmed merge. Inspected current
  auth-mail/actions/client capabilities: only disabled/private local-file delivery
  is implemented; no durable real-delivery outbox, SMTP/provider or verified-email
  policy is present. Package 2 is not complete. Its preparation checklist is in
  [EMAIL_DELIVERY_PLAN.md](docs/EMAIL_DELIVERY_PLAN.md).
- Asked only for provider/sender-domain names (or a request for a recommendation),
  never passwords/API keys. No configured environment secrets are available.
  Delivery stays disabled; no real email/provider, paid resource or billing was
  activated. No runtime code/dependencies/schema changed in this acceptance note;
  only documentation verification is required, not another device regression run.

## Fixed remaining Phase 2 scope — package 1 session refresh

The owner approved the [six-package checklist](docs/PHASE_2_CHECKLIST.md), in order,
with one review and focused native acceptance where needed. This is the current
remaining scope; older increment notes below are historical evidence. Packages
2–6 remain pending: real delivery, queue/host enforcement, observability/secrets/
costs, capacity/security and staging. No blocked gate is waived; no Phase 3 started.

- Implementation: `dev/phase-2-session-refresh`, based on merged main `295428d`.
  Migration **0015_refresh_sessions** adds hashed grants, absolute-expiry families
  and nullable indexed access-family linkage. Existing accounts/passwords/access
  sessions/media/uploads remain preserved. Sign in once for refresh credentials.
- New access default 15 minutes, refresh idle seven days/absolute 30 days.
  Owner-locked rotation, domain-separated keyed hashes, shared IP/token budgets
  and default 120-second same-key response recovery. Different-key reuse commits
  family revocation before 401; matching late retry fails without revoking newer
  credentials. Other login families survive. Theft of both old token and key
  permits recovery within the bounded window; this is not device identity proof.
  Old access remains valid until its short expiry after normal rotation.
- Logout-current/refresh logout revoke family access; logout-all, password change,
  reset and account deletion revoke every owner family atomically. Consumed refresh
  grants support logout even with expired access and remain to absolute expiry
  for replay detection. Maintenance removes <=1,000 expired families per batch,
  with grant count dependent on activity; global metadata limits remain package 5.
- Mobile uses one versioned SecureStore pair/retry intent, persistence before
  sending/using replacements, single-flight refresh and serialized storage.
  Stale replies cannot overwrite/borrow newer account credentials. Stable UI
  generation handles prevent rotation cancelling uploads. GET/native download
  retries once; writes/multipart are not replayed. Offline failures retain intent;
  definitive refresh 401 requires sign-in. All-device logout requires server
  confirmation. Direct S3 transfers remain free of API credentials/cookies.
- Baseline **248 backend tests passed (46.72 s)**. Final **264 tests passed on
  SQLite (57.87 s) and PostgreSQL (67.83 s)**, no skips, one existing Starlette/
  httpx warning each. Covers rotation/retry/reuse, concurrent same/different keys,
  logout scopes, password/reset/deletion revocation, idle/absolute/access expiry,
  secret-free validation/rate limits, consumed-hash retention/cleanup and additive
  legacy-session/password preservation, plus all prior regressions.
- **61 mobile logic tests**, TypeScript and SDK alignment passed, including
  expiry single-flight, restart/lost-reply journal, failed intent/replacement writes,
  stale login/rejection/write races, logout confirmation, legacy restore, API-origin
  isolation, native download renewal and prior upload/direct-S3/auth regressions.
  Android Hermes export passed: **1,016 modules / 2.73 MB**. These are adapter and
  bundler checks; no new physical Pixel/Windows/iOS acceptance is claimed.
- Full local HTTP upload/resume/queue/render/download/operations/retention/deletion/
  crash regression passed: 1080×1920/30 fps/4.9 s, baseline **1.83 s**. Evidence:
  `.data/smoke-ea385da976844feab4c572a00a8f714f/`. Separate real HTTP refresh proof
  restarted API after rotation, recovered exact pair, rejected different-key
  reuse, preserved another login and revoked via consumed refresh. It checked
  secret-free logs and temporary DB cleanup. Expired-access proof signs a past-
  expiry fixture JWT; it does not change a live application's clock/DB. Evidence:
  `.data/session-refresh-smoke-ad0d6094ca834f798b5627824c26036b/`.
- Disposable private S3/direct-upload full workflow also passed, same valid output;
  baseline **8.03 s** includes signed-link expiry wait. Original/output/staging
  cleanup, retention and separate local recovery/refresh proofs passed. Evidence:
  `.data/nextphase-s3-smoke-73deceeadf11/workflow/` and
  `.data/session-refresh-smoke-6500659d9505424eaa9bb83e95fb9761/`.
  Backend CI includes refresh proof via full smoke; mobile CI adds refresh tests.
  `npm test` now runs every client regression script in one command.
- Doctor, pip consistency and diff checks passed. No dependency/native module,
  reference-kit source/assets, email sending, paid API/infrastructure or billing
  activated. Existing 843-record inventory and last-known 17 npm advisories remain
  unresolved; no new security/license/privacy clearance is claimed.
- **Package 1: locally verified; review/remote CI/focused Pixel acceptance pending.**
  Runbook: [SESSION_REFRESH.md](docs/SESSION_REFRESH.md). Stop/back up/migrate/
  restart, sign in once, then one local short-expiry/app-reopen/upload/save/sign-out
  check. No repeated manual regression suite requested. Production cgroup-host
  acceptance remains package 3; managed Docker driver `none` was not bypassed.
  No production deployment performed.
- Delivery: implementation **`faf0fa7`** pushed to `dev/phase-2-session-refresh`.
  GitHub GraphQL returned **Forbidden** when creating the review PR. No PR or merge
  was performed here; owner review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-session-refresh

## Phase 2 increment — local authentication recovery proofs

- Migration **0014_auth_actions** adds expiring one-use action hashes, HMAC
  account/credential binding and nullable method-tagged email-proof fields.
  Existing accounts are not backfilled as verified or locked out. Login/upload
  verification enforcement remains false. No dependency or native module added.
- **Real email delivery remains disabled/unimplemented.** The sole opt-in adapter
  writes a private local inbox only for development/test; staging/production
  reject it. No SMTP/provider request, funded infrastructure or email send occurred.
  local_file proof is not evidence of real-world email ownership and must not
  become production verification authority. Public confirmations are unavailable
  by default; there is no unauthenticated reset bypass or API-returned debug code.
- Requests use uniform generic acceptance for known/unknown/failed/disabled
  delivery, with shared IP/email rate limits. Local preparation runs after the
  response; action commit precedes private atomic message publication. This is
  best-effort development delivery, not a durable production outbox. File failures
  invalidate undelivered actions without logging email/code/path/exception text.
- Reset requires a 256-bit random 5–30 minute proof and commits password update,
  competing-proof consumption and all-session revocation together. No JWT or
  automatic login is returned. Owner locking serializes competing resets and
  password/deletion races. Email confirmation records only local method/time.
  Password change/reset/delete invalidate pending proofs; re-registering an email
  cannot recover the deleted owner. Expired DB proofs are cleaned in <=1,000-row
  batches by auth maintenance; private local message files require operator cleanup.
- Mobile adds Forgot password and Account local email confirmation with clear
  disabled/test-only copy, secure inputs and no persisted code/password. Public
  requests send no bearer/cookies and do not expire another login on failure.
  Post-reset validation uses existing originating-token guards. Auth 422 validation
  responses now avoid echoing input passwords/codes. No new permissions/API keys.
- Baseline **233 tests passed (44.68 s)**. Final **248 tests passed on SQLite
  (58.37 s) and PostgreSQL (68.52 s)**, no skips, one existing Starlette/httpx
  warning each. Covers private opt-in/production rejection, uniform requests,
  secret-free validation/delivery failures, hashed proofs, purpose/expiry/single
  use, parallel competing resets, revoked sessions/changed credentials/deletion,
  private-folder restrictions, bounded expiry cleanup, commit-before-publication
  and additive legacy-account/password preservation, plus all prior regressions.
- TypeScript and **44 client logic tests** passed (seven new recovery tests plus
  prior 37). Android Hermes export passed: **1,016 modules / 2.72 MB**. Tests use
  adapters; no new native Windows/Pixel/iOS acceptance is claimed. Doctor, pip and
  diff checks passed. No new dependencies/assets: existing 843-record inventory
  and last-known 17 npm advisories remain unresolved; no new legal/audit clearance.
- Real private local HTTP proof restarted the API with a pending reset code,
  confirmed one-use reset/same account, old-session revocation, other-account
  preservation, credential-change invalidation, local method tagging, secret-free
  access logs and complete temporary inbox/DB cleanup. Default full HTTP and S3
  workflows keep delivery disabled, then run this separate disposable file fixture.
  No actual email address was contacted and no existing account DB was modified.
- Full HTTP upload/resume/queue/server-render/download/operations/deletion/retention/
  crash regression passed: 1080×1920/30fps/4.9 s, baseline 2.32 s. Evidence:
  `.data/smoke-4566f84040ef475aa001d13ac92cac29/` and
  `.data/auth-recovery-smoke-d18726c45d804f3ab8d399bec84f25b0/`.
  Disposable private S3 workflow also passed, baseline 7.95 s includes six-second
  signed-link expiry wait; same valid output, original/output/staging cleanup and
  separate local email-action proof. Evidence:
  `.data/nextphase-s3-smoke-fe4e1e45c3c4/workflow/` and
  `.data/auth-recovery-smoke-df26a060b0f84306a945816c121739bb/`.
- Owner-reported merged operations acceptance (`80d7d0e`): migration current,
  **230 Windows tests passed, three expected Linux-only skips (190.70 s)**; full
  S3-backed smoke passed (baseline 4.41 s; `.data\smoke-4783d10e820f4468820cfa22cdd7c028`).
  Windows hard termination correctly had zero stopped records in that fixture;
  stale classification used only the documented synthetic observation clock.
  Subsequent live readiness returned true, operations status ok, one fresh idle
  worker, zero expired/missing claims. Owner then confirmed listed Pixel upload/
  render/save checks. These are supplied results, not independent device tests.
- Upgrade: stop API/workers, back up DB/media, migrate 0014, restart server and
  Metro; no pip/npm reinstall needed solely for this build. First verify disabled
  behavior; optional file QA uses a disposable account and private operator inbox.
  Never paste codes/messages into chat/issues/screenshots or expose that folder.
  Runbook/protocol/retention boundaries: [AUTH_RECOVERY.md](docs/AUTH_RECOVERY.md).
- Remaining Phase 2: owner-approved real email delivery, verified-channel policy,
  durable encrypted outbox/cleanup/notifications, refresh/MFA, broker/lease renewal,
  per-tenant isolation/egress, monitoring/retention, load and privacy/legal signoff.
  Strict Docker cgroup-host acceptance remains open (managed driver none); it was
  not bypassed. Paid services, AI and billing remain disabled; remote CI and new
  native acceptance remain unobserved. No production deployment performed.

- Delivery: implementation `3181744` pushed to `dev/phase-2-auth-recovery`.
  GitHub GraphQL returned `Forbidden` creating the PR; no PR, merge or production
  deployment was performed. Manual owner review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-auth-recovery

## Phase 2 increment — operational visibility

- Migration **0013_worker_pulses** adds minimal per-process liveness metadata:
  random worker ID, start/last/stopped times, interval and sampled phase. No user,
  host, PID, media reference or credential is stored. Existing accounts/projects,
  media paths, upload intent/offset/rights records are preserved; no dependencies.
- Worker heartbeat thread uses its own short DB sessions during foreground work.
  Default 10 seconds (allowed 1–60), fresh for three intervals plus 15 seconds;
  stopped/future-clock/stale states are distinct. It **never renews job leases**
  or proves render progress. Hard kills retain last-seen until stale; orderly
  stops mark the process stopped. Old process metadata remains retained, not GC'd.
- GET `/ready` returns minimal no-store DB/schema availability (200/503), with
  no raw exceptions or operational counts; `/health` remains unchanged liveness.
  Compose API health now uses readiness. Provider reachability, worker capacity,
  driver timeout tuning, overload/edge hardening remain separate boundaries.
- Private `python -m app.operations` reports current nondeleted job states, oldest
  queue/processing ages, expired/missing deadlines, bounded recent worker states,
  windowed attempt states and fixed failure codes. Unknown labels are grouped as
  other. It exports no IDs, names, paths, titles, URLs or secrets. No public
  metrics/admin route. `--check` returns 1 for attention, 2 for unavailable DB/schema;
  otherwise reports are read-only and never mutate retries/deletion/leases.
- Worker lifecycle/render/recovery/outage events are validated JSON with fixed
  messages and narrow fields. Canonical job/process correlation UUIDs remain in
  private logs; arbitrary payloads, user IDs, URLs, tokens and exception text are
  rejected. Legacy maintenance/third-party lines may remain plain. No complete
  distributed tracing/exporter, external alert delivery or global log certification.
- Baseline **220 tests passed (44.46 s)**. Final **233 tests passed on SQLite
  (53.41 s) and PostgreSQL (61.91 s)**, no skips, one existing Starlette/httpx
  deprecation warning each. Coverage includes concurrent pulse advancement without
  lease mutation, shutdown/nonresurrection, DB retry privacy, worker truncation/
  skew, queue/failure privacy, CLI exits, readiness failures, JSON log guards and
  additive migration preservation. Final strengthened pending-upload/rights/key
  preservation assertion also passed separately on both DBs.
- TypeScript and all **37 client logic tests** passed. No mobile source/native
  change or new APK/device test claimed. Doctor, pip, Compose syntax and diff
  checks passed. No paid API/infrastructure, monitoring provider, AI, billing,
  reference-kit code/assets or production deployment. Existing 843-record license
  inventory and last-known 17 npm advisories remain unresolved, not newly audited.
- Real isolated HTTP upload/resume/render/download/deletion/retention/crash smoke
  passed (1080×1920/30fps/4.9 s; baseline 2.02 s). Readiness, fresh/advanced worker
  pulse, operator CLI snapshot and two structured render events passed. After its
  own writers stopped, the fixture observed stopped state, detected a synthetic
  expired claim with CLI exit 1, and classified no fresh workers with an observation
  clock advanced 200 seconds. No real waiting-period or production lease change.
  Ignored synthetic evidence: `.data/smoke-28b154327dcf424f9ca6bc0adde279be/`.
- Disposable private S3 direct-transfer/sealing/render/download/signed-expiry and
  cleanup smoke repeated the operational checks successfully. Output 1080×1920/
  30fps/4.9 s, baseline 7.99 s includes six-second signed-link expiry wait.
  Evidence: `.data/nextphase-s3-smoke-e24b6eaf0ab0/workflow/`.
  Initial new smoke assertions incorrectly expected retained successful jobs after
  project deletion; corrected them to distinguish current queue state from retained
  successful attempt history. No pass was claimed for those initial failed runs.
- Owner-reported post-fix Windows acceptance on merged `9f294fd`: complete S3-backed
  smoke exited zero (baseline 2.95 s), temporary SQLite cleanup passed, and owner
  then confirmed listed Pixel old/new project, upload/render/save/cancellation
  checks passed. Evidence: `.data\smoke-ce8a9b04c0844fedbf74ebc8bc649c5c` and
  `.data\worker-recovery-93f7ad0561f84fc58cd72bb52129360b`. No newer Windows pytest
  count or independent remote CI success was supplied. These are owner reports.
- Strict Docker cgroup enforcement remains unsupported in this managed runtime
  (driver none), as previously reproduced; the guard was not disabled. No rebuilt
  production stack or new enforced-resource claim. Private CLI/heartbeat data is
  a bounded observation, not a capacity/progress SLA. Remaining Phase 2: broker/
  lease renewal, per-tenant isolation/egress, alert/exporter/retention policy,
  verified auth recovery, global capacity/load/soak and production security/legal.
- Upgrade/runbook: [OPERATIONS.md](docs/OPERATIONS.md). Stop API/workers, back up
  DB/media, migrate 0013, restart updated processes and check readiness/private
  report. No npm/pip reinstall needed solely for this build. Native Windows/Pixel
  and strict Docker-host acceptance of this new increment remain outstanding.

- Delivery: implementation `0942d9d` pushed to `dev/phase-2-operations`.
  GitHub GraphQL returned `Forbidden` creating the PR; no PR, merge or production
  deployment was performed. Manual owner review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-operations

## CI follow-up — procfs process-exit race

- Owner supplied a failed PostgreSQL GitHub Actions run: **213 passed, one
  failed (85.68 s)**. The hard-worker-crash test raised ProcessLookupError
  reading `/proc/<pid>/stat`; it did not establish that FFmpeg survived. The
  kernel can remove a process after procfs open but before read (ESRCH), while
  the old observer handled only FileNotFoundError on open (ENOENT).
- Test observer now treats both specific exit conditions as stopped. Regression
  cases retain live-process detection, zombie handling and propagation of other
  errors such as permission failures. No blanket OSError suppression, relaxed
  kernel containment assertion or retry-to-pass behavior was added.
- Child readiness waits for complete marker JSON, not just the creation of an
  empty/partial file. A deterministic partial-marker regression covers that
  adjacent CI scheduling race. These changes affect tests only, not production
  process supervision, queue behavior or resource limits.
- **220 backend tests passed on SQLite (55.02 s) and PostgreSQL (60.92 s)**,
  no skips, one existing Starlette/httpx warning each. The 21 targeted resilience
  tests passed (3.91 s), and the actual Linux hard-crash/credential-stripping test
  passed **ten consecutive independent runs**, stopping immediately on any failure.
- No application/mobile/schema/dependency change. HTTP/S3 smoke and native device
  tests were not repeated for this test-observation fix. Existing validation and
  strict Docker cgroup/Windows-native acceptance limits remain as recorded below.
  No paid infrastructure, API, billing, AI or reference-kit assets introduced.
- After review/merge, assess the **new GitHub Actions run for the fix commit**;
  rerunning an older commit does not validate the fix. Remote CI success has not
  been observed by this agent. No local reinstall, migration or app change needed.

- Delivery: `d0d3d12` pushed to `fix/ci-process-exit-race`. GitHub GraphQL
  returned `Forbidden` creating the PR; no PR/merge was performed by the agent.
  Manual review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/fix/ci-process-exit-race

## Windows follow-up — worker smoke temporary SQLite cleanup

- Owner merged worker resilience (`f7fd233`) and reported **209 Windows tests
  passed, three expected Linux-only skips (410.52 s)** and TypeScript passed.
  HTTP/S3 upload/render/download/deletion/retention and crash/restart checks ran,
  but the overall smoke exited nonzero: WinError 32 removing its temporary SQLite
  database. This is not recorded as a complete Windows smoke pass. No new Pixel
  or strict Docker cgroup acceptance was supplied.
- Root cause: closing ORM sessions returned SQLite connections to the engine
  pool; the helper kept those idle file handles open until process exit. Linux
  unlink permits this, while Windows correctly refuses removal of the open DB.
- The disposable helper now registers engine disposal with ExitStack, which runs
  before TemporaryDirectory cleanup on success or exception. Child termination
  still precedes disposal. Success/report output is deferred until the temporary
  directory is confirmed absent, and includes `temporary_cleanup=passed`.
- Two real-subprocess regression cases simulate Windows refusal with any idle or
  checked-out pooled connection: both normal completion and an injected error
  after DB use pass. The same guard fails against the original helper with
  "SQLite pool still holds file handles", reproducing the defect on Linux.
- **214 backend tests passed on SQLite (51.01 s)**, no skips, one existing
  Starlette/httpx warning. Standalone crash/restart smoke and complete HTTP smoke
  exited zero, validated 1080×1920/30fps/4.9 s output, and confirmed temporary
  cleanup. Baseline flow 2.97 s; ignored synthetic evidence:
  `.data/smoke-dd76299e5eaf48909554e4b6db9a900b/` and
  `.data/worker-recovery-a50ac41cb65c40128f3f936117dfc769/`.
- Native Windows rerun remains outstanding; Linux simulation is not claimed as
  Windows execution. PostgreSQL, S3-specific and mobile tests were not repeated
  for this fixture-only fix; prior results and the owner's new reports remain
  scoped as above. No application code, schema, dependencies, media policy,
  resource guard, paid service, AI, billing or license asset change.
- After review/merge: pull and rerun `python scripts/smoke_e2e.py` from the root
  with the existing venv/server configuration. No migration or reinstall needed.

- Delivery: `0857f57` pushed to `fix/windows-worker-smoke-cleanup`. GitHub
  GraphQL returned `Forbidden` creating the PR; no PR or merge was performed.
  Manual review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/fix/windows-worker-smoke-cleanup

## Phase 2 increment — fair queue and worker containment

- Eligible accounts rotate by durable most-recent attempt claim, never-served
  accounts first, retaining FIFO inside each account and existing concurrency/
  disabled-account guards. Retries consume a turn. PostgreSQL keeps SKIP LOCKED;
  this is turn fairness, not equal CPU time, paid priority or Sybil resistance.
- Expired-job recovery now handles at most 100 jobs per pass (maximum 1,000),
  retaining state/expiry fences and the two-attempt cap. SIGINT/SIGTERM cooperates
  with rendering and expires only its own processing claim after teardown.
  DB loop failures retry without logging raw exceptions. No broker, heartbeat,
  immediate crash detection or exactly-once claim; unexpired static leases remain.
- FFmpeg/FFprobe environments omit server credentials, Python search overrides
  and proxy/provider configuration. Linux exec launcher enforces parent-death
  SIGKILL, zero core dumps, 128 descriptors and a bounded CPU rlimit; POSIX render
  groups are killed/reaped. Fixed media policy, wall/output limits and 9:16 <=60 s
  output validation remain. Discarded diagnostics avoid unbounded FFmpeg stderr.
  Windows development retains direct execution/cooperative cancellation; hard
  Windows worker death can leave a decoder, and three Linux-only tests are skipped.
- Compose adds init, read-only root, no capabilities/new privileges, 64-MiB /tmp,
  two CPUs, 2-GiB memory and 128 PIDs. Its worker requires actual cgroup v2 limits
  and fails before DB/queue work if missing/excessive. Standalone development
  defaults the guard off. No per-tenant filesystem/network sandbox or production
  hostile-code isolation is claimed; shared media/provider access remains trusted.
- **Runtime blocker, explicitly reproduced:** managed Docker reports cgroup
  driver none and memory/CPU/PID support false. Container view is outer 32 GiB,
  four CPUs, unlimited PIDs. A bounded synthetic container render, UID 1000,
  read-only root, zero capabilities and no-new-privileges passed, but requested
  worker cgroup ceilings cannot be verified/enforced here. The final worker
  correctly refused startup with the required-limit error before queue work.
  Strict Docker Desktop/Linux-host acceptance remains open; no guard bypass for
  production or claim that this managed host enforces those resource ceilings.
- Baseline **197 tests passed (32.87 s)**. Final **212 tests passed on SQLite
  (45.76 s) and PostgreSQL (52.01 s)**, no skips, one existing Starlette/httpx
  deprecation warning each. Covers fairness, bounded recovery/expiry/fencing,
  shutdown/outage behavior, actual hard-parent-death/process-group/CPU termination,
  credential reduction and fail-closed cgroup validation, plus prior regressions.
- Bounded burst: 100 synthetic submissions, ten accounts, up to 16 in flight;
  exactly 30 admitted/70 capacity refusals and three fair ten-account rounds.
  This is not 100 simultaneous renders, a long soak or a production SLA/capacity
  benchmark. Existing multi-process claim/cancellation/deletion races also passed.
- TypeScript and all **37 client logic tests** passed. Mobile code/dependencies
  unchanged; no new APK/Android export or independent device acceptance claimed.
  Doctor, pip, image build, Compose syntax and diff checks passed. No migration:
  existing **0012** remains current. No new dependency/provider/reference-kit asset,
  paid API/infrastructure, AI, billing or production deployment. Existing 843-record
  inventory and last-known 17 npm advisory/legal/security gates remain unresolved.
- Final isolated HTTP smoke passed restart/auth, 51-MiB interrupted/resumed upload,
  render/download/decode, deletion and offline retention. Output 1080×1920/30fps/
  4.9 s, baseline 1.79 s; ignored synthetic evidence:
  `.data/smoke-60a71d5a130d4c4b9d744858ee976b08/`.
  New disposable worker proof kills its claimant, advances only that killed fixture's
  lease, restarts another worker and validates real output plus stale publication
  refusal and two attempt records. No real production lease-wait observation.
- Final disposable S3 direct-upload/restart/sealing/render/download/signature/
  deletion/retention smoke passed (1080×1920/30fps/4.9 s; baseline 7.96 s includes
  six-second signed-link expiry wait). Synthetic evidence:
  `.data/nextphase-s3-smoke-9aa313fd5786/workflow/`. Worker crash/restart evidence:
  `.data/worker-recovery-d18ebac09e394c03978ef25d8f48d08e/` (local) and
  `.data/worker-recovery-7e263137861c4568b0fafb1b03999755/` (S3-run companion;
  that companion deliberately uses its own local fixture, not remote crash I/O).
  Sanitized container observation is `.data/worker-container-proof.log` (ignored).
  CI triggers include the new crash helper; remote CI remains unobserved.
- Validation initially hit disk exhaustion; no failed checks were reported as
  passes. Removed only regenerable 51-MiB synthetic stress inputs from prior smoke
  runs, unused build cache and two unreferenced worker image revisions. Application
  volumes/running services and reports/logs/result videos were preserved; checks
  reran successfully after space recovery. Final container-limit refusal is an
  expected safety check, separate from that earlier disk failure.
- Owner-reported merged account-deletion acceptance (`b2caa0e`): migration current,
  197 Windows tests (125.34 s), TypeScript/37 client tests and S3-backed smoke passed
  (baseline 5.31 s; `.data\smoke-a36a31c3ab1a47dcb4a8fe68e5a4e7b2`). Owner confirmed
  all listed disposable-account Pixel checks worked. These are supplied reports,
  not agent-executed device or kernel-limit verification.
- Upgrade/Windows versus Linux behavior and precise remaining limits:
  [WORKER_RESILIENCE.md](docs/WORKER_RESILIENCE.md). Stop/restart native services;
  no npm/pip installation or migration change is needed solely for this build.
  Docker must rebuild/recreate and pass enforcement checks first. Remaining Phase 2:
  strict host acceptance, broker/heartbeat, per-tenant sandbox/egress, global capacity,
  representative load/soak, verified auth recovery, observability and legal review.

- Delivery: implementation `dcd54ea` pushed to `dev/phase-2-worker-resilience`.
  Automatic PR creation returned GitHub GraphQL `Forbidden`; no PR, merge or
  production deployment was performed. Manual owner review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-worker-resilience

## Phase 2 increment — account deletion and recoverable confirmation

- Migration **0012_account_deletion** preserves live accounts and adds durable
  disablement/receipt/cleanup metadata. Password-confirmed deletion atomically
  revokes every session and render claim, tombstones projects/uploads and scrubs
  account email/password and media display/path fields. Owner-lock rechecks stop
  late admission, upload publication and worker claims after disablement.
- Mobile adds Delete account with explicit confirmation and current password,
  plus Finish account deletion on sign-in. A private random SecureStore receipt
  recovers lost replies after authentication revocation. Server stores its hash,
  offers only coarse status for seven days, rate limits recovery and never uses
  the key as account login. Only confirmed deletion clears that owner's pending
  private upload; network/local cleanup failures retain recovery state. Original,
  saved/shared videos, caches and other account data are preserved.
- Worker maintenance durably retries/resweeps canonical disabled-owner local and
  S3 prefixes after upload/lease/grant deadlines. Namespace mismatches, unsafe
  owner links and I/O failures stay pending. Operational tombstones, fingerprints,
  rights/cost/session/grant records, historical untracked stores, versions and
  backups are outside full erasure. No production privacy-compliance claim.
- Baseline **187 tests passed (30.19 s)**. Final **197 tests passed on SQLite
  (37.79 s) and PostgreSQL (45.66 s)**, no skips, one existing Starlette/httpx
  deprecation warning each. Regression coverage includes
  additive migration, session revocation, wrong password/rate limits, receipt
  secrecy/expiry/collision, fenced completion, concurrent late upload admission,
  pending-part/budget cleanup, namespace/provider failures and owner isolation.
- TypeScript and **37 client logic tests** passed (15 uploads, 9 auth/API,
  7 exports, 6 account recovery). Android Hermes export passed: 1,014 modules,
  2.70 MB. Native/network adapters are mocked; no new Pixel/iOS acceptance claimed.
- Real isolated HTTP smoke passed upload → queue → server render → download,
  restart/auth, resumable transfer and previous deletion/retention checks. Output
  1080×1920 / 30 fps / 4.9 s; baseline 2.43 s. Evidence (ignored synthetic only):
  `.data/smoke-a8c66e5939e645dc9dad13e9f4a504c5/`.
- Disposable local S3 smoke also passed direct transfer, verified sealing, render,
  signed download expiry and orphan/project cleanup (baseline 8.14 s includes
  six-second expiry wait). Evidence:
  `.data/nextphase-s3-smoke-e696b31a83c0/workflow/`.
  Both runs additionally disabled a separate synthetic account over HTTP,
  restarted its API, recovered its receipt and verified revocation/other-owner
  preservation. After stopping their own writers they advanced only the synthetic
  cleanup deadline and verified local/S3 owner-media removal. This does not claim
  an actual waiting-interval observation or deletion of the owner's real account.
- Doctor, pip and diff checks passed. No new dependency, proprietary kit code,
  asset, paid API/infrastructure, AI, billing or production deployment. Existing
  843-record license inventory and last-known 17 npm advisories remain unresolved;
  no fresh vulnerability scan or legal clearance claimed. Remote CI unobserved.
- Owner-reported retention acceptance after merge (`a552111`): 187 Windows tests
  passed (662.20 s), HTTP smoke passed (10.03 s); local preview scanned 51 entries,
  protected 28, zero candidates, complete. S3 preview scanned/protected two,
  zero candidates, complete. No owner retention apply was performed. Evidence:
  `.data\smoke-ae5bddb56cb64c2c944bc2962d79c6d8`. These are user-supplied results.
- Upgrade requires stopping API/worker, backing up DB/media, and migration 0012.
  No dependency install is required solely for this increment. Restart all
  services; test account deletion only with a disposable account. Runbook and
  recovery/erasure limits: [ACCOUNT_DELETION.md](docs/ACCOUNT_DELETION.md).
- Remaining Phase 2 gates include verified recovery/email delivery, refresh,
  stronger queue/isolation/load/soak controls, allocation-aware online collection,
  formal backup/version erasure, monitoring and production security/legal review.

- Delivery: implementation `49b1cb8` pushed to
  `dev/phase-2-account-deletion`. Automatic PR creation returned GitHub GraphQL
  `Forbidden`; no PR, merge or deployment was performed. Owner review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-account-deletion

## Phase 2 increment — bounded maintenance and offline orphan preview

- Worker expiration now selects a bounded batch (default 100, allowed 1–1000),
  locks the owner and rechecks status/deadline, instead of expiring an unbounded
  set. Existing terminal staging/deleted-project cleanup and budget release remain
  automatic between renders; active/valid paused uploads stay protected.
- New operator `python -m app.retention` defaults to a nondeleting local/S3 preview.
  Offline apply requires the reviewed digest from a fresh complete inventory and
  an explicit assertion that all writers are stopped. This is intentionally not
  unattended online orphan deletion: an uncommitted upload can have no DB row.
  No valid saved-project age expiry is introduced.
- Recognizes only canonical UUID layouts for known owners; removes aged untracked
  media/upload trees or unreferenced noncurrent failed/lost/cancelled attempt
  artifacts in terminal projects. All known jobs/sessions, current/winning attempts,
  source/output/part references (including cross-project references), young/unknown
  data, symlinks/junctions/hardlinks/special files remain protected. Minimum grace
  24 hours; local modification/change times and S3 LastModified must qualify.
- Bounded scans (default 10,000 entries, maximum 50,000; 100 S3 pages per prefix),
  namespace/DB/root-bound digest, changed/incomplete/nonprogressing inventory refusal,
  repeated metadata/reference checks and exact-key S3 deletion. Private nonversioned
  stores only. Group failure is reported without raw provider messages. Offline
  assertion is not distributed-writer detection; backup/restore reconciliation and
  no concurrent filesystem/provider writers remain essential safety requirements.
- No migration, new configuration default, dependency, mobile source or native
  change. No paid infrastructure/API, AI, billing or reference-kit assets added.
  Existing 843-record inventory and unresolved license/security/17 last-known npm
  advisory gates remain; no fresh vulnerability scan or legal clearance claimed.
- Baseline **168 backend tests passed (30.69 s)**. Final **187 tests passed on
  SQLite (34.59 s) and PostgreSQL (41.30 s)**, no skips; one existing Starlette/httpx
  warning each. Adds preview-only behavior, digest/offline/grace/scan protections,
  every known job state, new data/committed intents, unsafe links/files, cross-project
  references, stale-winner/source preservation, namespaces, S3 failures/versioning/
  pagination and bounded expiry/reservation checks. TypeScript and all **30 client
  tests** passed. No new native/device/build claim; app code was unchanged.
- Real local/API restart/resume/render/download/deletion smoke passed (baseline
  1.74 s; 1080×1920/30 fps/4.9 s). After stopping only its own writers, actual CLI
  preview/offline refusal/empty apply and synthetic old-orphan apply passed while
  a known source survived. Ignored synthetic evidence:
  `.data/smoke-c5fd8fa9cf75441086dd6a0bbd158a48/`.
- Real disposable S3 direct-upload/restart/checksum/expiry/sealing/render/download/
  project cleanup regression passed, followed by offline exact-object orphan
  removal and known-source preservation. CLI guards also passed. Baseline 7.88 s
  includes the six-second signed-download expiry wait, not total stress transfer
  or container startup. Output 1080×1920/30 fps/4.9 s. Evidence:
  `.data/nextphase-s3-smoke-6f61f15eee78/workflow/`. Retention fixture advances a test
  clock two days; it does not claim to have observed a real 24-hour waiting period.
- Doctor, pip and diff checks passed. CI now triggers for the retention fixture;
  remote CI remains unobserved. No production deployment or actual owner's media
  cleanup was performed. Apply testing used only isolated synthetic storage.
- Owner-reported merged direct-upload acceptance (`2ee5e27`): Windows migration
  0011, **168 backend tests (375.16 s)**, TypeScript and 30 client tests passed;
  local smoke passed (63.83 s; `.data/smoke-0d7a76b8e9bc4c6ba0bd984fd98d49d1`).
  Those slower timings were reported, not diagnosed as a specific hardware issue.
  Pixel normal-flow checks passed. Owner then configured local SeaweedFS/USB 8333
  and reported direct resume/render/save, pause over 60 s followed by resume/save,
  and discard preserving the original all worked. This is owner-reported device
  acceptance, not independent evidence of a specific HTTP expiry response or
  physical removal of that owner's server objects. The earlier unquoted PowerShell
  IP truncation was resolved using quoted argument arrays.
- Upgrade/runbook and exact remaining limits: [retention](docs/RETENTION.md).
  No apply is required just to upgrade; start with preview, and stop/back up all
  writers before any reviewed removal. Remaining: online allocation-aware orphan
  GC, global capacity/cost and load/soak controls, formal retention policy, full
  account/version/backup erasure and the rest of Phase 2 security/auth/queue work.

- Delivery: implementation `658f967` pushed to `dev/phase-2-retention-cleanup`.
  Automatic PR creation returned GitHub GraphQL `Forbidden`; no PR/merge/deployment
  was performed. Manual review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-retention-cleanup

## Phase 2 increment — signed direct chunks and verified sealing

- `DIRECT_UPLOADS_ENABLED=false` by default. Updated mobile can negotiate direct
  chunks only for new capable sessions when enabled with private S3. Existing
  upload keys, modes, checksums, offsets, rights and normal PC API uploads survive.
  No paid API/infrastructure, cloud deployment, AI or billing was activated.
- Migration **0011_direct_uploads** preserves legacy sessions/parts as API uploads;
  adds namespace/transfer/cleanup fields, remote part references and one durable
  random grant per offset. Renewal reuses the bounded incoming key and refuses
  changed content intent. No dependency was added; existing 843-record inventory,
  license notices and last known 17 npm findings remain applicable, not cleared.
- Owner-only part-url signs exact temporary PUT key/length/checksum/type for at
  most 60 s. Part commit downloads and rehashes the chunk, checks exact length and
  stores a separate private sealed reference before acknowledging. Signed links
  cannot write sealed chunks, source originals or results. Lost replies/restarts
  recover from DB offsets; concurrent commits publish once; abort/expiry/deletion
  during sealing cannot publish. Source completion verifies the sealed manifest
  and whole source before media admission and one-job publication.
- Mobile uses raw storage PUT with no bearer/cookies/redirects, validates the
  target/required headers and retains its journal/copy on expired-link/network
  failure. API 401 handling remains separate; original footage is never removed.
  No new native permission/module. Transfers are foreground only; no encoding/AI
  was moved onto phones. Owner subsequently reported S3 direct Pixel acceptance (see retention follow-up above).
- Direct admission reserves three source copies plus two render caps; reservation
  transfers once to the job and remains conservative until project deletion.
  Terminal staging removal waits for recorded signed expiry, retries failures and
  rescans late writes. Project deletion releases only after project and staging
  cleanup. Capabilities cannot be recalled by logout/abort alone; retained grant/
  operational tombstones, long in-flight writes, orphans, backup/account erasure,
  physical/global quotas and ingress/cost/ACL/provider policies remain limits.
- Baseline before changes: **158 tests passed** (29.08 s). Final **168 backend tests
  passed on SQLite (30.00 s) and PostgreSQL (37.23 s)**, no skips; one existing
  Starlette/httpx warning each. Coverage adds ownership, capability opt-in, legacy
  digest/migration compatibility, corruption/length rejection, renewal bounds,
  concurrent commits, mutation after sealing, abort races, namespaces and cleanup.
  Final direct PostgreSQL race tests also passed separately (9 tests, 2.76 s).
- An initial PostgreSQL run hit stale synthetic tombstones from a reused test DB,
  affecting an existing cleanup-priority assertion. The tests now create/drop a
  per-run schema inside the explicitly selected *_test DB, preserving unrelated
  data; backend tests also force local/off storage defaults to avoid a developer's
  real provider configuration. The full suite passed with this isolation. Migration
  preservation is still exercised independently in dedicated test schemas.
- TypeScript, **15 upload + 8 auth/API + 7 export tests** and Android Hermes export
  passed (1,011 modules / 2.69 MB). Includes sealed-ack restart without retransmit,
  lost direct PUT reply recovery, expired capability preserving intent, forbidden
  insecure origin and no API credentials in storage requests. Native/network
  adapters are mocked; this is not a physical direct upload or APK validation.
- Real disposable local S3 smoke passed a partially disconnected PUT, API kill/
  restart, resumed 51 MiB source at byte 1,048,576, true expired-link rejection,
  same-key renewal, sealed-path/signed-length tamper denial, overwrite protection,
  checksum/rights preservation, one-job completion and actual render/download/decode.
  Physical upload/project prefix removal, local cleanup and zero owner reservation
  were checked. Output 1080×1920/30 fps/4.9 s. Final baseline flow 8.30 s includes
  the six-second signed-GET expiry wait; it excludes stress-source generation and
  direct transfer setup and is not a production speed/SLA claim. Ignored evidence:
  `.data/nextphase-s3-smoke-17243d3c0827/workflow/`.
- Backed up the isolated PostgreSQL application DB, rebuilt and applied migration
  0011; API/worker/S3/DB healthy. Integrated external HTTP direct resume/signature/
  render/download/deletion smoke passed (8.77 s baseline including expiry wait;
  external API not restarted). Operator read-back verified removed direct staging,
  project objects and manifest, retained grant tombstones and released budget.
- Normal local/API restart/resume/render/download/deletion smoke also passed on
  migration 0011: 1.91 s baseline, 1080×1920/30 fps/4.9 s, owner isolation and
  physical cleanup/budget release. Ignored synthetic evidence:
  `.data/smoke-45b7556abb534c4daf0f28d7936d172d/`. Doctor, pip and diff checks passed.
- Owner-reported prior merged object-storage/CI-fix acceptance (`1734c1c`): Windows
  dependencies/migration succeeded, **158 tests (109.20 s)** and full local smoke
  passed (2.20 s; `.data/smoke-572d1192c2534f0abf4374f5e0a0e67b`). Owner subsequently
  reported old/new Pixel upload/render/save/delete checks worked. S3 was explicitly
  off on that PC; these are owner reports of the prior local path, not direct QA.
- Upgrade and acceptance: [direct uploads](docs/DIRECT_UPLOADS.md). Stop services,
  back up DB/media, pull, migrate 0011 and update API/mobile together. No new pip/npm
  installation is required solely for this increment. Keep normal PC local/off;
  run the disposable Docker S3 smoke separately. Review/remote CI and physical
  direct Pixel/OS tests remain; no independent CI success or merge is claimed.
- Remaining Phase 2: production IAM/TLS/edge abuse/cost controls, fully stateless
  validation, broad provider compatibility, retention/orphan/version/account/backup
  erasure, verified auth delivery/recovery, robust broker/isolation, observability
  and representative load/soak. Later AI styles and payments stay disabled.

- Delivery: implementation `3311468` pushed to `dev/phase-2-direct-uploads`.
  GitHub GraphQL PR creation returned `Forbidden`; no PR was created or merged.
  Manual review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-direct-uploads

## CI follow-up — private S3 startup permissions

- Owner supplied a failing GitHub SQLite job: the pinned image pulled successfully,
  then the S3 readiness check exhausted retries. The supplied output did not include
  its server log; remote CI success is not claimed here.
- Found and reproduced a runner-dependent permission defect: the pinned image's
  entrypoint drops to seaweed UID 1000, but host-created 0600 config can belong to
  UID 1001 on GitHub. Verified UID-1001-owned 0600 data is unreadable to seaweed;
  copying into the private data directory and setting seaweed ownership restores
  access while retaining mode 0600. No broad secret permissions or privileged
  server workaround were introduced.
- Smoke startup now creates the container, copies its generated config into /data
  before start, and lets the official entrypoint assign data ownership. No host
  secret bind mount remains. Readiness reports only a safe error type/service code
  and detects early container exit. Failure prints redacted log tail; CI retains
  only sanitized server.log for three days, excluding credentials and workflow data.
- **158 backend tests passed on SQLite (31.68 s)**, including two new diagnostics
  privacy regressions (credentials, signed URL parameters, response-less connection
  errors and unsafe service messages). One existing Starlette/httpx warning.
  Full real S3 restart/resume/render/download/signature/expiry/physical-delete smoke
  passed with the corrected startup, 1080×1920/30 fps/4.9 s output; baseline 8.76 s
  includes the six-second signature expiry wait. Synthetic ignored evidence:
  `.data/nextphase-s3-smoke-f2a5bc37de52/workflow/`.
- No API/mobile/schema/dependency change. Prior PostgreSQL validation remains as
  recorded below; not rerun for this script/workflow-only correction. GitHub rerun
  must establish remote acceptance after this branch update. No paid services.

## Phase 2 increment — private S3 originals/results and signed downloads

- Optional `MEDIA_BACKEND=s3` stores validated originals and fenced rendered MP4s
  in an existing private S3-compatible bucket. Local remains default; no cloud
  account/bucket, paid API/infrastructure, AI, billing or subscription was activated.
  This is the first object-storage increment, not all Phase 2 work completed.
- Migration **0010_object_backend** retains existing jobs as local and adds a
  nullable namespace fingerprint for new remote jobs. Existing accounts, paths,
  rights records and pending upload offsets remain intact. A changed internal
  endpoint/bucket blocks reads/rendering/deletion rather than claiming empty
  replacement storage was erased. No automatic old-media migration is supplied.
- UUID-only keys, bounded SHA-256 uploads and full source download verification;
  FFmpeg receives local attempt scratch, never an S3/HTTP input URL. Validated
  output must be stored before DB claim-fenced success. API-mediated resumable
  ingestion remains; direct signed uploads and remote part staging are pending.
- Owner-authenticated streaming downloads preserve the mobile Save/Share contract
  and keep bearer credentials on the API origin. New owner-only POST download-link
  issues exact-key SigV4 GET capabilities for 5–60 s. Anonymous, other-owner and
  deleted-project API access are refused. Already-issued URLs remain valid until
  expiry or object removal, even after logout/tombstoning; downloaded/in-flight
  copies cannot be recalled. Signed URLs must not enter logs/analytics/public git.
- Deletion retries remove only the canonical remote project prefix and private
  staging/scratch. Partial/unavailable deletion or namespace mismatch retains the
  reservation and unset media_deleted_at. Versioned/suspended buckets are refused;
  version-aware erasure/retention is not implemented. Local inventory cannot infer
  unknown retained remote usage from an empty scratch directory.
- SDK: boto3 1.43.126 with seven total new installed Python records including its
  transitives. Inventory regenerated to **843** records; packaged LICENSE/NOTICE
  files preserved under docs/licenses/s3-sdk/. Local test server SeaweedFS 4.06 is
  digest-pinned; official Apache-2.0 notice preserved. This is metadata/notice review,
  not full OS/container/transitive, legal/patent or production clearance. No kit
  code/assets were copied. Mobile dependency graph unchanged; last known 17 npm
  findings remain unresolved, not freshly audited by this increment.
- Final backend checks: **156 tests on SQLite (28.04 s) and PostgreSQL (37.16 s)**,
  no skips; one existing Starlette/httpx warning each. Includes legacy/additive
  migration, remote fault/ownership/hash/byte bounds, cancellation during output
  publication, namespace-safe deletion, versioning refusal and unknown-usage guards.
  Mobile TypeScript and all **26 client tests** passed; mobile source/dependencies
  did not change, so no new native-device or APK/export claim. Doctor, pip check
  and whitespace checks passed. Remote CI was configured, not independently observed.
- Final disposable real S3 HTTP smoke passed API kill/restart, auth/revocation,
  interrupted 51 MiB upload/resume, acknowledgement/checksum/repeat-safe completion,
  stored originals, remote render publication, API download/full decode, signed GET,
  anonymous denial, forbidden PUT, signature tamper and actual five-second expiry.
  Deletion read-back confirmed the remote prefix empty plus scratch removal and
  reservation release. 1080×1920/30 fps/4.9 s output; workflow 7.90 s **including a
  six-second expiry wait**, not a performance benchmark. Ignored synthetic evidence:
  `.data/nextphase-s3-smoke-a8cb786b75fa/workflow/`.
- Default local-storage restart/resume/render/download/deletion smoke also passed
  on the finalized migration (baseline 1.71 s; 1080×1920/30 fps/4.9 s output),
  including physical cleanup and budget release. Ignored synthetic evidence:
  `.data/smoke-beae1d2063bc42ddadf072081b9137d0/`.
- Rebuilt the isolated PostgreSQL/SeaweedFS/API/worker stack after DB backup and
  applied finalized migration 0010. All services healthy; real integrated HTTP
  auth/resume/signed-link/render/download/deletion smoke passed (8.68 s including
  expiry wait; external API not restarted). Operator read-back verified both remote
  synthetic jobs' namespace, original/output objects, removed scratch, physical
  deletion, reservation release and preserved old local job metadata. No paid cloud.
- A validation run initially exhausted local Docker disk because the test server
  preallocated large volumes; no success was claimed for that failed run/build.
  Removed only the agent-created disposable server, bounded test volumes to 64 MiB
  (16 slots), added writable-object readiness and owned anonymous-volume cleanup,
  then reran successfully. Existing application volumes were preserved. The draft
  migration was finalized on disposable databases before publication; the validation
  application DB was restored from its pre-increment backup before the final upgrade.
- Owner-reported acceptance of the merged acknowledgement increment (`718ba14`):
  Windows migration passed, **142 tests (54.80 s)**, TypeScript and all **26 client
  tests** passed; restart/resume/acknowledgement/render/download/cleanup smoke passed
  (baseline 5.09 s; evidence `.data/smoke-3c2929a56ae042269b2d2cc0617426f8`). Owner
  subsequently reported all listed Pixel acknowledgement/reset/resume/discard and
  render/save checks worked. These are owner reports, not independent device runs.
- Upgrade commands, exact storage/signed-link/deletion boundaries and local Docker
  smoke: [private object storage](docs/PRIVATE_OBJECT_STORAGE.md). Stop services,
  back up DB/media, install updated Python requirements, migrate 0010, restart and
  recheck old/new projects. Keep the PC on default local mode unless S3 is explicitly
  configured. No mobile npm/native dependency or automatic production rollout.
- Remaining: direct signed uploads with immutable-part protection, fully remote
  staging/stateless workers, orphan reconciliation and full account/version/backup
  erasure; IAM/secret-manager policies, TLS/edge limits, production queue/isolation,
  representative load/soak and legal/provider review. No production cloud, broad
  compatibility/performance/SLA or full privacy compliance is claimed.

- Delivery: implementation `85dabde` pushed to `dev/phase-2-private-objects`.
  Automatic PR creation returned `Post https://api.github.com/graphql: Forbidden`;
  no PR was created, merged or deployed. Manual review link:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-private-objects

## Phase 2 increment — upload acknowledgement and bounded media profile

- Create Short now requires an explicit, initially unchecked rights and server-
  processing acknowledgement. Choosing another file resets it. Both upload APIs
  enforce `upload-rights-v1`; strict session JSON rejects false/string/numeric
  booleans. This records authenticated self-attestation, not verified ownership,
  legal clearance, consent from depicted people or permission for AI training.
- Additive migration **0009** records nullable version/server UTC receipt time on
  sessions and jobs. Historical records remain unknown; no fabricated backfill.
  Old paused intents require explicit reconfirmation while retaining their key,
  private copy and acknowledged offset. Replay preserves current receipt times.
- Discard works without asserting rights. Owner-key locking and a zero-byte,
  zero-budget aborted tombstone prevent a late creation from resurrecting an
  intent discarded before its session ID was saved. Stale screens cannot replace
  a newer pending intent. Network failure retains the private saved copy.
- FFprobe and FFmpeg now restrict demuxers, decoders and protocols to the documented
  baseline profile and file-only input. Validate actual container, one video,
  optional single audio track, pixel/rate/audio/stream limits; worker revalidates
  queued sources before rendering. Selected allocation/probe/thread limits apply.
  This is not antivirus, a filesystem sandbox or a total memory/disk quota.
  Real H.264/MP4, HEVC/MOV, VP9/WebM and AV1 render tests pass; a disguised remote
  playlist cannot contact the HTTP canary through probe or renderer. HDR/VFR and
  broad real-device codec/hostile-file coverage remain unverified.
- **142 backend tests passed on SQLite (27.76 s) and PostgreSQL (45.00 s)**,
  no skips, one existing Starlette/httpx deprecation warning each. Includes strict
  acknowledgements, preserved legacy migration data/progress, repeated completion,
  concurrent create/discard, owner isolation, media profile and prior regressions.
- TypeScript, **11 upload + 8 auth/API + 7 export logic tests** passed. Android
  Hermes export passed (1,011 modules / 2.69 MB). Native adapters are mocked in
  client tests; owner subsequently reported the Pixel checkbox/reconfirmation flow passed (see above).
  Pip dependency and diff checks passed. No dependency changes: inventory remains
  836 records; last audit remains 17 unresolved (4 high, 12 moderate, 1 low),
  not a fresh vulnerability scan or commercial dependency clearance.
- Real isolated HTTP smoke passed restart/auth/revocation, interrupted 51 MiB
  upload, checksum/offset and acknowledgement preservation, repeat-safe completion,
  queue/render/download/decode, deletion cleanup and reservation release. Output
  1080×1920, 30 fps, 4.9 s; baseline workflow 1.99 s. Synthetic ignored evidence:
  `.data/smoke-0fd5ca6c05584616bcd2fcfbe05c9dfc/`.
- Backed up the isolated PostgreSQL application DB; rebuilt local Compose images,
  applied migration 0009 and verified healthy API/worker/database. External HTTP
  smoke passed auth/resume/acknowledgement/render/download/deletion access controls
  against those services (2.66 s baseline). This external run did not restart the
  API or independently inspect container filesystem cleanup. No paid cloud deployed.
- Owner-reported acceptance of the previously merged Save/Share/storage increment:
  Windows 106 backend tests, complete smoke (3.95 s), TypeScript and 22 client
  tests passed; inventory found 23 records, zero unverified trees, no deletion.
  Owner reported all Pixel checks worked, including separate Save/Share. This is
  normal-flow acceptance; native denied-permission/OS-full errors remain untested.
- Upgrade: stop API/worker/Expo, back up DB/media, pull this increment, run migration
  0009 and restart updated API/mobile together. No additional inventory or package
  installation is required solely for this increment. Old upload clients receive
  422/409 until updated. Commands and device checklist:
  [upload consent and media guide](docs/UPLOAD_CONSENT_AND_MEDIA.md).
- Phase 2 remains open: broader device/error QA, security and
  licensing review, private object storage/production queue/deployment foundations,
  retention and capacity controls. AI styles, transcription, provider calls,
  subscriptions and paid infrastructure are not enabled. Next implementation scope
  must follow the roadmap and the owner's approval boundary for paid services.

- Delivery: implementation commit `8eb9db3` pushed on
  `dev/phase-2-consent-media`. Automatic PR creation returned GitHub GraphQL
  `Forbidden`; branch push succeeded. Review PR must be opened manually:
  https://github.com/Ngum12/NextPhase-Shorts/pull/new/dev/phase-2-consent-media

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
  is not a claim that this app reads the gallery. Owner subsequently reported normal Pixel Save/Share working (see above).
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

1. Review/merge local recovery and observe the new CI run. Stop API/workers,
   back up DB/media and migrate 0014 before restarting server/mobile.
2. Check disabled delivery copy and normal old/new project behavior. Optional
   disposable-account file QA is in AUTH_RECOVERY.md; it sends no email.
3. Keep real delivery disabled pending an approved provider/channel plan and
   production privacy/security review. Continue remaining Phase 2 refresh/MFA,
   broker/lease renewal, isolation/monitoring/capacity gates before later AI work.

No paid APIs, paid infrastructure, real billing or subscription collection were
activated. Heavy rendering remains on the server; no private keys were put in mobile.
