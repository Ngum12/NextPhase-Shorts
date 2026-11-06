# Engineering work queue

The master contract in `prompt.md` owns phase order. Do not enable later paid
features or present planned styles as implemented.

| Priority | Work | Acceptance / dependency |
|---|---|---|
| P0, Phase 0/1 | Resolve mobile peers, lock dependencies, validate baseline, document audit | Automated checks and live smoke; tracked evidence in IMPLEMENTATION_STATUS.md |
| P0, Phase 1 remaining | Android device/emulator login/import/upload/poll/download/share | Consented or synthetic 5–10 s video; device/network/OS and evidence recorded |
| P0, release gate | Complete legal and license clearance | Per-source rights, exact versions, conditions, notices, owner/legal signoff |
| P1, Phase 2 | PostgreSQL migrations and fenced DB queue claims (this increment); submission idempotency/cancellation and bounded per-user concurrency added; full durable broker remains | Concurrent workers, idempotency, interruption/retry tests |
| P1, Phase 2 | DB session revocation, password change and shared auth limits implemented; verified recovery/email, refresh and upload resource controls remain | Native auth acceptance, delivery channel, edge limits, quotas and sandbox tests |
| P1, Phase 2 | Durable private-volume resumable sessions implemented; cloud object storage and full retention/deletion remain | Ownership, interrupted uploads, deletion and retention tests |
| P1, Phase 2 | Observability and cost baseline | Realistic consented dataset; P50/P95 timings and bounded concurrency |
| Later, Phase 3+ | ASR/EDL/highlights then style engines | Follow master phase gates; provider consent, budgets and licensing first |
| Later, Phase 9+ | Billing and subscriptions | Explicit owner authorization, legal/store review and verified payment tests |
