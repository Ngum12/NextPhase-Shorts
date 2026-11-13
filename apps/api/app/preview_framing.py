"""Fixed server framing choices, not client filter expressions or face tracking."""
from typing import Literal

Framing = Literal['fit', 'fill-center', 'fill-left', 'fill-right']


def framing_filter(framing: Framing) -> str:
    if framing == 'fit':
        return ('scale=1080:1920:force_original_aspect_ratio=decrease:flags=lanczos,'
                'pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black,'
                'fps=30,setsar=1,format=yuv420p')
    if framing not in ('fill-center', 'fill-left', 'fill-right'):
        raise ValueError('Unsupported preview framing')
    # Use a closed, constant source-space crop anchor. No client filter
    # expressions, detection or high-resolution intermediate canvas.
    x={'fill-left':'0', 'fill-center':'(iw-ow)/2', 'fill-right':'iw-ow'}[framing]
    # Crop in source coordinates before scaling: even very wide/tall inputs
    # cannot produce an enormous intermediate canvas. Preserve display aspect
    # via SAR, with unknown SAR treated as square; integer crop rounding remains.
    sar='if(gt(sar,0),sar,1)'
    return (f"crop=w='max(1,min(iw,ih*9/16/({sar})))':"
            f"h='max(1,min(ih,iw*16/9*({sar})))':"
            f'x={x}:y=(ih-oh)/2:exact=1,'
            'scale=1080:1920:flags=lanczos,fps=30,setsar=1,format=yuv420p')
