import React, {useEffect,useRef,useState} from 'react';
import {Alert,Pressable,ScrollView,Text,View} from 'react-native';
import {router,useLocalSearchParams} from 'expo-router';
import {useAuth} from '../../src/auth';
import {ApiError} from '../../src/api';
import {ClipEvidenceTimeline} from '../../src/ClipEvidenceTimeline';
import {CutReviewPanel} from '../../src/CutReviewPanel';
import {clipContext} from '../../src/clipSelection';
import {endingCues,previewTranscript} from '../../src/reviewShortcuts';
import {EnglishAnalysis,englishReviewVisible,getEnglishAnalysis,saveEnglishReview} from '../../src/analysis';
import {Body,Button,Loading,Page,Title,s} from '../../src/ui';
import {colors as c} from '../../src/theme';
import {PreviewFraming,requestClipPreview} from '../../src/clipPreviews';

export default function EnglishReview() {
  const {id:parameter}=useLocalSearchParams<{id:string}>();
  const id=String(parameter||'');const {token}=useAuth();
  const [data,setData]=useState<EnglishAnalysis|null>(null);
  const [ends,setEnds]=useState<number[]>([]),[confirmed,setConfirmed]=useState<number[]>([]);
  const [acknowledged,setAcknowledged]=useState(false),[busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(false),[error,setError]=useState(''),[conflict,setConflict]=useState(false);
  const [dirty,setDirty]=useState(false),[selected,setSelected]=useState(0);
  const [wordEditorOpen,setWordEditorOpen]=useState(false),[fullTranscriptOpen,setFullTranscriptOpen]=useState(false);
  const generation=useRef(0),saving=useRef(false),loadPending=useRef(false);
  const [rendering,setRendering]=useState(false);const requestingPreview=useRef(false);
  const [captionStyle,setCaptionStyle]=useState<'none'|'clean-1'>('none');
  const [framing,setFraming]=useState<PreviewFraming>('fit');
  const scope=`${token||''}:${id}`,loadedScope=useRef('');
  const adopt=(value:EnglishAnalysis)=>{
    loadedScope.current=scope;
    setData(value);setEnds(value.review?.sentence_end_words||[]);
    setConfirmed(value.review?.confirmed_low_confidence_words||[]);
    setAcknowledged(false);setDirty(false);setConflict(false);setSelected(0);
  };
  const load=async()=>{
    if(!token||!id||!englishReviewVisible||saving.current||loadPending.current)return;
    loadPending.current=true;const request=++generation.current;setLoading(true);setError('');
    try{const next=await getEnglishAnalysis(id,token);if(request===generation.current)adopt(next);}
    catch(e:any){if(request===generation.current){setError(e.message||'Could not load review. Check your connection.');
      if(e instanceof ApiError && [401,404].includes(e.status)){setData(null);setEnds([]);setConfirmed([]);setAcknowledged(false);setDirty(false);}}}
    finally{if(request===generation.current){loadPending.current=false;setLoading(false);}}
  };
  useEffect(()=>{
    setData(null);setEnds([]);setConfirmed([]);setAcknowledged(false);setDirty(false);setError('');
    saving.current=false;loadPending.current=false;requestingPreview.current=false;
    setRendering(false);setBusy(false);setLoading(false);
    setWordEditorOpen(false);setFullTranscriptOpen(false);load();
    setCaptionStyle('none');
    setFraming('fit');
    return()=>{generation.current++;loadedScope.current='';requestingPreview.current=false;};
  },[id,token]);
  const refresh=()=>dirty?Alert.alert('Discard unsaved review?',
    'Refreshing loads the saved review and replaces your unsaved marks.',[
      {text:'Keep editing',style:'cancel'},{text:'Refresh',style:'destructive',onPress:load},
    ]):load();
  const toggle=(number:number,update:React.Dispatch<React.SetStateAction<number[]>>)=>{
    update(list=>list.includes(number)?list.filter(n=>n!==number):[...list,number].sort((a,b)=>a-b));
    setAcknowledged(false);setDirty(true);
  };
  const save=async()=>{
    if(!data||!token||!acknowledged||!ends.length||saving.current||loadPending.current||conflict)return;
    saving.current=true;setBusy(true);setError('');const request=++generation.current;
    try{
      const next=await saveEnglishReview(id,token,data.revision,{
        schema_version:'transcript-review-1',source_sha256:data.transcript.source_sha256,
        transcript_sha256:data.transcript_sha256,acknowledged_original_recording:true,
        sentence_end_words:ends,confirmed_low_confidence_words:confirmed,
      });
      if(request===generation.current){adopt(next);Alert.alert('Review saved',
        next.proposal.candidates.length?`${next.proposal.candidates.length} clip suggestions found.`:
        'No complete clip fits these boundaries. Check sentence endings and unconfirmed words.');}
    }catch(e:any){if(request===generation.current){setError(e.message||'Could not save. Check your connection and retry.');
      if(e instanceof ApiError && e.status===409)setConflict(true);
      if(e instanceof ApiError && [401,404].includes(e.status)){setData(null);setEnds([]);setConfirmed([]);setAcknowledged(false);setDirty(false);}}}
    finally{if(request===generation.current){saving.current=false;setBusy(false);}}
  };
  const render=()=>{
    if(!data||!token||dirty||conflict||requestingPreview.current)return;
    const revision=data.revision,number=selected+1,style=data.clean_captions_supported?captionStyle:'none';
    const frame=data.portrait_framing_supported?framing:'fit';
    let description=style==='clean-1'?'The server will add phrase captions from your reviewed words. Timings are estimated: check the captions against the audio before sharing.':'The server will render this selected excerpt. Watch the result to check the cut and meaning.';
    if(frame==='fill-center')description+=' Center cropping removes outer edges. Check that your face, hands and important details stay visible.';
    Alert.alert('Render this clip preview?',
      description,[
        {text:'Keep reviewing',style:'cancel'},
        {text:'Render preview',onPress:async()=>{
          if(requestingPreview.current)return;
          requestingPreview.current=true;setRendering(true);setError('');const request=++generation.current;
          try{const job=await requestClipPreview(id,token,revision,number,style,frame);
            if(request===generation.current)router.push({pathname:'/project/[id]',params:{id:job.id}});
          }catch(e:any){if(request===generation.current){setError(e.message||'Could not confirm preview. Retry the same clip.');
            if(e instanceof ApiError&&e.status===409)setConflict(true);}}
          finally{if(request===generation.current){requestingPreview.current=false;setRendering(false);}}
        }},
      ]);
  };
  const blocked=busy||loading||rendering;
  const flags=data?.transcript.words.map((word,i)=>({word,number:i+1}))
    .filter(({word})=>word.confidence!==null&&word.confidence<.45)||[];
  const chosen=data?.proposal.candidates[selected];
  const cues=endingCues(data?.transcript.words||[]);
  const cueNumbers=cues.map(cue=>cue.wordNumber);
  const wordEditorCompact=(data?.transcript.words.length||0)>40;
  const suggest=()=>{
    if(!data||!cueNumbers.length||blocked||conflict)return;
    const apply=()=>{setEnds(cueNumbers);setAcknowledged(false);setDirty(true);};
    if(ends.length)Alert.alert('Replace marked sentence endings?',
      'This replaces your current word-end marks with unverified punctuation, pause and end-of-recording cues. Compare all proposed endings with the original recording.',[
        {text:'Keep marks',style:'cancel'},
        {text:'Use draft',onPress:apply},
      ]);
    else apply();
  };
  const context=data?clipContext(data,selected):null;
  return <Page><ScrollView contentContainerStyle={{paddingTop:20,paddingBottom:40,gap:18}}>
    <Title>Review English clips</Title>
    {!englishReviewVisible?<Body>The English review pilot is not enabled in this app.</Body>:<>
      <Body>Compare the words with your original recording. Your marks help choose complete clips; timing still needs video review.</Body>
      {!!error&&<Text accessibilityRole="alert" style={{color:c.warning}}>{error}</Text>}
      {loading&&!data&&<Loading/>}
      {data&&loadedScope.current===scope&&<>
        {data.proposal.warnings.includes('adjusted_word_timestamps')&&<Body>Some estimated word times were adjusted slightly because the speech engine gave them no duration. Check the clip cuts and captions against your recording.</Body>}
        {data.audio_timing&&<View style={s.card}><Text style={s.cardTitle}>Audio timing guide</Text>
          <Body>Audio checked: {(data.audio_timing.audio_duration_ms/1000).toFixed(1)} seconds.</Body>
          <Body>{data.audio_timing.quiet_intervals.length?`${data.audio_timing.quiet_intervals.length} quiet passage(s) found. These can help you check clip boundaries.`:'No quiet passages of half a second or longer were detected.'}</Body>
          {data.audio_timing.quiet_intervals.slice(0,5).map((interval,i)=><Body key={i}>Quiet: {(interval.start_ms/1000).toFixed(1)}–{(interval.end_ms/1000).toFixed(1)} seconds.</Body>)}
          {data.audio_timing.quiet_intervals.length>5&&<Body>Showing the first five quiet passages.</Body>}
          <Body>These are low-volume estimates. Background noise or music can hide pauses; check the recording in playback.</Body>
        </View>}
        {data.scene_analysis&&<View style={s.card}><Text style={s.cardTitle}>Visual change guide</Text>
          {data.scene_analysis.status==='available'?<>
            <Body>Sampled through {(data.scene_analysis.analyzed_duration_ms/1000).toFixed(1)} seconds of the video.</Body>
            <Body>{data.scene_analysis.changes.length?`${data.scene_analysis.changes.length} possible visual change(s) found.`:'No large visual changes were detected in these samples.'}</Body>
            {data.scene_analysis.changes.slice(0,5).map((event,i)=><Body key={i}>Possible change around {(event.at_ms/1000).toFixed(1)} seconds.</Body>)}
            {data.scene_analysis.changes.length>5&&<Body>Showing the first five possible changes.</Body>}
            <Body>These are sampled estimates. Flashes, movement and lighting can trigger them; check playback before changing a cut.</Body>
          </>:<Body>Visual guidance could not be prepared for this analysis. You can still review the transcript and render clips.</Body>}
        </View>}
        <View style={s.card}>
          <Text style={s.cardTitle}>Quick transcript review</Text>
          <Body>Read the original recording once, then check the estimated sentence breaks. You don't need to tap every word. No correction or clip is approved automatically.</Body>
          <Body>{data.transcript.words.length} transcribed words · {cues.length} draft ending cues · {flags.length} uncertain word(s) to verify.</Body>
          {cues.length>0&&<Button title={`Draft ${cues.length} sentence endings`} secondary disabled={blocked||conflict} onPress={suggest}/>}
          <Body>Draft cues come from punctuation, gaps of at least 0.9 seconds and the recording's final word. A pause is not proof of a complete sentence. Review the original video before acknowledging or saving.</Body>
          {wordEditorCompact&&<>
            <Body>{fullTranscriptOpen?data.transcript.words.map(word=>word.text).join(' '):previewTranscript(data.transcript.words,120)}</Body>
            <Button title={fullTranscriptOpen?'Show shorter transcript':'Read entire transcript'} secondary
              disabled={blocked} onPress={()=>setFullTranscriptOpen(value=>!value)}/>
          </>}
        </View>
        <View style={s.card}><Text style={s.cardTitle}>Clip suggestions</Text>
          {dirty?<Body>Save your changes to update suggestions.</Body>:<>
            {!data.proposal.candidates.length&&<Body>No complete clip fits yet. Check your sentence endings and flagged words above.</Body>}
            {data.proposal.algorithm==='sentence-window-v4-diverse-reviewed'&&<Body>Options compare word confidence, estimated speech coverage and duration, then reduce near-duplicate ranges. These rules do not judge meaning or predict popularity. Fewer than five options is normal.</Body>}
             {data.proposal.algorithm==='sentence-window-v5-discourse-reviewed'&&<Body>Options still compare confidence, speech coverage and duration, but now also consider simple English opening words and potential resolution phrases. A mid-thought opening may rank lower. These are heuristics, not real story understanding or popularity predictions. Always check the recording before rendering.</Body>}
            {data.proposal.candidates.map((candidate,i)=><View key={i} style={{gap:5}}><Button key={i}
              title={`Option ${i+1} · ${(candidate.output_frames/30).toFixed(1)} seconds${selected===i?' · selected':''}`}
              secondary={selected!==i} onPress={()=>setSelected(i)} disabled={blocked}/>
              <Body>{clipContext(data,i)?.opening}</Body>
            </View>)}
            {chosen&&<>
              <Body>{data.transcript.words.slice(chosen.first_word,chosen.last_word+1).map(w=>w.text).join(' ')}</Body>
              <ClipEvidenceTimeline candidate={chosen} duration={data.transcript.source_duration_ms}
                audio={data.audio_timing} scene={data.scene_analysis}/>
              <CutReviewPanel analysis={data} index={selected}/>
              <Body>From {(chosen.source_start_ms/1000).toFixed(1)} to {(chosen.source_end_ms/1000).toFixed(1)} seconds in your recording.</Body>
              {context&&<>
                <Text style={s.cardTitle}>Check the surrounding context</Text>
                <Body>{context.before?'Before this clip: '+context.before:'This clip begins at the first transcribed word.'}</Body>
                <Body>{context.after?'After this clip: '+context.after:'This clip reaches the last transcribed word.'}</Body>
                {context.contextOpening&&<Body>This opening may refer to an earlier point. Check that the clip makes sense on its own.</Body>}
                {!!context.confirmedWords&&<Body>This option includes {context.confirmedWords} word(s) you confirmed. Recheck them in playback.</Body>}
                {!!context.overlapOptions.length&&<Body>Shares some footage with option(s) {context.overlapOptions.join(', ')}.</Body>}
                <Body>These excerpts show nearby transcript words, not a summary. Watch the rendered preview to check the cut and meaning.</Body>
              </>}
              {data.polished_preview_supported&&data.review&&<Button title="Polish selected clip" disabled={blocked||conflict}
                onPress={()=>router.push({pathname:'/polish/[id]',params:{id,candidate:String(selected+1),revision:data.revision}})}/>}
              {data.portrait_framing_supported&&<View style={{gap:10}}>
                <Text style={s.cardTitle}>Framing</Text>
                <Button title={framing==='fit'?'Fit full video · selected':'Fit full video'} secondary
                  disabled={blocked} onPress={()=>setFraming('fit')}/>
                <Button title={framing==='fill-center'?'Fill portrait (center) · selected':'Fill portrait (center)'} secondary
                  disabled={blocked} onPress={()=>setFraming('fill-center')}/>
                <Body>{framing==='fit'?'Keeps the full picture, with bars where needed.':'Crops around the center to fill the screen. It does not follow faces. Watch the preview to check what is cut off.'}</Body>
              </View>}
              {data.clean_captions_supported&&<View style={{gap:10}}>
                <Button title={captionStyle==='none'?'Plain preview · selected':'Plain preview'} secondary
                  disabled={blocked} onPress={()=>setCaptionStyle('none')}/>
                <Button title={captionStyle==='clean-1'?'Clean captions · selected':'Clean captions'} secondary
                  disabled={blocked} onPress={()=>setCaptionStyle('clean-1')}/>
                {captionStyle==='clean-1'&&<Body>White phrase captions on a dark background. Timing is estimated; watch and check before sharing.</Body>}
              </View>}
              {data.queued_preview_supported&&data.review&&<Button title={rendering?'Requesting preview…':'Render selected preview'}
                onPress={render} disabled={blocked||conflict}/>}
            </>}
          </>}
        </View>
        <View style={s.card}><Text style={s.cardTitle}>1. Mark sentence endings</Text>
          <Body>Tap the last word of each complete sentence. A marked word shows ■. Tap again to undo.</Body>
          {wordEditorCompact&&<Button title={wordEditorOpen?'Hide individual word controls':'Edit individual word endings'} secondary
            disabled={blocked} onPress={()=>setWordEditorOpen(open=>!open)}/>}
          {(!wordEditorCompact||wordEditorOpen)&&<>
          <View style={{flexDirection:'row',flexWrap:'wrap',gap:5}}>
            {data.transcript.words.map((word,i)=><Pressable key={i} accessibilityRole="checkbox"
              accessibilityLabel={`Word ${i+1}: ${word.text}. Sentence ending`}
              accessibilityState={{checked:ends.includes(i+1),disabled:blocked}} disabled={blocked}
              onPress={()=>toggle(i+1,setEnds)} style={{minHeight:44,minWidth:44,maxWidth:'100%',
                justifyContent:'center',padding:8,borderRadius:8,borderWidth:1,
                borderColor:ends.includes(i+1)?c.accent:c.border,
                backgroundColor:ends.includes(i+1)?c.surface2:c.surface}}>
              <Text style={{color:c.text,fontSize:16}}>{word.text}{ends.includes(i+1)?' ■':''}</Text>
            </Pressable>)}
          </View>
          </>}
          <Body>{ends.length} sentence endings marked.</Body>
        </View>
        <View style={s.card}><Text style={s.cardTitle}>2. Confirm flagged words</Text>
          <Body>Only confirm words you hear correctly in the original recording.</Body>
          {!flags.length&&<Body>No words need confirmation.</Body>}
          {flags.map(({word,number})=><Pressable key={number} accessibilityRole="checkbox"
            accessibilityLabel={`Confirm word ${number}: ${word.text}`}
            accessibilityState={{checked:confirmed.includes(number),disabled:blocked}} disabled={blocked}
            onPress={()=>toggle(number,setConfirmed)} style={{minHeight:44,paddingVertical:10}}>
            <Text style={{color:c.text,fontSize:16}}>{confirmed.includes(number)?'☑':'☐'} Word {number}: {word.text}</Text>
          </Pressable>)}
          {!!flags.length&&<Button title="I checked every flagged word — confirm all" secondary disabled={blocked}
            onPress={()=>{setConfirmed(flags.map(flag=>flag.number));setAcknowledged(false);setDirty(true);}}/>}
        </View>
        <Pressable accessibilityRole="checkbox" accessibilityState={{checked:acknowledged,disabled:blocked}}
          disabled={blocked} onPress={()=>setAcknowledged(value=>!value)} style={{minHeight:44,paddingVertical:10}}>
          <Text style={{color:c.text,fontSize:16}}>{acknowledged?'☑':'☐'} I compared these sentence endings and word confirmations with my original recording.</Text>
        </Pressable>
        <Button title={busy?'Saving review…':'Save review and find clips'} onPress={save}
          disabled={blocked||!acknowledged||!ends.length||conflict}/>
      </>}
      <Button title={loading?'Loading…':'Refresh review'} onPress={refresh} disabled={blocked} secondary/>
    </>}
    <Button title="Back to project" onPress={()=>{
      const back=()=>router.replace({pathname:'/project/[id]',params:{id}});
      if(dirty)Alert.alert('Leave without saving?', 'Your unsaved review marks will be lost.',[
        {text:'Keep editing',style:'cancel'},{text:'Leave',onPress:back},
      ]);else back();
    }} disabled={blocked} secondary/>
  </ScrollView></Page>;
}
