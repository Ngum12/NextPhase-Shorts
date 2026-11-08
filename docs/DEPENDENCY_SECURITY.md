# Current resolution — Expo SDK 58, 2026-11-08

The reviewed branch upgrades the SDK-matched mobile graph to Expo 58.0.23,
Router 58.0.30, RN 0.88.1 and React 19.3.0. Narrow consumer-scoped glob 14.0.4 /
minimatch 11.0.5 overrides and the existing PostCSS patch remove the remaining
upstream tool chains. **Clean npm ci + current npm audit: zero findings.**
Actual Expo config/fingerprint/Android export and dedicated consumer/API regressions
pass; SDK 58 Pixel acceptance and complete image/legal/security review remain open.
This supersedes the historical unresolved counts below, not the legal/privacy gates.
See [exact override scope, tests and upgrade](STAGING_BLOCKERS.md).

# Mobile dependency security follow-up — 2026-11-06

## Measured change

`npm audit --json` on merged main reported 18 findings: 5 high, 12 moderate,
1 low. With only the PostCSS override and lockfile update it reports **17**:
4 high, 12 moderate, 1 low. These counts include affected parent packages and
are not 17 independently demonstrated application exploits.

The installed Expo Metro config pins PostCSS 8.4.49. A root npm override selects
**PostCSS 8.5.32**, within the same major version, outside the advisory range
`<=8.5.22`. It clears the PostCSS finding (source map disclosure / stringify XSS).
This project keeps Expo 54.0.38, Router 6.0.24, React Native 0.81.5 and React 19.1.
Do not run `npm audit fix --force` to silence these findings: it proposes SDK
changes and can even propose a downgrade. The owner's earlier audit-fix lockfile
changes are on their Windows machine and were not available here; this branch
starts from merged main and contains a reproducible targeted update instead.

## Unresolved direct advisory roots

| Dependency | Installed baseline | Reason a blanket override was not applied |
|---|---|---|
| decode-uri-component | 0.2.2 via query-string 7.1.3 / Router | Patched 0.5.1 declares ESM; query-string uses CommonJS require and expects the old API. Routing needs migration/runtime tests. |
| deepmerge | 4.3.1 | Audit affects >=4.2.0; registry latest is still 4.3.1. No supported fixed release found. |
| glob | 13.0.7 | Fixed release is in 14.x; Expo tooling API compatibility must be checked. |
| minimatch | 9.0.9 and 10.2.6 | Advisory covers 7–11.0.0; current patched 11.x crosses installed major versions. |
| image-size | 1.2.1 via Metro | No patched 1.x release found; current 2.1.0 requires a Metro API compatibility investigation. |

Decode advisories affect URL/query input handling and cannot simply be labeled
"development only". The other packages are principally used by build/config/asset
processing in this graph; exact exploitability depends on the entry point and
untrusted inputs. TypeScript and bundling do not establish security. Keep
untrusted assets/configuration away from development tooling and do not deploy
this prototype publicly. These are unresolved findings, not accepted production
risk waivers. Metadata sources: npm registry versions/module metadata and npm's
advisory report, including GHSA-vcc3-ghjq-m6fr, GHSA-qr28-fpjm-wq7f,
GHSA-gcqx-w48m-w2h4, GHSA-3g3m-2fjr-6pw4, GHSA-g3hv-75wg-m249,
GHSA-5p2g-fcmc-qvqq and GHSA-w3rx-r6r6-pgpr.

## Next security work

Evaluate supported Expo SDK migration incrementally with its matching React,
React Native, Router and Expo Go/development client; compare audit reports at each
step. Any transitive override needs module/API and routing/asset runtime tests,
not just an empty audit. Revisit deepmerge upstream status or a reviewed alternative.
Do not assume the npm-recommended SDK version clears every advisory.
