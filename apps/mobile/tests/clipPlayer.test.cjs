// Private-cache/focus lifecycle with adapters; native video decoding is device QA.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path');
function harness(){
 const h={slots:[],index:0,pending:true,tree:null,token:'session',id:'preview',focused:true,focus:null,active:null,cleanup:null,loads:0,removed:[]};
 const react={createElement:(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)}),
  useState(initial){const i=h.index++;if(!h.slots[i])h.slots[i]={value:initial};return [h.slots[i].value,next=>{h.slots[i].value=typeof next==='function'?next(h.slots[i].value):next;h.pending=true;}];},
  useRef(initial){const i=h.index++;if(!h.slots[i])h.slots[i]={current:initial};return h.slots[i];},
  useCallback(fn,deps){const i=h.index++,old=h.slots[i];if(!old||deps.some((v,n)=>v!==old.deps[n]))h.slots[i]={deps,fn};return h.slots[i].fn;},
  useEffect(){},
 };react.default=react;
 const adapters={react,'react-native':{Text:'Text',View:'View'},
  'expo-router':{useFocusEffect:fn=>{h.focus=fn;}},'expo-video':{useVideoPlayer:()=>{},VideoView:'VideoView'},
  './ui':{Body:'Body',Button:'Button',Loading:'Loading'},'./theme':{colors:{}},
  './clipPreviews':{loadPreviewFile:async()=>{const count=++h.loads;await h.wait;return {uri:`file:///private/${count}.mp4`,remove:async()=>{h.removed.push(count);}};}}};
 const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/ClipPlayer.tsx'),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
 const exports={};vm.runInNewContext(code,{exports,require:name=>adapters[name]});
 h.render=()=>{h.index=0;h.pending=false;h.tree=exports.ClipPlayer({id:h.id,token:h.token});
  if(h.focused&&h.focus!==h.active){h.cleanup?.();h.active=h.focus;h.cleanup=h.active();}};
 h.flush=async()=>{for(let i=0;i<12;i++){if(h.pending)h.render();await new Promise(r=>setImmediate(r));if(!h.pending)break;}};
 h.nodes=()=>{const list=[];function walk(n){if(n&&typeof n==='object'){list.push(n);n.children?.forEach(walk);}}walk(h.tree);return list;};
 h.watch=()=>h.nodes().find(n=>n.type==='Button'&&n.props.title==='Watch preview');
 h.blur=()=>{h.focused=false;h.cleanup?.();h.cleanup=null;h.active=null;};return h;
}
test('private local media is handed to the player and removed on leaving the screen',async()=>{
 const h=harness();await h.flush();await h.watch().props.onPress();await h.flush();
 const video=h.nodes().find(n=>typeof n.type==='function'&&n.type.name==='LocalVideo');
 assert.equal(video.props.uri,'file:///private/1.mp4');assert(!video.props.uri.includes(h.token));
 h.blur();await h.flush();assert.deepEqual(h.removed,[1]);assert(h.watch());
});
test('duplicate taps do not download twice and a late result after blur is removed',async()=>{
 const h=harness();let finish;h.wait=new Promise(r=>{finish=r;});await h.flush();
 const open=h.watch().props.onPress;const first=open(),second=open();await h.flush();assert.equal(h.loads,1);
 h.blur();await h.flush();finish();await Promise.all([first,second]);await h.flush();
 assert.deepEqual(h.removed,[1]);assert(h.watch());
});
