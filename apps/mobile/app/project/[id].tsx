import React, { useEffect, useState } from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';
import { api, downloadUrl, Job } from '../../src/api';
import { useAuth } from '../../src/auth';
import { colors as c } from '../../src/theme';
import { Body, Button, Loading, Page, Title, s } from '../../src/ui';
export default function Project() {
  const params=useLocalSearchParams<{id:string}>(); const id=String(params.id||'');
  const {token}=useAuth();const[job,setJob]=useState<Job|null>(null);const[error,setError]=useState('');
  const [downloading,setDownloading]=useState(false);
  const refresh=async()=>{
    if(!token||!id)return;
    try {setJob(await api<Job>(`/api/v1/jobs/${encodeURIComponent(id)}`,token));setError('');}
    catch(e:any){setError(e.message||'Unable to load project');}
  };
  useEffect(()=>{refresh(); const timer=setInterval(refresh,5000);return()=>clearInterval(timer);},[id,token]);
  const download=async()=>{
    if(!token||!job)return;
    setDownloading(true);
    try {
      const dest=(FileSystem.cacheDirectory||FileSystem.documentDirectory)+`nextphase-${job.id}.mp4`;
      const result=await FileSystem.downloadAsync(downloadUrl(job.id),dest,{headers:{Authorization:`Bearer ${token}`}});
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
        <Body>{job.status==='queued'?'Waiting for a server worker.':job.status==='processing'?'Processing on the server — your phone is not rendering.':job.status==='succeeded'?'Your 9:16 short is ready.':'Rendering failed; support and retry controls are planned.'}</Body>
        <Body>Requested {job.desired_seconds}s · {job.style} · actual {job.output_duration_seconds?.toFixed(1)||'—'}s</Body>
        {job.error_code&&<Body>Error code: {job.error_code}</Body>}
      </View>
      <Button title="Refresh status" onPress={refresh} secondary />
      {job.status==='succeeded'&&<Button title={downloading?'Downloading…':'Download or share MP4'} onPress={download} disabled={downloading}/>}
      <Body>Stage 1 preview: trimmed vertical MP4 only. Intelligent highlight selection and advanced styles will be built in later phases.</Body>
    </>}
  </ScrollView></Page>;
}
