const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path'),crypto=require('node:crypto');
const parent='11111111-1111-4111-8111-111111111111',child='22222222-2222-4222-8222-222222222222',revision='a'.repeat(64);
function fixture(){
 const storage=new Map(),files=new Map(),calls=[],state={status:202,offline:false,storageFailure:false,downloadStatus:200,size:100,downloadFailure:false};
 class ApiError extends Error{constructor(status,message){super(message);this.status=status;}}
 const adapters={
  'expo-crypto':{randomUUID:crypto.randomUUID},
  'expo-secure-store':{getItemAsync:async key=>storage.get(key)||null,setItemAsync:async(key,value)=>{if(state.storageFailure)throw Error('unavailable');storage.set(key,value);},deleteItemAsync:async key=>storage.delete(key)},
  './api':{BASE:'https://private.example.invalid',ApiError,downloadUrl:id=>'https://private.example.invalid/api/v1/jobs/'+id+'/download',
   authenticatedFetch:async(token,url,init)=>{calls.push({token,url,init});if(state.offline)throw Error('offline');if(state.wait)await state.wait;return {status:state.status};},
   extract:async response=>{if(response.status>=400)throw new ApiError(response.status,'fixed error');return {id:child,preview_parent_id:parent,status:'queued'};}},
  './authEvents':{prepareToken:async token=>'prepared-'+token,recoverToken:async()=>state.renewed||null},
  'expo-file-system/legacy':{cacheDirectory:'file:///private-cache/',
   downloadAsync:async(url,destination,options)=>{calls.push({download:url,destination,options});files.set(destination,state.size);if(state.downloadFailure)throw Error('offline');
    const status=Array.isArray(state.downloadStatus)?state.downloadStatus.shift():state.downloadStatus;
    return {status,uri:destination};},
   getInfoAsync:async uri=>({exists:files.has(uri),size:files.get(uri)}),
   deleteAsync:async uri=>{files.delete(uri);}},
 };
 function load(){const exports={};const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/clipPreviews.ts'),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(code,{exports,require:name=>adapters[name]});return exports;}
 return {actions:load(),reload:load,storage,files,calls,state};
}
test('one durable per-option key survives lost responses and app restart',async()=>{
 const f=fixture();f.state.offline=true;
 await assert.rejects(f.actions.requestClipPreview(parent,'token',revision,1),/offline/);
 const first=JSON.parse(f.calls[0].init.body);f.state.offline=false;
 await f.reload().requestClipPreview(parent,'token',revision,1);
 assert.equal(JSON.parse(f.calls[1].init.body).idempotency_key,first.idempotency_key);
 assert.equal(first.acknowledged_preview,true);assert.equal(f.calls[0].init.method,'POST');
 assert(!f.calls[0].url.includes('token'));
});
test('same-session duplicate taps share one request, distinct sessions do not',async()=>{
 const f=fixture();let release;f.state.wait=new Promise(r=>{release=r;});
 const one=f.actions.requestClipPreview(parent,'token',revision,1),two=f.actions.requestClipPreview(parent,'token',revision,1);
 await new Promise(r=>setImmediate(r));assert.equal(f.calls.length,1);
 const other=f.actions.requestClipPreview(parent,'other-token',revision,1);
 await new Promise(r=>setImmediate(r));assert.equal(f.calls.length,2);
 release();await Promise.all([one,two,other]);
});
test('keystore failure prevents POST and concurrent options retain both keys',async()=>{
 const f=fixture();f.state.storageFailure=true;
 await assert.rejects(f.actions.requestClipPreview(parent,'token',revision,1));assert.equal(f.calls.length,0);
 f.state.storageFailure=false;
 await Promise.all([f.actions.requestClipPreview(parent,'token',revision,1),f.actions.requestClipPreview(parent,'token',revision,2)]);
 const entry=JSON.parse([...f.storage.values()][0]);assert.deepEqual(Object.keys(entry.keys),['1','2']);
});
test('deleted preview resets only that option, while a new revision bounds retained metadata',async()=>{
 const f=fixture();await f.actions.requestClipPreview(parent,'token',revision,1);await f.actions.requestClipPreview(parent,'token',revision,2);
 f.state.status=410;await assert.rejects(f.actions.requestClipPreview(parent,'token',revision,1),/deleted/);
 const entry=JSON.parse([...f.storage.values()][0]);assert(!entry.keys['1']&&entry.keys['2']);
 f.state.status=202;await f.actions.requestClipPreview(parent,'token','b'.repeat(64),3);
 const next=JSON.parse([...f.storage.values()][0]);assert.deepEqual(Object.keys(next.keys),['3']);
 await f.actions.forgetPreviewIntents(parent);assert.equal(f.storage.size,0);
});
test('bad parent or candidate cannot create a request',async()=>{
 const f=fixture();await assert.rejects(f.actions.requestClipPreview('../foreign','token',revision,1));
 await assert.rejects(f.actions.requestClipPreview(parent,'token',revision,6));assert.equal(f.calls.length,0);
});
test('preview playback downloads only to private cache with refreshed credentials',async()=>{
 const f=fixture();f.state.downloadStatus=[401,200];f.state.renewed='new-token';
 const result=await f.actions.loadPreviewFile(child,'old-token');
 assert(result.uri.startsWith('file:///private-cache/'));assert.equal(f.calls.length,2);
 assert.equal(f.calls[0].options.headers.Authorization,'Bearer prepared-old-token');
 assert.equal(f.calls[1].options.headers.Authorization,'Bearer new-token');
 await result.remove();assert.equal(f.files.size,0);
});
test('failed, empty and oversized preview downloads remove their private file',async()=>{
 for(const condition of ['network','empty','large','denied']){
  const f=fixture();if(condition==='network')f.state.downloadFailure=true;
  if(condition==='empty')f.state.size=0;if(condition==='large')f.state.size=64*1024*1024+1;
  if(condition==='denied')f.state.downloadStatus=404;
  await assert.rejects(f.actions.loadPreviewFile(child,'token'));assert.equal(f.files.size,0);
 }
});
