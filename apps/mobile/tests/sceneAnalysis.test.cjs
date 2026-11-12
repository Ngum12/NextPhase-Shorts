const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path');
const exports_={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/sceneAnalysis.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:exports_});
function value(){return {status:'available',analyzed_duration_ms:6000,changes:[{at_ms:1000,delta_milli:800},{at_ms:3000,delta_milli:900},{at_ms:5000,delta_milli:850}]};}
test('changes near clip boundaries are approximate context, not new cut ranges',()=>{
 const source=value(),before=JSON.stringify(source);const result=exports_.sceneContext(source,2000,4000);
 assert.equal(result.inside,1);assert.equal(result.nearStart,1000);assert.equal(result.nearEnd,3000);assert.equal(result.partial,false);
 assert.equal(JSON.stringify(source),before);
});
test('boundary events are not counted inside and unavailable/legacy data is not zero-change proof',()=>{
 const result=exports_.sceneContext(value(),1000,5000);assert.equal(result.inside,1);
 assert.equal(result.nearStart,1000);assert.equal(result.nearEnd,5000);
 assert.equal(exports_.sceneContext(undefined,0,6000),null);assert.equal(exports_.sceneContext({status:'unavailable'},0,6000),null);
});
test('partial coverage is explicit and distant changes are not attached to a cut',()=>{
 const result=exports_.sceneContext({...value(),analyzed_duration_ms:3000,changes:[]},4000,6000);
 assert.equal(result.partial,true);assert.equal(result.nearStart,null);assert.equal(result.nearEnd,null);
});
