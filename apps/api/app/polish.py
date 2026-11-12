"""Closed choices for manual preview polish; never client FFmpeg expressions."""
from typing import Literal

from .analysis_plan import ClosedModel


class PolishSettings(ClosedModel):
    caption_size: Literal['standard','large']='standard'
    caption_color: Literal['white','yellow']='white'
    caption_position: Literal['lower','middle']='lower'
    voice: Literal['original','level']='original'


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
