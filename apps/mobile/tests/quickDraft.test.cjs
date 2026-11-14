const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const id='11111111-1111-4111-8111-111111111111',revision='a'.repeat(64);
function harness(){
  class ApiError extends Error{constructor(status,message){super(message);this.status=status;}}
  const state={review:{},supported:true,layout:true,clean:true,soft:true,manual:true,portrait:true,
    candidates:[{output_frames:900,source_start_ms:5000,source_end_ms:35000}],save:null,captionCalls:0,captionCandidate:1,calls:[],error:null,words:[],audioTiming:null,sceneAnalysis:null};
  const defaults={framing:'fit',captions:true,caption_size:'standard',caption_color:'white',
    caption_position:'lower',voice:'original',audio_edges:'original'};
  const deps={
    './api':{ApiError,api:async(p,t)=>{assert.equal(p,'/api/v1/me');state.calls.push({me:t});return {id:'22222222-2222-4222-8222-222222222222'};}},
    './analysis':{getEnglishAnalysis:async(p,t)=>{state.calls.push({analysis:p,token:t});return {
      job_id:p,revision,review:state.review,polished_preview_supported:state.supported,
      clean_captions_supported:state.clean,portrait_framing_supported:state.portrait,
      soft_audio_edges_supported:state.soft,manual_crop_focus_supported:state.manual,
      proposal:{candidates:state.candidates},transcript:{words:state.words},audio_timing:state.audioTiming,scene_analysis:state.sceneAnalysis,
    };}},
    './polish':{defaultPolish:defaults,loadPolishPreset:async()=>state.save,
      getCaptionDraft:async(p,t,rev,n)=>{state.captionCalls++;assert.equal(p,id);assert.equal(rev,revision);assert.equal(n,state.captionCandidate);
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


test('listing three ranked candidate choices is read-only and retains server order',async()=>{
 const h=harness();h.state.candidates=[1,2,3,4,5].map((n)=>({
   output_frames:n*150,source_start_ms:n*6000,source_end_ms:n*6000+n*5000,
 }));
 const result=await h.actions.listQuickDrafts(id,'token');
 assert.equal(result.needsReview,false);
 assert.equal(result.choices.length,3);
 assert.deepEqual(Array.from(result.choices,c=>c.candidate),[1,2,3]);
 assert.equal(result.choices[1].source_start_ms,12000);
 assert.equal(h.state.captionCalls,0);
 assert.equal(h.state.calls.filter(x=>x.render).length,0);
 assert.equal(h.state.calls.filter(x=>x.me).length,0);
});
test('selected second clip only preflights and renders candidate two',async()=>{
 const h=harness();h.state.candidates=[
  {output_frames:450,source_start_ms:0,source_end_ms:15000},
  {output_frames:600,source_start_ms:16000,source_end_ms:36000},
  {output_frames:300,source_start_ms:37000,source_end_ms:47000},
 ];h.state.captionCandidate=2;
 const result=await h.actions.prepareQuickDraft(id,'token',2);
 assert.equal(result.plan.candidate,2);
 assert.equal(result.plan.duration_ms,20000);
 assert.equal(h.state.captionCalls,1);
 assert(!h.state.calls.some(x=>x.render));
 await h.actions.renderQuickDraft(id,'token',result.plan);
 assert.equal(h.state.calls.find(x=>x.render).render[3],2);
});
test('rejects out-of-range choice before making requests',async()=>{
 const h=harness();await assert.rejects(h.actions.prepareQuickDraft(id,'token',4),/Choose one/);
 assert.equal(h.state.calls.length,0);
});
test('missing review offers human review without render or preflight',async()=>{
 const h=harness();h.state.review=null;
 assert.equal((await h.actions.listQuickDrafts(id,'token')).needsReview,true);
 assert.equal(h.state.captionCalls,0);assert(!h.state.calls.some(x=>x.render));
});


test('shows private, bounded spoken openings/endings and warns about dependent openings',async()=>{
 const h=harness();
 h.state.words=['But,','what','we','discovered','is','that','shorts','need','a','clear','opening','and','a','natural','ending',
   'Next','we','should','choose','the','right','story','segment','instead','of','using','the','very','first','seconds'].map(text=>({text}));
 h.state.candidates=[
   {first_word:0,last_word:14,source_start_ms:0,source_end_ms:15000,output_frames:450},
   {first_word:15,last_word:28,source_start_ms:15000,source_end_ms:30000,output_frames:450},
 ];
 const result=await h.actions.listQuickDrafts(id,'token');
 assert.equal(result.needsReview,false);assert.equal(result.choices.length,2);
 assert.match(result.choices[0].opening,/^But, what we discovered/);
 assert.match(result.choices[0].ending,/natural ending/);
 assert.match(result.choices[0].context_warning,/depend on earlier speech/);
 assert.equal(result.choices[1].context_warning,null);
 assert.match(result.choices[1].opening,/^Next we should choose/);
 assert.equal(h.state.calls.filter(x=>x.render).length,0);
 assert.equal(h.state.captionCalls,0);
 assert.equal(h.state.calls.filter(x=>x.me).length,0);
});
test('snippets are capped to 96 Unicode codepoints and do not include controls',async()=>{
 const h=harness();
 h.state.words=[{text:'I'},...Array.from({length:20},(_,i)=>({text:i===0?'🙂'.repeat(70):'clear'}))];
 h.state.candidates=[{first_word:0,last_word:20,source_start_ms:0,source_end_ms:20000,output_frames:600}];
 const result=await h.actions.listQuickDrafts(id,'token');
 const choice=result.choices[0];
 assert(Array.from(choice.opening).length<=96);
 assert(choice.opening.endsWith('…'));
 assert(!/[\x00-\x1f\x7f]/.test(choice.opening));
 assert(!choice.opening.includes('\ufffd'));
});
test('missing or invalid word ranges never fabricate spoken hooks',async()=>{
 const h=harness();
 h.state.words=[{text:'Known'}];h.state.candidates=[
   {first_word:0,last_word:9,source_start_ms:0,source_end_ms:12000,output_frames:360},
 ];
 const choice=(await h.actions.listQuickDrafts(id,'token')).choices[0];
 assert.equal(choice.opening,null);
 assert.equal(choice.ending,null);
 assert.equal(choice.context_warning,null);
 assert(!h.state.calls.some(x=>x.render));
});
test('preview preparation uses newly fetched candidate words and preserves single explicit render',async()=>{
 const h=harness();
 h.state.words=['This','is','a','sample','for','our','next','private','Short'].map(text=>({text}));
 h.state.candidates=[{first_word:0,last_word:8,source_start_ms:2000,source_end_ms:11000,output_frames:270}];
 const first=await h.actions.listQuickDrafts(id,'token');
 assert.match(first.choices[0].opening,/^This is/);
 const prepared=await h.actions.prepareQuickDraft(id,'token',1);
 assert.match(prepared.plan.opening,/^This is/);
 assert.equal(prepared.plan.candidate,1);
 assert(!h.state.calls.some(x=>x.render));
 await h.actions.renderQuickDraft(id,'token',prepared.plan);
 assert.equal(h.state.calls.filter(x=>x.render).length,1);
});


test('read-only choices show sampled quiet audio and scene-boundary cues without rendering',async()=>{
 const h=harness();
 h.state.words=['We','are','testing','shorts','from','a','reviewed','speech','clip'].map(text=>({text}));
 h.state.candidates=[
  {first_word:0,last_word:8,source_start_ms:10000,source_end_ms:20000,output_frames:300},
 ];
 h.state.audioTiming={quiet_intervals:[
  {start_ms:9700,end_ms:10500},{start_ms:19500,end_ms:20100},
 ]};
 h.state.sceneAnalysis={status:'available',analyzed_duration_ms:18000,
  changes:[{at_ms:10000,delta_milli:200},{at_ms:19500,delta_milli:280}]};
 const choice=(await h.actions.listQuickDrafts(id,'token')).choices[0];
 assert(choice.boundary_cues.some(x=>x.includes('Low-volume audio near opening')));
 assert(choice.boundary_cues.some(x=>x.includes('Low-volume audio near ending')));
 assert(choice.boundary_cues.some(x=>x.includes('visual change near opening')));
 assert(choice.boundary_cues.some(x=>x.includes('Visual samples do not cover')));
 assert.equal(choice.boundary_cues.length,4);
 assert.equal(h.state.captionCalls,0);assert(!h.state.calls.some(x=>x.render));
});
test('unavailable scene evidence is not mistaken for no changes',async()=>{
 const h=harness();
 h.state.audioTiming=null;h.state.sceneAnalysis={status:'unavailable',changes:[],analyzed_duration_ms:0};
 const choice=(await h.actions.listQuickDrafts(id,'token')).choices[0];
 assert.equal(choice.boundary_cues.length,0);
 assert(!h.state.calls.some(x=>x.render));
});
