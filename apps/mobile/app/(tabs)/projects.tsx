import React, { useCallback, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import { api, Job } from '../../src/api';
import { useAuth } from '../../src/auth';
import { colors as c } from '../../src/theme';
import { Body, Button, Page, Title, s } from '../../src/ui';
export default function Projects() {
  const {token} = useAuth(); const [jobs,setJobs]=useState<Job[]>([]);
  const revision=useRef(0);
  const [loading,setLoading]=useState(true); const [error,setError]=useState('');
  const refresh=useCallback(async()=>{
    if(!token)return;
    const request=++revision.current;
    try {const next=await api<Job[]>('/api/v1/jobs',token);
      if(request===revision.current){setJobs(next);setError('');}}
    catch(e:any){if(request===revision.current)setError(e.message||'Could not load projects');}
    finally{if(request===revision.current)setLoading(false);}
  },[token]);
  useFocusEffect(useCallback(()=>{refresh();return()=>{revision.current++;};},[refresh]));
  return <Page safeTop><ScrollView refreshControl={<RefreshControl refreshing={false} onRefresh={refresh} tintColor={c.accent}/>}
    contentContainerStyle={{paddingTop:24,gap:16,paddingBottom:40}}>
    <Title>My Shorts</Title><Body>Your videos are processed in the cloud. Pull down to refresh.</Body>
    {loading && <ActivityIndicator color={c.accent}/>}
    {!!error && <Body>{error}</Body>}
    {!loading && jobs.length===0 && <View style={s.card}><Body>No videos yet. Make your first one.</Body><Button title="Create Short" onPress={()=>router.push('/create')}/></View>}
    {jobs.map(job=><Pressable key={job.id} style={s.card} onPress={()=>router.push({pathname:'/project/[id]',params:{id:job.id}})}>
      <Text style={s.cardTitle}>{job.title}</Text>
      <Text style={{color:job.status==='succeeded'?c.accent:c.warning,fontWeight:'700'}}>{job.status.toUpperCase()}</Text>
      <Body>{job.style} · max {job.desired_seconds}s · {new Date(job.created_at).toLocaleDateString()}</Body>
    </Pressable>)}
  </ScrollView></Page>;
}
