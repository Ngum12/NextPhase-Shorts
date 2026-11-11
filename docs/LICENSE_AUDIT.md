# License provenance and integration gates

## Optional local analysis pilot — 2026-11-11

The independently authored pilot can invoke upstream **Whisper.cpp v1.7.6**,
commit `a8d002cfd879315632a579e73f0148d06959de36`, MIT. Source:
https://github.com/ggml-org/whisper.cpp/tree/a8d002cfd879315632a579e73f0148d06959de36 .
Its root MIT notice is preserved verbatim under `licenses/whisper-cpp-v1.7.6/`.
The engine was compiled outside the checkout; no native executable, ggml source,
model weights, upstream sample media, restricted reference kit or font is bundled.
Retain applicable native/source notices if distributing a build; a root MIT
notice is not a full system/transitive/model/patent/security/legal clearance.

Optional local build tool **cmake Python distribution 3.31.6** declares Apache 2.0
metadata and packages Apache-2.0/BSD-3 notices for its distribution/CMake content.
Source: https://pypi.org/project/cmake/3.31.6/ . It was installed in the cloud
development venv for compilation and is not added as an application runtime
dependency. See `analysis-pilot-dependencies.json` for the scoped record.
No model artifact was downloaded because outbound policy blocks its host; model
origin/digest/license review and actual speech-quality tests remain pending.
Fixture annotations and FFmpeg test patterns/tone are originally authored;
they are not consented real-speech benchmark evidence or proof of ASR accuracy.

## Private VPS preparation — 2026-11-10

No dependency, third-party image/version, reference-kit code, media, model or font
added. The trial overlay reuses existing reviewed image references; preparation
and acceptance code is independently authored using Python's standard library
and the existing HTTP smoke. Existing notices and full OS/transitive/codec/legal
review gates remain. No provider contract, paid resource or public deployment
was activated by this preparation.

IMPORTANT: This starter repository is newly authored scaffolding. It deliberately does **not** redistribute user-provided ZIP skill packs, fonts, clips, sample media, source code or branded assets.

Three uploaded reference materials reviewed, not included here:

1. `NextPhase-EditorV1.zip`: `LICENSE-NOTES.md` permits creation of commercial videos but explicitly asks that the kit not be resold or repackaged as a paid product. **Stop: Do not copy/redistribute/host this kit inside a paid SaaS without written permission and legal review.** Independently implement functionality based on lawful general concepts instead.
2. `Carousel-Kit (4).zip`: static carousel design; no unambiguous blanket commercial reuse grant for its own code/assets identified. Request license or implement own layouts. 4:5 source aspect ratios must be redesigned for 9:16.
3. `motion-carousels-skill.zip`: top-level `LICENSES.md` describes permissive usage of skill code/examples and third-party licenses, but no unambiguous standard license for all content. Confirm author rights, image rights, model/tool API usage and suitability for commercial SaaS before copying. 4:5 scenes need 9:16 re-layout. Specific 3D examples show paid third-party asset credits; do not use these demo visuals in the app.

Third-party audit before every merge: name, source URL, exact version, license URL, distribution/hosting conditions, commercial SaaS rights, transitive dependencies, sample media rights, attribution, data license, any copyleft constraints, maintainer approval. Store machine-readable SBOM/license inventory.

Never imply public footage/images are automatically licensed because they are searchable. Require a license manifest per B-roll asset: source, owner, license, attribution, expiry, consent, approved usage, cache retention.

## Migration dependency additions (metadata review)

This increment adds Alembic 1.20.1 (declared MIT), Mako 1.4.3 (declared MIT) and
MarkupSafe 3.0.4 (declared BSD-3-Clause) in the tested environment. Sources and
installed license locations are in `dependency-inventory.json` (834 records).
These metadata licenses permit broad commercial use subject to their notice and
license conditions; maintain the required notices in distributions. This records
metadata review, not independent legal clearance or a full transitive audit.
No reference ZIP code/assets or media were introduced.

## Resumable upload dependency (metadata review)

Expo Crypto 15.0.9 is SDK-matched and declares MIT; source:
https://www.npmjs.com/package/expo-crypto/v/15.0.9 . Preserve the package's MIT
license/notice with distributions. It supplies local native hashing/UUIDs, not a
paid service. The regenerated inventory has 835 records. This is metadata review;
commercial legal signoff and the remaining dependency advisories are not cleared.
No proprietary reference kit code or assets were used.

## Authentication session increment

No dependency, reference-kit code, media or third-party service was added. Existing
835-record dependency inventory and unresolved audit findings remain applicable;
this auth change does not confer additional licensing or production clearance.

## Render telemetry increment

No dependencies, third-party assets or reference-kit code were added. The existing
835-record inventory and unresolved commercial clearance/advisory gates still apply.

## Project deletion increment

No dependencies, third-party media or reference-kit assets were added. The existing
835-record inventory and unresolved legal/security dependency gates remain applicable.

## Save/Share native dependency

Added SDK-compatible expo-media-library 18.2.1, declared MIT in its installed npm
metadata: https://www.npmjs.com/package/expo-media-library/v/18.2.1 . Its package
archive omits a standalone LICENSE file; the official SDK 54 upstream license was
retrieved from https://raw.githubusercontent.com/expo/expo/sdk-54/LICENSE and is
preserved verbatim at `docs/licenses/expo-sdk54-MIT.txt` (650 Industries/Expo).
MIT permits commercial use subject to preserving copyright/permission notices;
include the notice in distributions. Inventory now has 836 records. This review
covers this dependency's declared license and upstream notice, not full transitive,
OS/container, commercial-policy or privacy clearance. No proprietary kit assets,
fonts, music or video were added. Paid services and billing remain disabled.

## Upload acknowledgement/media hardening increment

No dependency or reference-kit asset was added. Codec tests use the existing
FFmpeg installation and do not imply codec/patent clearance. The uploader statement
is self-attestation, not rights verification or a substitute for a rights manifest.
The 836-record inventory and unresolved legal/security gates remain applicable.

## Private object storage first increment

Added boto3 1.43.126 (Apache-2.0) pinned in requirements. Installed transitive
versions: botocore 1.43.126 (Apache-2.0), s3transfer 0.19.3 (Apache-2.0), jmespath
1.1.0 (MIT), python-dateutil 2.9.0.post0 (dual Apache-2.0/BSD terms; see full notice),
six 1.17.0 (MIT), urllib3 2.8.0 (MIT). Exact sources/metadata are inventoried in
`dependency-inventory.json` (843 records). Required packaged LICENSE/NOTICE files
are copied verbatim under `docs/licenses/s3-sdk/`; preserve these in distributions.
Sources are the corresponding official PyPI project/version records. This is
notice/metadata review, not full legal/security clearance or a frozen Python lock.

The disposable development test uses SeaweedFS 4.06, upstream
https://github.com/seaweedfs/seaweedfs/tree/4.06 , Apache-2.0 license retrieved from
https://raw.githubusercontent.com/seaweedfs/seaweedfs/4.06/LICENSE and preserved at
`docs/licenses/seaweedfs-4.06-Apache-2.0.txt`. Test image:
`chrislusf/seaweedfs:4.06@sha256:a064c6923daf4451c943cec2f437a67523d7792ee589089bc4d4c27a61d78dea`.
Apache-2.0 permits commercial use subject to its license/notice conditions. This
records the upstream project license, not a complete OS/container/transitive SBOM,
patent clearance, cloud-provider terms approval or production hosting decision.
No proprietary reference kit/media, paid provider or billing activation was added.

## CI diagnostic artifact action

Official actions/upload-artifact v4.6.2 is pinned to commit
`ea165f8d65b6e75b540449e92b4886f43607fa02` for sanitized failure logs only. Its
MIT notice was retrieved from the exact upstream commit's LICENSE and preserved
at docs/licenses/actions-upload-artifact-v4.6.2.txt. Source:
https://github.com/actions/upload-artifact/tree/ea165f8d65b6e75b540449e92b4886f43607fa02 .
This is a CI tool, outside the Python/npm inventory scope; no runtime dependency
or proprietary kit code was added. Metadata/notice review is not legal clearance.

## Direct upload increment

No dependency, third-party asset or reference-kit code was introduced. The existing
843-record inventory, preserved SDK/server/action notices and unresolved legal/
security gates remain applicable. Tests use synthetic media and the existing
local S3 service; signed requests do not activate a paid provider or clear rights.

## Retention/orphan-cleanup increment

No dependency, reference-kit source, asset or paid provider was added. The existing
843-record metadata inventory and licensing/security gates remain applicable.
Synthetic local/S3 fixtures are original test data; no real footage is committed.

## Account deletion increment

No dependency, reference-kit code, asset, paid provider or billing integration added.
The existing 843-record metadata inventory and unresolved licensing/security gates
remain applicable. Validation uses original synthetic media only.

## Worker resilience increment

No dependency, reference-kit code, media asset or paid provider added. Linux process
controls use Python standard library/system interfaces and the existing FFmpeg.
Existing 843-record inventory and unresolved legal/security gates remain applicable.

## Operational visibility increment

No dependency, reference-kit code, media asset or external monitoring provider added.
Existing 843-record metadata inventory and unresolved legal/security/advisory gates
remain applicable. SQLite/PostgreSQL and original synthetic fixtures are used for QA.

## Local authentication recovery increment

No dependency, reference-kit source/asset or email provider added. Proofs use the
existing Python cryptographic/password/database stack and native UI components.
Existing 843-record inventory and unresolved legal/security/advisory gates remain.

## Phase 2 package 1 — session refresh

No dependency, native module, reference-kit source/asset or paid service added.
Uses existing Python HMAC/JWT/DB stack and Expo SecureStore/Crypto. Existing
843-record inventory, notices and unresolved licensing/advisory gates remain;
no new commercial legal clearance is claimed.

## Phase 2 package 2 — authenticated outbox encryption

Added cryptography **50.0.2** (declared `Apache-2.0 OR BSD-3-Clause`), installed
transitives cffi **2.1.1** (`MIT-0`) and pycparser **3.12** (`BSD-3-Clause`). Sources:
https://pypi.org/project/cryptography/50.0.2/ ,
https://pypi.org/project/cffi/2.1.1/ , https://pypi.org/project/pycparser/3.12/ .
Exact packaged LICENSE/Apache/BSD notices are preserved verbatim under
`docs/licenses/mail-crypto/<package-version>/`; installed license metadata is in
the regenerated **846-record** inventory. Retain applicable copyright/license
notices in distributions. This is upstream metadata/notice review, not independent
legal clearance, a full bundled OpenSSL/Rust/OS audit or dependency-security signoff.

Resend transport uses existing httpx; no Resend SDK or reference-kit code/assets
were added. Provider terms, privacy/DPA/subprocessors, current plan/Forge behavior
and sender-owner approval remain real-channel acceptance gates; local transport
fixtures do not establish these. No provider request, outgoing real email, paid
resource/API or billing activation was performed during automated validation.

## Phase 2 package 3 — durable dispatch and decoder containment

Added Arq **0.28.0**, redis-py **5.3.1** and hiredis **3.5.0**, all declaring MIT.
Sources: https://pypi.org/project/arq/0.28.0/ ,
https://pypi.org/project/redis/5.3.1/ , https://pypi.org/project/hiredis/3.5.0/ .
Exact packaged notices are preserved under `docs/licenses/queue/`; retain copyright
and permission notices in distributions. Inventory now has **849** metadata records.
redis-py is a client library; no Redis server distribution/license was introduced.

The local broker is Valkey **8.1.11**, BSD-3-Clause, pinned image
`valkey/valkey:8.1-alpine@sha256:2602ace2be6569bc2bbb06f873776516ab9089821525be34f4305c67eb9db02a`.
Source/notice: https://github.com/valkey-io/valkey/tree/8.1.11 and
https://raw.githubusercontent.com/valkey-io/valkey/8.1.11/COPYING . Full upstream
COPYING is preserved at `docs/licenses/queue/valkey-8.1.11-BSD-3-Clause.txt`.
BSD permits commercial use subject to its copyright/notice/disclaimer and
non-endorsement conditions. This is metadata/upstream notice review, not a full
OS/image/transitive audit, security certification or production/legal signoff.

Landlock/seccomp use standard Linux interfaces and Python ctypes; no external
sandbox code, restricted reference-kit source/assets or paid provider added.
Shared-kernel/kernel-version/host acceptance and existing legal/advisory gates remain.

## Phase 2 package 4 — private observations and mounted secrets

No runtime/native dependency, external collector, secret-manager provider, paid
service, reference-kit code or media asset was added. OTLP JSON and Prometheus
text mappings are independently authored from their public protocol conventions;
no SDK/collector image was incorporated. Existing 849-record dependency inventory,
notices and unresolved OS/transitive/security/legal gates remain. Protocol-shaped
export is not an external collector, commercial-policy or privacy signoff.

## Phase 2 package 5 — capacity/security review

No application dependency or restricted reference-kit code/assets added. Build/CI
installer pip is now pinned to **26.3** (MIT), source
https://pypi.org/project/pip/26.3/ . Its packaged MIT notice is preserved at
`docs/licenses/pip-26.3/LICENSE.txt`; wheel/image installations retain upstream
vendored notices as supplied. Existing 849-record metadata inventory regenerated
for this installer update. This is not a full OS/vendored/FFmpeg GPL/patent or
commercial legal clearance. See SECURITY_REVIEW_2026-11-08.md for explicit blockers;
no public release/risk waiver is inferred from this review. Synthetic load/restore
media is independently generated; no customer footage or backup enters Git.

## Phase 2 package 6 preparation — SDK 58 mobile graph

Expo 58.0.23 / Router 58.0.30 / SDK-matched modules, React 19.3.0, React Native
0.88.1 and declared native peers replace SDK 54. Direct/framework declarations
are primarily MIT; scoped patched glob 14.0.4 and minimatch 11.0.5 declare
BlueOak-1.0.0 (read their full packaged notices/source terms). Packaged notices
for 29 direct/framework/tool/asset records are indexed at `docs/licenses/sdk58-index.json`
and retained under `docs/licenses/sdk58/`. Official Expo SDK 58 MIT root notice
was retrieved from https://raw.githubusercontent.com/expo/expo/sdk-58/LICENSE and
preserved at `docs/licenses/expo-sdk58-MIT.txt` for @expo/ui/Router archives that
omit standalone root notices. Preserve the applicable notices in distributions.

Metadata inventory now has **615** locked/installed records. No reference-kit
source/assets, paid provider, billing or AI integration added. This is metadata/
notice review, not independent legal approval or complete transitive/OS/native
redistribution/source/codec/patent clearance. The read-only image inventory helper
reports installed versions/copyright hashes, not a vulnerability or legal signoff.

Android export also bundles Material Symbols 400 Regular through Expo Router:
`@expo-google-fonts/material-symbols` **0.4.53**, declared **MIT AND Apache-2.0**.
Its packaged wrapper LICENSE and complete LICENSE_FONT are preserved under
`docs/licenses/sdk58/`; the asset path/SHA-256/source are recorded in the index.
Apache-2.0 permits commercial font use subject to its notice/license conditions;
this unmodified navigation font is not copied from a reference kit or used by the
server video renderer. React Navigation Elements' MIT notice is also retained for
bundled navigation assets. No proprietary stock video/music/font was introduced.


## Independent restore journal increment

No dependency, reference-kit code/media/font, paid provider or license change.
Journal encryption uses the already inventoried cryptography 50.0.2 Fernet API;
HMAC/fsync/flock and snapshot fixtures use standard Python/Linux/PostgreSQL tools.
Existing notices and unresolved full OS/transitive/codec/legal gates remain.


## Consolidated private staging tool

Added **Caddy 2.11.9**, upstream https://github.com/caddyserver/caddy/tree/v2.11.9 ,
Apache-2.0. Official release archive LICENSE is preserved verbatim at
`docs/licenses/caddy-2.11.9-LICENSE.txt`; official archive SHA-512 checksums at
`deploy/private-staging/caddy-2.11.9-checksums.txt`. Linux amd64 archive checksum
was verified before native execution. Docker reference is pinned to
`caddy:2.11.9-alpine@sha256:0bbb055bda6793c999bde78b1b5ce3e89f829fb031af2cf50056ea1246559fee`.
Retain license/notices with redistribution. This covers the upstream project
notice, not full Go/Alpine/image/native/transitive license or vulnerability clearance.

All Python additions use existing cryptography/HTTP/ASGI/database dependencies;
no new Python/npm dependency or reference-kit source/media/font was introduced.
Local certificate/backup keys are generated, private and never included in Git.
No paid service, provider contract, billing, AI or public certificate was activated.
