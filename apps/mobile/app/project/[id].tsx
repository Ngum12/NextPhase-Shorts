import React, { useEffect, useRef, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { api, cancelJob, downloadUrl, Job } from '../../src/api';
import { unauthorized } from '../../src/authEvents';
import { useAuth } from '../../src/auth';
import { colors as c } from '../../src/theme';
import { Body, Button, Loading, Page, Title, s } from '../../src/ui';
export default function Project() {
  const params=useLocalSearchParams<{id:string}>(); const id=String(params.id||'');
  const {token}=useAuth();const[job,setJob]=useState<Job|null>(null);const[error,setError]=useState('');
  const [downloading,setDownloading]=useState(false);
  const [cancelling,setCancelling]=useState(false);
  const revision=useRef(0);
  const refresh=async()=>{
    if(!token||!id)return;
    const request=++revision.current;
    try {const next=await api<Job>(`/api/v1/jobs/${encodeURIComponent(id)}`,token);
      if(request===revision.current){setJob(next);setError('');}}
    catch(e:any){if(request===revision.current)setError(e.message||'Unable to load project');}
  };
  useEffect(()=>{
    refresh();
    if(job && !['queued','processing'].includes(job.status))return ()=>{revision.current++;};
    const timer=setInterval(refresh,5000);return()=>{clearInterval(timer);revision.current++;};
  },[id,token,job?.status]);
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
  const download=async()=>{
    if(!token||!job)return;
    setDownloading(true);
    try {
      const dest=(FileSystem.cacheDirectory||FileSystem.documentDirectory)+`nextphase-${job.id}.mp4`;
      const result=await FileSystem.downloadAsync(downloadUrl(job.id),dest,{headers:{Authorization:`Bearer ${token}`}});
      if(result.status===401)unauthorized(token);
      if(result.status!==200)throw new Error('Download not authorized or unavailable');
      if(await Sharing.isAvailableAsync()) await Sharing.shareAsync(result.uri,{mimeType:'video/mp4'});
      else Alert.alert('Saved','Video stored in app cache. Sharing is unavailable on this device.');
    }catch(e:any){Alert.alert('Could not download',e.message||'Try again');}
    finally{setDownloading(false);}
  };
  return <Page><ScrollView contentContainerStyle={{paddingTop:22,gap:18}}>
    <Title>{job?.title||'Your project'}</Title>
    {!!error&&<Body>{error}</Body>}
    {!job?<Loading/>:<>
      <View style={s.card}><Text style={s.cardTitle}>Cloud render status</Text>
        <Text style={{fontSize:23,fontWeight:'800',color:job.status==='succeeded'?c.accent:c.warning}}>{job.status.toUpperCase()}</Text>
        <Body>{job.status==='queued'?'Waiting for a server worker.':job.status==='processing'?'Processing on the server — your phone is not rendering.':job.status==='succeeded'?'Your 9:16 short is ready.':job.status==='cancelled'?'This render was cancelled. You can create a new Short.':'Rendering failed; support and retry controls are planned.'}</Body>
        <Body>Requested {job.desired_seconds}s · {job.style} · actual {job.output_duration_seconds?.toFixed(1)||'—'}s</Body>
        {job.error_code&&<Body>Error code: {job.error_code}</Body>}
      </View>
      {['queued','processing'].includes(job.status)&&<Button title={cancelling?'Cancelling…':'Cancel render'} onPress={cancel} disabled={cancelling} secondary/>}
      <Button title="Refresh status" onPress={refresh} secondary />
      {job.status==='succeeded'&&<Button title={downloading?'Downloading…':'Download or share MP4'} onPress={download} disabled={downloading}/>}
      <Body>Stage 1 preview: trimmed vertical MP4 only. Intelligent highlight selection and advanced styles will be built in later phases.</Body>
    </>}
  </ScrollView></Page>;
}
