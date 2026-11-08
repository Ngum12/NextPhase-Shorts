// Exercise the real Expo consumers of the narrowly scoped glob/minimatch overrides.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises'),os=require('node:os'),path=require('node:path');
const {createRequire}=require('node:module');
const fingerprintRequire=createRequire(require.resolve('@expo/fingerprint'));
const cliRequire=createRequire(require.resolve('@expo/cli',{paths:[path.dirname(require.resolve('expo'))]}));

test('both Expo tool consumers load patched CommonJS glob with expected traversal and cancellation',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'nextphase-glob-'));
 try{
  await fs.mkdir(path.join(root,'app'));await fs.mkdir(path.join(root,'ignored'));
  await fs.writeFile(path.join(root,'app','index.tsx'),'fixture');await fs.writeFile(path.join(root,'ignored','secret.tsx'),'fixture');
  for(const consumer of [fingerprintRequire,cliRequire]){
   assert.equal(consumer('glob/package.json').version,'14.0.4');
   const {glob,globSync}=consumer('glob');
   assert.deepEqual(await glob('**/*.tsx',{cwd:root,ignore:['ignored/**'],nodir:true}),[path.join('app','index.tsx')]);
   assert.deepEqual(globSync('**/*.tsx',{cwd:root,ignore:['ignored/**'],nodir:true}),[path.join('app','index.tsx')]);
   const controller=new AbortController();controller.abort();
   await assert.rejects(glob('**/*',{cwd:root,signal:controller.signal}));
  }
 }finally{await fs.rm(root,{recursive:true,force:true});}
});

test('fingerprint path matching retains case/dot/glob semantics with patched minimatch',()=>{
 assert.equal(fingerprintRequire('minimatch/package.json').version,'11.0.5');
 const {minimatch}=fingerprintRequire('minimatch');
 assert(minimatch('app/index.tsx','**/*.tsx'));assert(!minimatch('app/index.ts','**/*.tsx'));
 assert(!minimatch('.private/file.ts','**/*'));assert(minimatch('.private/file.ts','**/*',{dot:true}));
 assert(minimatch('app/INDEX.TSX','**/*.tsx',{nocase:true}));
});
