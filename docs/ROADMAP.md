# Engineering work queue

The master contract in `prompt.md` owns phase order. Do not enable later paid
features or present planned styles as implemented.

| Priority | Work | Acceptance / dependency |
|---|---|---|
| P0, Phase 0/1 | Resolve mobile peers, lock dependencies, validate baseline, document audit | Automated checks and live smoke; tracked evidence in IMPLEMENTATION_STATUS.md |
| P0, Phase 1 remaining | Android device/emulator login/import/upload/poll/download/share | Consented or synthetic 5–10 s video; device/network/OS and evidence recorded |
| P0, release gate | Complete legal and license clearance | Per-source rights, exact versions, conditions, notices, owner/legal signoff |
| P1, Phase 2 | PostgreSQL migrations and fenced DB queue claims (this increment); submission idempotency/cancellation and bounded per-user concurrency added; full durable broker remains | Concurrent workers, idempotency, interruption/retry tests |
| P1, Phase 2 | DB session revocation, password change and shared auth limits implemented; verified recovery/email, refresh and upload resource controls remain | Owner-reported Pixel auth acceptance passed; delivery channel, edge limits, quotas and sandbox tests |
| P1, Phase 2 | Durable private-volume resumable sessions implemented; project deletion/private-volume cleanup implemented; opt-in S3 originals/results and signed GET links implemented; opt-in signed chunks/sealing implemented; account erasure and full retention remain | Ownership, interrupted uploads, deletion and retention tests |
| P1, Phase 2 | Attempt timings and aggregate P50/P95/optional cost calculation implemented; full observability/cost baseline remains | Realistic consented dataset, resource measurements, traces and bounded concurrency |
| Later, Phase 3+ | ASR/EDL/highlights then style engines | Follow master phase gates; provider consent, budgets and licensing first |
| Later, Phase 9+ | Billing and subscriptions | Explicit owner authorization, legal/store review and verified payment tests |

Save/Share separation and conservative per-account retained-media admission
budgets and owner-reported Pixel normal Save/Share acceptance are implemented; production disk/global
capacity/retention controls remain. See SAVE_AND_STORAGE.md.

Upload self-attestation records and restricted baseline media processing are
implemented. Verified rights/moderation, production sandbox/antivirus and broader
phone/HDR/VFR normalization remain. See UPLOAD_CONSENT_AND_MEDIA.md.

Private object storage first increment: API-mediated resumable ingestion to S3,
fenced remote results and expiring signed GETs. Signed remote chunks/sealing are opt-in; server assembly,
orphans/version-aware erasure and production provider deployment remain. See PRIVATE_OBJECT_STORAGE.md.

Direct chunk protocol and migration 0011: DIRECT_UPLOADS.md. Full provider/edge
controls, physical direct-phone acceptance and stateless validation remain.

Known upload expiry now uses bounded owner-locked maintenance. Preview-first offline
orphan/stale-attempt removal is implemented; online allocation-aware GC, saved-project
retention policy and full account/version/backup erasure remain. See RETENTION.md.

Account lifecycle increment: password-confirmed disablement, session/claim revocation,
durable local/S3 media cleanup and lost-response receipts. Full personal-data, backup
and version-aware erasure remains open; see ACCOUNT_DELETION.md.

Worker reliability now includes durable account-turn fairness, bounded recovery,
shutdown fencing, decoder containment and fail-closed Compose cgroup validation.
Broker/heartbeat, per-tenant sandboxing, enforced host caps, representative load/soak
and production acceptance remain open; see WORKER_RESILIENCE.md.

Operational visibility foundation: migration 0013 process-liveness pulses, minimal
DB/schema readiness, private aggregate queue/failure snapshot and structured worker
events. Job lease renewal, broker/watchdog, full tracing/exporters, alerts, metadata
retention and production load/security acceptance remain open. See OPERATIONS.md.
