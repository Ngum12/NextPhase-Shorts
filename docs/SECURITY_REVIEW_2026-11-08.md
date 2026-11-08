# Package 5 dependency, licensing and privacy risk disposition — 2026-11-08

This is an engineering review and explicit launch gate, **not** owner/legal
acceptance of unresolved risks or a penetration-test certification. No restricted
reference ZIP code/assets, paid API, billing or real customer media was introduced.

## Current mobile remediation update

Package 6 preparation resolves the historical 17 npm findings with the SDK 58
upgrade and narrowly scoped, consumer-tested glob/minimatch patches. Clean install,
current audit (zero findings), TypeScript, app/tool tests, native config/fingerprint
and Android export passed. Physical SDK 58 acceptance remains pending. The owner's
package 5 updated strict hostcheck and actual render/save/playback passed.

The npm and old containment rows below record the earlier review state and are
superseded by this evidence; image/OS, post-snapshot journal, privacy/legal, real
staging/quotas/cost/collector and remote CI gates remain open. A zero advisory count
is not a risk waiver or a complete security/rights certification. See
[remaining gates and concrete resolution steps](STAGING_BLOCKERS.md).

## Reproducible review scope

- `npm --prefix apps/mobile audit --json`: current locked tree, 17 findings
  (4 high, 12 moderate, 1 low, no critical), includes affected parent packages.
  Query/route decoding remains potentially client reachable; do not call every
  finding development-only. No blanket `audit fix --force` or unsupported Expo
  major upgrade was applied.
- Official PyPI exact-version JSON published advisories checked for **52 installed
  Python distributions**; this is neither a full independent vulnerability feed
  nor OS/wheel/static/native dependency analysis. The initial pip 25.0.1 had known
  advisories. Development installer updated to **26.3**, Docker/CI install that
  exact version, and the version endpoint reports no published advisories for it.
  All 52 final checked versions report no published advisories in that source.
  Absence in one feed is not proof of security.
- Metadata inventory regenerated: **849** records, pip version updated; other
  runtime/mobile dependencies unchanged. Existing notices retained, pip MIT notice
  added. Full image/distro/FFmpeg codec/transitive-vendored SBOM, artifact provenance,
  complete vulnerability scan and distribution/source obligations are not cleared.
- Dynamic regression corpus includes auth/session/deletion/ownership, malformed
  media/remote-playlist denial, strict broker JSON/no pickle, file/path isolation,
  CPU/parent-death/process teardown, upload caps, concurrency/backpressure and
  metadata/privacy failures. This is a defined synthetic corpus, not all attacks.

## Unresolved risks and decisions

| Risk | Evidence / mitigation | Disposition before public launch |
|---|---|---|
| decode-uri-component <=0.5.0 via Router/query-string (high) | Installed 0.2.2; known CommonJS/ESM migration issue; original audit details in DEPENDENCY_SECURITY.md | BLOCK: supported SDK/router migration plus route/runtime/security tests; no waiver |
| image-size affected <=2.0.2 (high) via Metro | Installed 1.2.1; principally tooling/assets, not proof of no reachable untrusted entry | BLOCK: reviewed compatible Metro/SDK/toolchain remediation or demonstrated isolation with approved risk disposition |
| glob/minimatch (moderate) and affected parents | Major-version/API compatibility; no untrusted third-party build assets accepted | BLOCK: supported coordinated toolchain fix/validated mitigation before distribution/hosting |
| deepmerge >=4.2.0 (low) | Installed 4.3.1; no validated compatible fix here | OPEN: upstream/alternative review and explicit owner/security disposition; not silently accepted |
| Full OS/FFmpeg/wheel/container provenance and license obligations | Python/npm metadata and notices only; FFmpeg can include GPL codecs | BLOCK: immutable staging-image SBOM/patch/license/source-notice review, patent/legal advice where required |
| Shared-kernel containment | Required mode fails closed; owner host passed earlier; one-file output/cap needs updated supported-host render check | BLOCK until new host + actual render acceptance; not VM isolation |
| Global logical budgets vs physical/provider capacity | Shared locks/intake, free-space floor, finite decoder file access/size; S3/external writers/DB/edge distinct | BLOCK: staging quotas, connections/body/TLS/abuse limits and real cost/inventory reconciliation |
| Post-snapshot deletion/credential restoration | Independent encrypted local journal, protected DB stream binding and offline replay/release implemented/tested; all restored credentials require recovery | BLOCK: immutable/offsite current journal/checkpoint/key custody, encrypted backups, real target fencing/restore policy before real-data hosting |
| Personal/operational metadata retention | Trace/stopped-worker aging bounded; rights/cost/grant/tombstones and crash metadata retained | BLOCK: documented owner/legal policy and verified complete deletion/export scope; no full erasure claim |
| Mail/provider data and legal/store rights | Owner functional inbox acceptance; keys/default sending off; no private media sent to AI | BLOCK: provider terms/DPA/consent/privacy/terms and commercial/store signoff; no billing/AI enabled |
| Production throughput/availability | 100-request admission and ten-minute synthetic steady CPU soak/restore, not a production benchmark | OPEN staging gate: representative codecs/durations/slow networks, longer soak, restart/load/error budgets and approved ceiling |

The owner approved implementation work, not acceptance of these vulnerabilities
or legal risks. Package 5 supplies controls, evidence and risk disposition; Phase 2
and public staging/release cannot be declared complete while blocking gates remain.
Package 6 must carry them explicitly; no Phase 3 AI or public/paid deployment starts
merely because this branch is merged. Fresh audit artifacts are private generated
`.data/package5-audit/`; they contain public dependency metadata, not credentials.
