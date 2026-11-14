"""Deterministic editorial cues for already human-reviewed English sentences.

These lexical hints are *not* language comprehension, virality predictions, or
permission to automatically publish. Candidate intervals, verified human word
boundaries, model confidence and the technical score are never changed. Old
review plans retain their original ranking when read from storage.
"""
import re

from .clip_selection import diverse

ALGORITHM = 'sentence-window-v5-discourse-reviewed'

# English only; intentionally small, auditable and independent of providers.
DEPENDENT_STARTS = frozenset({
    'and', 'but', 'because', 'however', 'therefore', 'thus', 'hence',
    'so', 'then', 'also', 'anyway', 'besides', 'although', 'though',
    'it', 'its', 'they', 'them', 'their', 'he', 'she', 'this', 'that',
    'these', 'those', 'which', 'whereas',
})
FILLER_STARTS = frozenset({'um', 'uh', 'erm', 'hmm'})
QUESTION_STARTS = frozenset({'why', 'how', 'what', 'when', 'where', 'who'})
HOOK_STARTS = frozenset({'imagine', 'discover', 'remember', 'today', 'first', "here's"})
RESOLUTION_CUES = frozenset({
    'learned', 'realized', 'discovered', 'result', 'solution', 'solved',
    'works', 'worked', 'achieved', 'finally', 'conclusion', 'lesson',
})


def normal(word):
    """Token prefix/suffix punctuation only; never interpret transcript as code."""
    return re.sub(r"^[^a-z0-9]+|[^a-z0-9]+$", "", word.lower().replace('\u2019', "'"))


def editorial_adjustment(words, candidate, language='en'):
    """[-.2,+.15] bounded rank adjustment; no claims about clip's actual meaning."""
    if language != 'en' or not 0 <= candidate.first_word <= candidate.last_word < len(words):
        return 0.0
    start = normal(words[candidate.first_word].text)
    tail = [normal(word.text) for word in words[max(candidate.first_word, candidate.last_word-9):candidate.last_word+1]]
    adjustment = 0.0
    if start in DEPENDENT_STARTS:
        adjustment -= .18
    elif start in FILLER_STARTS:
        adjustment -= .12
    elif start in QUESTION_STARTS:
        adjustment += .10
    elif start in HOOK_STARTS:
        adjustment += .08
    # A terminal punctuation mark alone is NOT a proof of semantic resolution.
    if any(token in RESOLUTION_CUES for token in tail):
        adjustment += .035
    return round(adjustment, 3)


def rank_reviewed(candidates, words, language='en'):
    """Apply transparent cues to selection order, not to the persisted score."""
    candidates = list(candidates)
    bonuses = {(item.first_word, item.last_word):
               editorial_adjustment(words, item, language) for item in candidates}
    return diverse(candidates, adjustments=bonuses)
