const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/videoExports.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
function fixture(){
 const calls=[];const state={granted:true,status:200,size:42,saveError:false,downloadError:false,shareAvailable:true,platform:{OS:'ios',Version:17}};
 const adapters={
  'react-native':{Platform:state.platform},
  'expo-file-system/legacy':{cacheDirectory:'file:///cache/',documentDirectory:null,
   downloadAsync:async(url,dest,init)=>{calls.push(['download',init.headers.Authorization]);if(state.downloadError)throw Error('offline');return {uri:dest,status:state.status};},
   getInfoAsync:async()=>({exists:true,size:state.size})},
  'expo-media-library':{requestPermissionsAsync:async(writeOnly,types)=>{calls.push(['permission',writeOnly,...types]);return {granted:state.granted};},
   saveToLibraryAsync:async uri=>{calls.push(['save',uri]);if(state.saveError)throw Error('storage full');}},
  'expo-sharing':{isAvailableAsync:async()=>state.shareAvailable,shareAsync:async uri=>{calls.push(['share',uri]);}},
  './api':{downloadUrl:id=>'http://localhost/'+id},'./authEvents':{prepareToken:async token=>token,recoverToken:async token=>{calls.push(['expired',token]);return null;}},
 };
 const exports={};vm.runInNewContext(code,{exports,require:name=>adapters[name]});return {exports,calls,state};
}
test('Save requests video-write permission then downloads and saves without sharing',async()=>{
 const f=fixture();await f.exports.exportVideo('save','job','token');
 assert.deepEqual(f.calls.map(c=>c[0]),['permission','download','save']);assert.deepEqual(f.calls[0],['permission',true]);
 assert.equal(f.calls[1][1],'Bearer token');assert(f.calls[2][1].endsWith('.mp4'));
});
test('Share downloads and opens sharing without requesting media-library access',async()=>{
 const f=fixture();await f.exports.exportVideo('share','job','token');assert.deepEqual(f.calls.map(c=>c[0]),['download','share']);
});
test('denied save permission does not download or report success',async()=>{
 const f=fixture();f.state.granted=false;await assert.rejects(f.exports.exportVideo('save','job','token'),/permission/);
 assert.deepEqual(f.calls.map(c=>c[0]),['permission']);
});
test('failed native save propagates failure without opening Share',async()=>{
 const f=fixture();f.state.saveError=true;await assert.rejects(f.exports.exportVideo('save','job','token'),/storage full/);
 assert(!f.calls.some(c=>c[0]==='share'));
});
test('unauthorized, deleted, offline and empty downloads never reach native save',async()=>{
 for(const state of [{status:401},{status:404},{downloadError:true},{size:0}]){
  const f=fixture();Object.assign(f.state,state);await assert.rejects(f.exports.exportVideo('save','job','token'));
  assert(!f.calls.some(c=>c[0]==='save'));if(state.status===401)assert(f.calls.some(c=>c[0]==='expired'));
 }
});
test('unavailable sharing never falls back to saving or downloads',async()=>{
 const f=fixture();f.state.shareAvailable=false;await assert.rejects(f.exports.exportVideo('share','job','token'),/unavailable/);assert.equal(f.calls.length,0);
});


test('modern Android saves its own video without requesting broad library access',async()=>{
 const f=fixture();f.state.platform.OS='android';f.state.platform.Version=35;
 await f.exports.exportVideo('save','job','token');assert.deepEqual(f.calls.map(c=>c[0]),['download','save']);
});
