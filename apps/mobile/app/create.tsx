import React, { useEffect, useRef, useState } from 'react';
import * as DocumentPicker from 'expo-document-picker';
import { Alert, ScrollView, Text, TextInput, View, Pressable } from 'react-native';
import { router } from 'expo-router';
import { api } from '../src/api';
import { discardUpload, loadPending, PendingUpload, prepareUpload, resumeUpload } from '../src/uploads';
import { useAuth } from '../src/auth';
import { colors as c } from '../src/theme';
import { Body, Button, Page, Title, s } from '../src/ui';
const styles = [
  ['vlog','Professional Vlog'], ['documentary','Cinematic Documentary'],
  ['reels','Viral Shorts'], ['ads','Business Ads'],
  ['education','Education'], ['interviews','Interviews'],
] as const;
export default function Create() {
  const {token}=useAuth();
  const [ownerId,setOwnerId]=useState('');
  const [recovery,setRecovery]=useState(0);
  const [asset,setAsset]=useState<DocumentPicker.DocumentPickerAsset|null>(null);
  const [style,setStyle]=useState('vlog');
  const [seconds,setSeconds]=useState(30);
  const [title,setTitle]=useState('My First Short');
  const [pending,setPending]=useState<PendingUpload|null>(null);
  const [busy,setBusy]=useState(false);
  const [loading,setLoading]=useState(true);
  const [progress,setProgress]=useState<number|null>(null);
  const [message,setMessage]=useState('');
  const running=useRef(false);
  const controller=useRef<AbortController|null>(null);
  useEffect(()=>{
    let mounted=true;
    setOwnerId('');setPending(null);
    const recover=async()=>{
      try {
        if(!token)return;
        const user=await api<{id:string}>('/api/v1/me',token);
        const saved=await loadPending(user.id);
        if(mounted){setOwnerId(user.id);setPending(saved);setMessage(saved?'A saved upload is ready to resume.':'');}
      }catch(error:any){if(mounted)setMessage(error.message||'Connect to the server to recover uploads.');}
      finally{if(mounted)setLoading(false);}
    };
    recover();
    return()=>{mounted=false;controller.current?.abort();};
  },[token,recovery]);
  const pick=async()=>{
    try {
      const result=await DocumentPicker.getDocumentAsync({type:'video/*',copyToCacheDirectory:true,multiple:false});
      if(!result.canceled&&result.assets.length)setAsset(result.assets[0]);
    }catch(error:any){Alert.alert('Could not select video',error.message||'Try again');}
  };
  const submit=async()=>{
    if(!token||!ownerId||running.current||(!pending&&!asset))return;
    running.current=true;setBusy(true);setMessage('Preparing your upload…');
    const abort=new AbortController();controller.current=abort;
    try {
      const record=pending||await prepareUpload(ownerId,asset!,title,style,seconds);
      setPending(record);
      if(abort.signal.aborted)throw new Error('Upload paused');
      const job=await resumeUpload(record,token,(sent,total)=>{
        setProgress(sent/total);
        setMessage(sent===total?'Upload received. Checking your video…':'Uploading verified chunks…');
      },abort.signal);
      setPending(null);
      router.replace({pathname:'/project/[id]',params:{id:job.id}});
    }catch(error:any){
      const saved=await loadPending(ownerId).catch(()=>null);
      setPending(saved);
      setMessage(abort.signal.aborted?'Upload paused. Resume when you are ready.':error.message||'Upload interrupted. You can resume.');
    }finally{running.current=false;controller.current=null;setBusy(false);}
  };
  const discard=()=>Alert.alert('Discard this upload?', 'Uploaded parts and the app’s saved copy will be removed. Your original video stays on your phone.',[
    {text:'Keep upload',style:'cancel'},
    {text:'Discard upload',style:'destructive',onPress:async()=>{
      if(!pending||!token||running.current)return;
      running.current=true;setBusy(true);
      try {
        const job=await discardUpload(pending,token);
        setPending(null);setProgress(null);setMessage(job?'Upload already completed. Opening its project.':'Upload discarded.');
        if(job)router.replace({pathname:'/project/[id]',params:{id:job.id}});
      }catch(error:any){setMessage(error.message||'Connect to the server to discard this upload.');}
      finally{running.current=false;setBusy(false);}
    }},
  ]);
  return <Page><ScrollView contentContainerStyle={{gap:16,paddingBottom:50}}>
    <Title>Create a Short</Title>
    <Body>Rendering runs on the server. Use only consented test footage in this development preview.</Body>
    {!!message&&<Body>{message}</Body>}
    {loading&&<Body>Checking for a saved upload…</Body>}
    {!loading&&!ownerId&&<Button title="Retry connection" onPress={()=>{setLoading(true);setRecovery(n=>n+1);}} secondary/>}
    {pending?<View style={s.card}>
      <Text style={s.cardTitle}>{pending.title}</Text>
      <Body>{pending.fileName} · {(pending.totalBytes/1048576).toFixed(1)} MiB</Body>
      <Body>{progress===null?'Progress will be checked with the server when you resume.':`Upload: ${Math.floor(progress*100)}% received`}</Body>
      <Body>Resume after a connection interruption or app restart. Keep this app’s data. Transfers run while the app is active.</Body>
      {busy&&controller.current?<Button title="Pause upload" onPress={()=>controller.current?.abort()} secondary/>:
        <Button title="Resume upload" onPress={submit} disabled={busy}/>}
      <Button title="Discard upload" onPress={discard} disabled={busy} secondary/>
    </View>:<>
      <View style={s.card}><Text style={s.cardTitle}>1. Choose your video</Text>
        <Body>MP4, MOV, WebM or M4V · up to 10 minutes · up to 300 MiB. A private copy is saved in the app until upload completes or is discarded.</Body>
        <Button title={asset?`Selected: ${asset.name}`:'Choose from phone'} onPress={pick} disabled={busy||loading||!ownerId} secondary/>
      </View>
      <View style={s.card}><Text style={s.cardTitle}>2. Name your project</Text>
        <TextInput style={s.input} editable={!busy} value={title} onChangeText={setTitle} maxLength={120} accessibilityLabel="Project name"/>
      </View>
      <View style={s.card}><Text style={s.cardTitle}>3. Select future editing style</Text>
        <Body>All styles currently use the same baseline converter; style effects are planned.</Body>
        {styles.map(([key,label])=><Pressable key={key} disabled={busy} onPress={()=>setStyle(key)}
          style={{backgroundColor:style===key?c.surface2:c.bg,padding:12,borderRadius:10,borderColor:style===key?c.accent:c.border,borderWidth:1}}>
          <Text style={{color:c.text,fontWeight:style===key?'800':'500'}}>{label}</Text>
        </Pressable>)}
      </View>
      <View style={s.card}><Text style={s.cardTitle}>4. Maximum output length</Text>
        <View style={{flexDirection:'row',gap:8}}>{[15,30,45,60].map(n=><Pressable key={n} disabled={busy} onPress={()=>setSeconds(n)}
          style={{flex:1,backgroundColor:seconds===n?c.accent:c.surface2,borderRadius:10,paddingVertical:13,alignItems:'center'}}>
          <Text style={{color:seconds===n?c.bg:c.text,fontWeight:'800'}}>{n}s</Text>
        </Pressable>)}</View>
      </View>
      <Button title={busy?'Saving your upload…':'Upload and start cloud render'} disabled={busy||loading||!ownerId||!asset||!title.trim()} onPress={submit}/>
    </>}
  </ScrollView></Page>;
}
