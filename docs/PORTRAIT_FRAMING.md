# Optional portrait framing for reviewed English previews

The original project and its fit preview are preserved. The saved-review screen
offers two choices on a matching server:

- **Fit full video** (default): retain the full picture with bars where needed.
- **Fill portrait (center)**: crop around the fixed center to fill 1080x1920.

The crop does not find or follow faces. It can remove a speaker, hands, text or
other important details at the edges. Watch the result before sharing; choose fit
if the center is unsuitable. This increment does not add a crop-position editor,
tracking, zoom animation or automatic aesthetic selection. Source material that
already has black borders can retain those baked-in borders.

## Owner flow

Open the existing reviewed English project, refresh its saved review and select
a suggestion. Choose a framing mode independently of Plain/Clean captions, then
confirm **Render selected preview**. A separate child project opens. Compare it
with the fit version and check the face, edges, first/last words and caption
placement. All processing remains on the server. Caption timing is still
estimated and requires comparison with speech.

## Contract and compatibility

The existing private preview POST accepts a closed `framing` enum: `fit` (default)
or `fill-center`. It accepts no filter, coordinates, paths or raw commands. The
choice is part of the immutable source/review-bound excerpt spec. Old specs
without it default to fit. Schema remains 0022; no database migration is added.

The server generates fixed crop/scale expressions. Cropping happens before
scaling, so a very wide or tall source does not create an enormous intermediate
canvas. Crop geometry accounts for source sample aspect ratio, treating unknown
SAR as square. Crop dimensions/position are rounded to source pixels; this is
not subpixel reframing. FFmpeg's normal input rotation handling is retained.
Existing decoder guards, environment restrictions, timeout, cancellation,
single-output size limits and 1080x1920/30-fps/frame-count/duration QA are reused.

Fit variants keep their original idempotency identities and SecureStore keys.
Fill variants have distinct keys; retries recover their same child. One bounded
SecureStore item per reviewed source now holds at most 20 keys (five options,
two caption choices, two framings), below the existing 2048-character guard.
Local source deletion removes that intent item. Existing owner/global admission,
byte reservations and child/source/account deletion rules apply to every variant;
the new choice does not grant extra slots or credits.

Capability `portrait_framing_supported` hides controls on older servers; fit
requests omit the new field for compatibility. Changing servers/capabilities
falls back to fit. Preserve the private owner allowlist and network restrictions.

## Deployment and acceptance

Use the verified-backup/build/stop-writers/migrate/restart procedure in
ENGLISH_PROJECT_REVIEW.md. API and worker images must match even though the schema
is unchanged, since older workers reject new spec fields. Mobile needs merged
code and a cleared Metro cache; no new package/native build is introduced.

Reproducible synthetic proof (new output folder only):

```bash
.venv/bin/python scripts/smoke_portrait_framing.py
```

This creates fit/fill MP4s with captions, a side-by-side PNG and actual frame,
duration, file-size/hash and render-time measurements. Its geometry and tone are
synthetic; they are not real-person/semantic-quality evidence. Automated coverage
checks actual image edges, exact frames, audio offset, tall/wide/anamorphic input,
caption placement, private queued download, closed request validation and durable
variant retries. Actual protected-VPS rendering and owner phone framing acceptance
remain separate deployment checks.
