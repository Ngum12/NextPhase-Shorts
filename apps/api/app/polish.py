"""Closed choices for manual preview polish; never client FFmpeg expressions."""
from typing import Literal

from .analysis_plan import ClosedModel


class PolishSettings(ClosedModel):
    caption_size: Literal['standard','large']='standard'
    caption_color: Literal['white','yellow']='white'
    caption_position: Literal['lower','middle']='lower'
    voice: Literal['original','level']='original'
    audio_edges: Literal['original','soft']='original'


def caption_appearance(settings):
    settings=PolishSettings.model_validate(settings)
    return (56 if settings.caption_size=='standard' else 64,
            'white' if settings.caption_color=='white' else '0xF8E45C',
            1500 if settings.caption_position=='lower' else 1100)


def voice_filter(settings):
    settings=PolishSettings.model_validate(settings)
    if settings.voice=='original':return None
    # Bounded gain (<=4x), no synthesis, pitch/time change, or denoising claim.
    return 'dynaudnorm=f=150:g=9:p=0.9:m=4,alimiter=limit=0.95:level=0:latency=1'


def clip_audio_filter(settings, *, start_ms, frames):
    """Opt-in short edge fades on the original source PTS, after optional leveling.

    FFmpeg uses output-side -ss after -i in render_excerpt, so audio filters see
    absolute source timestamps, not a zero-based excerpt clock.  Use the exact
    rendered frame duration to keep the end fade within the published clip.
    """
    settings=PolishSettings.model_validate(settings)
    existing=voice_filter(settings)
    if settings.audio_edges=='original':return existing
    # The excerpt contract guarantees >=150 frames and a source-bound offset.
    start=start_ms/1000
    last=start+frames/30
    fades=(f'afade=t=in:st={start:.6f}:d=0.08',
           f'afade=t=out:st={last-0.08:.6f}:d=0.08')
    return ','.join((*( (existing,) if existing else ()), *fades))
