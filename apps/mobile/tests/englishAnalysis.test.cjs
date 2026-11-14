const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript'),path=require('node:path');
function load(file,adapters,globals={}){const exports={};vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname,file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.React}}).outputText,{exports,require:n=>{assert(adapters[n],n);return adapters[n];},...globals});return exports;}
test('lost start replies and explicit retries use stable server-recoverable keys',async()=>{
 const calls=[];const adapters={'./api':{api:async()=>({available:true}),authenticatedFetch:async(token,url,init)=>{calls.push({token,url,init});return {};},extract:async()=>({})}};
 const api=load('../src/englishAnalysis.ts',adapters),initial={task:null};
 await api.startEnglish('source','token',initial);await load('../src/englishAnalysis.ts',adapters).startEnglish('source','token',initial);
 assert.equal(JSON.parse(calls[0].init.body).idempotency_key,JSON.parse(calls[1].init.body).idempotency_key);
 await api.startEnglish('source','token',{task:{id:'failed-attempt',status:'failed'}});
 const retry=JSON.parse(calls[2].init.body);assert.equal(retry.idempotency_key,'failed-attempt');assert(retry.retry_failed&&retry.acknowledged_server_analysis);
 await api.cancelEnglish('source','token');assert(calls[3].url.endsWith('/cancel'));assert.equal(calls[3].init.method,'POST');
});
function harness(){
 const h={slots:[],cursor:0,pending:true,effects:[],tree:null,props:{id:'source',token:'session'},calls:[],alerts:[],quick:{needsReview:false,plan:{revision:'a'.repeat(64),candidate:1,duration_ms:15000,options:{framing:'fit',captions:true,voice:'original'},title:'Top clip',notice:null}},
  choices:{needsReview:false,choices:[{revision:'a'.repeat(64),candidate:1,duration_ms:15000,source_start_ms:0,source_end_ms:15000,title:'Option 1 · 15.0s · source 0.0s–15.0s'}]},value:{ready:false,eligible:true,requested:false,task:null}};
 const react={createElement:(type,props,...children)=>({type,props:props||{},children:children.flat(Infinity)}),
  useState(initial){const i=h.cursor++;if(!h.slots[i])h.slots[i]={value:initial};return[h.slots[i].value,next=>{h.slots[i].value=typeof next==='function'?next(h.slots[i].value):next;h.pending=true;}];},
  useRef(initial){const i=h.cursor++;if(!h.slots[i])h.slots[i]={current:initial};return h.slots[i];},
  useEffect(effect,deps){const i=h.cursor++,old=h.slots[i];if(!old||deps.some((v,n)=>v!==old.deps[n]))h.effects.push(()=>{old?.cleanup?.();h.slots[i]={deps,cleanup:effect()};});}};react.default=react;
 const actions={englishCapability:async()=>({available:true}),englishState:async(id,token)=>{h.calls.push({get:id,token});return h.delay||structuredClone(h.value);},
 startEnglish:async(id,token,state)=>{h.calls.push({start:id,token,state});return {...h.value,task:{id:'attempt',status:'queued'}};},
 cancelEnglish:async(id,token)=>{h.calls.push({cancel:id,token});return {...h.value,task:{id:'attempt',status:'cancelled'}};}};
 const quickDraft={
  listQuickDrafts:async(id,token)=>{h.calls.push({list:id,token});return h.choiceWait||h.choices;},
  prepareQuickDraft:async(id,token,candidate)=>{h.calls.push({prepare:id,token,candidate});return h.quickWait||{...h.quick,plan:h.quick.plan&&{...h.quick.plan,candidate}};},
  renderQuickDraft:async(id,token,plan)=>{h.calls.push({renderDraft:id,token,plan});
    return h.renderWait||{id:'preview-2',status:'queued'};}};
  const component=load('../src/EnglishAnalysisPanel.tsx',{react,'react-native':{View:'View',Text:'Text',Alert:{alert:(...args)=>h.alerts.push(args)}},
  'expo-router':{router:{push:route=>h.calls.push({push:route})}},'./englishAnalysis':actions,'./quickDraft':quickDraft,'./ui':{Body:'Body',Button:'Button',s:{card:{},cardTitle:{}}}}, {setTimeout:()=>0,clearTimeout:()=>{}}).EnglishAnalysisPanel;
 h.render=()=>{h.cursor=0;h.pending=false;h.tree=component(h.props);};
 h.flush=async()=>{for(let i=0;i<12;i++){if(h.pending)h.render();while(h.effects.length)h.effects.shift()();await new Promise(r=>setImmediate(r));if(!h.pending&&!h.effects.length)break;}};
 h.nodes=()=>{const result=[];function visit(n){if(n&&typeof n==='object'){result.push(n);n.children?.forEach(visit);}}visit(h.tree);return result;};
 h.button=title=>h.nodes().find(n=>n.type==='Button'&&n.props.title===title);return h;
}
test('transcription requires consent and queued work exposes cancellation',async()=>{
 const h=harness();await h.flush();assert(!h.calls.some(c=>c.start));
 h.button('Find English clips').props.onPress();assert.equal(h.alerts.length,1);assert(!h.calls.some(c=>c.start));
 await h.alerts[0][2][1].onPress();await h.flush();assert(h.calls.some(c=>c.start));
 await h.button('Cancel English analysis').props.onPress();await h.flush();assert(h.calls.some(c=>c.cancel));assert(h.button('Retry English analysis'));
});
test('ready transcript opens human review without automatic preview render',async()=>{
 const h=harness();h.value.ready=true;await h.flush();h.button('Review English clips').props.onPress();
 assert(h.calls.some(c=>c.push?.pathname==='/review/[id]'));assert(!h.calls.some(c=>c.start));
});
test('old session reply and consent dialog cannot start work after account switch',async()=>{
 const h=harness();await h.flush();h.button('Find English clips').props.onPress();const consent=h.alerts[0][2][1];
 let release;h.delay=new Promise(r=>{release=r;});h.props={id:'different-source',token:'different-session'};h.pending=true;await h.flush();
 await consent.onPress();assert(!h.calls.some(c=>c.start));
 h.props={id:'third-source',token:'third-session'};h.delay=null;h.value.ready=false;h.pending=true;await h.flush();
 release({ready:true,eligible:true,requested:false,task:null});await h.flush();assert(!h.button('Review English clips'));assert(h.button('Find English clips'));
});

test('a ready review queues exactly one private draft only after confirmation',async()=>{
 const h=harness();h.value.ready=true;await h.flush();
 assert(h.button('Prepare a Short draft'));
 const task=h.button('Prepare a Short draft').props.onPress();await task;await h.flush();
 assert.equal(h.calls.filter(x=>x.prepare).length,1);
 assert.equal(h.calls.filter(x=>x.renderDraft).length,0);
 assert.equal(h.alerts.at(-1)[0],'Prepare a private Short draft?');
 assert(h.alerts.at(-1)[1].includes('not story meaning'));
 const action=h.alerts.at(-1)[2][1].onPress;
 const first=action();const second=action();
 await Promise.all([first,second]);await h.flush();
 assert.equal(h.calls.filter(x=>x.renderDraft).length,1);
 assert(h.calls.find(x=>x.push?.params.id==='preview-2'));
});
test('an unreviewed source directs the owner to review rather than silently rendering',async()=>{
 const h=harness();h.value.ready=true;h.choices={needsReview:true};await h.flush();
 await h.button('Prepare a Short draft').props.onPress();await h.flush();
 assert.equal(h.alerts.at(-1)[0],'Finish checking the recording');
 assert.equal(h.calls.filter(x=>x.renderDraft).length,0);
 h.alerts.at(-1)[2][1].onPress();await h.flush();
 assert(h.calls.some(x=>x.push?.pathname==='/review/[id]'));
});
test('stale prepare response after switching sessions cannot open a draft confirmation',async()=>{
 const h=harness();h.value.ready=true;
 let release;h.choiceWait=new Promise(r=>{release=r;});await h.flush();
 const pending=h.button('Prepare a Short draft').props.onPress();
 h.props={id:'another-project',token:'another-session'};h.choiceWait=null;h.pending=true;await h.flush();
 release(h.choices);await pending;await h.flush();
 assert(!h.alerts.length);assert(!h.calls.some(x=>x.renderDraft));
});

test('owner sees a fixed failure category instead of user recording text',async()=>{
 const h=harness();h.value.ready=false;h.value.task={
   id:'failure',status:'failed',error_code:'ASR_WORD_TIMING_REJECTED',
 };await h.flush();
 const texts=h.nodes().flatMap(n=>n.children).filter(c=>typeof c==='string').join(' ');
 assert.match(texts,/estimated word timings did not pass safety checks/);
 assert.match(texts,/limitation of our speech-timing pipeline/);
 assert.match(texts,/Retrying the same video may produce the same error/);
 assert.match(texts,/save or share it from this project/);
 assert(h.button('Retry timing analysis (experimental)'));
 assert(!h.calls.some(x=>x.start)); // A failed transcript must never auto-retry.

 assert.match(texts,/Your video is preserved/);
 h.value.task.error_code='unexpected Private speech transcript';
 h.pending=true;h.props={...h.props}; // Timer is stubbed; refresh by changing the identity.
 h.props={id:'new-source',token:'session'};await h.flush();
 const texts2=h.nodes().flatMap(n=>n.children).filter(c=>typeof c==='string').join(' ');
 assert.match(texts2,/precise cause is not yet available/);
 assert(!texts2.includes('Private speech transcript'));
});

for(const [code,explanation] of [
 ['ASR_OFFSETS_MISSING',/left out some word timing offsets/],
 ['ASR_OFFSETS_INVALID',/invalid word timing offsets/],
 ['ASR_OFFSETS_OUT_OF_SOURCE',/outside the recording/],
 ['ASR_WORD_ORDER_BACKWARD',/move backward/],
 ['ASR_WORD_OVERLAP_EXCESSIVE',/overlap too much/],
 ['ASR_TIMING_REPAIR_EXCEEDED',/allowed 20 milliseconds per boundary/],
])test(`timing failure ${code} explains the category without automatic retry`,async()=>{
 const h=harness();h.value.task={id:'failure',status:'failed',error_code:code};await h.flush();
 const text=h.nodes().flatMap(n=>n.children).filter(c=>typeof c==='string').join(' ');
 assert.match(text,explanation);
 assert.match(text,/limitation of our speech-timing pipeline/);
 assert.match(text,/Retrying the same video may produce the same error/);
 assert.match(text,/Your video is preserved/);
 assert.match(text,/save or share it from this project/);
 assert(h.button('Retry timing analysis (experimental)'));
 assert(!h.calls.some(x=>x.start));
 h.button('Retry timing analysis (experimental)').props.onPress();
 assert(!h.calls.some(x=>x.start));
 await h.alerts.at(-1)[2][1].onPress();await h.flush();
 assert.equal(h.calls.filter(x=>x.start).length,1);
});

for(const code of ['__proto__','constructor','toString','ASR_OFFSETS_INVALID private transcript'])
test(`unknown failure codes use a fixed fallback (${code.split(' ')[0]})`,async()=>{
 const h=harness();h.value.task={id:'failure',status:'failed',error_code:code};await h.flush();
 const text=h.nodes().flatMap(n=>n.children).filter(c=>typeof c==='string').join(' ');
 assert.match(text,/precise cause is not yet available/);
 assert(!text.includes('private transcript'));
 assert(h.button('Retry English analysis'));
 assert(!h.calls.some(x=>x.start));
});


test('three alternatives are shown without automatically queuing three preview jobs',async()=>{
 const h=harness();h.value.ready=true;
 h.choices={needsReview:false,choices:[1,2,3].map(i=>({
   revision:'a'.repeat(64),candidate:i,duration_ms:i*5000,
   source_start_ms:(i-1)*6000,source_end_ms:(i-1)*6000+i*5000,
   title:`Option ${i} · ${i*5}.0s`,
 }))};
 await h.flush();await h.button('Prepare a Short draft').props.onPress();await h.flush();
 assert(h.button('Option 1 · 5.0s')&&h.button('Option 2 · 10.0s')&&h.button('Option 3 · 15.0s'));
 assert.equal(h.calls.filter(x=>x.renderDraft).length,0);
 assert.equal(h.calls.filter(x=>x.prepare).length,0);
 await h.button('Option 2 · 10.0s').props.onPress();await h.flush();
 assert.equal(h.calls.filter(x=>x.prepare).length,1);
 assert.equal(h.calls.find(x=>x.prepare).candidate,2);
 assert.equal(h.alerts.at(-1)[0],'Prepare a private Short draft?');
 assert.equal(h.calls.filter(x=>x.renderDraft).length,0);
 await h.alerts.at(-1)[2][1].onPress();await h.flush();
 assert.equal(h.calls.filter(x=>x.renderDraft).length,1);
 assert.equal(h.calls.find(x=>x.renderDraft).plan.candidate,2);
});
test('canceling a draft confirmation does not reserve server storage',async()=>{
 const h=harness();h.value.ready=true;await h.flush();
 await h.button('Prepare a Short draft').props.onPress();await h.flush();
 h.alerts.at(-1)[2][0].onPress();await h.flush();
 assert(!h.calls.some(x=>x.renderDraft));
 assert(h.button('Prepare a Short draft'));
});
test('a changed review revision aborts rendering stale draft choices',async()=>{
 const h=harness();h.value.ready=true;await h.flush();
 await h.button('Prepare a Short draft').props.onPress();await h.flush();
 // The server review changed between the choices screen and selection.
 h.quick.plan.revision='b'.repeat(64);
 // Single option already confirmed; cancel and switch to a multi-choice review.
 h.alerts.at(-1)[2][0].onPress();await h.flush();
 h.choices={needsReview:false,choices:[
  {revision:'a'.repeat(64),candidate:1,duration_ms:5000,source_start_ms:0,source_end_ms:5000,title:'Option 1'},
  {revision:'a'.repeat(64),candidate:2,duration_ms:5000,source_start_ms:6000,source_end_ms:11000,title:'Option 2'},
 ]};
 await h.button('Prepare a Short draft').props.onPress();await h.flush();
 await h.button('Option 2').props.onPress();await h.flush();
 assert(!h.calls.some(x=>x.renderDraft));
 assert(!h.button('Option 2'));
});


test('proposed Short cards show spoken boundaries and technical evidence without creating previews',async()=>{
 const h=harness();h.value.ready=true;
 h.choices={needsReview:false,choices:[
  {revision:'a'.repeat(64),candidate:1,duration_ms:10000,source_start_ms:0,source_end_ms:10000,
    title:'Option 1 · 10.0s',opening:'But here is the point',ending:'This is what we learned',
    context_warning:'The opening may depend on earlier speech.',
    boundary_cues:['Low-volume audio near ending cut — verify playback.']},
  {revision:'a'.repeat(64),candidate:2,duration_ms:12000,source_start_ms:11000,source_end_ms:23000,
    title:'Option 2 · 12.0s',opening:'Today we learned something',ending:'And that is the conclusion',
    context_warning:null,boundary_cues:[]},
 ]};
 await h.flush();
 await h.button('Prepare a Short draft').props.onPress();await h.flush();
 const text=h.nodes().flatMap(n=>n.children).filter(x=>typeof x==='string').join(' ');
 assert.match(text,/But here is the point/);
 assert.match(text,/This is what we learned/);
 assert.match(text,/opening may depend/);
 assert.match(text,/Low-volume audio near ending cut/);
 assert.equal(h.calls.filter(x=>x.renderDraft).length,0);
 assert.equal(h.calls.filter(x=>x.prepare).length,0);
 h.button('Hide draft choices').props.onPress();await h.flush();
 assert(!h.button('Option 1 · 10.0s'));
 assert.equal(h.calls.filter(x=>x.renderDraft).length,0);
});
