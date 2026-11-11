"""Separate human annotations; never rewrite recognized words or model scores."""
import hashlib
import json
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .analysis_plan import ClosedModel, Digest, Transcript

WordNumber = Annotated[int, Field(strict=True, ge=1, le=5000)]


def fingerprint(value):
    """Stable identity of the validated contract, independent of JSON formatting."""
    encoded = json.dumps(value.model_dump(mode='json'), ensure_ascii=False,
                         sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


class TranscriptReview(ClosedModel):
    schema_version: Literal['transcript-review-1'] = 'transcript-review-1'
    source_sha256: Digest
    transcript_sha256: Digest
    acknowledged_original_recording: Literal[True]
    sentence_end_words: tuple[WordNumber, ...] = Field(max_length=5000)
    confirmed_low_confidence_words: tuple[WordNumber, ...] = Field(max_length=5000)

    @model_validator(mode='before')
    @classmethod
    def explicit_acknowledgement(cls, value):
        if isinstance(value, dict) and value.get('acknowledged_original_recording') is not True:
            raise ValueError('Review requires an explicit original-recording acknowledgement')
        return value

    @model_validator(mode='after')
    def ordered(self):
        for numbers in (self.sentence_end_words, self.confirmed_low_confidence_words):
            if tuple(sorted(set(numbers))) != numbers:
                raise ValueError('Review word numbers must be unique and sorted')
        return self


def validate_review(transcript: Transcript, review):
    review = TranscriptReview.model_validate(review)
    if (review.source_sha256 != transcript.source_sha256
            or review.transcript_sha256 != fingerprint(transcript)):
        raise ValueError('Review is not bound to this transcript')
    for number in (*review.sentence_end_words, *review.confirmed_low_confidence_words):
        if number > len(transcript.words):
            raise ValueError('Review references missing words')
    for number in review.confirmed_low_confidence_words:
        confidence = transcript.words[number - 1].confidence
        if confidence is None or confidence >= .45:
            raise ValueError('Review confirmation requires a flagged word')
    return review
