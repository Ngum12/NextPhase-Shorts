const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
function load(name,adapters={},globals={}) {
 const exports={},source=fs.readFileSync(path.join(__dirname,'../src/'+name+'.ts'),'utf8');
 vm.runInNewContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,
  {exports,require:key=>adapters[key],...globals});return exports;
}
const moduleSession=load('refreshSession'),{RefreshSessionController}=moduleSession;
const pair=(name='first',seconds=60)=>({access_token:name,refresh_token:name[0].repeat(43),expires_in:seconds,refresh_expires_in:6000});
const defer=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
function fixture(saved=null) {
 let value=saved,clock=100000,key=0;const published=[],rotations=[];
 const storage={read:async()=>value,write:async next=>{value=next;},remove:async()=>{value=null;}};
 const remote={validate:async()=>{},refresh:async(token,key)=>{rotations.push([token,key]);return pair('second',900);},
  revokeRefresh:async()=>{},revoke:async()=>{},password:async()=>{}};
 const controller=new RefreshSessionController(storage,remote,next=>published.push(next),()=>`00000000-0000-4000-8000-${String(++key).padStart(12,'0')}`,()=>clock);
 return {controller,storage,remote,published,rotations,get saved(){return value;},advance(ms){clock+=ms;}};
}
test('concurrent expiry requests share one rotation and old closures use the replacement',async()=>{
 const f=fixture();await f.controller.signIn(pair());f.advance(31000);
 const values=await Promise.all([f.controller.prepare('first'),f.controller.prepare('first'),f.controller.recover('first')]);
 assert.deepEqual(values,['second','second','second']);assert.equal(f.rotations.length,1);
 assert.equal(await f.controller.prepare('first'),'second');assert.equal(JSON.parse(f.saved).access,'second');
 assert.deepEqual(f.published,['first']); // Rotation must not trigger account-change upload cancellation.
});
test('lost refresh response preserves its durable key across runtime restart',async()=>{
 const f=fixture();await f.controller.signIn(pair());f.advance(31000);
 let intent;f.remote.refresh=async(token,key)=>{intent=[token,key];throw Error('lost response');};
 await assert.rejects(f.controller.prepare('first'),/lost response/);
 assert.equal(JSON.parse(f.saved).pending,intent[1]);
 const next=fixture(f.saved);next.remote.refresh=async(token,key)=>{assert.deepEqual([token,key],intent);return pair('second',900);};
 await next.controller.restore();assert.equal(next.controller.token,'second');assert.equal(JSON.parse(next.saved).pending,undefined);
});
test('failed journal write sends no refresh request',async()=>{
 const f=fixture();await f.controller.signIn(pair());f.advance(31000);f.storage.write=async()=>{throw Error('storage full');};
 await assert.rejects(f.controller.prepare('first'),/storage full/);assert.equal(f.rotations.length,0);assert.equal(f.controller.token,'first');
});
test('failed replacement write retains the same intent for retry',async()=>{
 const f=fixture();await f.controller.signIn(pair());f.advance(31000);const write=f.storage.write;let writes=0;
 f.storage.write=async value=>{if(++writes===2)throw Error('storage full');await write(value);};
 await assert.rejects(f.controller.prepare('first'),/storage full/);const key=JSON.parse(f.saved).pending;
 f.storage.write=write;assert.equal(await f.controller.prepare('first'),'second');
 assert.equal(f.rotations.length,2);assert.equal(f.rotations[0][1],key);assert.equal(f.rotations[1][1],key);
});
test('late refresh success cannot overwrite a newer account or lend its token',async()=>{
 const f=fixture(),wait=defer();await f.controller.signIn(pair());f.advance(31000);f.remote.refresh=()=>wait.promise;
 const renewal=f.controller.prepare('first');await new Promise(setImmediate);await f.controller.signIn(pair('new-account',900));
 wait.resolve(pair('second',900));await assert.rejects(renewal,/Session changed/);
 assert.equal(f.controller.token,'new-account');assert.equal(JSON.parse(f.saved).access,'new-account');
 await assert.rejects(f.controller.prepare('first'),/Session changed/);await f.controller.expire('first');assert.equal(f.controller.token,'new-account');
});
test('late refresh rejection cannot erase a newer login',async()=>{
 const f=fixture(),wait=defer();await f.controller.signIn(pair());f.advance(31000);f.remote.refresh=()=>wait.promise;
 const renewal=f.controller.prepare('first');await new Promise(setImmediate);await f.controller.signIn(pair('new-account',900));
 wait.reject({status:401});await assert.rejects(renewal);assert.equal(JSON.parse(f.saved).access,'new-account');
});
test('replacement storage finishing during sign-in is serialized before the newer credential',async()=>{
 const f=fixture(),wait=defer();await f.controller.signIn(pair());f.advance(31000);
 const write=f.storage.write;let blocked=false;
 f.storage.write=async value=>{if(JSON.parse(value).access==='second'){blocked=true;await wait.promise;}await write(value);};
 const renewal=f.controller.prepare('first');await new Promise(setImmediate);assert(blocked);
 const newer=f.controller.signIn(pair('new-account',900));wait.resolve();
 await assert.rejects(renewal,/Session changed/);await newer;assert.equal(JSON.parse(f.saved).access,'new-account');
});
test('definitive rejection removes credentials; offline refresh preserves them',async()=>{
 for(const status of [401,503]) {
  const f=fixture();await f.controller.signIn(pair());f.advance(31000);f.remote.refresh=async()=>{throw {status};};
  await assert.rejects(f.controller.prepare('first'));
  if(status===401)assert.equal(f.saved,null);else {assert.equal(f.controller.token,'first');assert(JSON.parse(f.saved).pending);}
 }
});
test('single-device logout works with an expired access token; offline logout retains credentials',async()=>{
 const f=fixture();await f.controller.signIn(pair());f.advance(100000);let refresh;
 f.remote.revokeRefresh=async token=>{refresh=token;throw Error('offline');};
 await assert.rejects(f.controller.signOut(),/offline/);assert(f.saved);assert.equal(f.rotations.length,0);
 f.remote.revokeRefresh=async token=>{refresh=token;};await f.controller.signOut();assert.equal(refresh,'f'.repeat(43));assert.equal(f.saved,null);
});
test('all-device logout and password change obtain fresh access first',async()=>{
 for(const action of ['all','password']) {
  const f=fixture();await f.controller.signIn(pair());f.advance(31000);let seen;
  f.remote.revoke=async(token,all)=>{seen=[token,all];};f.remote.password=async(token)=>{seen=[token];};
  if(action==='all')await f.controller.signOut(true);else await f.controller.changePassword('before','after');
  assert.equal(seen[0],'second');assert.equal(f.saved,null);
 }
});
test('a refused all-device logout preserves the renewed credential for an explicit retry',async()=>{
 const f=fixture();await f.controller.signIn(pair());f.advance(31000);
 f.remote.revoke=async()=>{throw {status:401};};
 await assert.rejects(f.controller.signOut(true));assert.equal(f.controller.token,'second');assert.equal(JSON.parse(f.saved).access,'second');
});
test('legacy token restore works; invalid stored JSON is removed',async()=>{
 const f=fixture('legacy');await f.controller.restore();assert.equal(f.controller.token,'legacy');assert.equal(await f.controller.prepare('legacy'),'legacy');
 assert.equal(await f.controller.recover('legacy'),null);assert.equal(f.saved,null);
 const invalid=fixture('{"version":2,"refresh":"bad"}');await invalid.controller.restore();assert.equal(invalid.saved,null);
});
test('old startup validation cannot publish over a newer sign-in',async()=>{
 const f=fixture('legacy'),wait=defer();f.remote.validate=()=>wait.promise;
 const restoration=f.controller.restore();await new Promise(setImmediate);await f.controller.signIn(pair('new-account',900));
 wait.resolve();await restoration;assert.equal(f.published.at(-1),'new-account');assert.equal(JSON.parse(f.saved).access,'new-account');
});
test('authenticated GET retries once; uploads refresh without replaying their bodies',async()=>{
 const events=load('authEvents'),calls=[];let recoveries=0;
 events.coordinateSession({prepare:async token=>token,recover:async()=>{recoveries++;return 'second';}});
 const api=load('api',{'./authEvents':events,'./refreshSession':moduleSession},{process:{env:{EXPO_PUBLIC_API_URL:'http://localhost'}},Headers,
  fetch:async(url,init)=>{calls.push(init);return {status:calls.length%2?401:200,ok:calls.length%2===0,json:async()=>({})};}});
 await api.api('/api/v1/me','first');assert.equal(calls.length,2);assert.equal(calls[1].headers.get('Authorization'),'Bearer second');
 calls.length=0;await api.authenticatedFetch('first','http://localhost/upload',{method:'PUT',body:'chunk'});
 assert.equal(calls.length,1);assert.equal(recoveries,2);
});
test('public refresh and refresh-logout send no bearer or cookies',async()=>{
 const events=load('authEvents'),calls=[];
 const api=load('api',{'./authEvents':events,'./refreshSession':moduleSession},{process:{env:{EXPO_PUBLIC_API_URL:'http://localhost'}},Headers,
  fetch:async(url,init)=>{calls.push([url,init]);return {status:url.endsWith('/logout')?204:200,ok:true,json:async()=>pair()};}});
 await api.refreshSession('f'.repeat(43),'key');await api.revokeRefreshSession('f'.repeat(43));
 for(const [url,init] of calls){assert.equal(init.credentials,'omit');assert.equal(init.headers.Authorization,undefined);assert(!url.includes('f'.repeat(43)));}
});
test('authenticated transport refuses another origin before resolving credentials',async()=>{
 const events=load('authEvents');let prepared=false;
 events.coordinateSession({prepare:async()=>{prepared=true;return 'secret';},recover:async()=>null});
 const api=load('api',{'./authEvents':events,'./refreshSession':moduleSession},{process:{env:{EXPO_PUBLIC_API_URL:'https://api.example'}},Headers});
 await assert.rejects(api.authenticatedFetch('first','https://storage.example/put'),/API origin/);assert.equal(prepared,false);
});
test('native Save retries a safe download with fresh access before saving',async()=>{
 const calls=[];let downloads=0;
 const exports=load('videoExports',{'react-native':{Platform:{OS:'android',Version:33}},
  'expo-file-system/legacy':{cacheDirectory:'file:///cache/',downloadAsync:async(url,dest,init)=>{
   calls.push(init.headers.Authorization);return {status:++downloads===1?401:200,uri:dest};},getInfoAsync:async()=>({exists:true,size:1})},
  'expo-media-library':{saveToLibraryAsync:async()=>calls.push('saved')},'expo-sharing':{},
  './api':{downloadUrl:()=> 'http://localhost/download'},'./authEvents':{prepareToken:async()=> 'first',recoverToken:async()=> 'second'}});
 await exports.exportVideo('save','job','old');assert.deepEqual(calls,['Bearer first','Bearer second','saved']);
});
