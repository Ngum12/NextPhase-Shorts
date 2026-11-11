# Private English clip previews in the app

After saving a human review, select a suggestion and press **Render selected
preview**. The app acknowledges the need to check the actual cut and opens a new
preview project. It polls the existing queue; when successful, **Watch preview**
plays the private result. Cancel/Delete, Save/Share and Back to source review are
available. Automatic transcription is still operator-only; no captions, effects,
semantic-quality claim, public release or French acceptance is introduced.

## Server and worker boundaries

- `POST /api/v1/jobs/{source_id}/analysis/previews` accepts closed JSON containing
  saved `revision`, one-based `candidate_number`, UUID4 `idempotency_key` and
  explicit boolean `acknowledged_preview:true`. Only an authenticated allowlisted
  development/test owner can request it. The source must be live, original and
  local-storage backed. S3 originals and nested previews are refused.
- The saved human review, proposal, source/transcript hashes and current revision
  determine every interval. Clients cannot submit paths, filters, models, commands,
  raw EDLs or arbitrary trim ranges. A separate RenderJob retains an immutable
  ExcerptSpec and parent link; the original baseline output is preserved.
- Existing owner/global admission, budget pause, Valkey dispatch, claim leases,
  two-attempt retry/dead-letter policy, cancellation, observations and cost
  accounting are reused. A child reserves two source copies plus two output caps
  to cover overlapping bounded stale attempts. Reservations remain conservative
  until deletion cleanup. Acknowledged retries recover the same job even after
  another device changes the review; mismatched keys fail and deleted keys return
  410. No new paid/provider operation is introduced.
- The worker derives the parent source by canonical owner/project identity and
  copies it into that attempt's private directory. Exact accepted length, SHA-256
  and probed duration must match before decoding. The copy is removed afterward.
  Source is <=300 MiB/10 minutes; output <=min(configured cap,64 MiB). The shared
  fixed renderer preserves source order/voice and produces 1080×1920/30-fps
  letterboxed H.264/AAC, not intelligent cropping. It checks exact frames, fps,
  dimensions, duration, size and live claim before publication. Requested and
  60-second caps remain mandatory; frame-floor timing drops <1 frame at the tail.
- Native calls retain the existing credential-reduced launcher, file-only input,
  bounded resources, process teardown and required Landlock/seccomp behavior.
  No worker guard is disabled and no ASR model enters this path. Platform/kernel
  support and actual-host containment are not established by native-mode tests.
- Deleting a child preserves its source. Deleting a source tombstones all linked
  children under the owner lock, revokes claims and journals each identity. Source
  cleanup waits for relevant parent/child attempt deadlines. Account deletion
  erases specs; protected replay cascades source tombstones and replays individual
  child records. Existing offsite backup/hold/old-host-fencing rules still apply.

## Phone storage and playback

One SecureStore item per source retains at most five option keys for the current
review revision; it contains hashes/UUIDs, not transcript/media. Storage operations
are serialized and in-flight requests scoped to session/project. Interrupted
requests reuse their keys after restart; a new revision replaces old keys. Local
source deletion removes that device's intent item. Other-device/account deletion
cannot remotely erase metadata already on this phone.

**expo-video 58.0.14**, matched to SDK 58, plays only a local app-cache URI. The app
downloads from its authenticated API endpoint, can recover authentication once,
rejects failed/empty/oversize downloads and keeps credentials out of the player
URI. Leaving/changing sessions cleans the cache; late downloads remove their file
after completion. Cleanup is best effort: OS/process termination can leave private
cache remnants. Native controls provide playback; background/PiP are not enabled.
Explicit Save/Share and already cached/delivered media cannot be remotely revoked.

## Update and acceptance

Migration **0022_excerpt_previews** adds the parent link/index and spec to
render_jobs. Existing originals default to NULL and keep baseline behavior. Use
the verified-backup/build/stop-writers/migrate/restart procedure in
ENGLISH_PROJECT_REVIEW.md and retain the private owner allowlist. The review
response adds `queued_preview_supported`; older servers hide the render action.
`render_enabled:false` still describes the inert planning EDL, not permission to
execute arbitrary edits.

Pull merged mobile code, run `npm ci` in apps/mobile and restart Metro with a
cleared cache, retaining EXPO_PUBLIC_ENGLISH_REVIEW=true. Expo Go must support
SDK 58's video module; custom development clients need rebuilding for the module.
Automated coverage exercises queue admission/retries, actual synthetic render/
download, checksums, cancellation/deletion and durable request/private-download
logic. Mocked screen tests are not device/player acceptance. Next, the owner must
render one already reviewed real English suggestion on the upgraded VPS and check
its first/last words, voice synchronization and meaning inside the phone app.
