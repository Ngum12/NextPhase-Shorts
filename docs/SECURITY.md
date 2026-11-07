# Security / privacy — gating checklist, not completed certification

### What Stage 1 already does

- Revocable, DB-backed JWT bearer sessions with required issuer/audience/expiry, current/all-session logout and authenticated password change; salted scrypt passwords; user-owned job/download filtering.
- Shared atomic auth attempt windows with HMAC identity keys, generic failed-login responses and strict socket-peer selection. See [auth limits and remaining risks](AUTH_SESSIONS.md).
- UUID-based storage paths; fixed command arguments (no `shell=True`); FFprobe media validation.
- FFmpeg runs in a separate worker process / Docker service; production Docker worker uses unprivileged user.
- Upload size and format checks, output <= 60 seconds, env-based private JWT secret.
- Owner-only project deletion immediately revokes access/claims, with retryable
  private-volume cleanup; backups, account deletion and full retention remain open.
  See [deletion boundaries](PROJECT_DELETION.md).
- Conservative per-account source/render reservations and bounded accepted output
  files; global physical disk, spooling/orphan and production quota controls remain.
- Explicit versioned uploader attestation (not verified rights), restricted media
  profiles and file-only FFprobe/FFmpeg input protocols. Full antivirus/sandbox,
  rights verification and legal/privacy review remain open.
- Billing disabled, AI model disabled, no secret keys in app.

Migration-managed PostgreSQL, private-volume resumable uploads and shared auth
limits are implemented; they do not satisfy the remaining production controls.

### MUST implement before accepting real public traffic

- HTTPS/TLS, WAF/reverse proxy upload body limit, user/email verification, broader abuse/edge rate controls, optional MFA, verified account recovery and session refresh.
- Secret manager, signed short-lived object URLs, private cloud object storage, virus/decompression defenses, media fingerprint checks and limits on codecs, resolution and upload duration.
- Defense-in-depth resource limits (workers CPU/RAM/process time, quotas and isolation), SSRF/network egress restriction, sandbox no arbitrary execution from AI outputs.
- Media ownership/consent, rights verification, lawful content/misinformation handling, moderation, appeals and reporting mechanisms; do not build misleading impersonation/voice clones without permission.
- Data deletion, retention transparency, GDPR/other local privacy review, opt-in third-party AI sending, privacy policy, terms of service, backups and incident playbook.
- Auditable payment events, server-side verified webhooks, no browser-asserted payment success; idempotency, reconciliation, cancellations, refunds and chargeback handling.
- Logs cannot contain full customer videos, full ASR transcripts, personal payment information or secret tokens; least privilege and rotation.

**Important:** Stage 1 is a developer prototype, not production-hardened; don't expose it as-is to the public internet.

Optional S3 storage and exact-key expiring signed GETs are implemented; the default
remains local. API downloads keep bearer credentials on-origin. Signed links are
capabilities and cannot be recalled by logout or tombstoning alone; physical
removal/expiry limits them. Private bucket policy, TLS, log redaction, version-aware
erasure, orphan/lifecycle controls and provider isolation remain deployment gates.
See PRIVATE_OBJECT_STORAGE.md; never treat a successful bucket HEAD as privacy proof.

Opt-in direct PUT capabilities are exact-key/length/checksum scoped to temporary
incoming objects. The API rehashes and privately seals before acknowledging;
client capabilities never target verified parts or accepted media. Expiry-aware
terminal cleanup/rescans and three-source admission reservations limit retained
staging. Capability revocation, late writes, provider policies, abuse/load and
full account/backup erasure remain bounded as documented in DIRECT_UPLOADS.md.

Unknown-orphan deletion is offline-only with minimum 24-hour grace, DB/reference
protection, namespace-bound preview digest, bounded inventories and metadata
rechecks. It is not an online race-proof collector or automatic saved-project
expiry. See RETENTION.md for writer shutdown, backup and deletion boundaries.
