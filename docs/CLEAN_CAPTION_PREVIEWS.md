# Clean captions in private English previews

The subsequent [polished-video workspace](POLISHED_VIDEO.md) adds optional manual
caption text/timing corrections and fixed appearance/voice choices. Plain and
the original clean-caption action remain available.

The existing saved-review flow can now render a separate **Clean captions**
version. Plain remains the default. A fixed server renderer overlays short white
phrases on a dark box in the lower portrait safe area. It preserves original
voice, word order, selected framing and the existing exact-frame/duration limits.
Fit is the default; optional centered fill is described in PORTRAIT_FRAMING.md.
This does not add automatic ASR, speaker tracking, music or other style presets.

## Owner flow

1. Open the original English project and refresh its saved review.
2. Select a suggestion, then **Clean captions**.
3. Choose **Render selected preview** and acknowledge the timing review.
4. Watch the result, checking caption wording, synchronization and first/last words.

Model word timestamps are **estimates**. Human confirmation of transcript words
does not establish accurate timing. There is no karaoke/word-highlight claim,
timing editor or automatic quality approval. Gaps over 300 ms split phrases;
up to six words are grouped and wrapped to at most two 26-character lines.
Long words or more than 80 cues are refused rather than silently dropping words;
the owner can use a plain preview. Layout is fixed and does not detect faces.

## Queue and privacy

`caption_style` is a closed optional enum (`none`, default, or `clean-1`) in the
existing owner-only allowlisted preview request. No text, timing, font, filter or
path comes from that request. Cues derive from the saved source-bound transcript
and selected candidate and are copied into the immutable excerpt spec. The
worker validates cue ordering, size and frame bounds. No database migration is
added; existing excerpt specs with no captions still decode as plain previews.

Plain and captioned requests use separate durable keys per option/revision;
retries recover the same child. Old plain request hashes and stored keys remain
valid. SecureStore retains at most ten keys per reviewed source. Capability
`clean_captions_supported` hides the choice against an older server. Every child
still consumes existing queue, compute, storage and owner admission budgets.

Caption text is written to up to 80 private mode-0600 UTF-8 files (<=256 bytes
each) in the attempt directory, then removed on success/failure/cancellation.
FFmpeg receives internal canonical paths and `expansion=none`; caption words
never enter the filter grammar. Required Landlock mode adds only exact read
grants for small `caption-*.txt` files in that same attempt, never a directory
grant. Existing single-output write limits, process/network restrictions and
credential reduction remain. Unsupported guards still fail closed. Files can
remain after a hard kill until existing attempt/project cleanup; caption text
also remains in the job spec/backups and visible in exported videos. Existing
project/account deletion erases specs; exported copies cannot be recalled.

## Build and acceptance

The worker image now installs Debian's `fonts-dejavu-core`; it uses the unmodified
DejaVu Sans Mono Bold font at a fixed system path. See LICENSE_AUDIT.md and the
retained font notice. CI verifies drawtext and the font and includes them in its
bounded signed APT fallback. No Python/npm dependency or paid provider was added.

Use the backup/build/stop-writers/migrate/restart procedure in
ENGLISH_PROJECT_REVIEW.md to deploy matching images, retaining private owner and
network restrictions. Schema stays at 0022; the explicit migration step remains
safe/current. Pull mobile code and restart Metro with a cleared cache; no new
native dependency is added in this increment. Actual protected-VPS rendering and
phone/audio/caption acceptance must be recorded after deployment.
