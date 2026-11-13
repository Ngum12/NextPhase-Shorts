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
 const detailExports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/clipSelection.ts'),'utf8'),
  {compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:detailExports});
 const visual={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/sceneAnalysis.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:visual});
 const timing={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,'../src/audioTiming.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,{exports:timing});
 const adapters={react,'react-native':{Alert:{alert:(...args)=>h.alerts.push(args)},Pressable:'Pressable',ScrollView:'ScrollView',Text:'Text',View:'View'},
  'expo-router':{useLocalSearchParams:()=>({id:h.id}),router:{replace:route=>h.calls.push({back:route}),push:route=>h.calls.push({push:route})}},
  '../../src/clipPreviews':{requestClipPreview:async(id,token,revision,candidate,captionStyle,framing)=>{
    h.calls.push({preview:id,token,revision,candidate,captionStyle,framing});if(h.previewError)throw h.previewError;
    if(h.delayedPreview)return h.delayedPreview;
    return {id:'preview-job',preview_parent_id:id,status:'queued'};}},
  '../../src/sceneAnalysis':visual,'../../src/audioTiming':timing,'../../src/clipSelection':detailExports,
  '../../src/ClipEvidenceTimeline':{ClipEvidenceTimeline:'ClipEvidenceTimeline'},'../../src/auth':{useAuth:()=>({token:h.token})},'../../src/api':{ApiError},
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

function enablePreviews(h){
 h.value.queued_preview_supported=true;
 h.value.review={sentence_end_words:[2],confirmed_low_confidence_words:[1]};
 h.value.proposal.candidates=[{first_word:0,last_word:1,source_start_ms:0,source_end_ms:12000,output_frames:360}];
}
test('only a saved selected suggestion can request a confirmed queued preview',async()=>{
 const h=harness();enablePreviews(h);await h.flush();
 h.button('Render selected preview').props.onPress();
 const confirmation=h.alerts.at(-1);assert.equal(confirmation[0],'Render this clip preview?');
 await confirmation[2][1].onPress();await h.flush();
 const request=h.calls.find(c=>c.preview);assert.equal(request.candidate,1);
 assert.equal(request.revision,h.value.revision);
 assert(h.calls.find(c=>c.push)?.push.params.id==='preview-job');
 h.check('Word 2:').props.onPress();await h.flush();assert(!h.button('Render selected preview'));
});
test('duplicate confirmations share one UI request and old-session results cannot navigate',async()=>{
 const h=harness();enablePreviews(h);await h.flush();let complete;
 h.delayedPreview=new Promise(r=>{complete=r;});h.button('Render selected preview').props.onPress();
 const action=h.alerts.at(-1)[2][1].onPress;
 const first=action();const second=action();await h.flush();assert.equal(h.calls.filter(c=>c.preview).length,1);
 h.token='new-session';h.pending=true;await h.flush();
 complete({id:'old-preview',status:'queued'});await Promise.all([first,second]);await h.flush();
 assert(!h.calls.some(c=>c.push));
});

test('caption choice is opt-in, disclosed and hidden on older servers',async()=>{
 const h=harness();enablePreviews(h);await h.flush();
 assert(!h.button('Clean captions'));
 h.value.clean_captions_supported=true;
 h.button('Refresh review').props.onPress();await h.flush();
 assert(h.button('Plain preview · selected'));
 h.button('Clean captions').props.onPress();await h.flush();
 assert(h.text().includes('Timing is estimated'));
 h.button('Render selected preview').props.onPress();
 assert(h.alerts.at(-1)[1].includes('Timings are estimated'));
 await h.alerts.at(-1)[2][1].onPress();await h.flush();
 assert.equal(h.calls.find(c=>c.preview).captionStyle,'clean-1');
});

test('portrait framing is optional, warns about cropping and composes with captions',async()=>{
 const h=harness();enablePreviews(h);await h.flush();
 assert(!h.button('Fill portrait (center)'));
 h.value.portrait_framing_supported=true;h.value.clean_captions_supported=true;
 h.button('Refresh review').props.onPress();await h.flush();
 assert(h.button('Fit full video · selected'));
 h.button('Fill portrait (center)').props.onPress();await h.flush();
 h.button('Clean captions').props.onPress();await h.flush();
 assert(h.text().includes('It does not follow faces'));
 h.button('Render selected preview').props.onPress();
 assert(h.alerts.at(-1)[1].includes('Center cropping removes outer edges'));
 await h.alerts.at(-1)[2][1].onPress();await h.flush();
 const request=h.calls.find(c=>c.preview);
 assert.equal(request.framing,'fill-center');assert.equal(request.captionStyle,'clean-1');
 h.value.portrait_framing_supported=false;
 h.button('Refresh review').props.onPress();await h.flush();
 assert(!h.button('Fill portrait (center)'));
 h.button('Render selected preview').props.onPress();
 await h.alerts.at(-1)[2][1].onPress();await h.flush();
 assert.equal(h.calls.filter(c=>c.preview).at(-1).framing,'fit');
});

test('saved selected clips open the combined polish workspace with bound revision',async()=>{
 const h=harness();enablePreviews(h);h.value.polished_preview_supported=true;await h.flush();
 h.button('Polish selected clip').props.onPress();
 const route=h.calls.find(c=>c.push).push;
 assert.equal(route.pathname,'/polish/[id]');assert.equal(route.params.revision,h.value.revision);
 assert.equal(route.params.candidate,'1');
 h.check('Word 2:').props.onPress();await h.flush();assert(!h.button('Polish selected clip'));
});


test('adjusted model timing is disclosed before transcript review',async()=>{
 const h=harness();h.value.proposal.warnings=['estimated_timestamps','adjusted_word_timestamps'];
 await h.flush();assert(h.text().includes('Some estimated word times were adjusted slightly'));
 assert.equal(h.button('Save review and find clips').props.disabled,true);
});


test('selected option shows nearby source context and transparent selection limits',async()=>{
 const h=harness();h.value.transcript.words=Array.from({length:30},(_,i)=>({text:i===8?'However,':'word'+i,start_ms:i*1000,end_ms:(i+1)*1000,confidence:.9}));
 h.value.proposal.algorithm='sentence-window-v4-diverse-reviewed';h.value.proposal.candidates=[
  {first_word:8,last_word:15,source_start_ms:8000,source_end_ms:16000,output_frames:240},
  {first_word:12,last_word:19,source_start_ms:12000,source_end_ms:20000,output_frames:240}];
 await h.flush();assert(h.text().includes('Before this clip: word0 word1'));
 assert(h.text().includes('After this clip: word16 word17'));
 assert(h.text().includes('This opening may refer to an earlier point'));
 assert(h.text().replace(/\s+/g,' ').includes('Shares some footage with option(s) 2'));
 assert(h.text().includes('These rules do not judge meaning or predict popularity'));
 assert(!h.calls.some(c=>c.preview));
});

test('legacy suggestions do not claim the new diversity rules',async()=>{
 const h=harness();h.value.proposal.algorithm='sentence-window-v3-reviewed';
 h.value.proposal.candidates=[{first_word:0,last_word:1,source_start_ms:0,source_end_ms:12000,output_frames:360}];
 await h.flush();assert(!h.text().includes('reduce near-duplicate ranges'));
 assert(h.text().includes('first transcribed word')&&h.text().includes('last transcribed word'));
});


test('audio guide shows bounded quiet passages and selected-range summary only when present',async()=>{
 const h=harness();h.value.audio_timing={audio_duration_ms:12000,quiet_intervals:[{start_ms:0,end_ms:1000}]};
 h.value.proposal.candidates=[{first_word:0,last_word:1,source_start_ms:0,source_end_ms:12000,output_frames:360}];
 await h.flush();assert(h.text().includes('Audio timing guide'));
 assert(h.text().includes('low-volume estimates'));assert(h.text().includes('Detected quiet audio inside this option:'));
 assert(!h.calls.some(c=>c.preview));
 h.value.audio_timing.audio_duration_ms=10000;await h.button('Refresh review').props.onPress();await h.flush();
 assert(h.text().includes('Audio timing covers only part of this option'));
 const old=harness();await old.flush();assert(!old.text().includes('Audio timing guide'));
});


test('visual guidance shows source changes near selected start/end without changing the option',async()=>{
 const h=harness();h.value.transcript.words=Array.from({length:20},(_,i)=>({text:'word'+i,start_ms:i*1000,end_ms:(i+1)*1000,confidence:.9}));
 h.value.scene_analysis={status:'available',sample_count:40,analyzed_duration_ms:20000,changes:[{at_ms:1500,delta_milli:800},{at_ms:6500,delta_milli:900}]};
 h.value.proposal.candidates=[{first_word:1,last_word:6,source_start_ms:1000,source_end_ms:7000,output_frames:180}];
 await h.flush();assert(h.text().includes('Visual change guide'));
 assert(h.text().includes('near the start')&&h.text().includes('near the end'));
 assert(h.text().includes('Flashes, movement and lighting'));
 assert.equal(h.value.proposal.candidates[0].source_start_ms,1000);assert(!h.calls.some(c=>c.preview));
});
test('unavailable visual guide preserves words and does not assert zero changes',async()=>{
 const h=harness();h.value.scene_analysis={status:'unavailable',issue:'decode_or_resource_limit',sample_count:0,analyzed_duration_ms:0,changes:[]};
 await h.flush();assert(h.text().includes('Visual guidance could not be prepared'));
 assert(h.text().includes('Original'));assert(!h.text().includes('No large visual changes'));
 const old=harness();await old.flush();assert(!old.text().includes('Visual change guide'));
});

test('source-bound timeline appears only for selected saved candidates without changing rendering',async()=>{
 const h=harness();enablePreviews(h);
 h.value.transcript.source_duration_ms=20000;
 h.value.audio_timing={source_duration_ms:20000,audio_duration_ms:15000,quiet_intervals:[]};
 h.value.scene_analysis={source_duration_ms:20000,status:'unavailable'};
 await h.flush();
 const timeline=h.nodes().find(n=>n.type==='ClipEvidenceTimeline');
 assert(timeline);assert.equal(timeline.props.candidate.source_start_ms,0);
 assert.equal(timeline.props.duration,20000);
 assert.equal(timeline.props.audio.audio_duration_ms,15000);
 assert.equal(timeline.props.scene.status,'unavailable');
 assert.equal(h.calls.filter(c=>c.preview).length,0);
 h.check('Word 2:').props.onPress();await h.flush();
 assert.equal(h.nodes().filter(n=>n.type==='ClipEvidenceTimeline').length,0);
});
