# Changelog

## Unreleased — Phase 2 queue controls

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
