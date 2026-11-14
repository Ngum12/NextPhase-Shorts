const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/saveAndFinish.ts'),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;

function fixture(){
  const calls=[];const state={saveFails:false,deleteFails:false,cacheFails:false,forgetFails:false};
  const adaptors={
    'expo-file-system/legacy':{
      cacheDirectory:'file:///cache/',documentDirectory:null,
      deleteAsync:async(uri,options)=>{calls.push(['erase-client-cache',uri,options.idempotent]);if(state.cacheFails)throw Error('cache cleanup unavailable');},
    },
    './api':{deleteJob:async(id,token)=>{
      calls.push(['revoke-server-and-schedule-delete',id,token]);
      if(state.deleteFails)throw Error('network request unconfirmed');
    }},
    './videoExports':{exportVideo:async(action,id,token)=>{
      calls.push(['save-to-gallery',action,id,token]);
      if(state.saveFails)throw Error('gallery storage full');
    }},
    './clipPreviews':{forgetPreviewIntents:async(id)=>{
      calls.push(['forget-preview-intents',id]);
      if(state.forgetFails)throw Error('local preferences unavailable');
    }},
  };
  const exports={};
  vm.runInNewContext(code,{exports,require:name=>adaptors[name]});
  return {exports,calls,state};
}

test('saved original is cleaned up only AFTER the gallery save succeeds',async()=>{
  const f=fixture();
  await f.exports.saveAndFinish('source','source','token');
  assert.deepEqual(f.calls.map(x=>x[0]),[
    'save-to-gallery','revoke-server-and-schedule-delete','erase-client-cache','forget-preview-intents']);
  assert.deepEqual(f.calls[1],['revoke-server-and-schedule-delete','source','token']);
  assert.equal(f.calls[2][1],'file:///cache/nextphase-source.mp4');
});

test('saving a reviewed preview deletes the original project tree, not only the preview',async()=>{
  const f=fixture();
  await f.exports.saveAndFinish('reviewed-short','original-video','token');
  assert.deepEqual(f.calls[0],['save-to-gallery','save','reviewed-short','token']);
  assert.deepEqual(f.calls[1],['revoke-server-and-schedule-delete','original-video','token']);
  assert.deepEqual(f.calls[3],['forget-preview-intents','original-video']);
});

test('failed gallery save never deletes original or previews',async()=>{
  const f=fixture();f.state.saveFails=true;
  await assert.rejects(f.exports.saveAndFinish('preview','original','token'),/gallery storage full/);
  assert.deepEqual(f.calls.map(x=>x[0]),['save-to-gallery']);
});

test('failed server deletion is not called successful; phone video stays saved and cache is cleared',async()=>{
  const f=fixture();f.state.deleteFails=true;
  await assert.rejects(f.exports.saveAndFinish('preview','original','token'),e=>
    e.name==='SavedButCleanupPending' && /saved to your phone/.test(e.message));
  assert.deepEqual(f.calls.map(x=>x[0]),['save-to-gallery','revoke-server-and-schedule-delete','erase-client-cache']);
});

test('cache or preference cleanup glitches do not undo a confirmed gallery save and server tombstone',async()=>{
  const f=fixture();f.state.cacheFails=true;f.state.forgetFails=true;
  await f.exports.saveAndFinish('preview','original','token');
  assert.equal(f.calls.length,4);
});

test('invalid missing project IDs cannot authorize any actions',async()=>{
  const f=fixture();
  await assert.rejects(f.exports.saveAndFinish('','original','token'),/authenticated project/);
  assert.equal(f.calls.length,0);
});
