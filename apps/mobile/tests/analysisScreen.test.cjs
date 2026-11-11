// Component logic with hook/native adapters; not a device or accessibility test.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path');
function document(){return {job_id:'project-1',revision:'a'.repeat(64),transcript_sha256:'b'.repeat(64),
 transcript:{language:'en',source_sha256:'c'.repeat(64),words:[
  {text:'Original',start_ms:0,end_ms:6000,confidence:.2},{text:'speech.',start_ms:6000,end_ms:12000,confidence:.9}]},
 review:null,proposal:{candidates:[],warnings:[]},render_enabled:false};}
function harness(){
 const h={slots:[],cursor:0,pending:true,effects:[],tree:null,token:'first-session',id:'project-1',calls:[],alerts:[],value:document(),getError:null,saveError:null};
 const react={createElement:(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)}),
  useState(initial){const i=h.cursor++;if(!h.slots[i])h.slots[i]={value:initial};return [h.slots[i].value,next=>{h.slots[i].value=typeof next==='function'?next(h.slots[i].value):next;h.pending=true;}];},
  useRef(initial){const i=h.cursor++;if(!h.slots[i])h.slots[i]={current:initial};return h.slots[i];},
  useEffect(effect,deps){const i=h.cursor++,old=h.slots[i];if(!old||deps.some((v,n)=>v!==old.deps[n])){
    h.effects.push(()=>{old?.cleanup?.();h.slots[i]={deps,cleanup:effect()};});}}
 };react.default=react;
 class ApiError extends Error{constructor(status,message){super(message);this.status=status;}}
 const adapters={react,'react-native':{Alert:{alert:(...args)=>h.alerts.push(args)},Pressable:'Pressable',ScrollView:'ScrollView',Text:'Text',View:'View'},
  'expo-router':{useLocalSearchParams:()=>({id:h.id}),router:{replace:route=>h.calls.push({back:route})}},
  '../../src/auth':{useAuth:()=>({token:h.token})},'../../src/api':{ApiError},
  '../../src/ui':Object.fromEntries(['Body','Button','Loading','Page','Title'].map(name=>[name,name]).concat([['s',{card:{},cardTitle:{}}]])),
  '../../src/theme':{colors:{}},'../../src/analysis':{englishReviewVisible:true,
   getEnglishAnalysis:async(id,token)=>{h.calls.push({get:id,token});if(h.getError)throw h.getError;return h.delayedGet?h.delayedGet:structuredClone(h.value);},
   saveEnglishReview:async(id,token,revision,review)=>{h.calls.push({save:id,token,revision,review});if(h.saveError)throw h.saveError;
    return {...structuredClone(h.value),review,proposal:{candidates:[{first_word:0,last_word:1,source_start_ms:0,source_end_ms:12000,output_frames:360}],warnings:[]}};}}};
 const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../app/review/[id].tsx'),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
 const exports={};vm.runInNewContext(code,{exports,require:name=>{assert(adapters[name],name);return adapters[name];}});
 h.render=()=>{h.cursor=0;h.pending=false;h.tree=exports.default();};
 h.flush=async()=>{for(let i=0;i<12;i++){if(h.pending)h.render();while(h.effects.length)h.effects.shift()();await new Promise(resolve=>setImmediate(resolve));if(!h.pending&&!h.effects.length)break;}};
 h.nodes=()=>{const found=[];function visit(node){if(node&&typeof node==='object'){found.push(node);node.children?.forEach(visit);}}visit(h.tree);return found;};
 h.button=title=>h.nodes().find(n=>n.type==='Button'&&n.props.title===title);
 h.check=prefix=>h.nodes().find(n=>n.type==='Pressable'&&n.props.accessibilityLabel?.startsWith(prefix));
 h.ack=()=>h.nodes().find(n=>n.type==='Pressable'&&!n.props.accessibilityLabel);
 h.text=()=>{function read(n){return typeof n==='string'?n:n&&typeof n==='object'?(n.children||[]).map(read).join(' '):'';}return read(h.tree);};
 h.ApiError=ApiError;return h;
}
async function ready(){const h=harness();await h.flush();return h;}
test('review starts empty and cannot save until boundaries and acknowledgement are supplied',async()=>{
 const h=await ready();assert(h.text().includes('Original'));
 assert.equal(h.button('Save review and find clips').props.disabled,true);
 h.check('Word 2:').props.onPress();await h.flush();
 h.check('Confirm word 1:').props.onPress();await h.flush();
 h.ack().props.onPress();await h.flush();
 assert.equal(h.button('Save review and find clips').props.disabled,false);
 await h.button('Save review and find clips').props.onPress();await h.flush();
 const saved=h.calls.find(c=>c.save);assert.deepEqual(Array.from(saved.review.sentence_end_words),[2]);
 assert.deepEqual(Array.from(saved.review.confirmed_low_confidence_words),[1]);
 assert.equal(saved.review.acknowledged_original_recording,true);
 assert(h.nodes().some(n=>n.type==='Button'&&n.props.title.startsWith('Option 1')));
});
test('two word taps in one render keep both boundaries and invalidate acknowledgement',async()=>{
 const h=await ready();h.ack().props.onPress();await h.flush();
 h.check('Word 1:').props.onPress();h.check('Word 2:').props.onPress();await h.flush();
 assert.equal(h.check('Word 1:').props.accessibilityState.checked,true);
 assert.equal(h.check('Word 2:').props.accessibilityState.checked,true);
 assert.equal(h.ack().props.accessibilityState.checked,false);
});
test('changed remote review disables save until explicit refresh',async()=>{
 const h=await ready();h.check('Word 2:').props.onPress();await h.flush();h.ack().props.onPress();await h.flush();
 h.saveError=new h.ApiError(409,'This review changed. Refresh before saving again.');
 await h.button('Save review and find clips').props.onPress();await h.flush();
 assert(h.text().includes('This review changed'));assert.equal(h.button('Save review and find clips').props.disabled,true);
 h.button('Refresh review').props.onPress();assert.equal(h.alerts.at(-1)[0],'Discard unsaved review?');
});
test('missing analysis presents a refresh path without transcript or enabled save',async()=>{
 const h=harness();h.getError=new h.ApiError(404,'No English transcript is ready for this project');await h.flush();
 assert(h.text().includes('No English transcript'));assert(!h.text().includes('Original'));
 assert(h.button('Refresh review'));assert(!h.button('Save review and find clips'));
});
test('account/session change hides prior text before effects run',async()=>{
 const h=await ready();assert(h.text().includes('Original'));h.token='second-session';h.render();
 assert(!h.text().includes('Original'));
});
test('a late response from an old project cannot replace the current review',async()=>{
 const h=harness();let resolve;h.delayedGet=new Promise(r=>{resolve=r;});await h.flush();
 h.id='project-2';h.value=document();h.value.job_id='project-2';h.value.transcript.words[0].text='Current';
 h.delayedGet=null;h.pending=true;await h.flush();assert(h.text().includes('Current'));
 resolve(document());await h.flush();assert(h.text().includes('Current'));assert(!h.text().includes('Original'));
});
