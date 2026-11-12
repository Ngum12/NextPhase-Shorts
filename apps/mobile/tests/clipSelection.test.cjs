const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path');
const exports_={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/clipSelection.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:exports_});
const context=exports_.clipContext;
function document(){return {transcript:{words:Array.from({length:30},(_,i)=>({text:i===8?'However,':'word'+i}))},review:{confirmed_low_confidence_words:[1,9,12,30]},proposal:{candidates:[
 {first_word:8,last_word:15,source_start_ms:8000,source_end_ms:16000},
 {first_word:12,last_word:19,source_start_ms:12000,source_end_ms:20000},
 {first_word:20,last_word:29,source_start_ms:20000,source_end_ms:30000},
 ]}};}
test('context comes only from nearby original words and overlap uses source time',()=>{
 const result=context(document(),0);assert.equal(result.before,'word0 word1 word2 word3 word4 word5 word6 word7');
 assert.equal(result.after,'word16 word17 word18 word19 word20 word21 word22 word23');
 assert.equal(result.confirmedWords,2);assert(result.contextOpening);assert.deepEqual(Array.from(result.overlapOptions),[2]);
});
test('recording edges and exact-touching clips do not invent context or overlap',()=>{
 const data=document();data.proposal.candidates[0].first_word=0;
 assert.equal(context(data,0).before,'');assert.equal(context(data,2).after,'');
 assert.equal(context(data,2).overlapOptions.length,0);assert.equal(context(data,100),null);
});
test('long transcript excerpts stay bounded and text remains inert',()=>{
 const data=document();for(const word of data.transcript.words)word.text='<script>'+('a'.repeat(100))+'</script>';
 const result=context(data,0);assert(result.before.length<=160&&result.after.length<=160&&result.opening.length<=96);
 assert(result.before.startsWith('<script>')); // Native Text displays this literally.
});
