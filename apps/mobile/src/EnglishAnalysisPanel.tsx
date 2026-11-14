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
  ASR_TRANSCRIPT_REJECTED:'The recognized text or metadata did not pass validation.',
};

const timingFailureHint:Record<string,string>={
  ASR_WORD_TIMING_REJECTED:'The estimated word timings did not pass safety checks.',
  ASR_OFFSETS_MISSING:'The speech engine left out some word timing offsets.',
  ASR_OFFSETS_INVALID:'The speech engine produced invalid word timing offsets.',
  ASR_OFFSETS_OUT_OF_SOURCE:'Some estimated word timings fall outside the recording.',
  ASR_WORD_ORDER_BACKWARD:'The estimated word timings move backward in the recording.',
  ASR_WORD_OVERLAP_EXCESSIVE:'The estimated word timings overlap too much to adjust safely.',
  ASR_TIMING_REPAIR_EXCEEDED:'The estimated word timings need more adjustment than the allowed 20 milliseconds per boundary.',
};

export function EnglishAnalysisPanel({id,token,disabled=false}:{id:string;token:string;disabled?:boolean}) {
  const [state,setState]=useState<EnglishState|null>(null),[available,setAvailable]=useState(false);
  const [error,setError]=useState(''),[busy,setBusy]=useState(false),[retry,setRetry]=useState(0);
  const [choices,setChoices]=useState<QuickDraftChoice[]>([]);
  const [automatic,setAutomatic]=useState(false);
  const generation=useRef(0),running=useRef(false);
  useEffect(()=>{
    const current=++generation.current;let timer:ReturnType<typeof setTimeout>|undefined;
    setState(null);setAvailable(false);setAutomatic(false);setError('');setBusy(false);setChoices([]);running.current=false;
    const refresh=async()=>{
      try{
        const capability=await englishCapability(token);
        if(generation.current!==current)return;
        setAvailable(capability.available);setAutomatic(capability.automatic_clips===true);if(!capability.available)return;
        const next=await englishState(id,token);
        if(generation.current===current){setState(next);setError('');}
      }catch(e:any){if(generation.current===current)setError(e.message||'Could not check English analysis.');}
      finally{if(generation.current===current)timer=setTimeout(refresh,5000);}
    };
    refresh();return()=>{generation.current++;if(timer)clearTimeout(timer);};
  },[id,token,retry]);

  const reviewPrompt=(release:()=>void,auto=false)=>{
    setChoices([]);
    Alert.alert(auto?'No suitable automatic clip yet':'Finish checking the recording',
      auto?'No usable speech range fits this duration. You can try another recording or use optional transcript review to adjust the choices.':
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
      if(result.needsReview){reviewPrompt(release,result.automatic);return;}
      const plan=result.plan;
      if(plan.revision!==choice.revision||plan.candidate!==choice.candidate){
        setChoices([]);
        throw Error('The saved review changed. Refresh the Short choices.');
      }
      let confirmed=false;
      const details=plan.options.captions?'Clean phrase captions':'No captions';
      const excerpt=plan.opening?`Opening words: “${plan.opening}”. `:'';
      Alert.alert('Prepare a private Short draft?',
        `${plan.title}. ${excerpt}${details} · ${plan.options.framing} framing · ${plan.options.voice} voice. ${plan.notice||''} ${plan.ranking_note||'Ranked by technical signals, not story meaning.'} Only this one choice will be rendered and occupy storage. Watch the finished clip before sharing.`,[
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
  const quickDraft=async(best=true)=>{
    if(running.current||disabled||!state?.ready)return;
    const current=generation.current;
    running.current=true;setBusy(true);setError('');
    const release=()=>{if(generation.current===current){running.current=false;setBusy(false);}};
    try{
      const result=await listQuickDrafts(id,token);
      if(generation.current!==current)return;
      if(result.needsReview){reviewPrompt(release,result.automatic);return;}
      setChoices(result.choices);
      release();
      // Single-candidate recordings preserve the original one-action flow.
      if(result.choices.length===1||(best&&result.choices[0]?.automatic))await confirmChoice(result.choices[0]);
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
  const failureCode=state?.task?.error_code||'';
  const timingHint=Object.hasOwn(timingFailureHint,failureCode)?timingFailureHint[failureCode]:null;
  const waiting=!!state?.requested&&!state.task&&!state.ready&&state.eligible;
  return <View style={s.card}><Text style={s.cardTitle}>English clip suggestions</Text>
    {!!error&&<Body>{error}</Body>}
    {!state?<Body>Checking analysis…</Body>:state.ready?<>
      <Body>{automatic?'Create a suggested Short directly from your recording. The server picks the clip; sentence marking is optional. Watch the result and check captions before sharing.':'Choose from up to three different reviewed clip options. Checking choices does not render anything: only the draft you confirm is rendered. No automatic transcript approval or publishing.'}</Body>
      <Button title={busy?'Preparing draft…':automatic?'Create suggested Short':'Prepare a Short draft'} disabled={disabled||busy}
        onPress={()=>quickDraft()}/>
      {automatic&&<Button title="Other clip suggestions" secondary disabled={disabled||busy} onPress={()=>quickDraft(false)}/>}
      {choices.length>1&&<View style={s.card}>
         <Text style={s.cardTitle}>Choose one Short draft</Text>
         <Body>{automatic?'Compare alternative parts of your recording. Only the option you confirm is rendered.':'These options use technical scores, and newer reviewed plans also use simple language cues. Neither approach verifies story quality or predicts popularity. Each render reserves storage.'}</Body>
         {choices.map(choice=><View key={choice.candidate} style={s.card}>
           <Text style={s.cardTitle}>Option {choice.candidate}</Text>
           {choice.opening&&<Body>Opens: “{choice.opening}”</Body>}
           {choice.ending&&<Body>Ends: “{choice.ending}”</Body>}
           {choice.context_warning&&<Body>{choice.context_warning}</Body>}
           {!!choice.ranking_note&&<Body>{choice.ranking_note}</Body>}
           {(choice.boundary_cues||[]).map((cue,i)=><Body key={i}>{cue}</Body>)}
           <Button title={choice.title} secondary disabled={disabled||busy}
             onPress={()=>confirmChoice(choice)}/>
         </View>)}
         <Button title="Hide draft choices" secondary disabled={disabled||busy} onPress={()=>setChoices([])}/>
       </View>}
       <Button title={automatic?'Review or adjust transcript (optional)':'Review English clips'} disabled={disabled||busy} secondary
        onPress={()=>router.push({pathname:'/review/[id]',params:{id}})}/>
    </>:<>
      <Body>{active?(state.task!.status==='queued'?'English analysis is queued. You may leave this screen.':'Analyzing your recording on the server. Your original voice stays unchanged.'):waiting?'Waiting for queue space. Your uploaded video is safe.':!state.eligible?'This English pilot supports original local recordings up to three minutes.':state.task?.status==='failed'?(timingHint?'Automatic clip suggestions are unavailable. '+timingHint+' This is a limitation of our speech-timing pipeline, not a judgement about your recording. Retrying the same video may produce the same error. Your video is preserved. If your basic Short finished rendering, you can still save or share it from this project.':'Transcription failed. '+((Object.hasOwn(englishFailureHint,failureCode)?englishFailureHint[failureCode]:null)||'The precise cause is not yet available.')+' Your video is preserved. You can retry.'):state.task?.status==='cancelled'?'English analysis was cancelled.':'Find clip suggestions from your English speech, then review the transcript.'}</Body>
      {(active||waiting)?<Button title={busy?'Please wait…':'Cancel English analysis'} disabled={disabled||busy} onPress={()=>action(true)} secondary/>:
        state.eligible&&<Button title={busy?'Please wait…':state.task?(state.task.status==='failed'&&!!timingHint?'Retry timing analysis (experimental)':'Retry English analysis'):'Find English clips'} disabled={disabled||busy} onPress={()=>{
          const current=generation.current;
          Alert.alert('Analyze your English recording?',automatic?
            'The server will transcribe this video and suggest clips automatically. Watch your finished private draft before sharing. Detailed transcript review is optional. This does not publish your video.':
            'The server will transcribe this video and check visual changes using temporary samples. Check the transcript, sentence endings and suggested clips before rendering. This does not publish your video.',[
            {text:'Not now',style:'cancel'},{text:'Analyze recording',onPress:()=>{if(current===generation.current)action();}},
          ]);
        }}/>}
    </>}
  </View>;
}
