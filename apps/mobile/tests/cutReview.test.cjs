const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path');
const output={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/cutReview.ts'),'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}
}).outputText,{exports:output});
const digest='a'.repeat(64);
function recording(){
 return {transcript:{source_sha256:digest,source_duration_ms:20000,words:[
  {text:'Before',start_ms:0,end_ms:1000},{text:'However,',start_ms:1000,end_ms:2000},
  {text:'now',start_ms:2000,end_ms:5000},{text:'finish.',start_ms:5000,end_ms:8000}]},
  proposal:{candidates:[{first_word:1,last_word:3,source_start_ms:1000,source_end_ms:8000,output_frames:210}]},
  audio_timing:{source_sha256:digest,source_duration_ms:20000,audio_duration_ms:12000,
    quiet_intervals:[{start_ms:0,end_ms:900},{start_ms:7500,end_ms:8500}]},
  scene_analysis:{status:'available',source_sha256:digest,source_duration_ms:20000,
    analyzed_duration_ms:10000,changes:[{at_ms:1500,delta_milli:900},{at_ms:7500,delta_milli:850}]},
 };
}
const messages=checkpoint=>checkpoint.cues.map(x=>x.message).join(' ');
test('cut review produces two source-time checkpoints without changing an edit',()=>{
 const doc=recording(),before=JSON.stringify(doc),result=output.cutReview(doc,0);
 assert.equal(result.opening.atMs,1000);assert.equal(result.ending.atMs,8000);
 assert.equal(result.opening.title,'Opening');assert.equal(result.ending.title,'Ending');
 assert(result.opening.cues.some(x=>x.type==='context'));
 assert(messages(result.opening).includes('earlier point'));
 assert(messages(result.opening).includes('possible sampled visual change'));
 assert(messages(result.ending).includes('low-volume passage'));
 assert(messages(result.ending).includes('possible sampled visual change'));
 assert.equal(JSON.stringify(doc),before);
});
test('unavailable evidence never becomes false proof of a clean cut',()=>{
 const doc=recording();
 doc.scene_analysis.status='unavailable';
 doc.scene_analysis.changes=[];
 doc.audio_timing=null;
 const result=output.cutReview(doc,0);
 assert(!result.opening.cues.some(x=>x.type==='visual'));
 assert(!result.ending.cues.some(x=>x.type==='quiet'));
 assert(result.disclosure.includes('not a quality score'));
});
test('partial sampling explicitly marks the uncovered cut without inventing events',()=>{
 const doc=recording();doc.scene_analysis.analyzed_duration_ms=7000;
 doc.scene_analysis.changes=[{at_ms:1500,delta_milli:900}];
 doc.audio_timing.audio_duration_ms=7000;
 doc.audio_timing.quiet_intervals=[{start_ms:0,end_ms:900}];
 const result=output.cutReview(doc,0);
 assert(result.ending.cues.filter(x=>x.type==='coverage').length===2);
 assert(messages(result.ending).includes('did not reach this cut'));
 assert(!result.ending.cues.some(x=>x.type==='visual'||x.type==='quiet'));
});
test('source digest mismatch rejects suggestions from other recordings',()=>{
 const doc=recording();
 doc.scene_analysis.source_sha256='b'.repeat(64);
 doc.audio_timing.source_sha256='b'.repeat(64);
 const result=output.cutReview(doc,0);
 assert(!result.opening.cues.some(x=>x.type==='quiet'||x.type==='visual'));
 assert(!result.ending.cues.some(x=>x.type==='quiet'||x.type==='visual'));
});
test('boundary distances are bounded and equal-distance samples resolve earlier first',()=>{
 const doc=recording();
 doc.scene_analysis.changes=[{at_ms:500,delta_milli:900},{at_ms:1500,delta_milli:850},
  {at_ms:6500,delta_milli:850}];
 const result=output.cutReview(doc,0);
 assert(messages(result.opening).includes('source 0.5s'));
 assert(!result.ending.cues.some(x=>x.type==='visual'));
});
test('invalid candidates and option indices yield no review',()=>{
 const doc=recording();
 assert.equal(output.cutReview(doc,1),null);
 assert.equal(output.cutReview(doc,-1),null);
 assert.equal(output.cutReview(doc,1.5),null);
 doc.proposal.candidates[0].source_end_ms=25000;
 assert.equal(output.cutReview(doc,0),null);
});
