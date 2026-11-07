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
