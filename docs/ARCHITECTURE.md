# Architecture — current versus proposed

## Current Stage 1 (functional starter)

Expo (Android / iOS) -> FastAPI (JWT auth, validated uploads, job listing, downloads)
                                      | PostgreSQL or local SQLite (metadata)
                                      | local volume (development only)
                       worker poller -> FFmpeg -> verified 1080x1920 MP4 (<=60 s)

**Truth in UI:** this is a standard baseline conversion from the first N seconds. Styles are listed as planned, not implemented. No AI, captions or subscriptions. Optional S3 originals/results and signed GETs
are now implemented; local remains the development default. API-mediated resumable
staging still needs a private volume; workers are not fully stateless yet.
See [storage boundaries](PRIVATE_OBJECT_STORAGE.md).

## Production target (Codex stages 2-12)

- Android/iOS: record/select; resumable upload; previews; editing request; progress; secure download; notification.
- API: auth, projects, ownership policies, upload sessions, subscriptions, quotas, receipts, deletion, admin, abuse controls.
- PostgreSQL transactional state; object storage with private buckets and expiring signed URLs; queue (Redis or durable alternative); metrics.
- Director: ASR with word timestamps, best-moment selection, semantic segments, safety, brand rules, rights-aware retrieval; validated JSON EDL.
- Scene modules: talking-head reframing, editorial graphics, 2D motion, optional 3D, captions, sound, brand identity.
- Rendering: isolated ephemeral workspaces, deterministic versions, cache scene renders, GPU/CPU benchmarks, async workers.
- Billing: server-verified payment events with entitlements. MoMo on compliant web flows; store billing for native digital purchases where required.

## Hard invariants

1. Final output is exactly vertical 1080x1920 in production, H.264/AAC MP4, <=60.0 seconds (small encoder tolerance allowed only in automated probing and must be fixed for export).
2. All CPU/GPU-intensive editing occurs on server workers, never via a video-processing SDK on phones.
3. No raw private API keys in Expo `EXPO_PUBLIC_*`, git, logs or client bundles.
4. Video access and outputs are owner-scoped; server rejects invalid media and never trusts user-supplied paths, URLs or AI-generated commands.
5. No production subscriptions or quotas until webhooks, store policies, invoices, refunds and entitlements have been independently tested.
6. Licenses for original uploaded skill packs are not automatically transferable for SaaS; don't bundle restricted code/assets.
