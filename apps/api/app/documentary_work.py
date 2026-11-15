"""Automatic private documentary: directed research -> relevant assets -> source voice.

All network work is in the orchestrator; native rendering stays network-denied.
Interrupted/failed model calls never auto-repeat, even after queue recovery.
"""
import json,os,tempfile,time
from .config import get_settings
from .db import SessionLocal
from .models import ProjectAnalysis,RenderJob
from .analysis_plan import Transcript
from .analysis_annotations import fingerprint
from .documentary_jobs import DocumentarySpec,checkpoint
from .documentary_plan import DocumentaryFailure,DocumentaryPlan
from .documentary_director import direct,select_visuals,headings
from .documentary_render import render_documentary
from .excerpt_jobs import snapshot_source
from .gemini_selection import available
from .automatic_analysis import enabled
from .media import MediaCancelled,RenderDeadlineExceeded
from .commons_assets import CommonsResearch
from .observability import stage
from .story_planner import StoryPlannerUnavailable


def process_documentary(job,source,output,*,should_cancel):
    began=time.monotonic();settings=get_settings();limit=min(300,settings.render_timeout_seconds)
    def check():
        from .budget_control import require_open
        from fastapi import HTTPException
        try:require_open()
        except HTTPException:raise DocumentaryFailure('CONSENT_REQUIRED') from None
        if should_cancel():raise MediaCancelled('Documentary cancelled')
        if time.monotonic()-began>=limit:raise RenderDeadlineExceeded('Documentary deadline exceeded')
        if not available(job['user_id']) or not enabled(job['user_id']):raise DocumentaryFailure('CONSENT_REQUIRED')
    def save(**values):
        return checkpoint(job,lambda old:DocumentarySpec.model_validate({**old.model_dump(),**values}))
    spec=DocumentarySpec.model_validate_json(job['preview_spec_json']);check()
    with SessionLocal() as db:
        parent=db.get(RenderJob,job['preview_parent_id']);row=db.get(ProjectAnalysis,job['preview_parent_id'])
        if not parent or parent.user_id!=job['user_id'] or parent.deleted_at is not None or not row:
            raise MediaCancelled('Documentary source removed')
        transcript=Transcript.model_validate_json(row.transcript_json)
        if fingerprint(transcript)!=spec.transcript_sha256 or transcript.source_sha256!=spec.source_sha256:
            raise DocumentaryFailure('SOURCE_INVALID')
        if spec.last_word>=len(transcript.words) or (transcript.words[spec.first_word].start_ms,
            transcript.words[spec.last_word].end_ms)!=(spec.source_start_ms,spec.source_end_ms):raise DocumentaryFailure('PLAN_INVALID')
        words=[w.text for w in transcript.words[spec.first_word:spec.last_word+1]]
    # Existing copy verifies owner, source path, checksum, bytes and duration.
    with stage('source_fetch') as observed:
        snapshot_source(job,source,should_cancel=should_cancel,spec=spec)
        observed['storage_read_bytes']=spec.source_bytes;observed['storage_write_bytes']=spec.source_bytes
    try:
        with stage('planning'):
            # A previous crash may have left a provider call in flight. Fail closed.
            current=checkpoint(job,lambda old:old)
            if current.visuals_started or (current.direction_started and current.direction is None):
                raise DocumentaryFailure('PLAN_INVALID')
            spec=current
            if spec.direction is None:
                def claim(old):
                    if old.direction_started:raise DocumentaryFailure('PLAN_INVALID')
                    return DocumentarySpec.model_validate({**old.model_dump(),'direction_started':True})
                spec=checkpoint(job,claim);check()
                direction,usage=direct(words,api_key=settings.gemini_api_key,model=spec.model)
                check();spec=save(direction=direction,usage=(*spec.usage,usage))
            direction=spec.direction;opening,closing=headings(direction,words)
            if direction.public_query.upper()=='DECLINE':raise DocumentaryFailure('RIGHTS_UNCONFIRMED')
        # Attempt-local storage is removed on success, failure, cancellation.
        with tempfile.TemporaryDirectory(prefix='research-',dir=source.parent) as work:
            root=Path(work);os.chmod(root,0o700);assets={}
            research=CommonsResearch(consented=True)
            try:
                with stage('planning'):
                    check();references=research.search_context(direction.public_query)
                    check();candidates=research.search(direction.public_query,kind='image')
                    if not candidates:raise DocumentaryFailure('RIGHTS_UNCONFIRMED')
                    def claim_visuals(old):
                        if old.visuals_started:raise DocumentaryFailure('PLAN_INVALID')
                        return DocumentarySpec.model_validate({**old.model_dump(),'visuals_started':True})
                    spec=checkpoint(job,claim_visuals);check()
                    selected,usage=select_visuals(words,candidates,api_key=settings.gemini_api_key,model=spec.model)
                    check();spec=save(usage=(*spec.usage,usage))
                    indexes=list(dict.fromkeys([selected.first,selected.second]));indexes=[i for i in indexes if i]
                    chosen=[]
                    for index in indexes:
                        check();receipt,path=research.download(candidates[index-1],root/'assets')
                        assets[receipt.asset_id]=(receipt,path);chosen.append(receipt.asset_id)
            finally:research.close()
            # Preserve speaker opening/ending and continuous original audio.
            # At most 15 seconds per scene; four scenes cover even a 60s Short.
            frames=spec.output_frames
            # Balanced partitions keep every scene within the 15s maximum.
            cuts=[0,frames//4,frames//2,frames*3//4,frames]
            plan=DocumentaryPlan(source_sha256=spec.source_sha256,source_start_ms=spec.source_start_ms,
                source_end_ms=spec.source_end_ms,output_frames=frames,requested_seconds=spec.requested_seconds,
                scenes=[{'kind':'source','start_frame':cuts[0],'end_frame':cuts[1],'heading':opening},
                    {'kind':'image','start_frame':cuts[1],'end_frame':cuts[2],'asset_id':chosen[0],'motion':direction.motion},
                    {'kind':'image','start_frame':cuts[2],'end_frame':cuts[3],'asset_id':chosen[-1],'motion':'drift_right'},
                    {'kind':'source','start_frame':cuts[3],'end_frame':cuts[4],'heading':closing}])
            check();remaining=int(limit-(time.monotonic()-began))
            if remaining<1:raise RenderDeadlineExceeded('Documentary deadline exceeded')
            with stage('encode') as observed:
                info=render_documentary(source,output,plan,assets,should_cancel=should_cancel,timeout=remaining,
                    max_output_bytes=min(64*1024**2,job['max_render_bytes']))
                measures=info.get('measurements',[])
                observed['cpu_seconds_lower_bound']=sum(m.get('cpu_seconds_lower_bound',0) for m in measures)
                observed['rss_bytes_sampled_max']=max((m.get('rss_bytes_sampled_max',0) for m in measures),default=0)
                observed['frames']=frames
            check();checkpoint(job,lambda old:old)
            manifest={'schema_version':'documentary-sources-1','claims_verified':False,
                'assets':[r.model_dump(mode='json') for r,p in assets.values()],
                'research_sources':references,'storyboard':plan.model_dump(mode='json')}
            raw=json.dumps(manifest,ensure_ascii=False).encode()
            if len(raw)>65536:raise DocumentaryFailure('PLAN_INVALID')
            path=output.parent/'documentary-sources.json'
            with path.open('xb') as handle:os.chmod(path,0o600);handle.write(raw)
            return info
    except StoryPlannerUnavailable:
        # Whitelisted diagnostic code only, never provider/native exception text.
        raise DocumentaryFailure('PLAN_INVALID') from None
    finally:
        source.unlink(missing_ok=True)
