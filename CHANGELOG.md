# Changelog

## Windows SDK 58 tooling assertion fix

- Expect native path separators in async/sync glob tests and add focused Windows CI coverage. Application behavior and dependencies are unchanged.

## Phase 2 package 6 preparation — mobile security and staging evidence

- Upgrade to SDK-matched Expo 58 / RN 0.88 / React 19.3, adapt asynchronous file
  reads and explicit legacy Save API, retain bounded upload/pause recovery.
- Scope patched glob/minimatch to Expo consumers; clean audit drops 17 findings
  to zero, with tool/API/Android/config regression coverage and retained notices.
- Bind Docker API to loopback, add private read-only local image inventory, draft
  unpublished privacy/preview terms and map remaining staging approval/work gates.
- Record owner package 5 strict host/Pixel acceptance; no paid/public deployment,
  billing, mail or AI enabled. Phase 2 remains open pending real acceptance gates.

## Phase 2 package 5 — capacity, cleanup and security review

- Migration 0019 adds shared slot/storage/processing and in-flight intake budgets;
  bound API execution/body parsing, preserve replay/reservations and guard disk space.
- Narrow strict decoder writes to one file with kernel size cap; bound operational
  observation/stopped-worker retention and expose stale intake reservations.
- Prove 100 simultaneous admissions, ten-minute/98-cycle real soak and new-DB/media
  restore; add short CI drill. Pin reviewed pip installer 26.3 and retain notice.
- Record package 4 owner acceptance and explicit unresolved dependency/privacy/
  image/staging launch blockers; no paid service, billing, AI or public deployment.

## Phase 2 package 4 — monitoring, secrets and measured costs

- Migration 0018 preserves media/auth state and adds private observations, known
  artifact measurements and durable job trace correlation without historical guesses.
- Record stage timing, decoder CPU/RSS samples and transfer bytes; export bounded
  OTLP JSON/Prometheus text and evaluate private local queue/failure/cost alerts.
- Add mounted secret-file loading, rotation guidance and content-free request/error
  logging. Monetary estimates require explicit rates and disclose unknown coverage.
- Record owner-supplied package 3 host/Docker/Pixel acceptance after PR #22.
  No paid provider, billing, real mail, public metrics or automatic network exporter.

## Phase 2 package 3 — durable queue and worker supervision

- Add Valkey/Arq durable dispatch with transactional SQL signals, strict JSON,
  bounded reconciliation and duplicate/lost-response recovery.
- Migration 0017 adds renewable fenced leases, fixed hard deadlines and dead letters;
  preserve two-attempt budgets and delayed deletion safety for older writers.
- Add decoder filesystem/network guards, probe/render process-tree teardown, private
  configuration helper, queue supervisor and focused fail-closed host check.
- Verified 317 tests on each SQL backend, 63 mobile tests, TypeScript and real broker/
  S3 workflows. Strict host acceptance remains blocked on this managed kernel/runtime.
- Owner reports package 2 real email acceptance passed; sending remains opt-in.

## Phase 2 package 2 — optional Resend and verified email

- Migration 0016 adds an encrypted durable outbox, shared attempt budgets and
  action delivery-method tagging without promoting historical local proofs.
- Separate fenced sender with stable idempotency, bounded retries, private reports,
  payload/key lifecycle and password/reset/deletion cancellation.
- Opt-in server verified-email gate on upload routes and accurate mobile delivery/
  policy states; sign-in/recovery/deletion and existing-project reads remain open.
- Private Windows-friendly configuration helper leaves sending disabled. Existing
  smokes force real email off and include a separate mock-provider restart/crash proof.
- Added pinned cryptography and preserved notices/inventory. Actual provider/inbox/
  Pixel acceptance is pending; no real email, paid infrastructure or billing enabled.

## Phase 2 package 1 — rotating refresh sessions

- Migration 0015 preserves access-only sessions; new logins get short access
  tokens and opaque refresh families with idle/absolute expiry.
- Owner-locked rotation, bounded same-key recovery, committed family reuse
  revocation and logout/password/reset/account-deletion integration.
- SecureStore journal, single-flight refresh, generation guards, stable upload
  context and safe GET/native-download retry; writes require explicit retry.
- Fixed six-package checklist, HTTP restart proof and mobile refresh CI tests.
  No new dependency, paid service, email delivery or billing.

## Bounded retention maintenance and offline orphan preview

- Owner-locked, bounded upload expiration; existing terminal cleanup/budget rules retained.
- Preview-first offline collection of aged recognized orphans and unreferenced
  noncurrent terminal attempts, with DB/reference/link/namespace/digest protections.
- No automatic saved-project expiry, schema/dependency change or paid activation.

## Direct resumable storage uploads

- Opt-in signed temporary chunks with verified private sealing, restart-safe
  acknowledgement and bounded same-key renewal. Default API uploads preserved.
- Migration 0011, conservative three-source reservations and expiry-aware remote
  staging cleanup/rescans; mobile never sends API credentials to storage.
- No new dependency or paid infrastructure.

## Private object storage foundation

- Opt-in S3 originals and fenced results, bounded checksum-verified worker fetches,
  owner-only short-lived signed GETs and authenticated API streaming downloads.
- Migration 0010 preserves existing local jobs; retryable remote prefix deletion
  releases budgets only after success. Local remains default; no paid deployment.
- Real local-S3 signature/privacy/expiry/render/erasure smoke; direct signed uploads
  and full orphan/version/retention controls remain open.

## Unreleased — upload acknowledgement and media input hardening

- Add migration 0009 with nullable rights-version/time records; require new upload acknowledgement and copy it from sessions to jobs without inventing historical consent.
- Gate durable mobile preparation/transfer with an explicit per-file acknowledgement; reconfirm older saved intents without changing keys/offsets. Keep discard available without a rights assertion.
- Add owner-only session lookup by key and stale-intent guards for confirmation/resume/discard.
- Restrict FFprobe/FFmpeg protocols, demuxers/decoders, source metadata and selected resource paths; revalidate legacy queued sources before rendering.
- Test real supported codecs and a live network canary; record the owner's prior Pixel Save/Share acceptance.

## Phase 2 Save/Share and server storage budgets

- Separate native Save video to phone from Share video, with write-only permissions where required, explicit native save confirmation and no broad Android 13+ library read request.
- Add SDK-compatible MIT-declared Expo Media Library 18.2.1 and preserve its upstream notice.
- Add migration 0008, persistent per-upload/job storage reservations, owner-only usage reporting and offline legacy inventory; new uploads fail closed when usage is unverified/full.
- Reserve source plus two bounded render attempts, transfer once at completion and release only after media cleanup. Oversize exports fail instead of silently truncating.
- Add Account storage status and record owner-reported previous deletion acceptance.

## Phase 2 project deletion and media cleanup

- Add migration 0007 with durable owner-only deletion tombstones and retryable cleanup timestamps. Existing media/accounts are not deleted by migration.
- Hide deleted jobs, revoke active claims, block upload/key replay and scrub title/path/upload metadata; return 202 before physical cleanup, not an erasure claim.
- Retry/rescan UUID-derived project/staging trees without following symlink parents; defer active work past its prior lease.
- Add mobile destructive confirmation, explicit server acknowledgement, unavailable-project navigation and safe discard after remote deletion.
- Verify real synthetic download/deletion/replay denial and filesystem cleanup; record the owner's previous Pixel telemetry acceptance.

## Phase 2 render attempt telemetry

- Add migration 0006 and transactionally recorded attempt start/completion/loss/cancellation with monotonic observed render time and successful output bytes.
- Add private operator aggregate report with sample-counted P50/P95, unknown/truncated coverage and optional decimal wall-time cost estimates; no provider calls or billing.
- Preserve retry fencing and redact raw unexpected-worker exception details. Extend real render smoke to verify durable measurements.
- Record owner-reported Windows/Pixel acceptance of the previous auth increment.

## Phase 2 revocable authentication sessions

- Add migration 0005 for persistent session revocation and shared atomic auth-rate windows.
- Add current/all-session logout and authenticated password changes; retain existing accounts, jobs and pending uploads. Existing tokens require one new sign-in.
- Add mobile account security controls, startup validation and stale-response-safe credential handling.
- Disable implicit proxy-header trust in documented/container launches; test API-restart persistence and password/session races. Verified email/reset/refresh remain pending.
- Record owner-reported Pixel acceptance of the previous resumable upload increment.

## Phase 2 durable resumable uploads

- Add migration 0004, owner-scoped session creation/progress/parts/completion/abort, per-part/full-source checksums and shared queue reservations.
- Persist verified chunks across API restarts, make completion repeat-safe, bound chunk receive time and clean terminal/expired staging data.
- Add mobile private-copy/journal recovery, acknowledged-byte progress, Pause/Resume/Discard and SDK-compatible Expo Crypto.
- Test real partial disconnect/API kill/restart/resume/render, concurrent completions, and client recovery with simulated native adapters. The owner later reported physical Pixel checks passed; new auth controls still require device acceptance.

## Phase 2 queue controls

- Add owner-scoped, fingerprinted upload idempotency keys and additive migration 0003.
- Add owner-only queued/processing cancellation, cooperative FFmpeg termination and mobile cancel/retry controls.
- Enforce configurable per-user active/processing limits under short owner-row locks; preserve replay at capacity.
- Extend SQLite/PostgreSQL process-race tests and real HTTP cancellation/replay smoke checks. Phase 2 remains in progress.

## Phase 2 migrations and worker claims

- Add explicit Alembic baseline/lease migrations, checked legacy adoption and startup version checks; keep completed job downloads compatible.
- Add atomic claims, UUID lease fencing, attempt-specific output files and bounded expired-attempt recovery.
- Require PostgreSQL for staging/production; run one-shot migrations before Compose API/worker startup.
- Test migration preservation, concurrent claimant processes, crashes/stale attempts and both SQLite/PostgreSQL; Phase 2 remains in progress.

## Pixel validation follow-up

- Record owner-reported Pixel upload/render/download success over USB and document SDK 54 Expo Go setup.
- Apply top safe-area insets to headerless screens and use light status-bar icons; keep stack-header insets separate.
- Pin PostCSS 8.5.32 via npm override; reduce audit findings from 18 to 17 while preserving Expo SDK 54. Remaining 17 findings are unresolved.

## Phase 0/1 validation

- Align React Native with Expo SDK 54, pin matching React DOM, commit npm lockfile and use npm ci in mobile CI.
- Add isolated live HTTP/worker/render/download smoke command and regression coverage for upload boundaries, auth, worker errors/retries and the full 60-second cap.
- Fix container source permissions for the unprivileged user, add API health/readiness ordering, and support an optional build-time proxy CA secret without weakening pip TLS verification.
- Clarify preview UI copy; document architecture decision, threat model, dependency metadata and remaining phase gates.

## 0.1.0 — 2026-11-06

- Initial original NextPhase Shorts developer scaffold.
- Added developer-oriented FastAPI server, PostgreSQL/local SQLite, FFmpeg worker, Expo mobile screens, backend API tests, docs/ and a full Codex `prompt.md` for phased product delivery.
- No production AI, subscription billing, commercial deployment or redistribution of uploaded skill packs.

## Account deletion increment (2026-11-07)

- Password-confirmed account disablement and immediate session/claim revocation.
- Durable owner-scoped media cleanup and expiring lost-response recovery receipts.
- Mobile confirmation/recovery; migration 0012 required. Full backup erasure excluded.

## Worker resilience increment (2026-11-07)

- Rotate eligible accounts by durable last-claim history; bound expired-job recovery.
- Fence shutdown, retry database outages, and contain Linux decoder child lifetimes.
- Reduce decoder environments and enforce a guarded Docker resource profile.
- Add disposable crash/restart/render proof and bounded 100-submission queue test.
- No migration or dependency changes; strict Docker runtime acceptance required.

## Windows worker smoke cleanup fix

- Dispose the helper's pooled SQLite handles before temporary-directory cleanup,
  including failure paths; report success only after cleanup completes.
- No application behavior, schema, dependency or resource-limit change.

## CI process-exit observation fix

- Treat procfs ENOENT and ESRCH as exited processes in Linux containment tests.
- Wait for complete child-marker JSON; keep live-process and unexpected-error
  assertions intact. No application or deployment behavior changes.

## Operational visibility increment (2026-11-07)

- Add migration 0013 and independent worker heartbeat records without lease renewal.
- Add minimal DB/schema readiness and private queue/failure/worker operator reports.
- Add allowlisted JSON worker events and live/shutdown/expired-claim smoke checks.
- No dependency, mobile, paid-service or billing change.

## Local authentication recovery increment (2026-11-08)

- Add migration 0014, local proof metadata and one-use credential-bound email actions.
- Add disabled-by-default private development inbox; no email provider activated.
- Add mobile Forgot password/local email proof screens and sanitized auth validation.
- Reset/change/delete revoke pending proofs; reset revokes all account sessions.
- No dependency, paid-service or real email-owner verification/enforcement change.
