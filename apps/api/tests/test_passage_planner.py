"""Authored source fixtures only; provider calls are mocked and output is closed."""
import json
import httpx
import pytest

from app.analysis_annotations import fingerprint
from app.automatic_clips import suggest
from app.passage_plan import WordRange,apply_passages,units_for,candidates_for
from app.story_planner import passage_prompt,decode_passages,plan_passages,StoryPlannerUnavailable
from test_automatic_clips import transcript


@pytest.fixture
def source():
    original=transcript([f'Lesson {i} explains one practical idea with a complete ending.' for i in range(12)])
    return original,suggest(original,10,'d'*64)


def test_every_word_and_later_idea_reaches_model_without_a_shortlist_filter(source):
    original,base=source;text,units=passage_prompt(original,base);payload=json.loads(text)
    words=' '.join(w.text for w in original.words)
    assert ' '.join(unit['text'] for unit in payload['units'])==words
    assert len(units)<=128 and units[0].first_word==0 and units[-1].last_word==len(original.words)-1
    assert all(a.last_word+1==b.first_word for a,b in zip(units,units[1:]))
    # Find a whole later sentence that the five-option heuristic did not offer.
    offered={(c.first_word,c.last_word) for c in base.candidates}
    candidates=[]
    for i,unit in enumerate(units):
        for j in range(i,len(units)):
            value=WordRange(first_word=unit.first_word,last_word=units[j].last_word)
            try:candidates_for(original,base,(value,))
            except ValueError:continue
            if (value.first_word,value.last_word) not in offered:candidates.append((i,j,value))
    i,j,value=candidates[-1]
    ranges=decode_passages(json.dumps({'clips':[{'first_unit':i,'last_unit':j}]}),original,base,units)
    result=apply_passages(original,base,ranges)
    assert (result.candidates[0].first_word,result.candidates[0].last_word) not in offered
    assert result.candidates[0].source_start_ms==original.words[value.first_word].start_ms
    assert result.candidates[0].source_end_ms==original.words[value.last_word].end_ms
    assert result.review_sha256 is None and result.semantic_quality_verified is False
    assert len(result.candidates)<=5


def test_pathological_punctuation_is_merged_without_truncating_source():
    original=transcript([' '.join(['Word.']*700)])
    # Use a bounded valid duration independent of this helper's long fixture.
    words=tuple(w.model_copy(update={'start_ms':i*200,'end_ms':i*200+180}) for i,w in enumerate(original.words))
    original=original.model_copy(update={'words':words,'source_duration_ms':140000})
    units=units_for(original,15)
    assert len(units)==128
    assert [n for u in units for n in range(u.first_word,u.last_word+1)]==list(range(700))
    text,_=passage_prompt(original,suggest(original,15,'d'*64))
    assert len(text.encode())<=24000


@pytest.mark.parametrize('raw',[
    '{"clips":[{"first_unit":true,"last_unit":1}]}',
    '{"clips":[{"first_unit":"0","last_unit":1}]}',
    '{"clips":[{"first_unit":0.0,"last_unit":1}]}',
    '{"clips":[{"first_unit":-1,"last_unit":1}]}',
    '{"clips":[{"first_unit":127,"last_unit":127}]}',
    '{"clips":[{"first_unit":2,"last_unit":1}]}',
    '{"clips":[{"first_unit":0,"last_unit":30}]}',
    '{"clips":[{"first_unit":0,"last_unit":0,"text":"rewrite"}]}',
    '{"clips":[{"first_unit":0,"last_unit":0}],"explanation":"private"}',
    '{"clips":[],"clips":[{"first_unit":0,"last_unit":0}]}',
    '{"clips":[{"first_unit":0,"last_unit":1},{"first_unit":0,"last_unit":1}]}',
    '{"clips":[{"first_unit":0,"last_unit":0},{"first_unit":1,"last_unit":1},{"first_unit":2,"last_unit":2},{"first_unit":3,"last_unit":3}]}',
])
def test_invalid_model_ranges_never_become_source_edits(source,raw):
    original,base=source;_,units=passage_prompt(original,base)
    with pytest.raises(StoryPlannerUnavailable) as failed:decode_passages(raw,original,base,units)
    assert failed.value.code=='OUTPUT_INVALID'
    assert 'private' not in str(failed.value)


def test_decline_is_explicit_and_does_not_force_a_clip(source):
    original,base=source;_,units=passage_prompt(original,base)
    with pytest.raises(StoryPlannerUnavailable) as failed:decode_passages('{"clips":[]}',original,base,units)
    assert failed.value.code=='MODEL_DECLINED'


def test_missing_source_wrong_identity_long_silence_low_confidence_and_cap_are_rejected(source):
    original,base=source
    with pytest.raises(StoryPlannerUnavailable):passage_prompt(original,base.model_copy(update={'source_sha256':'e'*64}))
    with pytest.raises(ValueError):candidates_for(original,base,(WordRange(first_word=0,last_word=50),))
    with pytest.raises(ValueError):candidates_for(original,base,(WordRange(first_word=0,last_word=0),))
    quiet=transcript(['One useful idea takes time to explain clearly.','Another useful idea takes time to explain clearly.'],gap=3000)
    plan=suggest(quiet,30,'d'*64)
    with pytest.raises(ValueError):candidates_for(quiet,plan,(WordRange(first_word=0,last_word=len(quiet.words)-1),))
    unreliable=transcript(['One useful idea takes time to explain clearly.'],confidence=.1)
    with pytest.raises(ValueError):candidates_for(unreliable,suggest(unreliable,15,'d'*64),(WordRange(first_word=0,last_word=len(unreliable.words)-1),))


def test_single_bounded_transport_request_returns_original_word_ranges_without_raw_output(source,caplog,capsys):
    original,base=source;_,units=passage_prompt(original,base);calls=[]
    def response(request):
        calls.append(request);body=json.loads(request.content)
        assert body['generationConfig']['maxOutputTokens']==128
        assert body['generationConfig']['responseSchema']['properties']['clips']['maxItems']==3
        assert 'ENTIRE source' in body['systemInstruction']['parts'][0]['text']
        assert not request.url.query
        return httpx.Response(200,json={'candidates':[{'finishReason':'STOP','content':{'parts':[
            {'text':'{"clips":[{"first_unit":0,"last_unit":1}]}','thoughtSignature':'opaque'}]}}]})
    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        selected=plan_passages(original,base,api_key='synthetic-key',client=client)
    assert len(calls)==1 and selected.plan_sha256==fingerprint(base)
    assert selected.word_ranges==(WordRange(first_word=units[0].first_word,last_word=units[1].last_word),)
    assert not capsys.readouterr().out and 'Lesson' not in caplog.text and 'opaque' not in caplog.text
