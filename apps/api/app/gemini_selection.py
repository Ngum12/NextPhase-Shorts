"""Explicit transcript-sharing consent, bounded calls and source-bound cached choices.

No provider response text, signatures, keys or transcript copies are persisted.
The transaction is released before contacting Google; late results cannot recreate
removed projects or replace newer analysis. A crashed claim is never auto-retried.
"""
import hashlib
import hmac
import time
from datetime import timedelta
from typing import Literal

from fastapi import HTTPException
from pydantic import Field, UUID4, model_validator

from .analysis_annotations import fingerprint
from .analysis_plan import ClosedModel, Digest, Transcript
from .automatic_clips import for_project
from .config import get_settings
from .models import AuthRateBucket, ProjectAnalysis, utcnow
from . import story_planner
from .passage_plan import WordRange, apply_passages

CONSENT='gemini-transcript-v1'
PASSAGE_CONSENT='gemini-passages-v1'
PRIVATE={'Cache-Control':'private, no-store'}
Code=Literal['INPUT_INVALID','NOT_CONFIGURED','MODEL_UNSUPPORTED','PROMPT_TOO_LARGE',
    'PROVIDER_AUTH_FAILED','PROVIDER_RATE_LIMITED','PROVIDER_UNAVAILABLE',
    'OUTPUT_INVALID','MODEL_DECLINED','DAILY_LIMIT','PENDING_EXPIRED']


class Request(ClosedModel):
    revision: Digest
    idempotency_key: UUID4
    mode: Literal['shortlist','passages']='shortlist'
    consent_version: Literal['gemini-transcript-v1','gemini-passages-v1']
    acknowledged_google_transcript_sharing: bool=Field(strict=True)

    @model_validator(mode='after')
    def consent_required(self):
        if self.consent_version!=(PASSAGE_CONSENT if self.mode=='passages' else CONSENT):
            raise ValueError('Consent does not match planning mode')
        if not self.acknowledged_google_transcript_sharing:raise ValueError("Explicit transcript sharing consent is required")
        return self


class Cached(ClosedModel):
    schema_version: Literal['gemini-selection-1','gemini-selection-2']='gemini-selection-1'
    planning_mode: Literal['shortlist','passages']='shortlist'
    word_ranges: tuple[WordRange,...] | None=Field(default=None,min_length=1,max_length=3)
    base_plan_sha256: Digest
    request_id: UUID4
    model: Literal['gemini-3.1-flash-lite']='gemini-3.1-flash-lite'
    status: Literal['pending','selected','fallback']
    consent_version: Literal['gemini-transcript-v1','gemini-passages-v1']=CONSENT
    consent_at: int=Field(strict=True,ge=0)
    candidate_id: int|None=Field(default=None,strict=True,ge=1,le=5)
    code: Code|None=None
    input_tokens: int|None=Field(default=None,strict=True,ge=0,le=10000000)
    output_tokens: int|None=Field(default=None,strict=True,ge=0,le=10000000)
    wall_ms: int|None=Field(default=None,strict=True,ge=0,le=90000)

    @model_validator(mode='after')
    def consistent(self):
        passages=self.planning_mode=='passages'
        if (self.schema_version=='gemini-selection-2')!=passages:raise ValueError('Invalid planning schema')
        if self.consent_version!=(PASSAGE_CONSENT if passages else CONSENT):raise ValueError('Invalid planning consent')
        if (passages and self.status=='selected')!=(self.word_ranges is not None):raise ValueError('Invalid passage proof')
        if passages and self.candidate_id not in (None,1):raise ValueError('Invalid passage index')
        if (self.status=='selected')!=(self.candidate_id is not None):raise ValueError('Invalid selection')
        if (self.status=='fallback')!=(self.code is not None):raise ValueError('Invalid fallback')
        return self


def available(owner):
    s=get_settings()
    return bool(s.gemini_planning_enabled and s.gemini_free_tier_confirmed and s.gemini_api_key
        and s.english_review_enabled and owner in s.english_review_user_ids)


def cached(row,base):
    raw=row.gemini_selection_json
    if raw is None:return None
    try:
        if len(raw.encode())>4096:raise ValueError()
        value=Cached.model_validate_json(raw)
        if value.base_plan_sha256!=fingerprint(base):return None
        if value.planning_mode=='shortlist' and value.candidate_id is not None and value.candidate_id>len(base.candidates):raise ValueError()
        if value.word_ranges is not None:
            apply_passages(Transcript.model_validate_json(row.transcript_json),base,value.word_ranges)
        return value
    except ValueError:
        raise HTTPException(409,'Gemini selection could not be verified; use standard suggestions',headers=PRIVATE) from None


def effective(row,parent):
    base=for_project(row,parent);value=cached(row,base)
    if value is None or value.status=='pending':
        raise HTTPException(409,'Gemini selection is not ready; use standard suggestions',headers=PRIVATE)
    if value.status=='selected':
        if value.planning_mode=='passages':
            base=apply_passages(Transcript.model_validate_json(row.transcript_json),base,value.word_ranges)
        else:
            index=value.candidate_id-1
            base=base.model_copy(update={'candidates':(base.candidates[index],)+base.candidates[:index]+base.candidates[index+1:]})
    identity=f'{fingerprint(base)}:gemini:{value.model}:{value.request_id}:{value.status}'
    if value.planning_mode=='passages':identity+=':passages'
    return base,hashlib.sha256(identity.encode()).hexdigest(),value


def result(row,parent):
    base=for_project(row,parent);value=cached(row,base)
    if value is None:raise HTTPException(409,'No current Gemini selection',headers=PRIVATE)
    if value.status=='pending':return {'job_id':parent.id,'gemini_status':'pending'}
    plan,revision,value=effective(row,parent)
    return {**plan.model_dump(mode='json'),'job_id':parent.id,'revision':revision,
        'gemini_status':value.status,'gemini_model':value.model,'gemini_code':value.code,
        'gemini_strategy':value.planning_mode,
        'gemini_candidate_count':len(value.word_ranges) if value.word_ranges else (1 if value.status=='selected' else 0)}


def budget(db,owner):
    """Caller holds owner, then global lock. Counts failures; no refund or retry."""
    from .capacity import lock
    lock(db)
    now=utcnow();day=now.date().isoformat()
    expires=now.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)
    s=get_settings();entries=[]
    for label,identity,limit in [('global','all',min(20,s.gemini_daily_limit)),
                               ('owner',owner,min(5,s.gemini_owner_daily_limit))]:
        key=hmac.new(s.jwt_secret.encode(),f'gemini:{label}:{day}:{identity}'.encode(),hashlib.sha256).hexdigest()
        row=db.get(AuthRateBucket,key)
        if limit<=0 or (row is not None and row.attempts>=limit):return False
        entries.append((key,row))
    for key,row in entries:
        if row is None:db.add(AuthRateBucket(key=key,attempts=1,expires_at=expires))
        else:row.attempts+=1
    return True


def start(db,owner,job_id,payload):
    from .project_analysis import owned_project,document
    parent=owned_project(db,owner,job_id)
    if parent.preview_parent_id is not None or parent.media_backend!='local':
        raise HTTPException(409,'Gemini requires an original local project',headers=PRIVATE)
    row=db.get(ProjectAnalysis,job_id)
    if row is None:raise HTTPException(404,'No English transcript is ready',headers=PRIVATE)
    document(row);base=for_project(row,parent)
    if fingerprint(base)!=payload.revision:raise HTTPException(409,'Suggestions changed; refresh first',headers=PRIVATE)
    if not available(owner):raise HTTPException(409,'Gemini is unavailable; use standard suggestions',headers=PRIVATE)
    old=cached(row,base)
    # A new explicit passage-mode consent may upgrade a completed legacy cache.
    # Never replace a live claim or spend again for unchanged passage analysis.
    if old is not None and (old.status=='pending' or payload.mode=='shortlist' or old.planning_mode=='passages'):
        if old.status=='pending' and int(time.time())-old.consent_at>=90:
            row.gemini_selection_json=old.model_copy(update={'status':'fallback','code':'PENDING_EXPIRED'}).model_dump_json()
        # Cache successes and failures. Reopening or retrying never spends another
        # call for this unchanged plan. A new project/analysis can request anew.
        output=result(row,parent);db.commit();return output
    from .budget_control import require_open
    require_open()
    if not base.candidates and payload.mode=='shortlist':raise HTTPException(409,'No suitable clip is available',headers=PRIVATE)
    value=Cached(base_plan_sha256=fingerprint(base),request_id=payload.idempotency_key,
        schema_version='gemini-selection-2' if payload.mode=='passages' else 'gemini-selection-1',
        planning_mode=payload.mode,consent_version=payload.consent_version,
        status='pending',consent_at=int(time.time()))
    if not budget(db,owner):value=value.model_copy(update={'status':'fallback','code':'DAILY_LIMIT'})
    row.gemini_selection_json=value.model_dump_json()
    transcript=Transcript.model_validate_json(row.transcript_json)
    output=result(row,parent);db.commit()
    if value.status=='fallback':return output
    # No database locks or render slots held over external I/O.
    s=get_settings()
    try:
        planner=story_planner.plan_passages if payload.mode=='passages' else story_planner.select
        selection=planner(transcript,base,api_key=s.gemini_api_key,model=s.gemini_model)
        if selection.plan_sha256!=fingerprint(base):raise story_planner.StoryPlannerUnavailable('OUTPUT_INVALID')
        if payload.mode=='passages':
            if selection.candidate_id!=1:raise story_planner.StoryPlannerUnavailable('OUTPUT_INVALID')
            try:apply_passages(transcript,base,selection.word_ranges or ())
            except (ValueError,TypeError):raise story_planner.StoryPlannerUnavailable('OUTPUT_INVALID') from None
        elif not 1<=selection.candidate_id<=len(base.candidates):raise story_planner.StoryPlannerUnavailable('OUTPUT_INVALID')
        completed=Cached.model_validate({**value.model_dump(), 'status':'selected','candidate_id':selection.candidate_id,
            'word_ranges':selection.word_ranges if payload.mode=='passages' else None,
            'input_tokens':selection.input_tokens,'output_tokens':selection.output_tokens,
            'wall_ms':min(90000,max(0,int(selection.wall_seconds*1000)))})
    except story_planner.StoryPlannerUnavailable as exc:
        completed=value.model_copy(update={'status':'fallback','code':exc.code})
    # Expire the identity map; deletion/account cleanup wins while Google runs.
    db.expire_all()
    parent=owned_project(db,owner,job_id);row=db.get(ProjectAnalysis,job_id)
    if row is None:raise HTTPException(404,'Analysis was removed',headers=PRIVATE)
    document(row);current=cached(row,for_project(row,parent))
    if current!=value:raise HTTPException(409,'Analysis changed while selecting; refresh first',headers=PRIVATE)
    row.gemini_selection_json=completed.model_dump_json();output=result(row,parent);db.commit();return output
