const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path');
const result={};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/reviewShortcuts.ts'),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:result});
const word=(text,start,end)=>({text,start_ms:start,end_ms:end,confidence:.91});
test('sentence-end cues mark punctuation, long pauses and last word without fabricating approval',()=>{
  const words=[word('Welcome',0,400),word('everyone.',410,800),
    word('We',900,1200),word('continue',1250,1400),
    word('today',2500,2800),word('because',2900,3400)];
  const cues=Array.from(result.endingCues(words));
  assert.deepEqual(cues.map(c=>[c.wordNumber,c.reason]),[
    [2,'punctuation'],[4,'pause'],[6,'last-word']]);
});
test('abbreviations and quoted punctuation are cautious bounded cues',()=>{
  const words=[word('Dr.',0,300),word('Jane',400,800),
    word('agreed!”',900,1300),word('Okay',1400,1800)];
  const cues=Array.from(result.endingCues(words));
  assert.deepEqual(cues.map(c=>[c.wordNumber,c.reason]),[
    [3,'punctuation'],[4,'last-word']]);
  assert.deepEqual(Array.from(result.endingCues([])),[]);
  assert.deepEqual(Array.from(result.endingCues(Array(1001).fill(words[0]))),[]);
});
test('compact transcript tells the reader it is truncated without modifying words',()=>{
  const words=[word('one',0,200),word('two',200,400),word('three',400,600)];
  assert.equal(result.previewTranscript(words,2),'one two …');
  assert.equal(result.previewTranscript(words,10),'one two three');
  assert.equal(result.previewTranscript([]),'');
});
