const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path'),crypto=require('node:crypto');
const parent='11111111-1111-4111-8111-111111111111',owner='22222222-2222-4222-8222-222222222222',child='33333333-3333-4333-8333-333333333333',revision='a'.repeat(64);
function fixture(){
 const storage=new Map(),calls=[],state={status:202,offline:false,storageFailure:false};
 class ApiError extends Error{constructor(status,message){super(message);this.status=status;}}
 const adapters={
  'expo-secure-store':{getItemAsync:async key=>storage.get(key)||null,setItemAsync:async(key,value)=>{
    if(state.storageFailure)throw Error('storage unavailable');storage.set(key,value);},deleteItemAsync:async key=>storage.delete(key)},
  'expo-crypto':{randomUUID:crypto.randomUUID,CryptoDigestAlgorithm:{SHA256:'SHA-256'},
    digestStringAsync:async(_,text)=>crypto.createHash('sha256').update(text).digest('hex')},
  './api':{ApiError,BASE:'https://private.example.invalid',api:async()=>state.draft||{job_id:parent,revision,candidate_number:1,duration_ms:5000,cues:[{text:'Original words.',start_ms:0,end_ms:2000}]},
   authenticatedFetch:async(token,url,init)=>{calls.push({token,url,body:JSON.parse(init.body)});if(state.offline)throw Error('offline');if(state.wait)await state.wait;return {status:state.status};},
   extract:async response=>{if(response.status>=400)throw new ApiError(response.status,'fixed error');return {id:child,preview_parent_id:parent,status:'queued'};}}
 };
 function load(){const exports={};const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/polish.ts'),'utf8'),
   {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  vm.runInNewContext(code,{exports,require:name=>{assert(adapters[name],name);return adapters[name];}});return exports;}
 const actions=load();return {actions,reload:load,storage,calls,state,options:{...actions.defaultPolish}};
}
test('automatic and reviewed render intents stay distinct without persisting transcript text',async()=>{
 const f=fixture();
 await f.actions.requestPolishedPreview(parent,'token',revision,1,f.options,null,5000,false,true);
 await f.actions.requestPolishedPreview(parent,'token',revision,1,f.options,null,5000,false);
 assert.equal(f.calls[0].body.automatic_draft,true);
 assert.equal(f.calls[1].body.automatic_draft,undefined);
 assert.notEqual(f.calls[0].body.idempotency_key,f.calls[1].body.idempotency_key);
 assert([...f.storage.values()].every(raw=>!raw.includes('token')&&!raw.includes('Original')));
});

test('seconds and caption wrapping enforce closed bounded times/text',()=>{
 const {actions:a}=fixture();assert.equal(a.captionMilliseconds('1,250'),1250);assert.equal(a.captionMilliseconds('.5'),500);
 for(const value of ['','-1','1e3','60.001','1.0001','NaN'])assert.throws(()=>a.captionMilliseconds(value));
 assert(a.wrapCaption('These original words stay readable.').includes('\n'));
 assert.throws(()=>a.wrapCaption('x'.repeat(53)));assert.throws(()=>a.wrapCaption('bad\x00text'));
 assert.throws(()=>a.validateCues([{text:'a',start_ms:0,end_ms:2000},{text:'b',start_ms:1500,end_ms:3000}],5000));
});
test('presets are per-account enums only and reject poisoned settings',async()=>{
 const f=fixture();await f.actions.savePolishPreset(owner,{...f.options,voice:'level'});
 assert.equal((await f.actions.loadPolishPreset(owner)).voice,'level');
 assert.equal(await f.actions.loadPolishPreset(parent),null);
 const raw=[...f.storage.values()][0];assert(raw.length<512&&!raw.includes('text'));
 await assert.rejects(f.actions.savePolishPreset(owner,{...f.options,fontfile:'/etc/passwd'}));
 await assert.rejects(f.actions.savePolishPreset(owner,{...f.options,audio_edges:'movie=evil'}));
 await assert.rejects(f.actions.savePolishPreset(owner,{...f.options,framing:'crop=movie=evil'}));
 await f.actions.savePolishPreset(owner,{...f.options,framing:'fill-right'});
 assert.equal((await f.actions.loadPolishPreset(owner)).framing,'fill-right');
 const legacy={...f.options};delete legacy.audio_edges;
 f.storage.set(`nextphase.polish.preset.${owner}`,JSON.stringify(legacy));
 assert.equal((await f.actions.loadPolishPreset(owner)).audio_edges,'original');
 f.storage.set(`nextphase.polish.preset.${owner}`,'{"voice":"filter=evil"}');
 await assert.rejects(f.actions.loadPolishPreset(owner));
});
test('edited text stays out of durable intents and retries survive restart',async()=>{
 const f=fixture();const edits=[{text:'Human correction.',start_ms:100,end_ms:1800}];f.state.offline=true;
 await assert.rejects(f.actions.requestPolishedPreview(parent,'token',revision,1,f.options,edits,5000,true));
 const first=f.calls[0].body;f.state.offline=false;
 await f.reload().requestPolishedPreview(parent,'token',revision,1,f.options,edits,5000,true);
 assert.equal(f.calls[1].body.idempotency_key,first.idempotency_key);
 assert.equal(first.acknowledged_caption_edits,true);assert.equal(first.caption_edits[0].text,edits[0].text);
 assert([...f.storage.values()].every(raw=>!raw.includes('Human')&&!raw.includes('token')));
});
test('changed settings create distinct keys and duplicate in-flight requests share one POST',async()=>{
 const f=fixture();let release;f.state.wait=new Promise(r=>{release=r;});
 const one=f.actions.requestPolishedPreview(parent,'token',revision,1,f.options,null,5000,false);
 const two=f.actions.requestPolishedPreview(parent,'token',revision,1,f.options,null,5000,false);
 await new Promise(r=>setImmediate(r));assert.equal(f.calls.length,1);release();await Promise.all([one,two]);
 await f.actions.requestPolishedPreview(parent,'token',revision,1,{...f.options,voice:'level'},null,5000,false);
 assert.notEqual(f.calls[0].body.idempotency_key,f.calls[1].body.idempotency_key);
});
test('left, center and right crop are distinct idempotent render intents',async()=>{
 const f=fixture();
 for(const framing of ['fill-left','fill-center','fill-right'])
   await f.actions.requestPolishedPreview(parent,'token',revision,1,{...f.options,framing},null,5000,false);
 const requests=f.calls.map(call=>call.body);
 assert.deepEqual(requests.map(body=>body.framing),['fill-left','fill-center','fill-right']);
 assert.equal(new Set(requests.map(body=>body.idempotency_key)).size,3);
 await f.reload().requestPolishedPreview(parent,'token',revision,1,{...f.options,framing:'fill-right'},null,5000,false);
 assert.equal(f.calls.at(-1).body.idempotency_key,requests[2].idempotency_key);
});
test('soft audio fades are explicit; default requests keep backward-compatible payloads',async()=>{
 const f=fixture();await f.actions.requestPolishedPreview(parent,'token',revision,1,f.options,null,5000,false);
 assert.equal(f.calls[0].body.polish.audio_edges,undefined);
 await f.actions.requestPolishedPreview(parent,'token',revision,1,{...f.options,audio_edges:'soft'},null,5000,false);
 assert.equal(f.calls[1].body.polish.audio_edges,'soft');
 assert.notEqual(f.calls[0].body.idempotency_key,f.calls[1].body.idempotency_key);
});
test('edits require recording comparison and storage failure prevents POST',async()=>{
 const f=fixture();await assert.rejects(f.actions.requestPolishedPreview(parent,'token',revision,1,f.options,
  [{text:'change',start_ms:0,end_ms:1000}],5000,false));assert.equal(f.calls.length,0);
 f.state.storageFailure=true;
 await assert.rejects(f.actions.requestPolishedPreview(parent,'token',revision,1,f.options,null,5000,false));
 assert.equal(f.calls.length,0);
});
test('deleted preview key is retired and source deletion clears bounded intent history',async()=>{
 const f=fixture();f.state.status=410;
 await assert.rejects(f.actions.requestPolishedPreview(parent,'token',revision,1,f.options,null,5000,false));
 f.state.status=202;await f.actions.requestPolishedPreview(parent,'token',revision,1,f.options,null,5000,false);
 assert.notEqual(f.calls[0].body.idempotency_key,f.calls[1].body.idempotency_key);
 for(let i=0;i<8;i++)await f.actions.requestPolishedPreview(parent,'token',String(i).repeat(64),1,f.options,null,5000,false);
 assert([...f.storage.values()].every(raw=>raw.length<2048&&JSON.parse(raw).length<=5));
 await f.actions.forgetPolishIntents(parent);assert.equal(f.storage.size,0);
});
test('caption drafts are checked against project, revision, timing and count',async()=>{
 const f=fixture();const value=await f.actions.getCaptionDraft(parent,'token',revision,1);assert.equal(value.cues.length,1);
 f.state.draft={job_id:child,revision,candidate_number:1,duration_ms:5000,cues:[]};
 await assert.rejects(f.actions.getCaptionDraft(parent,'token',revision,1));
});

test('Gemini render intent is distinct and stable after restart',async()=>{
 const f=fixture();
 await f.actions.requestPolishedPreview(parent,'token',revision,1,f.options,null,5000,false,true,true);
 await f.reload().requestPolishedPreview(parent,'token',revision,1,f.options,null,5000,false,true,true);
 await f.actions.requestPolishedPreview(parent,'token',revision,1,f.options,null,5000,false,true);
 assert.equal(f.calls[0].body.gemini_draft,true);assert.equal(f.calls[1].body.gemini_draft,true);
 assert.equal(f.calls[0].body.idempotency_key,f.calls[1].body.idempotency_key);
 assert.notEqual(f.calls[0].body.idempotency_key,f.calls[2].body.idempotency_key);
 assert.equal(f.calls[2].body.gemini_draft,undefined);
});
