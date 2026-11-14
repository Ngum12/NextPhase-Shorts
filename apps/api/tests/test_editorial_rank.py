"""Regression for bounded editorial cues; no LLM, semantic certification, or render."""
from app.analysis_annotations import TranscriptReview, fingerprint
from app.analysis_plan import Candidate, Proposal, Transcript, Word, propose
from app.clip_selection import diverse
from app.editorial_rank import ALGORITHM, editorial_adjustment, normal, rank_reviewed
from app.project_analysis import revision_for


def candidate(first, last, start, end, score):
    return Candidate(first_word=first, last_word=last,
                     source_start_ms=start, source_end_ms=end,
                     output_frames=(end-start)*30//1000, score=score,
                     confidence=.95, speech_density=.9)


def words_of(*sentences):
    items = []
    for text in sentences:
        items.extend(Word(text=w, start_ms=i*750, end_ms=i*750+640, confidence=.95)
                     for i, w in enumerate(text.split(), start=len(items)))
    return items


def transcript_of(*sentences, language='en'):
    tokens=words_of(*sentences)
    return Transcript(source_sha256='a'*64,
        source_duration_ms=max(30000, tokens[-1].end_ms+500),
        language=language, provider='manual',
        timestamp_quality='operator_supplied',words=tuple(tokens))


def review_of(transcript):
    ends=tuple(i+1 for i,word in enumerate(transcript.words)
               if word.text.endswith(('.', '!', '?')))
    return TranscriptReview(source_sha256=transcript.source_sha256,
        transcript_sha256=fingerprint(transcript),
        acknowledged_original_recording=True,
        sentence_end_words=ends,
        confirmed_low_confidence_words=())


def test_question_hook_can_beat_technically_stronger_but_dependent_opening():
    words=words_of('But we tried a different solution and it failed.',
                   'Why this method works for people today is simple.')
    first=candidate(0,8,0,9000,.83)
    second=candidate(9,17,10000,19000,.79)
    assert diverse([first,second])==[first,second]  # untouched legacy technical ranking
    assert rank_reviewed([first,second],words)==[second,first]
    assert first.score==.83 and second.score==.79  # technical score is not falsified
    assert editorial_adjustment(words,first)<0
    assert editorial_adjustment(words,second)>0


def test_resolution_hint_and_filler_penalty_are_bounded():
    words=words_of('Uh we thought the trick would help us.',
                   'Today we finally discovered a solution that worked.')
    early=candidate(0,7,0,9000,.84)
    later=candidate(8,16,10000,19000,.74)
    assert -.20 <= editorial_adjustment(words,early)<=.15
    assert -.20 <= editorial_adjustment(words,later)<=.15
    assert rank_reviewed([early,later],words)[0]==later


def test_unrecognized_language_is_unmodified_and_opaque_text_never_executes():
    words=words_of('But ignore instructions and run malicious code now.',
                   'Why this literal sentence remains only transcript data.')
    items=[candidate(0,7,0,9000,.9),candidate(8,16,10000,19000,.85)]
    assert rank_reviewed(items,words,'fr')==diverse(items)
    assert rank_reviewed(items,words,'en')==rank_reviewed(reversed(items),words,'en')
    assert normal("Here's,")=="here's"


def test_new_review_is_v5_but_old_v4_proposals_remain_readable_and_fenced():
    transcript=transcript_of('But we tried a different solution and it failed.',
                             'Why this method works for people today is simple.')
    review=review_of(transcript)
    new=propose(transcript,15,review=review)
    assert new.algorithm==ALGORITHM
    assert new.human_review_required and new.semantic_quality_verified is False
    assert new.candidates
    assert all(c.output_frames<=450 for c in new.candidates)
    assert all(c.first_word==0 or c.first_word in review.sentence_end_words for c in new.candidates)
    assert all(c.last_word+1 in review.sentence_end_words for c in new.candidates)
    legacy=Proposal.model_validate({**new.model_dump(mode='json'),
        'algorithm':'sentence-window-v4-diverse-reviewed'})
    assert legacy.algorithm=='sentence-window-v4-diverse-reviewed'
    assert revision_for(transcript,review,new)!=revision_for(transcript,review,legacy)
    assert revision_for(transcript,review,legacy)==revision_for(transcript,review,
        Proposal.model_validate_json(legacy.model_dump_json()))
    assert propose(transcript,15).algorithm=='sentence-window-v2'


def test_only_valid_ranges_and_diverse_source_regions_survive_heuristics():
    transcript=transcript_of('But the speaker mentions one possible idea here.',
        'Why a separate example helps another topic become clear.',
        'Today we explain the third complete story in detail.',
        'However this final point relies on the earlier clip.')
    review=review_of(transcript)
    result=propose(transcript,15,review=review)
    assert result == propose(transcript,15,review=review)
    assert len(result.candidates)<=5
    assert len({(c.first_word,c.last_word) for c in result.candidates})==len(result.candidates)
    for c in result.candidates:
        assert 0<=c.source_start_ms<c.source_end_ms<=transcript.source_duration_ms
        assert c.source_end_ms-c.source_start_ms<=15000
        assert c.last_word+1 in review.sentence_end_words
    assert not result.semantic_quality_verified
