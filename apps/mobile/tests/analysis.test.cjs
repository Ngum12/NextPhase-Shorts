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
 const api={BASE:'https://example.invalid',api:async(route,token)=>{calls.push({route,token});if(state.error)throw state.error;return structuredClone(state.value);},
  authenticatedFetch:async(token,url,init)=>{calls.push({token,url,init});if(state.error)throw state.error;return structuredClone(state.value);},extract:async response=>response};
 const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/analysis.ts'),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const timing={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/audioTiming.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:timing});
 const exports={};vm.runInNewContext(code,{exports,require:name=>name==='./audioTiming'?timing:api,process:{env:{EXPO_PUBLIC_ENGLISH_REVIEW:'true'}}});
 return {actions:exports,state,calls};
}
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
