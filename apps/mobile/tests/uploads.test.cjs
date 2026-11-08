// Exercise the real upload manager across JS runtime restarts. Native storage,
// checksumming and HTTP are adapters here; this does not replace a device test.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const crypto=require('node:crypto');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const javascript=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/uploads.ts'),'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022},
}).outputText;

function fixture(options={}) {
  const storage=new Map([['file:///original.mp4',Buffer.from('abcdefghijk')]]);
  const sessions=new Map();
  const offsets=[];
  const signedTransfers=[];
  let denySigned=false,dropSigned=false,signedOrigin='https://storage.example';
  let gone=false;
  let openHandles=0,dropPart=false,dropCompletion=false,offline=false,failDeleteCopy=false;
  const root='file:///documents/nextphase-uploads/';
  const disk={documentDirectory:'file:///documents/',
    makeDirectoryAsync:async()=>{},
    getInfoAsync:async uri=>({exists:storage.has(uri)}),
    readAsStringAsync:async uri=>{if(!storage.has(uri))throw Error('missing');return storage.get(uri).toString();},
    writeAsStringAsync:async(uri,text)=>{storage.set(uri,Buffer.from(text));},
    copyAsync:async({from,to})=>{assert(storage.has(from));storage.set(to,Buffer.from(storage.get(from)));},
    deleteAsync:async uri=>{if(failDeleteCopy&&uri.startsWith(root)&&uri.endsWith('.mp4')){failDeleteCopy=false;throw Error('storage busy');}storage.delete(uri);},
  };
  class File {
    constructor(uri){this.uri=uri;}
    get exists(){return storage.has(this.uri);}
    get size(){return storage.get(this.uri)?.length||0;}
    open(){
      openHandles++;
      const bytes=storage.get(this.uri);
      return {offset:0,async readBytes(length){const part=new Uint8Array(bytes.buffer,bytes.byteOffset+this.offset,Math.min(length,bytes.length-this.offset));this.offset+=part.length;await Promise.resolve();options.afterRead?.();return part;},
        close(){openHandles--;}};
    }
  }
  const snapshot=s=>({id:s.id,status:s.status,total_bytes:11,received_bytes:s.offset,chunk_bytes:4,job_id:s.jobId||null,transfer_backend:options.direct?'direct-s3':'api'});
  const response=(body,status=200)=>({ok:status<400,status,json:async()=>body});
  const fetch=async(url,options={})=>{
    if(offline)throw Error('offline');
    if(options.signal?.aborted)throw Error('aborted');
    const route=new URL(url);
    if(route.hostname==='storage.example') {
      assert.equal(options.credentials,'omit');assert.equal(options.redirect,'error');
      assert(!Object.keys(options.headers).some(name=>name.toLowerCase()==='authorization'));
      const [id,offsetText]=route.pathname.slice(1).split('/');const offset=Number(offsetText);
      const session=[...sessions.values()].find(s=>s.id===id);assert(session);
      signedTransfers.push(offset);
      if(denySigned){denySigned=false;return response({},403);}
      const bytes=Buffer.from(options.body);
      assert.equal(options.headers['Content-Length'],String(bytes.length));
      assert.equal(options.headers['x-amz-checksum-sha256'],crypto.createHash('sha256').update(bytes).digest('base64'));
      session.incoming??=new Map();session.incoming.set(offset,bytes);
      if(dropSigned){dropSigned=false;throw Error('lost signed PUT response');}
      return response({});
    }
    if(route.pathname.startsWith('/api/v1/upload-sessions/by-key/')){
      if(gone)return response({detail:'Deleted project'},410);
      const found=sessions.get(route.pathname.split('/').at(-1));
      return found?response(snapshot(found)):response({detail:'No session'},404);
    }
    if(gone&&route.pathname.startsWith('/api/v1/upload-sessions'))return response({detail:'Deleted project'},410);
    if(route.pathname==='/api/v1/upload-sessions/discard-by-key'){
      const key=options.headers['Idempotency-Key'];
      assert.equal(options.body,undefined);
      if(!sessions.has(key))sessions.set(key,{id:crypto.randomUUID(),key,status:'aborted',offset:0,parts:[],completeCalls:0,discardOnly:true});
      const session=sessions.get(key);if(session.status!=='completed')session.status='aborted';
      return response(snapshot(session));
    }
    if(route.pathname==='/api/v1/upload-sessions') {
      const key=options.headers['Idempotency-Key'];
      if(!sessions.has(key))sessions.set(key,{id:crypto.randomUUID(),key,status:'uploading',offset:0,parts:[],completeCalls:0});
      return response(snapshot(sessions.get(key)));
    }
    if(route.pathname.startsWith('/api/v1/jobs/'))return response({id:'job-one',status:'queued'});
    const id=route.pathname.split('/')[4];
    const session=[...sessions.values()].find(s=>s.id===id);
    assert(session,route.pathname);
    if(route.pathname.endsWith('/part-url')) {
      const intent=JSON.parse(options.body);const length=Math.min(4,11-intent.offset);
      const checksum=Buffer.from(intent.sha256,'hex').toString('base64');
      return response({committed:false,grant_id:String(intent.offset),url:`${signedOrigin}/${session.id}/${intent.offset}?signed=fixture`,
        headers:{'Content-Length':String(length),'Content-Type':'application/octet-stream','x-amz-meta-sha256':intent.sha256,
        'x-amz-checksum-sha256':checksum,Authorization:'must-not-forward'}});
    }
    if(route.pathname.includes('/part-commit/')) {
      const offset=Number(route.pathname.split('/').at(-1));const bytes=session.incoming.get(offset);
      assert.equal(offset,session.offset);offsets.push(offset);session.offset+=bytes.length;session.parts.push(bytes);
      if(dropPart){dropPart=false;throw Error('lost chunk response');}
      return response(snapshot(session));
    }
    if(route.pathname.endsWith('/parts')) {
      const offset=Number(route.searchParams.get('offset'));
      const bytes=Buffer.from(options.body);
      assert.equal(options.headers['X-Chunk-SHA256'],crypto.createHash('sha256').update(bytes).digest('hex'));
      assert.equal(offset,session.offset);
      offsets.push(offset);session.offset+=bytes.length;session.parts.push(bytes);
      if(dropPart){dropPart=false;throw Error('lost chunk response');}
      return response(snapshot(session));
    }
    if(route.pathname.endsWith('/complete')) {
      session.completeCalls++;
      assert.equal(Buffer.concat(session.parts).toString(),'abcdefghijk');
      session.status='completed';session.jobId='job-one';
      if(dropCompletion){dropCompletion=false;throw Error('lost completion response');}
      return response({id:'job-one',status:'queued'});
    }
    if(route.pathname.endsWith('/abort')){session.status='aborted';return response(snapshot(session));}
    return response(snapshot(session));
  };
  class ApiError extends Error{constructor(status,message){super(message);this.status=status;}}
  const extract=async result=>{const body=await result.json();if(!result.ok)throw new ApiError(result.status,body.detail);return body;};
  function restart() {
    const exports={};
    const adapters={
      'expo-file-system':{File},'expo-file-system/legacy':disk,
      'expo-crypto':{randomUUID:crypto.randomUUID,CryptoDigestAlgorithm:{SHA256:'SHA-256'},digest:async(_,bytes)=>{
        const result=crypto.createHash('sha256').update(bytes).digest();
        return result.buffer.slice(result.byteOffset,result.byteOffset+result.length);
      }},
      './uploadRights':{RIGHTS_VERSION:'upload-rights-v1'},
      './api':{BASE:'http://localhost',ApiError,extract,authenticatedFetch:async(token,url,options)=>{assert.equal(new URL(url).hostname,'localhost');return fetch(url,options);},api:async endpoint=>extract(await fetch('http://localhost'+endpoint))},
    };
    vm.runInNewContext(javascript,{exports,require:name=>{assert(adapters[name],name);return adapters[name];},
      fetch,URL,AbortController,console,Uint8Array,ArrayBuffer});
    return exports;
  }
  return {restart,storage,sessions,offsets,signedTransfers,root,
    set denySigned(value){denySigned=value;},set dropSigned(value){dropSigned=value;},
    set signedOrigin(value){signedOrigin=value;},
    set gone(value){gone=value;},
    set dropPart(value){dropPart=value;},set dropCompletion(value){dropCompletion=value;},set offline(value){offline=value;},
    set failDeleteCopy(value){failDeleteCopy=value;},get openHandles(){return openHandles;}};
}
async function prepared(runtime) {
  return runtime.prepareUpload('owner-a',{uri:'file:///original.mp4',name:'source.mp4'},'Test','vlog',15,true);
}

test('runtime restart resumes after the server-acknowledged chunk without retransferring it',async()=>{
  const world=fixture();let app=world.restart();const record=await prepared(app);
  world.dropPart=true;
  await assert.rejects(app.resumeUpload(record,'token',()=>{}),/lost chunk response/);
  assert.equal(world.openHandles,0);
  app=world.restart();const saved=await app.loadPending('owner-a');assert(saved.sessionId);
  assert.equal(await app.loadPending('owner-b'),null);
  const progress=[];
  const job=await app.resumeUpload(saved,'token',(sent,total)=>progress.push([sent,total]));
  assert.equal(job.id,'job-one');assert.deepEqual(world.offsets,[0,4,8]);
  assert.deepEqual(progress[0],[4,11]);assert.equal(await app.loadPending('owner-a'),null);
  assert(world.storage.has('file:///original.mp4'));assert(!world.storage.has(world.root+record.localName));
});

test('lost completion response is recovered as one job after restart',async()=>{
  const world=fixture();let app=world.restart();const record=await prepared(app);world.dropCompletion=true;
  await assert.rejects(app.resumeUpload(record,'token',()=>{}),/lost completion response/);
  app=world.restart();const saved=await app.loadPending('owner-a');
  const job=await app.resumeUpload(saved,'token',()=>{});
  assert.equal(job.id,'job-one');assert.equal([...world.sessions.values()][0].completeCalls,1);
  assert.deepEqual(world.offsets,[0,4,8]);assert.equal(world.openHandles,0);
});

test('a torn newest journal slot recovers the earlier intent key and existing server session',async()=>{
  const world=fixture();let app=world.restart();const record=await prepared(app);world.dropPart=true;
  await assert.rejects(app.resumeUpload(record,'token',()=>{}));
  const newest=await app.loadPending('owner-a');
  world.storage.set(world.root+`owner-a-${newest.revision%2}.json`,Buffer.from('{broken'));
  app=world.restart();const older=await app.loadPending('owner-a');
  assert.equal(older.key,record.key);assert.equal(older.sessionId,undefined);
  assert.equal((await app.resumeUpload(older,'token',()=>{})).id,'job-one');
  assert.equal(world.sessions.size,1);assert.deepEqual(world.offsets,[0,4,8]);
});

test('pause preserves intent and confirmed discard removes only the private copy',async()=>{
  const world=fixture();const app=world.restart();const record=await prepared(app);
  const controller=new AbortController();controller.abort();
  await assert.rejects(app.resumeUpload(record,'token',()=>{},controller.signal),/paused/);
  assert((await app.loadPending('owner-a')).key===record.key);
  world.offline=true;
  await assert.rejects(app.discardUpload(record,'token'),/offline/);
  assert(world.storage.has(world.root+record.localName));
  world.offline=false;
  assert.equal(await app.discardUpload(record,'token'),null);
  assert.equal(await app.loadPending('owner-a'),null);
  assert(world.storage.has('file:///original.mp4'));assert(!world.storage.has(world.root+record.localName));
});

test('two screens cannot replace the same account pending intent',async()=>{
  const world=fixture();const app=world.restart();
  const results=await Promise.allSettled([prepared(app),prepared(app)]);
  assert.equal(results.filter(r=>r.status==='fulfilled').length,1);
  assert.equal(results.filter(r=>r.status==='rejected').length,1);
  const saved=await app.loadPending('owner-a');assert(saved);
  assert.equal([...world.storage.keys()].filter(uri=>uri.startsWith(world.root)&&uri.endsWith('.mp4')).length,1);
});


test('local cleanup failure retains the completed intent rather than creating a duplicate job',async()=>{
  const world=fixture();let app=world.restart();const record=await prepared(app);
  world.failDeleteCopy=true;
  await assert.rejects(app.resumeUpload(record,'token',()=>{}),/storage busy/);
  app=world.restart();const saved=await app.loadPending('owner-a');assert(saved);
  assert.equal((await app.resumeUpload(saved,'token',()=>{})).id,'job-one');
  assert.equal([...world.sessions.values()][0].completeCalls,1);
  assert.equal(await app.loadPending('owner-a'),null);
});


test('confirmed discard after remote project deletion removes only its private pending copy',async()=>{
  const world=fixture();const app=world.restart();const record=await prepared(app);
  world.dropPart=true;await assert.rejects(app.resumeUpload(record,'token',()=>{}));
  const saved=await app.loadPending('owner-a');world.gone=true;
  await assert.rejects(app.resumeUpload(saved,'token',()=>{}));
  assert(world.storage.has(world.root+saved.localName));
  assert.equal(await app.discardUpload(saved,'token'),null);
  assert.equal(await app.loadPending('owner-a'),null);
  assert(world.storage.has('file:///original.mp4'));
  assert(!world.storage.has(world.root+saved.localName));
});


test('rights are required before durable upload preparation or starting network upload',async()=>{
  const world=fixture();const app=world.restart();
  await assert.rejects(app.prepareUpload('owner-a',{uri:'file:///original.mp4',name:'source.mp4'},'Test','vlog',15),/Confirm upload rights/);
  assert.equal(await app.loadPending('owner-a'),null);assert.equal(world.sessions.size,0);
  const record=await prepared(app);delete record.rightsVersion;
  await assert.rejects(app.resumeUpload(record,'token',()=>{}),/Confirm upload rights/);
  assert.equal(world.sessions.size,0);
});

test('old saved intents require explicit reconfirmation and keep their original key and progress',async()=>{
  const world=fixture();let app=world.restart();const record=await prepared(app);
  world.dropPart=true;await assert.rejects(app.resumeUpload(record,'token',()=>{}));
  for(const [uri,bytes] of world.storage){
    if(uri.endsWith('.json')){const value=JSON.parse(bytes.toString());delete value.rightsVersion;world.storage.set(uri,Buffer.from(JSON.stringify(value)));}
  }
  app=world.restart();let saved=await app.loadPending('owner-a');assert.equal(saved.rightsVersion,undefined);
  await assert.rejects(app.resumeUpload(saved,'token',()=>{}),/Confirm upload rights/);
  await assert.rejects(app.confirmUploadRights(saved,false),/Confirm upload rights/);
  saved=await app.confirmUploadRights(saved,true);
  assert.equal(saved.key,record.key);assert.equal(saved.rightsVersion,'upload-rights-v1');
  assert.equal((await app.resumeUpload(saved,'token',()=>{})).id,'job-one');
  assert.deepEqual(world.offsets,[0,4,8]);assert.equal(world.sessions.size,1);
});

test('discarding an unstarted legacy intent uses a key-only tombstone and asserts no rights',async()=>{
  const world=fixture();const app=world.restart();const record=await prepared(app);delete record.rightsVersion;
  assert.equal(await app.discardUpload(record,'token'),null);
  assert.equal(world.sessions.size,1);assert.equal([...world.sessions.values()][0].discardOnly,true);assert.deepEqual(world.offsets,[]);
  assert.equal(await app.loadPending('owner-a'),null);assert(world.storage.has('file:///original.mp4'));
});


test('a stale screen cannot confirm, resume or discard a newer pending intent',async()=>{
  const world=fixture();const app=world.restart();const old=await prepared(app);
  await app.discardUpload(old,'token');const next=await prepared(app);
  await assert.rejects(app.confirmUploadRights(old,true),/changed/);
  await assert.rejects(app.resumeUpload(old,'token',()=>{}),/changed/);
  await assert.rejects(app.discardUpload(old,'token'),/changed/);
  assert.equal((await app.loadPending('owner-a')).key,next.key);
  assert(world.storage.has(world.root+next.localName));
});

test('direct upload restart skips a sealed chunk after losing its commit response',async()=>{
  const world=fixture({direct:true});let app=world.restart();const record=await prepared(app);
  world.dropPart=true;
  await assert.rejects(app.resumeUpload(record,'private-token',()=>{}),/lost chunk response/);
  app=world.restart();
  const job=await app.resumeUpload(await app.loadPending('owner-a'),'private-token',()=>{});
  assert.equal(job.id,'job-one');assert.deepEqual(world.signedTransfers,[0,4,8]);
  assert.deepEqual(world.offsets,[0,4,8]);assert.equal(world.openHandles,0);
});

test('expired storage capability preserves intent and never receives API credentials',async()=>{
  const world=fixture({direct:true});const app=world.restart();const record=await prepared(app);
  world.denySigned=true;
  await assert.rejects(app.resumeUpload(record,'private-token',()=>{}),/failed or expired/);
  const saved=await app.loadPending('owner-a');assert.equal(saved.key,record.key);
  assert(world.storage.has(world.root+record.localName));assert.deepEqual(world.offsets,[]);
  await app.resumeUpload(saved,'private-token',()=>{});
  assert.deepEqual(world.signedTransfers,[0,0,4,8]);assert.deepEqual(world.offsets,[0,4,8]);
});

test('lost direct PUT response retransfers only unacknowledged data after restart',async()=>{
  const world=fixture({direct:true});let app=world.restart();const record=await prepared(app);
  world.dropSigned=true;
  await assert.rejects(app.resumeUpload(record,'private-token',()=>{}),/lost signed PUT/);
  assert.deepEqual(world.offsets,[]);app=world.restart();
  await app.resumeUpload(await app.loadPending('owner-a'),'private-token',()=>{});
  assert.equal(world.sessions.size,1);assert.deepEqual(world.signedTransfers,[0,0,4,8]);
  assert.equal(world.openHandles,0);
});

test('direct client refuses insecure storage addresses and preserves the private copy',async()=>{
  const world=fixture({direct:true});const app=world.restart();const record=await prepared(app);
  world.signedOrigin='http://storage.example';
  await assert.rejects(app.resumeUpload(record,'private-token',()=>{}),/not secure/);
  assert.deepEqual(world.signedTransfers,[]);assert.equal(world.openHandles,0);
  assert(world.storage.has(world.root+record.localName));assert(await app.loadPending('owner-a'));
});


test('SDK 58 asynchronous chunk read respects pause before sending and closes its handle',async()=>{
  const controller=new AbortController();
  const world=fixture({afterRead:()=>controller.abort()});const app=world.restart();const record=await prepared(app);
  await assert.rejects(app.resumeUpload(record,'token',()=>{},controller.signal),/paused/);
  assert.deepEqual(world.offsets,[]);assert.equal(world.openHandles,0);
  assert(world.storage.has(world.root+record.localName));assert(await app.loadPending('owner-a'));
});
