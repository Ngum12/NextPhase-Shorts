const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path');
const exported={};
const source=fs.readFileSync(path.join(__dirname,'../src/clipTimeline.ts'),'utf8');
vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:exported});
const candidate={first_word:0,last_word:2,source_start_ms:2500,source_end_ms:7500,output_frames:150};
const quiet={source_duration_ms:20000,audio_duration_ms:10000,quiet_intervals:[
 {start_ms:500,end_ms:1500},{start_ms:9000,end_ms:10000}]};
const scene={source_duration_ms:20000,status:'available',analyzed_duration_ms:15000,changes:[
 {at_ms:1000,delta_milli:800},{at_ms:3000,delta_milli:850},{at_ms:16000,delta_milli:900}]};

test('the timeline measures selected cuts against original source, never clip-relative time',()=>{
 const timeline=exported.clipTimeline(candidate,20000,null,null);
 assert.equal(timeline.selection.left,'12.5%');assert.equal(timeline.selection.width,'25%');
 assert.equal(timeline.audioCoverage,null);assert.equal(timeline.visualCoverage,null);
 assert.equal(timeline.audioCoverageMs,null);assert.equal(timeline.visualCoverageMs,null);
 assert.equal(exported.timelineTime(0),'0:00');assert.equal(exported.timelineTime(61500),'1:01');
 assert.equal(exported.timelineTime(-100),'—');
});

test('bounded source-relative quiet passages and visual samples disclose partial coverage',()=>{
 const before=JSON.stringify({candidate,quiet,scene});
 const value=exported.clipTimeline(candidate,20000,quiet,scene);
 assert.equal(value.audioCoverage,'50%');assert.equal(value.visualCoverage,'75%');
 assert.deepEqual(Array.from(value.quiet,b=>[b.left,b.width]),[['2.5%','5%'],['45%','5%']]);
 assert.deepEqual(Array.from(value.visualTicks),['5%','15%']);
 assert.equal(value.audioCoverageMs,10000);assert.equal(value.visualCoverageMs,15000);
 assert.equal(JSON.stringify({candidate,quiet,scene}),before);
});

test('missing or unavailable analysis is not represented as an empty verified track',()=>{
 const value=exported.clipTimeline(candidate,20000,null,{...scene,status:'unavailable',changes:[]});
 assert.equal(value.visualCoverage,null);assert.equal(value.visualTicks.length,0);
 const wrong=exported.clipTimeline(candidate,20000,{...quiet,source_duration_ms:10000},scene);
 assert.equal(wrong.audioCoverage,null);assert.equal(wrong.visualCoverage,'75%');
});

test('strict candidate bounds reject invalid or untrusted intervals without changing input',()=>{
 for(const item of [
  {...candidate,source_start_ms:-1},{...candidate,source_end_ms:20001},
  {...candidate,source_end_ms:2500},{...candidate,source_start_ms:2.5},
 ])assert.equal(exported.clipTimeline(item,20000,null,null),null);
 assert.equal(exported.clipTimeline(candidate,0,null,null),null);
 assert.equal(exported.clipTimeline(candidate,NaN,null,null),null);
});

test('defensive clipping never draws guidance past checked source duration',()=>{
 const out=exported.clipTimeline(candidate,20000,
  {...quiet,quiet_intervals:[{start_ms:9000,end_ms:18000}]},
  scene);
 assert.deepEqual(Array.from(out.quiet,b=>[b.left,b.width]),[['45%','5%']]);
 assert(!out.visualTicks.includes('80%'));
});
