# Changelog

## Unreleased — render attempt telemetry

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
