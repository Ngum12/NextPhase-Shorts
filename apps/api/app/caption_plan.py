"""Bounded phrase captions from reviewed words; no invented text or timing claim."""
import re
import textwrap
from typing import Annotated

from pydantic import Field, model_validator

from .analysis_plan import ClosedModel


class CaptionCue(ClosedModel):
    start_ms: Annotated[int, Field(strict=True, ge=0, lt=60000)]
    end_ms: Annotated[int, Field(strict=True, gt=0, le=60000)]
    text: str = Field(min_length=1, max_length=53)

    @model_validator(mode='after')
    def valid(self):
        lines = self.text.split('\n')
        if (self.end_ms <= self.start_ms or len(lines) > 2 or
                any(not line or len(line) > 26 for line in lines) or
                any((ord(c) < 32 and c != '\n') or ord(c) == 127 for c in self.text)):
            raise ValueError('Invalid caption cue')
        return self


def validate_cues(cues, frames):
    cues = tuple(CaptionCue.model_validate(cue) for cue in cues)
    if len(cues) > 80:
        raise ValueError('Caption cue limit exceeded')
    cursor = 0
    for cue in cues:
        if cue.start_ms < cursor or cue.end_ms * 30 > frames * 1000:
            raise ValueError('Caption exceeds excerpt or overlaps another cue')
        cursor = cue.end_ms
    return cues


def captions_for(transcript, candidate):
    """Preserve word order/text, wrap at 26 columns and retain silence gaps."""
    cues = []
    group = []
    cap = candidate.output_frames * 1000 // 30

    def flush():
        if not group:
            return
        text = ' '.join(word.text.strip() for word in group)
        lines = textwrap.wrap(text, width=26, break_long_words=True,
                              break_on_hyphens=False, replace_whitespace=False)
        if len(lines) > 2:
            raise ValueError('A caption word is too long for this style')
        start = max(0, group[0].start_ms - candidate.source_start_ms)
        end = min(cap, group[-1].end_ms - candidate.source_start_ms)
        if end <= start:
            raise ValueError('Caption word falls outside rendered frames')
        cues.append(CaptionCue(start_ms=start, end_ms=end, text='\n'.join(lines)))
        group.clear()

    for word in transcript.words[candidate.first_word:candidate.last_word + 1]:
        trial = ' '.join(w.text.strip() for w in (*group, word))
        if group and (len(group) >= 6 or len(trial) > 48 or
                      word.start_ms - group[-1].end_ms > 300):
            flush()
        group.append(word)
        if re.search(r'[.!?]["\u201d\u2019]*$', word.text):
            flush()
    flush()
    return validate_cues(cues, candidate.output_frames)
