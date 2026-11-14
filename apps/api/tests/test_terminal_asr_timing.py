"""Synthetic terminal estimates, not real speech or acoustic alignment proof."""
from copy import deepcopy

import pytest

from app.analysis_annotations import fingerprint
from app.analysis_plan import Transcript, propose
from app.local_transcription import parse_whisper, WordTimingUnavailable

DURATION=29905


def output(pieces):
    tokens=[dict(text=text,id=100+i,p=.9-i*.01,offsets={'from':start,'to':end})
            for i,(text,start,end) in enumerate(pieces)]
    return {'params':{'translate':False},'result':{'language':'en'},
        'model':{'multilingual':True,'vocab':51865},
        'transcription':[{'text':''.join(t['text'] for t in tokens),'tokens':tokens}]}


def parse(data):
    return parse_whisper(data,source_sha256='a'*64,source_duration_ms=DURATION,
        language='en',model_sha256='b'*64,engine_sha256='c'*64)


def rejected(pieces,code='ASR_OFFSETS_OUT_OF_SOURCE'):
    with pytest.raises(WordTimingUnavailable) as failed:parse(output(pieces))
    assert failed.value.code==code


def test_observed_135_ms_overrun_keeps_25_ms_interval_and_review_disclosure():
    data=output([(' Earlier.',0,10000),(' Ending.',29880,30040)])
    before=deepcopy(data)
    transcript=parse(data)
    assert transcript.source_duration_ms==DURATION
    assert [(w.text,w.start_ms,w.end_ms,w.confidence) for w in transcript.words]==[
        ('Earlier.',0,10000,.9),('Ending.',29880,29905,.89)]
    assert transcript.words[-1].end_ms-transcript.words[-1].start_ms==25
    assert transcript.timestamp_quality=='model_token_estimate_adjusted'
    assert Transcript.model_validate_json(transcript.model_dump_json())==transcript
    proposal=propose(transcript,15)
    assert 'adjusted_word_timestamps' in proposal.warnings
    assert proposal.human_review_required and not proposal.semantic_quality_verified
    # No input mutation, successive application or accumulated drift on retry.
    for _ in range(3):assert fingerprint(parse(data))==fingerprint(transcript)
    assert data==before


@pytest.mark.parametrize('overrun',[1,135,200])
def test_terminal_tolerance_boundary_is_inclusive(overrun):
    transcript=parse(output([(' Ending.',29880,DURATION+overrun)]))
    assert transcript.words[0].end_ms==DURATION
    assert transcript.words[0].start_ms==29880
    assert transcript.timestamp_quality=='model_token_estimate_adjusted'


@pytest.mark.parametrize('start,end,code',[
    (29880,DURATION+201,'ASR_OFFSETS_OUT_OF_SOURCE'),
    (DURATION,DURATION+1,'ASR_OFFSETS_OUT_OF_SOURCE'),
    (DURATION+1,DURATION+135,'ASR_OFFSETS_OUT_OF_SOURCE'),
    (-1,DURATION+135,'ASR_OFFSETS_OUT_OF_SOURCE'),
    (30040,29880,'ASR_OFFSETS_INVALID'),
    (29880.0,30040,'ASR_OFFSETS_INVALID'),
    (True,30040,'ASR_OFFSETS_INVALID'),
    (29880,'30040','ASR_OFFSETS_INVALID'),
    (29880,None,'ASR_OFFSETS_INVALID'),
])
def test_terminal_repair_does_not_accept_invalid_offsets(start,end,code):
    rejected([(' Ending.',start,end)],code)


def test_multiple_pieces_merge_into_final_word_without_text_or_score_loss():
    transcript=parse(output([(' End',29800,29880),('ing',29880,30040),('.',29890,29900)]))
    word=transcript.words[0]
    assert (word.text,word.start_ms,word.end_ms,word.confidence)==('Ending.',29800,DURATION,.88)


def test_piece_reductions_share_one_fixed_budget():
    transcript=parse(output([(' End',29800,30000),('ing.',29880,30010)]))
    assert transcript.words[0].end_ms==DURATION  # 95+105 == 200 ms, not 200 per piece.
    rejected([(' End',29800,30000),('ing.',29880,30011)])
    rejected([(' E',29800,30005),('nd',29810,30005),('ing.',29880,30005)])


def test_word_correction_cannot_hide_a_piece_starting_at_source_end():
    rejected([(' Ending',29880,30040),('.',DURATION,DURATION)])
    rejected([(' Ending',DURATION,DURATION),('.',29880,30040)],'ASR_WORD_ORDER_BACKWARD')


def test_nonterminal_overrun_and_repeated_word_corrections_are_rejected():
    rejected([(' First',29800,29940),(' second.',29880,29950)])
    data=output([(' First.',29800,30040)])
    data['transcription'].extend(output([(' Second.',29890,29900)])['transcription'])
    with pytest.raises(WordTimingUnavailable) as failed:parse(data)
    assert failed.value.code=='ASR_OFFSETS_OUT_OF_SOURCE'


def test_cap_does_not_relax_word_order_or_positive_overlap_allowance():
    rejected([(' Earlier.',29890,29895),(' Ending.',29880,30040)],'ASR_WORD_ORDER_BACKWARD')
    rejected([(' Earlier.',0,29901),(' Ending.',29880,30040)],'ASR_WORD_OVERLAP_EXCESSIVE')
    transcript=parse(output([(' Earlier.',0,29900),(' Ending.',29880,30040)]))
    assert (transcript.words[-1].start_ms,transcript.words[-1].end_ms)==(29900,DURATION)
    assert transcript.words[0].end_ms==29900


def test_accumulated_existing_word_repair_limit_remains_enforced():
    pieces=[(' First',0,200)]+[(' next',195,201)]*23+[(' Ending.',29880,30040)]
    rejected(pieces,'ASR_TIMING_REPAIR_EXCEEDED')


def test_control_and_blank_tokens_after_final_word_do_not_change_its_identity():
    data=output([(' Ending.',29880,30040)])
    data['transcription'][0]['tokens'].extend([
        {'text':'[_EOT_]','id':50257}, {'text':' ','id':1}])
    assert parse(data).words[0].text=='Ending.'


def test_valid_timing_serialization_and_fingerprint_are_unchanged():
    data=output([(' Earlier.',0,10000),(' Ending.',29880,DURATION)])
    expected=Transcript(source_sha256='a'*64,source_duration_ms=DURATION,language='en',
        provider='whisper_cpp',model_sha256='b'*64,engine_sha256='c'*64,
        timestamp_quality='model_token_estimate',words=(
            dict(text='Earlier.',start_ms=0,end_ms=10000,confidence=.9),
            dict(text='Ending.',start_ms=29880,end_ms=DURATION,confidence=.89)))
    assert parse(data).model_dump_json()==expected.model_dump_json()
    assert fingerprint(parse(data))==fingerprint(expected)
    assert 'adjusted_word_timestamps' not in propose(parse(data),15).warnings
