"""Synthetic timing categories; no real recordings or raw ASR logging."""
import pytest
from app.local_transcription import WordTimingUnavailable
from test_analysis_plan import whisper_data, parse, zero_words


@pytest.mark.parametrize('offsets,code',[
    ({},'ASR_OFFSETS_MISSING'),
    ({'from':0},'ASR_OFFSETS_MISSING'),
    ({'to':200},'ASR_OFFSETS_MISSING'),
    (None,'ASR_OFFSETS_INVALID'),
    ([],'ASR_OFFSETS_INVALID'),
    ('private-offset-payload','ASR_OFFSETS_INVALID'),
    ({'from':None,'to':200},'ASR_OFFSETS_INVALID'),
    ({'from':True,'to':200},'ASR_OFFSETS_INVALID'),
    ({'from':0.5,'to':200},'ASR_OFFSETS_INVALID'),
    ({'from':0,'to':'private-offset-payload'},'ASR_OFFSETS_INVALID'),
    ({'from':201,'to':200},'ASR_OFFSETS_INVALID'),
    ({'from':-1,'to':200},'ASR_OFFSETS_BEFORE_SOURCE'),
    ({'from':0,'to':2001},'ASR_OFFSETS_AFTER_SOURCE'),
    ({'from':-1,'to':2001},'ASR_OFFSETS_BEYOND_BOTH_BOUNDS'),
    ({'from':-2,'to':-1},'ASR_OFFSETS_BEFORE_SOURCE'),
    ({'from':2001,'to':2002},'ASR_OFFSETS_AFTER_SOURCE'),
    ({'from':-1,'to':-2},'ASR_OFFSETS_INVALID'),
    ({'from':10**100,'to':10**100+1},'ASR_OFFSETS_AFTER_SOURCE'),
])
def test_offset_diagnosis_is_fixed_without_content(offsets,code,caplog,capsys):
    data=whisper_data()
    data['transcription'][0]['tokens'][1]['offsets']=offsets
    with pytest.raises(WordTimingUnavailable) as failed:parse(data)
    assert failed.value.code==code
    assert str(failed.value)=='ASR word timing rejected'
    captured=capsys.readouterr()
    assert not captured.out+captured.err+caplog.text


def test_absent_offsets_are_missing_and_subword_order_is_backward():
    data=whisper_data()
    del data['transcription'][0]['tokens'][1]['offsets']
    with pytest.raises(WordTimingUnavailable) as failed:parse(data)
    assert failed.value.code=='ASR_OFFSETS_MISSING'
    data=whisper_data()
    data['transcription'][0]['tokens'][1]['offsets']={'from':100,'to':200}
    data['transcription'][0]['tokens'][2]['offsets']={'from':99,'to':500}
    with pytest.raises(WordTimingUnavailable) as failed:parse(data)
    assert failed.value.code=='ASR_WORD_ORDER_BACKWARD'


@pytest.mark.parametrize('intervals,duration,code',[
    ([(0,200),(190,210),(180,300)],1000,'ASR_WORD_ORDER_BACKWARD'),
    ([(500,500),(0,1000)],1000,'ASR_WORD_ORDER_BACKWARD'),
    ([(0,500),(479,900)],1000,'ASR_WORD_OVERLAP_EXCESSIVE'),
    ([(0,600),(500,500),(500,1000)],1000,'ASR_WORD_OVERLAP_EXCESSIVE'),
    ([(0,200)]+[(195,201)]*23,1000,'ASR_TIMING_REPAIR_EXCEEDED'),
    ([(0,1000)]+[(1000,1000)]*21,1000,'ASR_TIMING_REPAIR_EXCEEDED'),
    ([(0,0),(0,0)],1,'ASR_TIMING_REPAIR_EXCEEDED'),
])
def test_order_overlap_and_repair_failures_remain_distinct(intervals,duration,code):
    with pytest.raises(WordTimingUnavailable) as failed:zero_words(intervals,duration=duration)
    assert failed.value.code==code


def test_exact_existing_allowance_is_accepted_with_word_scores_and_order_preserved():
    result=zero_words([(0,500),(480,900)],duration=1000)
    assert [(w.start_ms,w.end_ms) for w in result.words]==[(0,500),(500,900)]
    assert [w.text for w in result.words]==['word0','word1']
    assert [w.confidence for w in result.words]==[.8,.8]
    assert result.timestamp_quality=='model_token_estimate_adjusted'


def test_exact_accumulated_allowance_at_source_end_still_passes():
    intervals=[(0,1000)]+[(1000,1000)]*20
    result=zero_words(intervals,duration=1000)
    assert len(result.words)==21
    assert result.words[0].end_ms==980 and result.words[-1].end_ms==1000
    for before,after in zip(intervals,result.words):
        assert 0<=after.start_ms<after.end_ms<=1000
        assert max(abs(before[0]-after.start_ms),abs(before[1]-after.end_ms))<=20
    assert all(a.end_ms<=b.start_ms for a,b in zip(result.words,result.words[1:]))


def test_timing_exception_rejects_content_as_code():
    with pytest.raises(ValueError):WordTimingUnavailable('private transcript payload')


def test_exact_source_boundaries_remain_valid():
    transcript=zero_words([(0,2000)],duration=2000)
    assert transcript.words[0].start_ms==0 and transcript.words[0].end_ms==2000
    assert transcript.timestamp_quality=='model_token_estimate'
