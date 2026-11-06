const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
function load(name,adapters={},globals={}) {
 const exports={},source=fs.readFileSync(path.join(__dirname,'../src/'+name+'.ts'),'utf8');
 const code=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(code,{exports,require:key=>adapters[key],...globals});return exports;
}
const {SessionController}=load('session');
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};}
function fixture(saved=null) {
 const published=[];let value=saved;
 const storage={read:async()=>value,write:async token=>{value=token;},remove:async()=>{value=null;}};
 const calls=[],remote={validate:async()=>{},revoke:async(token,all)=>{calls.push([token,all]);},password:async()=>{}};
 return {storage,remote,published,calls,controller:new SessionController(storage,remote,token=>published.push(token)),get saved(){return value;}};
}
test('startup rejects revoked credentials but preserves them during an outage',async()=>{
 const a=fixture('old');a.remote.validate=async()=>{throw {status:401};};await a.controller.restore();assert.equal(a.saved,null);assert.equal(a.controller.token,null);
 const b=fixture('offline');b.remote.validate=async()=>{throw Error('offline');};await b.controller.restore();assert.equal(b.saved,'offline');assert.deepEqual(b.published,['offline']);
});
test('late startup validation cannot overwrite a newer sign-in',async()=>{
 const f=fixture('old'),wait=deferred();f.remote.validate=()=>wait.promise;
 const restore=f.controller.restore();await Promise.resolve();await f.controller.signIn('new');wait.resolve();await restore;
 assert.equal(f.controller.token,'new');assert.equal(f.saved,'new');assert.deepEqual(f.published,['new']);
});
test('late unauthorized response cannot clear a newer account session',async()=>{
 const f=fixture();await f.controller.signIn('old');await f.controller.signIn('new');await f.controller.expire('old');assert.equal(f.saved,'new');assert.equal(f.controller.token,'new');
});
test('secure storage serializes expiration before a newer sign-in',async()=>{
 const f=fixture(),wait=deferred();let disk=null;f.storage.write=async token=>{disk=token;};f.storage.remove=async()=>{await wait.promise;disk=null;};
 await f.controller.signIn('old');const expire=f.controller.expire('old'),signin=f.controller.signIn('new');wait.resolve();await Promise.all([expire,signin]);assert.equal(disk,'new');assert.equal(f.controller.token,'new');
});
test('offline sign-out retains credentials until server revocation succeeds',async()=>{
 const f=fixture();await f.controller.signIn('active');f.remote.revoke=async()=>{throw Error('offline');};await assert.rejects(f.controller.signOut(),/offline/);assert.equal(f.saved,'active');assert.equal(f.controller.token,'active');
 f.remote.revoke=async(token,all)=>f.calls.push([token,all]);await f.controller.signOut(true);assert.deepEqual(f.calls,[['active',true]]);assert.equal(f.saved,null);
});
test('password change removes credentials only after server success',async()=>{
 const f=fixture();await f.controller.signIn('active');f.remote.password=async()=>{throw {status:400};};await assert.rejects(f.controller.changePassword('wrong','new'));assert.equal(f.saved,'active');
 f.remote.password=async()=>{};await f.controller.changePassword('correct','new');assert.equal(f.saved,null);
});
test('authenticated 401 reports its token; login failures do not expire sessions',async()=>{
 const events=load('authEvents'),expired=[];events.onUnauthorized(token=>expired.push(token));let status=401;const calls=[];
 const api=load('api',{'./authEvents':events},{process:{env:{EXPO_PUBLIC_API_URL:'http://localhost'}},Headers,fetch:async(url,init)=>{calls.push([url,init]);return {status,ok:status<400,json:async()=>({detail:'denied'})};}});
 await assert.rejects(api.api('/api/v1/me','older'));assert.deepEqual(expired,['older']);await assert.rejects(api.login('test@example.com','wrong'));assert.deepEqual(expired,['older']);
 await api.logoutSession('revoked',true);assert.deepEqual(expired,['older','revoked']);assert(calls.at(-1)[0].endsWith('/logout-all'));
 status=204;await api.changePassword('current','before','after');assert.equal(calls.at(-1)[1].headers.get('Authorization'),'Bearer current');
});
