# License provenance and integration gates

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
