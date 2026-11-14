const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..');
test('the upload screen displays current retention limitations before consent',()=>{
  const screen=fs.readFileSync(path.join(root,'app/create.tsx'),'utf8');
  const copy=fs.readFileSync(path.join(root,'src/uploadRights.ts'),'utf8');
  assert.match(screen,/MEDIA_RETENTION_NOTICE/);
  assert.match(screen,/Video storage and deletion/);
  assert.match(copy,/automatic expiration is NOT active yet/);
  assert.match(copy,/Save & finish/);
  assert.match(copy,/encrypted backups/);
  assert.doesNotMatch(copy,/deleted permanently after download/i);
});
