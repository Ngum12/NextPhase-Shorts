// Mocked component lifecycle proof, not physical-device/audio acceptance.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path');
const revision='a'.repeat(64),parent='11111111-1111-4111-8111-111111111111',owner='22222222-2222-4222-8222-222222222222';
function harness(){
 const h={slots:[],cursor:0,pending:true,effects:[],tree:null,token:'token',owner,ready:true,softEdges:true,calls:[],alerts:[],draft:[{text:'Original words.',start_ms:0,end_ms:3000}]};
 const react={createElement:(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)}),
  useState(initial){const i=h.cursor++;if(!h.slots[i])h.slots[i]={value:initial};return [h.slots[i].value,next=>{h.slots[i].value=typeof next==='function'?next(h.slots[i].value):next;h.pending=true;}];},
  useRef(initial){const i=h.cursor++;if(!h.slots[i])h.slots[i]={current:initial};return h.slots[i];},
  useEffect(effect,deps){const i=h.cursor++,old=h.slots[i];if(!old||deps.some((v,n)=>v!==old.deps[n])){
   h.effects.push(()=>{old?.cleanup?.();h.slots[i]={deps,cleanup:effect()};});}}
 };react.default=react;
 class ApiError extends Error{constructor(status,message){super(message);this.status=status;}}
 const defaults={framing:'fit',captions:true,caption_size:'standard',caption_color:'white',caption_position:'lower',voice:'original',audio_edges:'original'};
 const adapters={react,'react-native':{Alert:{alert:(...args)=>h.alerts.push(args)},Pressable:'Pressable',ScrollView:'ScrollView',Text:'Text',TextInput:'TextInput',View:'View'},
  'expo-router':{useLocalSearchParams:()=>({id:parent,candidate:'1',revision}),
   usePreventRemove:(active,callback)=>{h.prevent=active;h.preventCallback=callback;return()=>{h.prevent=false;};},
   router:{replace:r=>h.calls.push({back:r}),push:r=>h.calls.push({push:r})}},
  '../../src/auth':{useAuth:()=>({token:h.token})},'../../src/api':{ApiError,api:async()=>({id:h.owner})},
  '../../src/analysis':{getEnglishAnalysis:async()=>{if(h.loadError)throw h.loadError;return {revision,review:{},polished_preview_supported:h.ready,
    soft_audio_edges_supported:h.softEdges,proposal:{candidates:[{output_frames:150}]}};}},
  '../../src/ui':Object.fromEntries(['Body','Button','Loading','Page','Title'].map(name=>[name,name]).concat([['s',{card:{},cardTitle:{},input:{}}]])),
  '../../src/theme':{colors:{}},
  '../../src/polish':{defaultPolish:defaults,getCaptionDraft:async()=>({duration_ms:5000,cues:structuredClone(h.draft)}),
   captionMilliseconds:value=>{if(!value.trim()||!Number.isFinite(Number(value)))throw Error('Invalid caption time');return Math.round(Number(value)*1000);},
   validateCues:cues=>{let last=0;for(const cue of cues){if(cue.start_ms<last||cue.end_ms<=cue.start_ms||cue.end_ms>5000)throw Error('Invalid caption times');last=cue.end_ms;}return cues;},
   savePolishPreset:async(id,options)=>{h.calls.push({save:id,options});h.preset=structuredClone(options);},
   loadPolishPreset:async id=>{h.calls.push({loadPreset:id});return h.preset||null;},
   requestPolishedPreview:async(id,token,revision,candidate,options,edits,duration,ack)=>{
    h.calls.push({render:id,token,options,edits,duration,ack});if(h.wait)return h.wait;
    if(h.renderError)throw h.renderError;return {id:'child'};}}
 };
 const exports={};const code=ts.transpileModule(fs.readFileSync(path.join(__dirname,'../app/polish/[id].tsx'),'utf8'),
   {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText;
 vm.runInNewContext(code,{exports,require:name=>{assert(adapters[name],name);return adapters[name];}});
 h.render=()=>{h.cursor=0;h.pending=false;h.tree=exports.default();};
 h.flush=async()=>{for(let i=0;i<15;i++){if(h.pending)h.render();while(h.effects.length)h.effects.shift()();await new Promise(r=>setImmediate(r));if(!h.pending&&!h.effects.length)break;}};
 h.nodes=()=>{const result=[];function visit(node){if(node&&typeof node==='object'){
   if(typeof node.type==='function'){visit(node.type({...node.props,children:node.children}));return;}
   result.push(node);node.children?.forEach(visit);}}visit(h.tree);return result;};
 h.button=title=>h.nodes().find(n=>n.type==='Button'&&n.props.title===title);
 h.input=label=>h.nodes().find(n=>n.type==='TextInput'&&n.props.accessibilityLabel===label);
 h.check=()=>h.nodes().find(n=>n.type==='Pressable'&&n.props.accessibilityRole==='checkbox');
 h.text=()=>h.nodes().flatMap(n=>n.children).filter(n=>typeof n==='string').join(' ');
 return h;
}
test('one screen edits captions, appearance and voice, then renders confirmed immutable choices',async()=>{
 const h=harness();await h.flush();h.button('Edit caption words and timing').props.onPress();await h.flush();
 h.input('Caption text').props.onChangeText('Corrected words.');await h.flush();
 h.input('Caption start seconds').props.onChangeText('0.250');await h.flush();
 h.button('Large').props.onPress();h.button('Warm yellow').props.onPress();h.button('Middle').props.onPress();
 h.button('Level voice volume').props.onPress();h.button('Gentle audio fades (80 ms)').props.onPress();await h.flush();
 await h.button('Render polished preview').props.onPress();await h.flush();assert(h.text().includes('Compare your caption corrections'));
 h.check().props.onPress();await h.flush();await h.button('Render polished preview').props.onPress();
 assert(h.alerts.at(-1)[1].includes('background noise'));
 await h.alerts.at(-1)[2][1].onPress();await h.flush();
 const sent=h.calls.find(c=>c.render);assert.equal(sent.edits[0].text,'Corrected words.');assert.equal(sent.edits[0].start_ms,250);
 assert.equal(sent.options.voice,'level');assert.equal(sent.options.audio_edges,'soft');assert.equal(sent.options.caption_color,'yellow');assert(h.calls.some(c=>c.push?.params.id==='child'));
});
test('old server hides soft edges and keeps older polish previews compatible',async()=>{
 const h=harness();h.softEdges=false;await h.flush();
 assert.equal(h.button('Gentle audio fades (80 ms)'),undefined);
 assert(h.button('Keep original cut')===undefined);
});
test('preset save/use is scoped to the validated owner and excludes draft words',async()=>{
 const h=harness();await h.flush();h.button('Level voice volume').props.onPress();await h.flush();
 await h.button('Save my preset').props.onPress();await h.flush();
 const saved=h.calls.find(c=>c.save);assert.equal(saved.save,owner);assert(!('edits' in saved.options));
 h.button('Original volume').props.onPress();await h.flush();await h.button('Use my saved preset').props.onPress();await h.flush();
 assert(h.button('Level voice volume · selected'));
});
test('same-owner access refresh preserves edits after validation and another owner never sees them',async()=>{
 const h=harness();await h.flush();h.button('Edit caption words and timing').props.onPress();await h.flush();
 h.input('Caption text').props.onChangeText('Private edit');await h.flush();
 h.token='refreshed';h.render();assert(!h.input('Caption text'));await h.flush();
 assert.equal(h.input('Caption text').props.value,'Private edit');
 h.owner='33333333-3333-4333-8333-333333333333';h.token='other-account';h.render();
 assert(!h.input('Caption text'));await h.flush();
 h.button('Edit caption words and timing').props.onPress();await h.flush();assert.equal(h.input('Caption text').props.value,'Original words.');
});
test('old-session render results cannot navigate and duplicate confirmations share one request',async()=>{
 const h=harness();await h.flush();let done;h.wait=new Promise(r=>{done=r;});
 await h.button('Render polished preview').props.onPress();const action=h.alerts.at(-1)[2][1].onPress;
 const one=action(),two=action();await h.flush();assert.equal(h.calls.filter(c=>c.render).length,1);
 h.token='other';h.pending=true;await h.flush();done({id:'old-child'});await Promise.all([one,two]);await h.flush();
 assert(!h.calls.some(c=>c.push));
});
test('invalid times and older-server capabilities present actionable errors',async()=>{
 const h=harness();await h.flush();h.button('Edit caption words and timing').props.onPress();await h.flush();
 h.input('Caption end seconds').props.onChangeText('99');await h.flush();
 await h.button('Render polished preview').props.onPress();await h.flush();assert(h.text().includes('Invalid caption times'));
 const old=harness();old.ready=false;await old.flush();assert(old.text().includes('needs the polished-video update'));assert(!old.button('Render polished preview'));
});

test('dirty drafts guard native navigation but authentication changes can leave',async()=>{
 const h=harness();await h.flush();assert.equal(h.prevent,false);
 h.button('Level voice volume').props.onPress();await h.flush();assert.equal(h.prevent,true);
 let repeated=false;h.preventCallback({repeat:()=>{repeated=true;}});
 assert.equal(h.alerts.at(-1)[0],'Discard unsaved polish edits?');
 h.alerts.at(-1)[2][1].onPress();await h.flush();assert(repeated);assert.equal(h.prevent,false);
 h.button('Original volume').props.onPress();await h.flush();h.token=null;h.render();assert.equal(h.prevent,false);
});
