# Security / privacy — gating checklist, not completed certification

### What Stage 1 already does

- JWT bearer authentication; password salted scrypt (not plain text); user-owned job/download filtering.
- UUID-based storage paths; fixed command arguments (no `shell=True`); FFprobe media validation.
- FFmpeg runs in a separate worker process / Docker service; production Docker worker uses unprivileged user.
- Upload size and format checks, output <= 60 seconds, env-based private JWT secret.
- Billing disabled, AI model disabled, no secret keys in app.

### MUST implement before accepting real public traffic

- HTTPS/TLS, WAF/reverse proxy upload body limit, user/email verification, login throttling, abuse controls, optional MFA, rate limits, secure account recovery.
- Database migrations, secret manager, signed short-lived object URLs, private object storage, multipart resumable uploads, virus/decompression defenses, media fingerprint checks and limits on codecs, resolution and upload duration.
- Defense-in-depth resource limits (workers CPU/RAM/process time, quotas and isolation), SSRF/network egress restriction, sandbox no arbitrary execution from AI outputs.
- Media ownership/consent, rights verification, lawful content/misinformation handling, moderation, appeals and reporting mechanisms; do not build misleading impersonation/voice clones without permission.
- Data deletion, retention transparency, GDPR/other local privacy review, opt-in third-party AI sending, privacy policy, terms of service, backups and incident playbook.
- Auditable payment events, server-side verified webhooks, no browser-asserted payment success; idempotency, reconciliation, cancellations, refunds and chargeback handling.
- Logs cannot contain full customer videos, full ASR transcripts, personal payment information or secret tokens; least privilege and rotation.

**Important:** Stage 1 is a developer prototype, not production-hardened; don't expose it as-is to the public internet.
