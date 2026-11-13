import React,{useEffect,useRef,useState} from 'react';
import {Alert,View,Text} from 'react-native';
import {router} from 'expo-router';
import {englishCapability,englishState,startEnglish,cancelEnglish,EnglishState} from './englishAnalysis';
import {listQuickDrafts,prepareQuickDraft,renderQuickDraft,QuickDraftChoice} from './quickDraft';
import {Body,Button,s} from './ui';

const englishFailureHint:Record<string,string>={
  ASR_PROCESS_FAILED:'The speech engine stopped before finishing.',
  ASR_DEADLINE_EXCEEDED:'The speech engine exceeded its time limit.',
  ASR_OUTPUT_INVALID:'The speech engine did not produce a valid result file.',
  ASR_WORD_TIMING_REJECTED:'The estimated word timings did not pass safety checks.',
  ASR_TRANSCRIPT_REJECTED:'The recognized text or metadata did not pass validation.',
};

export function EnglishAnalysisPanel({id,token,disabled=false}:{id:string;token:string;disabled?:boolean}) {
  const [state,setState]=useState<EnglishState|null>(null),[available,setAvailable]=useState(false);
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[retry,setRetry]=useState(0);
  const [choices,setChoices]=useState<QuickDraftChoice[]>([]);
  const generation=useRef(0),running=useRef(false);
  useEffect(()=>{
    const current=++generation.current;let timer:ReturnType<typeof setTimeout>|undefined;
    setState(null);setAvailable(false);setError('');setBusy(false);setChoices([]);running.current=false;
    const refresh=async()=>{
      try{
        const capability=await englishCapability(token);
        if(generation.current!==current)return;
        setAvailable(capability.available);if(!capability.available)return;
        const next=await englishState(id,token);
        if(generation.current===current){setState(next);setError('');}
      }catch(e:any){if(generation.current===current)setError(e.message||'Could not check English analysis.');}
      finally{if(generation.current===current)timer=setTimeout(refresh,5000);}
    };
    refresh();return()=>{generation.current++;if(timer)clearTimeout(timer);};
  },[id,token,retry]);

  const reviewPrompt=(release:()=>void)=>{
    setChoices([]);
    Alert.alert('Finish checking the recording',
      'The suggestions need your saved transcript review before a draft can render. Review the original speech, then return here.',[
      {text:'Not now',onPress:release},
      {text:'Open review',onPress:()=>{release();router.push({pathname:'/review/[id]',params:{id}});}},
    ],{cancelable:false});
  };
  const confirmChoice=async(choice:QuickDraftChoice)=>{
    if(running.current||disabled||!state?.ready)return;
    const current=generation.current;
    running.current=true;setBusy(true);setError('');
    const release=()=>{if(generation.current===current){running.current=false;setBusy(false);}};
    try{
      const result=await prepareQuickDraft(id,token,choice.candidate);
      if(generation.current!==current)return;
      if(result.needsReview){reviewPrompt(release);return;}
      const plan=result.plan;
      if(plan.revision!==choice.revision||plan.candidate!==choice.candidate){
        setChoices([]);
        throw Error('The saved review changed. Refresh the Short choices.');
      }
      let confirmed=false;
      const details=plan.options.captions?'Clean phrase captions':'No captions';
      Alert.alert('Prepare a private Short draft?',
        `${plan.title}. ${details} · ${plan.options.framing} framing · ${plan.options.voice} voice. ${plan.notice||''} The suggestion is ranked by technical signals, not story meaning. Only this one choice will be rendered and occupy storage. Watch the finished clip before sharing.`,[
          {text:'Not now',onPress:release},
          {text:'Render draft',onPress:async()=>{
            if(confirmed||generation.current!==current)return;
            confirmed=true;
            try{
              const job=await renderQuickDraft(id,token,plan);
              if(generation.current===current){
                setChoices([]);
                router.push({pathname:'/project/[id]',params:{id:job.id}});
              }
            }catch(e:any){
              if(generation.current===current)setError(e.message||'Could not queue the draft. Retry the same settings.');
            }finally{release();}
          }},
        ],{cancelable:false});
    }catch(e:any){
      if(generation.current===current)setError(e.message||'Could not prepare the Short draft. Retry when connected.');
      release();
    }
  };
  const quickDraft=async()=>{
    if(running.current||disabled||!state?.ready)return;
    const current=generation.current;
    running.current=true;setBusy(true);setError('');
    const release=()=>{if(generation.current===current){running.current=false;setBusy(false);}};
    try{
      const result=await listQuickDrafts(id,token);
      if(generation.current!==current)return;
      if(result.needsReview){reviewPrompt(release);return;}
      setChoices(result.choices);
      release();
      // Single-candidate recordings preserve the original one-action flow.
      if(result.choices.length===1)await confirmChoice(result.choices[0]);
    }catch(e:any){
      if(generation.current===current)setError(e.message||'Could not find Short drafts. Retry when connected.');
      release();
    }
  };
  const action=async(cancel=false)=>{
    if(running.current||disabled||!state)return;
    const current=generation.current;running.current=true;setBusy(true);
    try{const next=cancel?await cancelEnglish(id,token):await startEnglish(id,token,state);
      if(generation.current===current){setState(next);setError('');}}
    catch(e:any){if(generation.current===current)setError(e.message||'Check the connection and retry.');}
    finally{if(generation.current===current){running.current=false;setBusy(false);}}
  };
  if(!available)return error?<View style={s.card}><Body>{error}</Body><Button title="Retry English connection" onPress={()=>setRetry(n=>n+1)} secondary/></View>:<Button title="Review English clips" disabled={disabled} onPress={()=>router.push({pathname:'/review/[id]',params:{id}})} secondary/>;
  const active=state?.task&&['queued','processing'].includes(state.task.status);
  const waiting=!!state?.requested&&!state.task&&!state.ready&&state.eligible;
  return <View style={s.card}><Text style={s.cardTitle}>English clip suggestions</Text>
    {!!error&&<Body>{error}</Body>}
    {!state?<Body>Checking analysis…</Body>:state.ready?<>
      <Body>Choose from up to three different reviewed clip options. Checking choices does not render anything: only the draft you confirm is rendered. No automatic transcript approval or publishing.</Body>
      <Button title={busy?'Preparing draft…':'Prepare a Short draft'} disabled={disabled||busy}
        onPress={quickDraft}/>
      {choices.length>1&&<View style={s.card}>
         <Text style={s.cardTitle}>Choose one Short draft</Text>
         <Body>Technically ranked excerpts, not story-quality predictions. Each preview reserves server storage; no batch rendering.</Body>
         {choices.map(choice=><Button key={choice.candidate} title={choice.title}
           secondary disabled={disabled||busy} onPress={()=>confirmChoice(choice)}/>)}
         <Button title="Hide draft choices" secondary disabled={disabled||busy} onPress={()=>setChoices([])}/>
       </View>}
       <Button title="Review English clips" disabled={disabled||busy} secondary
        onPress={()=>router.push({pathname:'/review/[id]',params:{id}})}/>
    </>:<>
      <Body>{active?(state.task!.status==='queued'?'English analysis is queued. You may leave this screen.':'Analyzing your recording on the server. Your original voice stays unchanged.'):waiting?'Waiting for queue space. Your uploaded video is safe.':!state.eligible?'This English pilot supports original local recordings up to three minutes.':state.task?.status==='failed'?`Transcription failed. ${englishFailureHint[state.task.error_code||'']||'The precise cause is not yet available.'} Your video is preserved. You can retry.`:state.task?.status==='cancelled'?'English analysis was cancelled.':'Find clip suggestions from your English speech, then review the transcript.'}</Body>
      {(active||waiting)?<Button title={busy?'Please wait…':'Cancel English analysis'} disabled={disabled||busy} onPress={()=>action(true)} secondary/>:
        state.eligible&&<Button title={busy?'Please wait…':state.task?'Retry English analysis':'Find English clips'} disabled={disabled||busy} onPress={()=>{
          const current=generation.current;
          Alert.alert('Analyze your English recording?','The server will transcribe this video and check visual changes using temporary samples. Check the transcript, sentence endings and suggested clips before rendering. This does not publish your video.',[
            {text:'Not now',style:'cancel'},{text:'Analyze recording',onPress:()=>{if(current===generation.current)action();}},
          ]);
        }}/>}
    </>}
  </View>;
}
