"""Experimental local transcript contracts and explainable sentence windows.

No provider calls, semantic-quality claim, rendering or persistent customer state.
Transcript text is data. Planning preserves source order and never executes text.
"""
from bisect import bisect_left, bisect_right
import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Milliseconds = Annotated[int, Field(strict=True, ge=0, le=600000)]
Digest = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)


class Word(ClosedModel):
    start_ms: Milliseconds
    end_ms: Milliseconds
    text: str = Field(min_length=1, max_length=160)
    confidence: float | None = Field(default=None, ge=0, le=1, strict=True)

    @model_validator(mode='after')
    def valid(self):
        if self.end_ms <= self.start_ms or not self.text.strip():
            raise ValueError('Invalid word interval or text')
        if any(ord(c) < 32 or ord(c) == 127 for c in self.text):
            raise ValueError('Control characters are forbidden')
        return self


class Transcript(ClosedModel):
    schema_version: Literal['1'] = '1'
    source_sha256: Digest
    source_duration_ms: Annotated[int, Field(strict=True, ge=1, le=600000)]
    language: Literal['en', 'fr']
    provider: Literal['manual', 'whisper_cpp']
    model_sha256: Digest | None = None
    engine_sha256: Digest | None = None
    timestamp_quality: Literal['operator_supplied', 'model_token_estimate', 'model_token_estimate_adjusted']
    words: tuple[Word, ...] = Field(max_length=5000)

    @model_validator(mode='after')
    def valid(self):
        cursor = 0
        for word in self.words:
            if word.start_ms < cursor or word.end_ms > self.source_duration_ms:
                raise ValueError('Words must be ordered, nonoverlapping and inside source')
            cursor = word.end_ms
        if self.provider == 'whisper_cpp':
            if not self.model_sha256 or not self.engine_sha256 or self.timestamp_quality not in ('model_token_estimate','model_token_estimate_adjusted'):
                raise ValueError('Model transcripts require artifact identity and timestamp disclosure')
        elif self.model_sha256 or self.engine_sha256 or self.timestamp_quality != 'operator_supplied':
            raise ValueError('Manual input cannot claim model provenance')
        return self


class Candidate(ClosedModel):
    first_word: Annotated[int, Field(strict=True, ge=0, le=4999)]
    last_word: Annotated[int, Field(strict=True, ge=0, le=4999)]
    source_start_ms: Milliseconds
    source_end_ms: Milliseconds
    output_frames: Annotated[int, Field(strict=True, ge=150, le=1800)]
    confidence: float | None = Field(ge=0, le=1)
    speech_density: float = Field(ge=0, le=1)
    score: float = Field(ge=0, le=1)

    @model_validator(mode='after')
    def valid(self):
        if self.last_word < self.first_word or self.source_end_ms <= self.source_start_ms:
            raise ValueError('Invalid candidate interval')
        if self.output_frames != (self.source_end_ms-self.source_start_ms)*30//1000:
            raise ValueError('Output frame count must derive from source duration')
        return self


class Proposal(ClosedModel):
    schema_version: Literal['1'] = '1'
    algorithm: Literal['sentence-window-v1','sentence-window-v2','sentence-window-v3-reviewed','sentence-window-v4-diverse-reviewed'] = 'sentence-window-v2'
    source_sha256: Digest
    source_duration_ms: Annotated[int, Field(strict=True, ge=1, le=600000)]
    language: Literal['en', 'fr']
    requested_seconds: Annotated[int, Field(strict=True, ge=5, le=60)]
    width: Literal[1080] = 1080
    height: Literal[1920] = 1920
    fps: Literal[30] = 30
    human_review_required: Literal[True] = True
    semantic_quality_verified: Literal[False] = False
    transcript_sha256: Digest | None = None
    review_sha256: Digest | None = None
    candidates: tuple[Candidate, ...] = Field(max_length=5)
    warnings: tuple[Literal['manual_transcript', 'estimated_timestamps', 'adjusted_word_timestamps', 'confidence_unavailable',
                            'no_speech', 'no_complete_window', 'low_confidence_excluded',
                            'human_reviewed_boundaries', 'human_confirmed_words'], ...]

    @model_validator(mode='after')
    def valid(self):
        if (self.algorithm in ('sentence-window-v3-reviewed','sentence-window-v4-diverse-reviewed')) != (self.review_sha256 is not None):
            raise ValueError('Reviewed proposals must disclose review identity')
        if (self.review_sha256 is None) != (self.transcript_sha256 is None):
            raise ValueError('Review and transcript identities must be paired')
        for candidate in self.candidates:
            if (candidate.source_end_ms > self.source_duration_ms or
                    candidate.source_end_ms-candidate.source_start_ms > self.requested_seconds*1000 or
                    candidate.output_frames > self.requested_seconds*30):
                raise ValueError('Candidate exceeds source or requested duration')
        return self


def sentence_ranges(transcript, sentence_end_words=()):
    """Use punctuation or explicit human boundaries; never infer missing text."""
    first = 0
    reviewed_ends = set(sentence_end_words)
    sentences = []
    for i, word in enumerate(transcript.words):
        if i+1 in reviewed_ends or re.search(r'''[.!?…]["'\u201d\u2019\u00bb)\]]*$''', word.text.strip()):
            sentences.append((first, i))
            first = i+1
        elif i+1 < len(transcript.words) and transcript.words[i+1].start_ms-word.end_ms > 2000:
            # An unfinished phrase before a long gap is not a complete sentence.
            first = i+1
    return sentences


def propose(transcript: Transcript, requested_seconds: int, *, review=None) -> Proposal:
    if type(requested_seconds) is not int or not 5 <= requested_seconds <= 60:
        raise ValueError('Requested duration must be an integer from 5 to 60')
    warnings = ['manual_transcript' if transcript.provider == 'manual' else 'estimated_timestamps']
    if transcript.timestamp_quality=='model_token_estimate_adjusted':
        warnings.append('adjusted_word_timestamps')
    confirmed = set()
    sentence_ends = ()
    identities = {}
    if review is not None:
        from .analysis_annotations import fingerprint, validate_review
        review = validate_review(transcript, review)
        confirmed = set(review.confirmed_low_confidence_words)
        sentence_ends = review.sentence_end_words
        identities = {'algorithm': 'sentence-window-v4-diverse-reviewed',
                      'transcript_sha256': review.transcript_sha256,
                      'review_sha256': fingerprint(review)}
        if sentence_ends:
            warnings.append('human_reviewed_boundaries')
        if confirmed:
            warnings.append('human_confirmed_words')
    if any(w.confidence is None for w in transcript.words):
        warnings.append('confidence_unavailable')
    sentences = sentence_ranges(transcript, sentence_ends)
    ends = [transcript.words[end].end_ms for _, end in sentences]
    end_words = [end for _, end in sentences]
    words = transcript.words
    low = [i for i,w in enumerate(words)
           if w.confidence is not None and w.confidence < .45 and i+1 not in confirmed]
    gaps = [i for i in range(1,len(words)) if words[i].start_ms-words[i-1].end_ms>2000]
    if low:
        warnings.append('low_confidence_excluded')
    # Prefix statistics make every sentence start affordable: <=5,000 words,
    # <=10,000 candidate evaluations, each using logarithmic endpoint lookup
    # and constant-time scoring. No source region is skipped by start sampling.
    known_counts=[0];probabilities=[0.0];speech_ms=[0]
    for word in words:
        known_counts.append(known_counts[-1]+int(word.confidence is not None))
        probabilities.append(probabilities[-1]+(word.confidence or 0.0))
        speech_ms.append(speech_ms[-1]+word.end_ms-word.start_ms)
    candidates = {}
    for index,(first,_) in enumerate(sentences):
        start = words[first].start_ms
        limit=len(words)
        next_low=bisect_left(low,first)
        if next_low<len(low):
            limit=min(limit,low[next_low])
        next_gap=bisect_right(gaps,first)
        if next_gap<len(gaps):
            limit=min(limit,gaps[next_gap])
        furthest = min(bisect_right(ends,start+requested_seconds*1000)-1,
                       bisect_left(end_words,limit)-1)
        for end_index in {index, furthest}:
            if end_index < index or end_index > furthest:
                continue
            last = sentences[end_index][1]
            duration = words[last].end_ms-start
            frames = duration*30//1000
            if not 150 <= frames <= requested_seconds*30 or duration > requested_seconds*1000:
                continue
            count=last-first+1
            confidence=(probabilities[last+1]-probabilities[first])/count \
                if known_counts[last+1]-known_counts[first]==count else None
            density = min(1,(speech_ms[last+1]-speech_ms[first])/duration)
            score = .5*(confidence if confidence is not None else .5)+.25*density+.25*duration/(requested_seconds*1000)
            candidates[first,last] = Candidate(first_word=first,last_word=last,
                source_start_ms=start,source_end_ms=words[last].end_ms,output_frames=frames,
                confidence=round(confidence,4) if confidence is not None else None,
                speech_density=round(density,4),score=round(score,4))
    if review is not None:
        from .clip_selection import diverse
        ranked=diverse(candidates.values())
    else:
        ranked = sorted(candidates.values(),key=lambda c:(-c.score,c.source_start_ms,c.source_end_ms))[:5]
    if not ranked:
        warnings.append('no_speech' if not transcript.words else 'no_complete_window')
    return Proposal(source_sha256=transcript.source_sha256,source_duration_ms=transcript.source_duration_ms,
        language=transcript.language,requested_seconds=requested_seconds,candidates=tuple(ranked),
        warnings=tuple(warnings),**identities)


def planning_edl(proposal: Proposal, index=0):
    """Data-only proposal for later renderer integration. Never an execution plan."""
    if type(index) is not int or not 0 <= index < len(proposal.candidates):
        raise ValueError('Choose an available candidate')
    candidate = proposal.candidates[index]
    edl = {'schema_version':'analysis-1','source_sha256':proposal.source_sha256,
        'human_review_required':True,'render_supported':False,
        'output':{'width':1080,'height':1920,'fps':30,'duration_frames':candidate.output_frames},
        'scenes':[{'type':'talking_head','start_frame':0,'end_frame':candidate.output_frames,
                   'source_start_ms':candidate.source_start_ms,'source_end_ms':candidate.source_end_ms}],
        'rounding':'Output floors duration to whole frames; tail difference is less than one frame.'}
    if proposal.review_sha256 is not None:
        edl.update(review_sha256=proposal.review_sha256,
                   transcript_sha256=proposal.transcript_sha256,
                   human_annotations_applied=True)
    return edl
