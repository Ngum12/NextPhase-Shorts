const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const exportsObject={};vm.runInNewContext(ts.transpileModule(fs.readFileSync('src/accountDeletionFlow.ts','utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:exportsObject});
const uid='11111111-1111-4111-8111-111111111111',key='22222222-2222-4222-8222-222222222222';
function fixture(){
 const state={raw:null,requestError:null,receiptError:null,cleanupError:null},calls=[];
 const storage={read:async()=>state.raw,write:async value=>{state.raw=value;},remove:async()=>{state.raw=null;}};
 const remote={me:async()=>({id:uid}),request:async()=>{calls.push('request');if(state.requestError)throw state.requestError;return {status:'account_disabled'};},receipt:async()=>{calls.push('receipt');if(state.receiptError)throw state.receiptError;return {status:'account_disabled'};}};
 const make=()=>new exportsObject.AccountDeletionFlow(storage,remote,async owner=>{calls.push('cleanup:'+owner);if(state.cleanupError)throw state.cleanupError;},()=>key);
 return {state,calls,remote,make};
}
test('lost acceptance response is recovered before private cleanup and token expiration',async()=>{
 const f=fixture();f.state.requestError=Error('offline');await f.make().submit(uid,'old-token','secret',async token=>f.calls.push(token));
 assert.deepEqual(f.calls,['request','receipt','cleanup:'+uid,'old-token']);assert.equal(f.state.raw,null);
});
test('ambiguous failure survives runtime restart without storing credentials',async()=>{
 const f=fixture();f.state.requestError=Error('offline');f.state.receiptError=Error('offline');
 await assert.rejects(f.make().submit(uid,'old-token','secret',async()=>{}));
 assert(f.state.raw.includes(key));assert(!f.state.raw.includes('secret'));assert(!f.state.raw.includes('old-token'));
 assert(!f.calls.some(c=>c.startsWith('cleanup')));f.state.receiptError=null;
 await f.make().recover();assert.equal(f.state.raw,null);
});
test('definitive initial password rejection discards only the confirmation intent',async()=>{
 const f=fixture();f.state.requestError={status:400};f.state.receiptError={status:404};
 await assert.rejects(f.make().submit(uid,'token','wrong',async()=>{}));assert.equal(f.state.raw,null);
 assert(!f.calls.some(c=>c.startsWith('cleanup')));
});
test('password rejection after ambiguous earlier request preserves recovery key',async()=>{
 const f=fixture();f.state.raw=JSON.stringify({version:1,ownerId:uid,key,sent:true});
 f.state.requestError={status:400};f.state.receiptError={status:404};
 await assert.rejects(f.make().submit(uid,'token','wrong',async()=>{}));assert(f.state.raw.includes(key));
});
test('local cleanup failure preserves confirmation for safe retry',async()=>{
 const f=fixture();f.state.cleanupError=Error('busy');await assert.rejects(f.make().submit(uid,'token','secret',async()=>{}));
 assert(f.state.raw);f.state.cleanupError=null;await f.make().recover();assert.equal(f.state.raw,null);
});
test('stale account screen cannot submit deletion for another account',async()=>{
 const f=fixture();await assert.rejects(f.make().submit(key,'token','secret',async()=>{}),/Account changed/);assert.equal(f.calls.length,0);
});
