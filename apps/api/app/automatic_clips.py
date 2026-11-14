"""Automatic private-draft ranges; no human annotations or semantic approval.

Choose original contiguous speech using punctuation, pauses, confidence and
bounded editorial cues. Never rewrite words, timing or source media.
"""
from bisect import bisect_left, bisect_right
import re
from typing import Literal

from pydantic import Field, model_validator

from .analysis_annotations import fingerprint
from .analysis_plan import Candidate, ClosedModel, Digest, Transcript
from .clip_selection import diverse
from .editorial_rank import editorial_adjustment

ALGORITHM='automatic-speech-clips-v1'
ABBREVIATIONS=frozenset({'mr.','mrs.','ms.','dr.','prof.','vs.','etc.','e.g.','i.e.'})


class AutomaticClips(ClosedModel):
    algorithm: Literal['automatic-speech-clips-v1']=ALGORITHM
    automatic: Literal[True]=True
    source_sha256: Digest
    source_duration_ms: int=Field(strict=True,ge=1,le=600000)
    transcript_sha256: Digest
    base_revision: Digest
    requested_seconds: int=Field(strict=True,ge=5,le=60)
    review_sha256: Literal[None]=None
    human_review_required: Literal[True]=True  # Watch the output before sharing.
    semantic_quality_verified: Literal[False]=False
    candidates: tuple[Candidate,...]=Field(max_length=5)
    warnings: tuple[Literal['estimated_boundaries','estimated_timestamps',
        'adjusted_word_timestamps','uncertain_words','word_boundary_fallback',
        'no_usable_clip'],...]

    @model_validator(mode='after')
    def bounded(self):
        for candidate in self.candidates:
            if (candidate.source_end_ms>self.source_duration_ms or
                    candidate.source_end_ms-candidate.source_start_ms>self.requested_seconds*1000 or
                    candidate.output_frames>self.requested_seconds*30):
                raise ValueError('Automatic clip exceeds source or duration')
        return self


def terminal(text):
    return text.lower() not in ABBREVIATIONS and bool(re.search(r'''[.!?…]["'\u201d\u2019\u00bb)\]]*$''',text))


def suggest(transcript,requested_seconds,base_revision):
    transcript=Transcript.model_validate(transcript)
    if type(requested_seconds) is not int or not 5<=requested_seconds<=60:
        raise ValueError('Unsupported clip duration')
    words=transcript.words
    if len(words)>1000 or transcript.language!='en':
        raise ValueError('Automatic clips require the bounded English profile')
    cap=requested_seconds*1000
    warnings=['estimated_boundaries','estimated_timestamps']
    if transcript.timestamp_quality=='model_token_estimate_adjusted':warnings.append('adjusted_word_timestamps')
    if any(w.confidence is not None and w.confidence<.45 for w in words):warnings.append('uncertain_words')
    # Every utterance start is evaluated, including speech after an unfinished
    # passage. A pause is an estimate, not proof of a complete thought.
    ends=[i for i,w in enumerate(words) if terminal(w.text) or i==len(words)-1 or
          words[i+1].start_ms-w.end_ms>=900]
    starts=sorted({0,*[i+1 for i in ends if i+1<len(words)]}) if words else []
    # If a very long utterance has no punctuation, also explore pause/clause
    # starts and a bounded half-duration grid, rather than always taking its head.
    next_grid=0
    for i,w in enumerate(words):
        if w.start_ms>=next_grid:
            starts.append(i);next_grid=w.start_ms+max(2500,cap//2)
        if i and (w.start_ms-words[i-1].end_ms>=250 or words[i-1].text.endswith((',', ';', ':'))):
            starts.append(i)
    starts=sorted(set(starts))
    end_times=[words[i].end_ms for i in ends]
    word_ends=[w.end_ms for w in words]
    hard_gaps=[i for i in range(1,len(words)) if words[i].start_ms-words[i-1].end_ms>2000]
    confidence=[0.0];known=[0];speech=[0]
    for w in words:
        confidence.append(confidence[-1]+(w.confidence or 0))
        known.append(known[-1]+int(w.confidence is not None))
        speech.append(speech[-1]+w.end_ms-w.start_ms)
    candidates={};fallbacks=set()
    for first in starts:
        start=words[first].start_ms
        gap=bisect_right(hard_gaps,first)
        limit=hard_gaps[gap] if gap<len(hard_gaps) else len(words)
        left=bisect_left(end_times,start+5000)
        right=min(bisect_right(end_times,start+cap),bisect_left(ends,limit))
        # At most three complete endpoints per start, plus one fallback.
        choices={ends[j] for j in (left,left+1,right-1) if left<=j<right}
        fallback=not choices
        if fallback:
            last=min(bisect_right(word_ends,start+cap)-1,limit-1)
            if last>=first:choices.add(last)
        for last in choices:
            duration=words[last].end_ms-start
            frames=duration*30//1000
            if not 150<=frames<=requested_seconds*30 or duration>cap:continue
            count=last-first+1
            avg=(confidence[last+1]-confidence[first])/count if known[last+1]-known[first]==count else None
            # Uncertain words need no per-word confirmation for a private draft;
            # broadly unreliable spans are still withheld, never marked correct.
            if avg is not None and avg<.45:continue
            density=min(1,(speech[last+1]-speech[first])/duration)
            item=Candidate(first_word=first,last_word=last,source_start_ms=start,
                source_end_ms=words[last].end_ms,output_frames=frames,
                confidence=round(avg,4) if avg is not None else None,
                speech_density=round(density,4),score=0)
            score=.5*(avg if avg is not None else .5)+.2*density+.1*duration/cap
            score+=editorial_adjustment(words,item)
            # Prefer a question with its follow-up over an isolated question.
            score+=(-.18 if words[last].text.rstrip('"\u201d').endswith('?') else .05)
            if fallback:score-=.12;fallbacks.add((first,last))
            candidates[first,last]=item.model_copy(update={'score':round(max(0,min(1,score)),4)})
    ranked=diverse(candidates.values())
    if any((c.first_word,c.last_word) in fallbacks for c in ranked):warnings.append('word_boundary_fallback')
    if not ranked:warnings.append('no_usable_clip')
    return AutomaticClips(source_sha256=transcript.source_sha256,
        source_duration_ms=transcript.source_duration_ms,transcript_sha256=fingerprint(transcript),
        base_revision=base_revision,requested_seconds=requested_seconds,
        candidates=tuple(ranked),warnings=tuple(warnings))


def for_project(row,parent):
    # Reading historical analysis never modifies its transcript, review or plan.
    return suggest(Transcript.model_validate_json(row.transcript_json),parent.desired_seconds,row.revision)
