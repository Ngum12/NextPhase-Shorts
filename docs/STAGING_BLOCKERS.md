# Phase 2 package 6 — resolving the remaining gates

## Resolved locally in this increment

The mobile graph moves from Expo **54.0.38 / Router 6.0.24 / RN 0.81.5 / React
19.1.0** to the official Expo **58.0.23** module map: Router **58.0.30**, RN
**0.88.1**, React **19.3.0**, SDK-matched Expo modules and required navigation/UI
peers. Node must meet Expo's `^22.13.0 || ^24.3.0 || ^26.0.0 || >=27` range;
the owner's reported Node 24.15 meets it. The npm lockfile pins actual resolution.

SDK 58 removes the old query-string/decode-uri-component, deepmerge and image-size
advisory chains from this app. Its CLI/fingerprint still requested vulnerable glob
13/minimatch 10, so **narrow consumer-scoped overrides** select glob **14.0.4** for
`@expo/cli` and `@expo/fingerprint`, and minimatch **11.0.5** for fingerprint.
These major tool updates are intentionally reviewed overrides, not a claim that
upstream Expo has changed its own dependency declarations. Their CommonJS export,
async/sync traversal, ignore/case/dot behavior, pre-aborted cancellation, actual
fingerprinting, config introspection and Android bundling are checked. PostCSS's
existing same-major security override remains. No `audit fix --force` was used.

**Fresh clean-lockfile npm audit: zero findings**, previously 17 (four high).
This is a point-in-time advisory result, not a guarantee of no vulnerabilities.
CI now fails on audit findings and runs the tool-consumer regressions.

SDK compatibility fixes:

- await `FileHandle.readBytes()` and recheck Pause before sending; bounded chunks
  remain, no phone encoding/inference, original file/pending journal are preserved;
- import Save's API from `expo-media-library/legacy`; the SDK 58 root's deprecated
  `saveToLibraryAsync` throws at runtime. Save and Share remain separate;
- media permission introspection retains Android read/location removal and iOS
  add-only wording. No new broad gallery permission was requested by the app.

Docker API now binds **127.0.0.1:8000** by default. USB forwarding works unchanged;
LAN/public exposure is an explicit separately reviewed choice, not a default. This
is private development safety, not HTTPS, a firewall or public staging approval.

## Owner upgrade after review/merge

**Do not uninstall Expo Go or clear app data as a routine upgrade step.** Finish a
pending upload first if possible; keep your original video and server backup. Expo
Go/native sandbox changes can require signing in again; tests do not guarantee
cross-SDK preservation of every Expo Go native storage location.

Keep the existing Docker backend running; this mobile upgrade has **no backend
schema/API change**, so no repeated Docker image build/database migration or full
manual regression is required. Applying the loopback port change only needs
`docker compose up -d`. Update Expo Go to the official **SDK 58-compatible** Android
version (Play Store or https://expo.dev/go). A custom development client must be
rebuilt for SDK 58; the SDK 54 client cannot open this project.

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
git pull --ff-only
docker compose up -d
cd apps\mobile
npm ci
$env:EXPO_PUBLIC_API_URL = "http://127.0.0.1:8000"
$env:EXPO_NO_TYPESCRIPT_SETUP = "1"
$env:EXPO_NO_TELEMETRY = "1"
$env:EXPO_OFFLINE = "1"
npx expo start --localhost --clear
```

Restore `adb reverse` for API 8000 and the actual Metro port, as before. Focused
Pixel check: sign in/reopen; navigate Home/My Shorts/Account and an existing result;
create/pause/resume a new upload; render; **Save and play**; Share opens its separate
sheet. The styles remain baseline/coming-soon, not AI editing. On an owned disposable
account, verify sign-out/new login and any pending journal without clearing originals.
Report an actual failure rather than resetting storage to conceal it. Physical
SDK 58 acceptance remains pending; Hermes/type tests are not that proof.

## Container inventory, without credentials or paid tools

The local application image already on your PC can be inventoried without a
rebuild, network, application environment variables, media mounts or DB startup:

```powershell
cd C:\Users\Ngum\NextPhase-Shorts
.\.venv\Scripts\python.exe scripts/image_inventory.py --image nextphase-shorts-worker --output .data\worker-image-inventory.json
```

Use a new output filename for each run. It captures immutable image ID, installed
Debian/source package versions, copyright-file hashes, Python versions/declared
licenses and FFmpeg build configuration; create-only UTF-8/POSIX 0600, protect NTFS
with current-user permissions. It never dumps Docker environment/inspect payloads
or credentials and pulls no image. No privileged mounts or Docker socket enter
the inventory container. Docker controls may be unsupported in a managed host;
this inventory does not certify their enforcement.

The helper was tested against an **existing earlier validation image**, with 292
OS/41 Python packages; no new/current production image or vulnerability scan was
claimed. Its output explicitly keeps scan/legal review false. The owner's actual
image is needed to complete its exact-image review. Share only the operator summary
or a privately reviewed inventory; do not publish real backup/config/secret files.

## Remaining work, in priority order

| Gate | Concrete route to resolution | Evidence needed / who acts |
|---|---|---|
| SDK/native migration | Apply this reviewed build and run one focused Pixel check | Owner device; cloud agent cannot replace real native acceptance |
| Exact image security/licensing | Inventory the actual image, pin reviewed base/resolution and scan that artifact; retain notices/corresponding-source obligations | Engineering plus owner/legal decision on notices, codecs/patents/redistribution; inventory alone is not clearance |
| Post-snapshot erasure/revocation | Local encrypted journal, schema binding and offline replay/release implemented/tested; configure immutable/offsite journal/checkpoint/key custody and encrypted backup retention | Local operator restore gate is reviewable; actual staging fencing/offsite policy and remote erasure remain open |
| Private staging transport/edge | Build a separate PostgreSQL/private-storage/broker/worker deployment with valid TLS, bounded connections/body/rates and private networks; verify from Pixel | Free disposable local TLS protocol checks can be implemented; genuine publicly trusted deployment needs a selected host/domain and approval before any paid resource |
| Secret manager and least privilege | Mount per-service scoped secrets through the existing `_FILE` adapter; rotate/revoke old credentials after a synthetic check | Owner-controlled runtime/provider credentials entered privately, not chat; no cloud vault was provisioned here |
| Collector and alert delivery | Import the tested OTLP format into an approved collector, route CLI/metrics alarms and test detection | Further integration on the selected private staging runtime; no external recipient is messaged without authorization |
| Real total cost ceiling | Reconcile direct signed traffic/idle/API/DB/broker/backup/provider costs with real rates/usage; enforce infrastructure quotas and kill switches | Owner-approved rate/budget/provider scope; no estimate is relabeled a provider billing stop |
| Privacy/terms/retention/provider rules | Finalize controller entity/contact, jurisdiction, retention/backup/deletion disclosures, provider DPA and consent | Owner/legal approval; the unpublished PRIVACY_TERMS_DRAFT.md records implemented behavior and missing owner decisions; engineering cannot sign on their behalf |
| Representative staging acceptance | Mixed real consented codecs/durations and slow networks, longer soak/restart/restore, owner isolation and cost/latency/error evidence | Engineering and supported hardware/runtime; earlier 100-request/10-minute synthetic test is retained, not inflated into full production evidence |
| Remote CI | Observe the run for the new reviewed commit | GitHub API is Forbidden in this environment; owner can supply job results |

The recommended immediate environment remains **private local Docker + USB**, with
paid services, AI and billing disabled. We can prepare code and disposable tests
without changing your domain or opening public access. Hosting/paid provider
activation and legal approvals are separate decisions after concrete configurations
and evidence exist. Do not treat a merge, zero audit, passing host check or this
plan as Phase 2/public production signoff. The remaining engineering rows above
are work, not completed features; they are not skipped by this dependency repair.


### SDK 58 Android picker follow-up

If Expo Go reports that `cache/DocumentPicker` is unreadable, use the reviewed
picker-copy correction: Android skips the picker host-cache copy and retains its
user-granted content URI, then awaits modern File.copy into the private UUID
upload file before saving an intent. iOS still requests picker cache copying.
No broader media permission or sandbox bypass is required. Pull the fix, restart
Metro and choose the video again; a previously selected host-cache URI remains
unreadable. Keep original footage/app data. This changes no backend/schema or
lockfile, so no backend rebuild/migration/npm reinstall is necessary.


### Backup rollback protection update

Independent encrypted local security journaling and offline replay/release are now
implemented in the next increment; see [RESTORE_JOURNAL.md](RESTORE_JOURNAL.md).
Protected restores invalidate all old credentials/passwords and reapply deletion
intentions from a separately retained current stream/checkpoint. This supersedes
the earlier "unimplemented journal" entry only for that tested local scope.
Offsite/immutable journal custody, encrypted snapshots, key rotation, actual staging
fencing and remote/versioned erasure remain open and are not waived.


### Consolidated completion build

The remaining backup/private-TLS/operations/review software is packaged together;
[CONSOLIDATED_ACCEPTANCE.md](CONSOLIDATED_ACCEPTANCE.md) supersedes fragmented
local implementation steps. Authenticated local bundles, actual verified Caddy
TLS/renderer, private trace/alert receipt and application budget gates pass the
single automation report. Nine explicitly external release approvals remain
false by default; no public-hosting, provider-bill, offsite-custody or legal proof
is invented. One Windows activation script is the remaining owner host check.
