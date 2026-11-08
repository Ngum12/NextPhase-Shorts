# Fixed remaining Phase 2 checklist

Agreed with the owner on 2026-11-08. These six packages consolidate the remaining
`prompt.md` Phase 2 requirements. Work in order, one coherent review per package;
automate repeated regressions and request focused device checks where needed.
An external blocker remains visible and must be resolved before Phase 2 closes.

| Order | Package | Completion evidence | Status |
|---|---|---|---|
| 1 | Session refresh | Short access lifetime; opaque rotation; replay revocation; durable lost-response recovery; logout/reset/deletion; secure mobile storage; DB/HTTP restart/device tests | Merged f200dc3; automated local tests passed; owner reports all focused Pixel checks passed; remote CI observation blocked by GitHub API Forbidden |
| 2 | Real email verification/recovery | Approved channel, durable outbox/retries, safe delivery/cleanup, verified ownership policy and delivery-failure acceptance | Merged 06e5c86; owner reports real inbox/verification/reset/new-password/upload/render/save checks passed and sending disabled again; CI/privacy/provider-terms observation remains separate |
| 3 | Queue/worker reliability | Robust durable queue implementation, confirmed completion/ACK, retries/dead-letter/cancellation/fairness, supervision/leases, enforced CPU/RAM/PID limits and tenant isolation/egress | Merged PR #22 (017bf20); owner supplied ready:true for all host protections, healthy Docker stack/operations and confirmed Pixel render/save/playback; managed cloud host still unsupported, remote CI unobserved |
| 4 | Monitoring/secrets/costs | Trace correlation and OpenTelemetry-compatible export, resource/stage metrics, alerts/redaction, secret management/rotation, measured compute/storage/egress cost coverage | Merged PR #23 (4c565b0); owner supplied healthy monitoring/new measured render and confirmed Pixel save/playback; external collector/vault/provider-cost reconciliation explicitly pending staging acceptance |
| 5 | Capacity/cleanup/security | Global admission/storage, retention/erasure scope, tested backup restoration, 100 concurrent submissions and representative soak/security checks, dependency/license/privacy review and risk disposition | Merged PR #24 (82f1ab1); owner supplied updated ready:true/healthy capacity report and confirmed Pixel Save/playback; historical 100-request/ten-minute/restore evidence retained; remaining privacy/legal/image/staging gates explicit |
| 6 | Staging acceptance | PostgreSQL, private storage/signed access, HTTPS/edge limits, separated constrained workers, complete device-to-server-to-save flow, capacity/cost ceiling, runbooks/signoff | Preparation in review: SDK 58 graph/audit zero, 66 tests and Android/config checks; image inventory/drafts/private binding prepared. Native SDK 58, journal, TLS/edge/provider runtime/cost/collector/legal/CI gates remain OPEN; paid infrastructure needs approval |

## Definition of done

Implement all package criteria, run relevant tests and automated regressions,
record evidence/blockers in `IMPLEMENTATION_STATUS.md`, submit one review branch,
and complete focused device checks where needed. A merge alone is not production
or device acceptance. Do not mark blocked criteria complete or skip them silently.
Phase 2 closes when all six gates pass; Phase 3 AI work starts afterward.

No paid APIs/infrastructure, email sending or real billing may be activated without
the required owner approval. Local adapters are not production proof. Throughout:
9:16 output <=60 seconds, intensive processing on the server, licensed assets and
privacy/security gates. No reference ZIP assets/code are introduced.
