const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path');
function load(name,adapters={},globals={}){
 const exports={};const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/'+name+'.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(code,{exports,require:name=>adapters[name],...globals});return exports;
}
function fixture(){
 const calls=[],expired=[],events=load('authEvents');events.onUnauthorized(token=>expired.push(token));
 const state={status:202,body:{status:'accepted'},offline:false};
 const fetch=async(url,init={})=>{if(state.offline)throw Error('offline');calls.push({url,init});return {status:state.status,ok:state.status<400,json:async()=>state.body};};
 const api=load('api',{'./authEvents':events},{fetch,Headers,process:{env:{EXPO_PUBLIC_API_URL:'http://localhost'}}});
 const actions=load('emailActions',{'./api':api},{fetch});return {actions,state,calls,expired};
}
test('reset request is public, POST-only and does not claim account existence',async()=>{
 const f=fixture();await f.actions.requestPasswordReset(' user@example.com ');
 const call=f.calls.at(-1);assert.equal(call.init.method,'POST');assert.equal(call.init.credentials,'omit');
 assert.deepEqual(JSON.parse(call.init.body),{email:'user@example.com'});assert.equal(call.init.headers.Authorization,undefined);
});
test('reset code and password stay in the body, never URL or auth headers',async()=>{
 const f=fixture();f.state.status=204;await f.actions.confirmPasswordReset(' a-private-code ','a new private password');
 const call=f.calls.at(-1);assert(!call.url.includes('private'));assert.deepEqual(JSON.parse(call.init.body),{code:'a-private-code',new_password:'a new private password'});
 assert.equal(call.init.credentials,'omit');assert.equal(call.init.headers.Authorization,undefined);
});
test('public action failures never expire an existing session',async()=>{
 const f=fixture();f.state.status=401;f.state.body={detail:'denied'};
 await assert.rejects(f.actions.confirmPasswordReset('code','new password'));await assert.rejects(f.actions.confirmEmail('code'));
 assert.deepEqual(f.expired,[]);
});
test('verification request authenticates and expires only its originating token',async()=>{
 const f=fixture();await f.actions.requestEmailVerification('older');
 assert.equal(f.calls.at(-1).init.headers.get('Authorization'),'Bearer older');
 f.state.status=401;f.state.body={detail:'denied'};await assert.rejects(f.actions.requestEmailVerification('older'));
 assert.deepEqual(f.expired,['older']);
});
test('unexpected success status is not confirmation',async()=>{
 const f=fixture();f.state.status=200;
 await assert.rejects(f.actions.confirmPasswordReset('code','new password'),/not confirmed/);
 await assert.rejects(f.actions.confirmEmail('code'),/not confirmed/);
 await assert.rejects(f.actions.requestPasswordReset('email@example.com'),/not confirmed/);
});
test('delivery availability fails closed for an unsupported backend',async()=>{
 const f=fixture();f.state.status=200;f.state.body={delivery:'smtp',verification_enforced:false};
 await assert.rejects(f.actions.recoveryCapabilities(),/unavailable/);
 f.state.body={delivery:'disabled',verification_enforced:false};assert.equal((await f.actions.recoveryCapabilities()).delivery,'disabled');
 f.state.body={delivery:'local_file',verification_enforced:false};assert.equal((await f.actions.recoveryCapabilities()).delivery,'local_file');
});
test('network failure propagates without success or session mutation',async()=>{
 const f=fixture();f.state.offline=true;
 await assert.rejects(f.actions.confirmPasswordReset('code','new password'),/offline/);assert.deepEqual(f.expired,[]);
});
