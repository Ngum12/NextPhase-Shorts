# Changelog

## Unreleased — Pixel validation follow-up

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
