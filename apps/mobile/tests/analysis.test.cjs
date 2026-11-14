const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path');
function document(){return {
 job_id:'project-1',revision:'a'.repeat(64),transcript_sha256:'b'.repeat(64),render_enabled:false,
 transcript:{language:'en',source_sha256:'c'.repeat(64),source_duration_ms:15000,words:[
  {text:'Original',start_ms:0,end_ms:6000,confidence:.2},
  {text:'speech.',start_ms:6000,end_ms:12000,confidence:.9},
 ]},review:null,proposal:{requested_seconds:15,warnings:['estimated_timestamps'],candidates:[
  {first_word:0,last_word:1,source_start_ms:0,source_end_ms:12000,output_frames:360},
 ]},
};}
function review(){return {schema_version:'transcript-review-1',source_sha256:'c'.repeat(64),
 transcript_sha256:'b'.repeat(64),acknowledged_original_recording:true,
 sentence_end_words:[2],confirmed_low_confidence_words:[1]};}
function fixture(){
 const calls=[],state={value:document(),error:null};
  const api={BASE:'https://example.invalid',api:async(route,token)=>{calls.push({route,token});if(state.error)throw state.error;return structuredClone(route.includes('/automatic-clips')?state.automatic:route.endsWith('/gemini-selection')?state.gemini:state.value);},
  authenticatedFetch:async(token,url,init)=>{calls.push({token,url,init});if(state.error)throw state.error;return structuredClone(state.gemini||state.value);},extract:async response=>response};
 const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/analysis.ts'),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const visual={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/sceneAnalysis.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:visual});
 const timing={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/audioTiming.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:timing});
 const exports={};vm.runInNewContext(code,{exports,require:name=>name==='expo-crypto'?{randomUUID:()=> '11111111-1111-4111-8111-111111111111'}:name==='./sceneAnalysis'?visual:name==='./audioTiming'?timing:api,process:{env:{EXPO_PUBLIC_ENGLISH_REVIEW:'true'}}});
 return {actions:exports,state,calls};
}

function autoPlan(value){return {
 job_id:value.job_id,revision:'d'.repeat(64),base_revision:value.revision,automatic:true,
 algorithm:'automatic-speech-clips-v1',source_sha256:value.transcript.source_sha256,
 source_duration_ms:value.transcript.source_duration_ms,transcript_sha256:value.transcript_sha256,
 review_sha256:null,requested_seconds:value.proposal.requested_seconds,
 human_review_required:true,semantic_quality_verified:false,
 candidates:structuredClone(value.proposal.candidates),warnings:['estimated_boundaries'],
};}
test('automatic choices are source/transcript/revision bound without manufacturing human review',async()=>{
 const f=fixture();f.state.automatic=autoPlan(f.state.value);
 const result=await f.actions.getAutomaticClips('project-1','token',f.state.value);
 assert.equal(result.automatic_draft,true);assert.equal(result.review,null);
 assert.equal(result.revision,'d'.repeat(64));assert.equal(f.calls.length,1);
});
for(const [name,mutate] of Object.entries({
 'other project':p=>p.job_id='other',
 'stale review':p=>p.base_revision='e'.repeat(64),
 'other source':p=>p.source_sha256='e'.repeat(64),
 'other transcript':p=>p.transcript_sha256='e'.repeat(64),
 'claimed human review':p=>p.review_sha256='e'.repeat(64),
 'claimed semantic verification':p=>p.semantic_quality_verified=true,
 'invalid candidate':p=>p.candidates[0].source_end_ms=999999,
 'unknown algorithm':p=>p.algorithm='untrusted',
}))test('automatic choices refuse '+name,async()=>{
 const f=fixture();f.state.automatic=autoPlan(f.state.value);mutate(f.state.automatic);
 await assert.rejects(f.actions.getAutomaticClips('project-1','token',f.state.value));
});
test('review reads the authenticated project route without altering source data',async()=>{
 const f=fixture(),before=structuredClone(f.state.value);const value=await f.actions.getEnglishAnalysis('project-1','private-session');
 assert.equal(f.actions.englishReviewVisible,true);assert.deepEqual(value,before);
 assert.equal(f.calls[0].route,'/api/v1/jobs/project-1/analysis');assert.equal(f.calls[0].token,'private-session');
});
test('save sends only revision and human annotations through the authenticated PUT',async()=>{
 const f=fixture(),annotation=review();f.state.value.review=annotation;
 await f.actions.saveEnglishReview('project-1','private-session','a'.repeat(64),annotation);
 const call=f.calls[0];assert.equal(call.url,'https://example.invalid/api/v1/jobs/project-1/analysis/review');
 assert.equal(call.init.method,'PUT');assert.deepEqual(JSON.parse(call.init.body),{revision:'a'.repeat(64),review:annotation});
 assert(!call.url.includes('private-session'));assert(!call.url.includes('Original'));
});
test('save errors and offline failures propagate without implicit write replay',async()=>{
 for(const status of [401,409,429,503]){const f=fixture();f.state.error=Object.assign(new Error('fixed failure'),{status});
  await assert.rejects(f.actions.saveEnglishReview('project-1','token','a'.repeat(64),review()),/fixed failure/);
  assert.equal(f.calls.length,1);}
});
test('a response for a different project cannot populate this review',async()=>{
 const f=fixture();f.state.value.job_id='foreign-project';
 await assert.rejects(f.actions.getEnglishAnalysis('project-1','token'),/different project/);
 await assert.rejects(f.actions.saveEnglishReview('project-1','token','a'.repeat(64),review()),/different project/);
});
const mutations={
 'French response':d=>{d.transcript.language='fr';},
 'oversized word inventory':d=>{d.transcript.words=Array(1001).fill(d.transcript.words[0]);},
 'nonfinite confidence':d=>{d.transcript.words[0].confidence=NaN;},
 'boolean confidence':d=>{d.transcript.words[0].confidence=true;},
 'foreign word references':d=>{d.proposal.candidates[0].last_word=3;},
 'negative source time':d=>{d.transcript.words[0].start_ms=-1;},
 'word outside source':d=>{d.transcript.words[1].end_ms=16000;},
 'inconsistent frame duration':d=>{d.proposal.candidates[0].output_frames=150;},
 'requested duration exceeded':d=>{d.proposal.requested_seconds=5;},
 'confirmation of an unflagged word':d=>{d.review=review();d.review.confirmed_low_confidence_words=[2];},
 'duplicate word confirmations':d=>{d.review=review();d.review.confirmed_low_confidence_words=[1,1];},
 'changed transcript identity':d=>{d.review=review();d.review.transcript_sha256='0'.repeat(64);},
 'missing acknowledgement':d=>{d.review=review();d.review.acknowledged_original_recording=false;},
 'unexpected render activation':d=>{d.render_enabled=true;},
};
for(const [label,mutate] of Object.entries(mutations))test('refuses '+label,async()=>{
 const f=fixture();mutate(f.state.value);
 await assert.rejects(f.actions.getEnglishAnalysis('project-1','token'));
});


function timing(){return {schema_version:'audio-timing-1',source_sha256:'c'.repeat(64),source_duration_ms:15000,
 audio_duration_ms:14000,alignment:'normalized_pcm_first_pts_zero',method:'pcm_window_energy',window_ms:20,
 threshold_dbfs:-40,minimum_quiet_ms:500,quiet_intervals:[{start_ms:0,end_ms:1000},{start_ms:13000,end_ms:14000}]};}
test('source-bound audio timing is optional for legacy reviews and retained for new ones',async()=>{
 const f=fixture();f.state.value.audio_timing=timing();
 const value=await f.actions.getEnglishAnalysis('project-1','token');assert.equal(value.audio_timing.quiet_intervals.length,2);
 f.state.value.audio_timing=null;assert.equal((await f.actions.getEnglishAnalysis('project-1','token')).audio_timing,null);
});
for(const [name,mutate] of Object.entries({
 'foreign source':v=>v.source_sha256='0'.repeat(64),
 'different duration':v=>v.source_duration_ms=16000,
 'audio outside source':v=>v.audio_duration_ms=16000,
 'overlapping quiet passages':v=>v.quiet_intervals=[{start_ms:0,end_ms:1000},{start_ms:500,end_ms:1500}],
 'outside audio':v=>v.quiet_intervals=[{start_ms:13000,end_ms:15000}],
 'short quiet passage':v=>v.quiet_intervals=[{start_ms:0,end_ms:499}],
 'different method':v=>v.method='speech_detector',
 'boolean window':v=>v.window_ms=true,
 'oversized intervals':v=>v.quiet_intervals=Array(361).fill({start_ms:0,end_ms:1000}),
}))test('invalid audio timing refuses '+name,async()=>{
 const f=fixture();f.state.value.audio_timing=timing();mutate(f.state.value.audio_timing);
 await assert.rejects(f.actions.getEnglishAnalysis('project-1','token'),/Audio timing could not be verified/);
});


function scenes(){return {schema_version:'scene-analysis-1',source_sha256:'c'.repeat(64),source_duration_ms:15000,
 status:'available',issue:null,method:'sampled_rgb_difference',alignment:'ffmpeg_fps_start_zero',sample_interval_ms:500,
 proxy_width:64,proxy_height:36,threshold_milli:180,minimum_gap_ms:1000,sample_count:30,analyzed_duration_ms:15000,
 changes:[{at_ms:3000,delta_milli:800}]};}
test('visual metadata is optional and unavailable guidance still permits transcript review',async()=>{
 const f=fixture();f.state.value.scene_analysis=scenes();
 assert.equal((await f.actions.getEnglishAnalysis('project-1','token')).scene_analysis.changes.length,1);
 f.state.value.scene_analysis={...scenes(),status:'unavailable',issue:'decode_or_resource_limit',sample_count:0,analyzed_duration_ms:0,changes:[]};
 assert.equal((await f.actions.getEnglishAnalysis('project-1','token')).scene_analysis.status,'unavailable');
 f.state.value.scene_analysis=null;assert.equal((await f.actions.getEnglishAnalysis('project-1','token')).scene_analysis,null);
});
for(const [name,mutate] of Object.entries({
 'foreign source':v=>v.source_sha256='0'.repeat(64),
 'wrong duration':v=>v.source_duration_ms=16000,
 'too many samples':v=>v.sample_count=33,
 'wrong coverage':v=>v.analyzed_duration_ms=9000,
 'event outside source':v=>v.changes=[{at_ms:15000,delta_milli:900}],
 'off-grid event':v=>v.changes=[{at_ms:1250,delta_milli:900}],
 'closely repeated events':v=>v.changes=[{at_ms:1000,delta_milli:900},{at_ms:1500,delta_milli:900}],
 'bad delta':v=>v.changes=[{at_ms:1000,delta_milli:1001}],
 'different method':v=>v.method='semantic_scene_detection',
 'unavailable with false coverage':v=>{v.status='unavailable';v.issue='decode_or_resource_limit';},
}))test('visual metadata rejects '+name,async()=>{
 const f=fixture();f.state.value.scene_analysis=scenes();mutate(f.state.value.scene_analysis);
 await assert.rejects(f.actions.getEnglishAnalysis('project-1','token'),/Visual change guidance could not be verified/);
});

test('explicit Gemini request sends consent and hashes only; preflight reads cache without another POST',async()=>{
 const f=fixture();f.state.automatic=autoPlan(f.state.value);
 f.state.gemini={...f.state.automatic,revision:'e'.repeat(64),gemini_status:'selected',gemini_model:'gemini-3.1-flash-lite'};
 const selected=await f.actions.requestGeminiSelection('project-1','token',f.state.value);
 assert.equal(selected.gemini_draft,true);assert.equal(selected.gemini_status,'selected');
 const posts=f.calls.filter(c=>c.init);assert.equal(posts.length,1);
 const body=JSON.parse(posts[0].init.body);
 assert.equal(body.acknowledged_google_transcript_sharing,true);
 assert.equal(body.consent_version,'gemini-transcript-v1');assert.equal(body.revision,'d'.repeat(64));
 assert(!posts[0].init.body.includes('Original'));
 f.state.automatic=f.state.gemini;
 assert.equal((await f.actions.getAutomaticClips('project-1','token',f.state.value,true)).revision,selected.revision);
 assert(f.calls.at(-1).route.endsWith('/automatic-clips?gemini=true'));
 assert.equal(f.calls.filter(c=>c.init).length,1);
});
test('Gemini fallback stays marked and malformed metadata cannot become a draft',async()=>{
 const f=fixture();f.state.automatic=autoPlan(f.state.value);
 f.state.gemini={...f.state.automatic,gemini_status:'fallback',gemini_model:'gemini-3.1-flash-lite'};
 assert.equal((await f.actions.requestGeminiSelection('project-1','token',f.state.value)).gemini_status,'fallback');
 f.state.gemini.gemini_model='untrusted';
 await assert.rejects(f.actions.requestGeminiSelection('project-1','token',f.state.value),/could not be verified/);
});
