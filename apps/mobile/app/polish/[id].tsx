import React,{useEffect,useRef,useState} from 'react';
import {Alert,Pressable,ScrollView,Text,TextInput,View} from 'react-native';
import {router,useLocalSearchParams,usePreventRemove} from 'expo-router';
import {useAuth} from '../../src/auth';
import {api,ApiError} from '../../src/api';
import {getEnglishAnalysis} from '../../src/analysis';
import {Cue,PolishOptions,defaultPolish,getCaptionDraft,captionMilliseconds,validateCues,
  requestPolishedPreview,savePolishPreset,loadPolishPreset} from '../../src/polish';
import {Body,Button,Loading,Page,Title,s} from '../../src/ui';
import {colors as c} from '../../src/theme';

type Editable={text:string;start:string;end:string};
function Choice({label,value,choices,change,disabled}:{label:string;value:string;
  choices:[string,string][];change:(value:string)=>void;disabled:boolean}){
  return <View style={{gap:8}}><Text style={s.cardTitle}>{label}</Text>
    {choices.map(([key,title])=><Button key={key} secondary disabled={disabled}
      title={title+(value===key?' · selected':'')} onPress={()=>change(key)}/>)}</View>;
}
export default function PolishClip(){
  const params=useLocalSearchParams<{id:string;candidate:string;revision:string}>();
  const id=String(params.id||''),candidate=Number(params.candidate),revision=String(params.revision||'');
  const {token}=useAuth();const scope=`${token}:${id}:${candidate}:${revision}`;
  const generation=useRef(0),loaded=useRef(''),working=useRef(false);
  const workspace=useRef('');
  const [ready,setReady]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const [owner,setOwner]=useState(''),[duration,setDuration]=useState(0),[base,setBase]=useState<Cue[]>([]);
  const [edits,setEdits]=useState<Editable[]>([]),[index,setIndex]=useState(0),[editing,setEditing]=useState(false);
  const [options,setOptions]=useState<PolishOptions>({...defaultPolish});
  const [softEdgesSupported,setSoftEdgesSupported]=useState(false);
  const [ack,setAck]=useState(false),[dirty,setDirty]=useState(false),[captionNotice,setCaptionNotice]=useState('');
  const load=async()=>{
    if(!token||working.current)return;
    const request=++generation.current;setReady(false);setError('');loaded.current='';
    try{
      const [analysis,me]=await Promise.all([getEnglishAnalysis(id,token),api<{id:string}>('/api/v1/me',token)]);
      if(!analysis.polished_preview_supported)throw Error('This server needs the polished-video update. Return to your clip review.');
      if(analysis.revision!==revision||!analysis.review||!analysis.proposal.candidates[candidate-1])
        throw Error('The saved review changed. Return to review and select the clip again.');
      if(request!==generation.current)return;
      setSoftEdgesSupported(analysis.soft_audio_edges_supported===true);
      const identity=`${me.id}:${id}:${candidate}:${revision}`;
      // An access-token refresh must not erase a draft. Revalidate ownership
      // before revealing it; a different owner/review gets a fresh workspace.
      if(workspace.current===identity){loaded.current=scope;setReady(true);return;}
      setBase([]);setEdits([]);setOwner('');workspace.current='';
      const chosen=analysis.proposal.candidates[candidate-1];
      let cues:Cue[]=[];let notice='';
      try{cues=(await getCaptionDraft(id,token,revision,candidate)).cues;}
      catch(e){if(e instanceof ApiError&&e.status===422)notice='This clip exceeds caption layout limits. You can still render without captions.';else throw e;}
      if(request!==generation.current)return;
      setOwner(me.id);setDuration(Math.floor(chosen.output_frames*1000/30));setBase(cues);
      setEdits(cues.map(cue=>({text:cue.text,start:(cue.start_ms/1000).toFixed(3),end:(cue.end_ms/1000).toFixed(3)})));
      setOptions({...defaultPolish,captions:cues.length>0});setCaptionNotice(notice);
      setAck(false);setDirty(false);setIndex(0);setEditing(false);loaded.current=scope;setReady(true);
      workspace.current=identity;
    }catch(e:any){if(request===generation.current)setError(e.message||'Could not load this clip. Retry on a working connection.');}
  };
  useEffect(()=>{
    working.current=false;setBusy(false);setReady(false);load();
    return()=>{generation.current++;loaded.current='';};
  },[scope]);
  const choose=<K extends keyof PolishOptions>(key:K,value:PolishOptions[K])=>{
    setOptions(old=>({...old,[key]:value}));setDirty(true);
  };
  const update=(key:keyof Editable,value:string)=>{
    setEdits(old=>old.map((cue,i)=>i===index?{...cue,[key]:value}:cue));setAck(false);setDirty(true);
  };
  const preset=async(save:boolean)=>{
    if(working.current||loaded.current!==scope)return;
    working.current=true;setBusy(true);const request=++generation.current;setError('');
    try{
      if(save){await savePolishPreset(owner,options);if(request===generation.current)Alert.alert('Preset saved','Appearance, framing and voice choices are saved for this account on this device. Caption words and times are not stored in the preset.');}
      else{const value=await loadPolishPreset(owner);if(request===generation.current){
        if(!value)Alert.alert('No saved preset','Choose your settings, then save your preset.');
        else{setOptions({...value,audio_edges:softEdgesSupported?value.audio_edges:'original',
          captions:base.length>0&&value.captions});setDirty(true);}}}
    }catch(e:any){if(request===generation.current)setError(e.message||'Preset storage is unavailable.');}
    finally{if(request===generation.current){working.current=false;setBusy(false);}}
  };
  const render=async()=>{
    if(!token||working.current||loaded.current!==scope)return;
    let changed:Cue[]|null=null;
    try{if(options.captions){const cues=validateCues(edits.map(cue=>({text:cue.text,
      start_ms:captionMilliseconds(cue.start),end_ms:captionMilliseconds(cue.end)})),duration);
      if(JSON.stringify(cues)!==JSON.stringify(base))changed=cues;
      if(changed&&!ack)throw Error('Compare your caption corrections with the recording, then confirm below.');
    }}catch(e:any){setError(e.message);return;}
    Alert.alert('Render this polished preview?',
      'Watch the result before sharing. '+(options.framing==='fill-center'?'Center cropping removes outer details. ':'')+
      (options.voice==='level'?'Voice leveling can also raise background noise. ':'')+
      (options.audio_edges==='soft'?'Short fades soften only the first and last 80 ms of audio. ':'')+
      (options.captions?'Check caption wording and timing against the speech.':''),[
      {text:'Keep editing',style:'cancel'},
      {text:'Render preview',onPress:async()=>{
        if(working.current||loaded.current!==scope)return;
        working.current=true;setBusy(true);setError('');const request=++generation.current;
        try{const job=await requestPolishedPreview(id,token,revision,candidate,options,changed,duration,ack);
          if(request===generation.current){setDirty(false);disablePrevention();router.push({pathname:'/project/[id]',params:{id:job.id}});}}
        catch(e:any){if(request===generation.current)setError(e.message||'Could not confirm the render. Retry the same settings.');}
        finally{if(request===generation.current){working.current=false;setBusy(false);}}
      }},
    ]);
  };
  const visible=ready&&loaded.current===scope;const cue=edits[index];
  const disablePrevention=usePreventRemove(visible&&dirty,({repeat})=>{
    Alert.alert('Discard unsaved polish edits?','Your unrendered caption and appearance changes will be lost.',[
      {text:'Keep editing',style:'cancel'},
      {text:'Leave',style:'destructive',onPress:()=>{setDirty(false);repeat();}},
    ]);
  });
  return <Page><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{paddingTop:20,paddingBottom:40,gap:18}}>
    <Title>Polish your clip</Title>
    {!!error&&<Text accessibilityRole="alert" style={{color:c.warning}}>{error}</Text>}
    {!ready&&!error&&<Loading/>}
    {visible&&<>
      <Body>Option {candidate} · {(duration/1000).toFixed(1)} seconds. Your original recording stays unchanged.</Body>
      <View style={s.card}>
        <Choice label="Framing" value={options.framing} disabled={busy}
          choices={[["fit","Fit full video"],["fill-center","Fill portrait (center)"]]}
          change={value=>choose('framing',value as PolishOptions['framing'])}/>
        <Body>{options.framing==='fit'?'Keeps the full picture, with bars where needed.':'Crops around the center; it does not follow faces. Check the edges in the preview.'}</Body>
      </View>
      <View style={s.card}>
        <Choice label="Captions" value={options.captions?'on':'off'} disabled={busy||!base.length}
          choices={[["on","Captions on"],["off","Captions off"]]} change={value=>choose('captions',value==='on')}/>
        {!!captionNotice&&<Body>{captionNotice}</Body>}
        {options.captions&&<>
          <Choice label="Caption size" value={options.caption_size} disabled={busy}
            choices={[["standard","Standard"],["large","Large"]]} change={v=>choose('caption_size',v as PolishOptions['caption_size'])}/>
          <Choice label="Caption colour" value={options.caption_color} disabled={busy}
            choices={[["white","White"],["yellow","Warm yellow"]]} change={v=>choose('caption_color',v as PolishOptions['caption_color'])}/>
          <Choice label="Caption position" value={options.caption_position} disabled={busy}
            choices={[["lower","Lower"],["middle","Middle"]]} change={v=>choose('caption_position',v as PolishOptions['caption_position'])}/>
          <Body>Captions use a dark background. Each phrase fits at most two lines. Original word timing is estimated.</Body>
          <Button title={editing?'Hide caption editor':'Edit caption words and timing'} secondary disabled={busy} onPress={()=>setEditing(!editing)}/>
          {editing&&cue&&<View style={{gap:10}}>
            <Body>Caption {index+1} of {edits.length}. Check your recording when correcting words or times.</Body>
            <TextInput accessibilityLabel="Caption text" style={s.input} multiline maxLength={160}
              value={cue.text} editable={!busy} onChangeText={value=>update('text',value)}/>
            <Body>Start in seconds</Body><TextInput accessibilityLabel="Caption start seconds" keyboardType="decimal-pad"
              style={s.input} maxLength={8} value={cue.start} editable={!busy} onChangeText={value=>update('start',value)}/>
            <Body>End in seconds</Body><TextInput accessibilityLabel="Caption end seconds" keyboardType="decimal-pad"
              style={s.input} maxLength={8} value={cue.end} editable={!busy} onChangeText={value=>update('end',value)}/>
            <Button title="Previous caption" secondary disabled={busy||index===0} onPress={()=>setIndex(index-1)}/>
            <Button title="Next caption" secondary disabled={busy||index===edits.length-1} onPress={()=>setIndex(index+1)}/>
            <Button title="Reset all caption corrections" secondary disabled={busy} onPress={()=>Alert.alert('Reset caption corrections?',
              'Restore the prepared words and estimated times for this clip.',[{text:'Keep edits',style:'cancel'},
              {text:'Reset',onPress:()=>{setEdits(base.map(c=>({text:c.text,start:(c.start_ms/1000).toFixed(3),end:(c.end_ms/1000).toFixed(3)})));setAck(false);setDirty(true);}}])}/>
          </View>}
          <Pressable accessibilityRole="checkbox" accessibilityLabel="I compared my caption corrections with the recording"
            accessibilityState={{checked:ack,disabled:busy}} disabled={busy} style={{minHeight:48,justifyContent:'center'}} onPress={()=>setAck(!ack)}>
            <Text style={{color:c.text}}>{ack?'☑':'☐'} I compared my caption corrections with the recording.</Text>
          </Pressable>
        </>}
      </View>
      <View style={s.card}>
        <Choice label="Voice volume" value={options.voice} disabled={busy}
          choices={[["original","Original volume"],["level","Level voice volume"]]} change={v=>choose('voice',v as PolishOptions['voice'])}/>
        <Body>Leveling adjusts quiet and loud passages when audio exists. It can raise background noise; it does not remove noise or change the speaker.</Body>
        {softEdgesSupported&&<><Choice label="Audio cut edges" value={options.audio_edges} disabled={busy}
          choices={[["original","Keep original cut"],["soft","Gentle audio fades (80 ms)"]]}
          change={v=>choose('audio_edges',v as PolishOptions['audio_edges'])}/>
          <Body>Optional short volume fades at both clip boundaries; no background music, voice replacement or noise removal. Compare the preview with the original.</Body></>}
      </View>
      <Button title="Save my preset" secondary disabled={busy} onPress={()=>preset(true)}/>
      <Button title="Use my saved preset" secondary disabled={busy} onPress={()=>preset(false)}/>
      <Body>Presets save your style choices on this device. Unrendered caption edits can be lost if you close the app.</Body>
      <Button title={busy?'Please wait…':'Render polished preview'} disabled={busy} onPress={render}/>
    </>}
    {!ready&&!!error&&<Button title="Retry loading" secondary onPress={load}/>}
    <Button title="Back to clip review" disabled={busy} secondary
      onPress={()=>router.replace({pathname:'/review/[id]',params:{id}})}/>
  </ScrollView></Page>;
}
