# ADR 0001: Validate the original server-rendered baseline

Date: 2026-11-06. Status: accepted for local development.

Keep Expo SDK 54 with React 19.1, SDK-compatible React Native 0.81.5,
and matching React DOM 19.1 to resolve Expo Router's optional peer graph.
Commit npm's lockfile and use `npm ci` in CI. Do not use legacy peer resolution.

Use FastAPI and a separate polling worker with system FFmpeg; SQLite is a
single-worker local option, PostgreSQL is the Compose option. Phones only select,
upload, poll and download/share. Every style uses the same first-seconds baseline.
The renderer validates 1080x1920 and a strict <=60-second/requested-cap export.
AI and billing remain disabled; no paid services are required.

Consequences: this proves baseline functionality, not production readiness.
SQLite does not provide PostgreSQL's SKIP LOCKED worker coordination. Queue leases,
migrations, cancellation, object storage, rate limits and account lifecycle remain
Phase 2 work. Dependency metadata is an inventory, not a commercial license signoff.
