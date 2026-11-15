"""Full-source speech units and source-checked model ranges; no provider I/O."""
from pydantic import Field, model_validator

from .analysis_annotations import fingerprint
from .analysis_plan import Candidate, ClosedModel, Transcript
from .automatic_clips import AutomaticClips, terminal
from .clip_selection import overlap

MAX_UNITS=128


class WordRange(ClosedModel):
    first_word: int=Field(strict=True,ge=0,le=999)
    last_word: int=Field(strict=True,ge=0,le=999)

    @model_validator(mode='after')
    def ordered(self):
        if self.last_word<self.first_word:raise ValueError('Backward word range')
        return self


def source_for(transcript,base):
    transcript=Transcript.model_validate(transcript);base=AutomaticClips.model_validate(base)
    if (transcript.language!='en' or not transcript.words or len(transcript.words)>1000 or
            base.source_sha256!=transcript.source_sha256 or
            base.source_duration_ms!=transcript.source_duration_ms or
            base.transcript_sha256!=fingerprint(transcript)):
        raise ValueError('Passage source identity differs')
    return transcript,base


def units_for(transcript,requested_seconds=60):
    """Cover every word once, in order; bounded units are never a top-five filter."""
    words=transcript.words;units=[];first=0
    for last,word in enumerate(words):
        if last>first and word.end_ms-words[first].start_ms>requested_seconds*500:
            units.append(WordRange(first_word=first,last_word=last-1));first=last
        if (terminal(word.text) or last==len(words)-1 or last-first+1>=16 or
                words[last+1].start_ms-word.end_ms>=900):
            units.append(WordRange(first_word=first,last_word=last));first=last+1
    # Pathological one-word punctuation still retains all text. Merge adjacent
    # shortest units rather than truncating the transcript or dropping context.
    while len(units)>MAX_UNITS:
        i=min(range(len(units)-1),key=lambda j:units[j+1].last_word-units[j].first_word)
        units[i:i+2]=[WordRange(first_word=units[i].first_word,last_word=units[i+1].last_word)]
    return tuple(units)


def candidates_for(transcript,base,ranges):
    transcript,base=source_for(transcript,base)
    if not 1<=len(ranges)<=3:raise ValueError('Invalid passage count')
    selected=[]
    for value in ranges:
        value=WordRange.model_validate(value)
        if value.last_word>=len(transcript.words):raise ValueError('Unknown word range')
        words=transcript.words[value.first_word:value.last_word+1]
        start,end=words[0].start_ms,words[-1].end_ms;duration=end-start
        if (not 5000<=duration<=base.requested_seconds*1000 or
                any(right.start_ms-left.end_ms>2000 for left,right in zip(words,words[1:]))):
            raise ValueError('Passage exceeds the speech profile')
        known=all(word.confidence is not None for word in words)
        confidence=sum(word.confidence for word in words)/len(words) if known else None
        if confidence is not None and confidence<.45:raise ValueError('Unreliable passage')
        density=min(1,sum(word.end_ms-word.start_ms for word in words)/duration)
        # These remain technical scores, never model confidence/semantic proof.
        candidate=Candidate(first_word=value.first_word,last_word=value.last_word,
            source_start_ms=start,source_end_ms=end,output_frames=duration*30//1000,
            confidence=round(confidence,4) if confidence is not None else None,
            speech_density=round(density,4),score=round(.5*(confidence if known else .5)+.2*density,4))
        if any(overlap(candidate,old)>=.85 for old in selected):raise ValueError('Duplicate passages')
        selected.append(candidate)
    return tuple(selected)


def apply_passages(transcript,base,ranges):
    transcript,base=source_for(transcript,base)
    selected=list(candidates_for(transcript,base,ranges))
    for candidate in base.candidates:
        if len(selected)>=5:break
        if all(overlap(candidate,old)<.85 for old in selected):selected.append(candidate)
    warnings=tuple(w for w in base.warnings if w!='no_usable_clip')
    return AutomaticClips.model_validate({**base.model_dump(), 'candidates':tuple(selected),'warnings':warnings})
