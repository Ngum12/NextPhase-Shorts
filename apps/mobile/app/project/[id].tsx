import React, { useEffect, useRef, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { useLocalSearchParams, router } from 'expo-router';
import * as FileSystem from 'expo-file-system/legacy';
import { api, ApiError, cancelJob, deleteJob, Job } from '../../src/api';
import { exportVideo } from '../../src/videoExports';
import {saveAndFinish, SavedButCleanupPending} from '../../src/saveAndFinish';
import {englishReviewVisible} from '../../src/analysis';
import {EnglishAnalysisPanel} from '../../src/EnglishAnalysisPanel';
import {ClipPlayer} from '../../src/ClipPlayer';
import {forgetPreviewIntents} from '../../src/clipPreviews';
import { useAuth } from '../../src/auth';
import { colors as c } from '../../src/theme';
import { Body, Button, Loading, Page, Title, s } from '../../src/ui';
export default function Project() {
  const params=useLocalSearchParams<{id:string}>(); const id=String(params.id||'');
  const {token}=useAuth();const[job,setJob]=useState<Job|null>(null);const[error,setError]=useState('');
  const [downloading,setDownloading]=useState(false);const exportBusy=useRef(false);
  const [cancelling,setCancelling]=useState(false);
  const [deleting,setDeleting]=useState(false);const [unavailable,setUnavailable]=useState(false);
  const revision=useRef(0);
  const refresh=async()=>{
    if(!token||!id)return;
    const request=++revision.current;
    try {const next=await api<Job>(`/api/v1/jobs/${encodeURIComponent(id)}`,token);
      if(request===revision.current){setJob(next);setError('');}}
    catch(e:any){if(request===revision.current){setError(e.message||'Unable to load project');
      if(e instanceof ApiError&&e.status===404){setUnavailable(true);setJob(null);}}}
  };
  useEffect(()=>{
    refresh();
    if(unavailable || (job && !['queued','processing'].includes(job.status)))return ()=>{revision.current++;};
    const timer=setInterval(refresh,5000);return()=>{clearInterval(timer);revision.current++;};
  },[id,token,job?.status,unavailable]);
  const cancel=()=>Alert.alert('Cancel this render?', 'This project will stop processing.', [
    {text:'Keep rendering',style:'cancel'},
    {text:'Cancel render',style:'destructive',onPress:async()=>{
      if(!token)return;
      setCancelling(true);revision.current++;
      try {const next=await cancelJob(id,token);revision.current++;setJob(next);setError('');}
      catch(e:any){Alert.alert('Could not cancel',e.message||'Try again');await refresh();}
      finally{setCancelling(false);}
    }},
  ]);
  const remove=()=>Alert.alert('Delete this project?',
    'This stops any render and removes server access now. Server files are scheduled for cleanup. Your original gallery video and copies already saved or shared remain.',[
      {text:'Keep project',style:'cancel'},
      {text:'Delete project',style:'destructive',onPress:async()=>{
        if(!token||deleting)return;
        setDeleting(true);revision.current++;
        try {
          await deleteJob(id,token);revision.current++;
          if(!job?.preview_parent_id)await forgetPreviewIntents(id).catch(()=>{});
          let cacheFailed=false;
          try{await FileSystem.deleteAsync((FileSystem.cacheDirectory||FileSystem.documentDirectory)+`nextphase-${id}.mp4`,{idempotent:true});}
          catch{cacheFailed=true;}
          router.replace('/(tabs)/projects');
          Alert.alert('Project deleted',cacheFailed?'Server access removed; file cleanup is scheduled. The cached copy on this phone could not be removed.':'Server access removed. Server file cleanup is scheduled.');
        }catch(e:any){Alert.alert('Could not delete',e.message||'Check your connection and retry.');}
        finally{setDeleting(false);}
      }},
    ]);
  const finish=()=>Alert.alert('Save and finish this project?',
    'We will save the finished Short to your phone first. Only after your phone confirms the save will we request deletion of this original project and all of its server-side previews. Server cleanup is scheduled and may take time. This cannot be undone.',[
      {text:'Keep editing',style:'cancel'},
      {text:'Save and finish',onPress:async()=>{
        if(!token||!job||exportBusy.current||deleting)return;
        exportBusy.current=true;setDownloading(true);revision.current++;
        try{
          await saveAndFinish(job.id,job.preview_parent_id||job.id,token);
          revision.current++;router.replace('/(tabs)/projects');
          Alert.alert('Short saved','Saved to your phone. Server access was revoked and project-media cleanup is scheduled. Historical backups, if any, have separate retention rules.');
        }catch(e:any){
          if(e instanceof SavedButCleanupPending){
            Alert.alert('Saved; cleanup not confirmed',e.message);
          }else Alert.alert('Could not save and finish',e.message||'Your project was kept. Check the video and retry.');
          await refresh();
        }finally{exportBusy.current=false;setDownloading(false);}
      }},
    ]);
  const download=async(action:'save'|'share')=>{
    if(!token||!job||exportBusy.current)return;
    exportBusy.current=true;setDownloading(true);
    try {
      await exportVideo(action,job.id,token);
      if(action==='save')Alert.alert('Video saved','Saved to your phone’s media library. Open Photos or Gallery to find it.');
    }catch(e:any){Alert.alert(action==='save'?'Could not save video':'Could not share video',e.message||'Try again');}
    finally{exportBusy.current=false;setDownloading(false);}
  };
  return <Page><ScrollView contentContainerStyle={{paddingTop:22,gap:18}}>
    <Title>{job?.title||'Your project'}</Title>
    {!!error&&<Body>{error}</Body>}
    {!job?(unavailable?<Button title="Back to My Shorts" onPress={()=>router.replace('/(tabs)/projects')}/>:<Loading/>):<>
      <View style={s.card}><Text style={s.cardTitle}>Cloud render status</Text>
        <Text style={{fontSize:23,fontWeight:'800',color:job.status==='succeeded'?c.accent:c.warning}}>{job.status.toUpperCase()}</Text>
        <Body>{job.status==='queued'?'Waiting for a server worker.':job.status==='processing'?'Processing on the server — your phone is not rendering.':job.status==='succeeded'?'Your 9:16 short is ready.':job.status==='cancelled'?'This render was cancelled. You can create a new Short.':'Rendering failed; support and retry controls are planned.'}</Body>
        <Body>Requested {job.desired_seconds}s · {job.style} · actual {job.output_duration_seconds?.toFixed(1)||'—'}s</Body>
        {job.error_code&&<Body>{job.error_code==='OUTPUT_LIMIT_EXCEEDED'?'This export exceeded its server file limit. Try a shorter output.':`Error code: ${job.error_code}`}</Body>}
      </View>
      {['queued','processing'].includes(job.status)&&<Button title={cancelling?'Cancelling…':'Cancel render'} onPress={cancel} disabled={cancelling||deleting||downloading} secondary/>}
      <Button title="Refresh status" onPress={refresh} disabled={deleting} secondary />
      {englishReviewVisible&&!job.preview_parent_id&&token&&<EnglishAnalysisPanel key={`${id}:${token}`} id={id} token={token} disabled={deleting||downloading||cancelling}/>}
      {job.preview_parent_id&&<Button title="Back to source review" onPress={()=>router.push({pathname:'/review/[id]',params:{id:job.preview_parent_id!}})} disabled={deleting||downloading||cancelling} secondary/>}
      {job.status==='succeeded'&&job.operation!=='analysis'&&<>
        {job.preview_parent_id&&token&&<ClipPlayer key={`${job.id}:${token}`} id={job.id} token={token}/>}
        <Button title={downloading?'Please wait…':'Save & finish (delete project)'} onPress={finish} disabled={downloading||deleting||cancelling}/>
        <Button title="Save without deleting" onPress={()=>download('save')} disabled={downloading||deleting||cancelling} secondary/>
        <Button title="Share video" onPress={()=>download('share')} disabled={downloading||deleting||cancelling} secondary/>
      </>}
      <Button title={deleting?'Deleting…':'Delete project'} onPress={remove} disabled={deleting||downloading||cancelling} secondary/>
      <Body>{job.preview_parent_id?'Reviewed clip preview. Framing, captions and voice settings follow your chosen options.':'The baseline short trims the start of your recording. English suggestions use a separate transcript review; advanced editing styles are still planned.'}</Body>
    </>}
  </ScrollView></Page>;
}
