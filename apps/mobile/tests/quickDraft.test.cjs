const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const id='11111111-1111-4111-8111-111111111111',revision='a'.repeat(64);
function harness(){
  class ApiError extends Error{constructor(status,message){super(message);this.status=status;}}
  const state={review:{},supported:true,layout:true,clean:true,soft:true,manual:true,portrait:true,
    candidates:[{output_frames:900,source_start_ms:5000,source_end_ms:35000}],save:null,captionCalls:0,calls:[],error:null};
  const defaults={framing:'fit',captions:true,caption_size:'standard',caption_color:'white',
    caption_position:'lower',voice:'original',audio_edges:'original'};
  const deps={
    './api':{ApiError,api:async(p,t)=>{assert.equal(p,'/api/v1/me');state.calls.push({me:t});return {id:'22222222-2222-4222-8222-222222222222'};}},
    './analysis':{getEnglishAnalysis:async(p,t)=>{state.calls.push({analysis:p,token:t});return {
      job_id:p,revision,review:state.review,polished_preview_supported:state.supported,
      clean_captions_supported:state.clean,portrait_framing_supported:state.portrait,
      soft_audio_edges_supported:state.soft,manual_crop_focus_supported:state.manual,
      proposal:{candidates:state.candidates},
    };}},
    './polish':{defaultPolish:defaults,loadPolishPreset:async()=>state.save,
      getCaptionDraft:async(p,t,rev,n)=>{state.captionCalls++;assert.equal(p,id);assert.equal(rev,revision);assert.equal(n,1);
        if(state.error)throw state.error;
        if(!state.layout)throw new ApiError(422,'Caption layout unavailable');
        return {duration_ms:30000,cues:[{start_ms:0,end_ms:500,text:'My real words.'}]};},
      requestPolishedPreview:async(...args)=>{state.calls.push({render:args});return {id:'draft-preview',status:'queued'};}}
  };
  const exports={};const compiled=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/quickDraft.ts'),'utf8'),
    {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(compiled,{exports,require:name=>{assert(deps[name],name);return deps[name];}});
  return {state,defaults,actions:exports,ApiError};
}
test('does not render or load settings if review is absent or has no candidate',async()=>{
 const h=harness();h.state.review=null;
 assert.equal((await h.actions.prepareQuickDraft(id,'token')).needsReview,true);
 assert.equal(h.state.calls.length,1);
 h.state.review={};h.state.candidates=[];
 assert.equal((await h.actions.prepareQuickDraft(id,'token')).needsReview,true);
 assert.equal(h.state.captionCalls,0);
 assert(!h.state.calls.some(x=>x.render));
});
test('first server-ranked reviewed clip becomes a private captioned preview without editing transcript',async()=>{
 const h=harness();
 const result=await h.actions.prepareQuickDraft(id,'token');
 assert.equal(result.needsReview,false);
 const plan=result.plan;
 assert.equal(plan.candidate,1);assert.equal(plan.duration_ms,30000);
 assert.equal(plan.options.framing,'fit');assert.equal(plan.options.captions,true);
 assert.equal(plan.options.voice,'original');assert.equal(h.state.captionCalls,1);
 assert(!h.state.calls.some(x=>x.render));
 await h.actions.renderQuickDraft(id,'token',plan);
 const sent=h.state.calls.find(x=>x.render).render;
 assert.equal(sent[0],id);assert.equal(sent[2],revision);assert.equal(sent[3],1);
 assert.equal(sent[5],null);assert.equal(sent[6],30000);assert.equal(sent[7],false);
});
test('saved polish preset is retained but unsupported server choices are safely downgraded',async()=>{
 const h=harness();h.state.soft=false;h.state.manual=false;
 h.state.save={...h.defaults,framing:'fill-right',voice:'level',audio_edges:'soft',caption_color:'yellow'};
 const result=await h.actions.prepareQuickDraft(id,'token');
 assert.equal(result.plan.options.framing,'fill-center');
 assert.equal(result.plan.options.audio_edges,'original');
 assert.equal(result.plan.options.voice,'level');
 assert.equal(result.plan.options.caption_color,'yellow');
 h.state.portrait=false;const old=await h.actions.prepareQuickDraft(id,'token');
 assert.equal(old.plan.options.framing,'fit');
});
test('caption layout 422 yields a clearly disclosed no-caption preview; other errors abort',async()=>{
 const h=harness();h.state.layout=false;
 const result=await h.actions.prepareQuickDraft(id,'token');
 assert.equal(result.plan.options.captions,false);
 assert.match(result.plan.notice,/Captions do not fit/);
 assert(!h.state.calls.some(x=>x.render));
 h.state.error=new Error('Network unavailable');
 await assert.rejects(h.actions.prepareQuickDraft(id,'token'),/Network unavailable/);
 assert(!h.state.calls.some(x=>x.render));
});
test('unsupported polished backend is never sent a new render request',async()=>{
 const h=harness();h.state.supported=false;
 await assert.rejects(h.actions.prepareQuickDraft(id,'token'),/does not support polished previews/);
 assert.equal(h.state.captionCalls,0);
 assert(!h.state.calls.some(x=>x.render));
});
