import React, { useRef, useState } from 'react';
import * as DocumentPicker from 'expo-document-picker';
import { Alert, ScrollView, Text, TextInput, View, Pressable } from 'react-native';
import { router } from 'expo-router';
import { uploadVideo } from '../src/api';
import { useAuth } from '../src/auth';
import { colors as c } from '../src/theme';
import { Body, Button, Page, Title, s } from '../src/ui';

const styles = [
  ['vlog','Professional Vlog'], ['documentary','Cinematic Documentary'],
  ['reels','Viral Shorts'], ['ads','Business Ads'],
  ['education','Education'], ['interviews','Interviews'],
] as const;

export default function Create() {
  const {token} = useAuth(); const [asset,setAsset]=useState<DocumentPicker.DocumentPickerAsset|null>(null);
  const [style,setStyle]=useState('vlog'); const [seconds,setSeconds]=useState(30);
  const [title,setTitle]=useState('My First Short'); const [busy,setBusy]=useState(false);
  const submission = useRef<{signature:string; key:string}|null>(null);
  const uploading = useRef(false);
  const pick=async()=>{
    const result=await DocumentPicker.getDocumentAsync({type:'video/*',copyToCacheDirectory:true,multiple:false});
    if(!result.canceled && result.assets.length) setAsset(result.assets[0]);
  };
  const submit=async()=>{
    if(!asset||!token||uploading.current)return;
    uploading.current=true;
    setBusy(true);
    const signature=JSON.stringify([asset.uri,asset.name,asset.size,style,title.trim(),seconds]);
    if(submission.current?.signature!==signature) {
      submission.current={signature,key:`upload_${Date.now().toString(36)}_${Math.random().toString(36).slice(2)}_${Math.random().toString(36).slice(2)}`};
    }
    try {const job=await uploadVideo(token,asset,style,title,seconds,submission.current.key);
      router.replace({pathname:'/project/[id]',params:{id:job.id}});
    } catch(e:any){Alert.alert('Upload failed',e.message||'Try again');}
    finally{uploading.current=false;setBusy(false);}
  };
  return <Page><ScrollView contentContainerStyle={{gap:16,paddingBottom:50}}>
    <Title>Create a Short</Title><Body>No phone-based video rendering. Your original file is uploaded to the API server. Use only consented test footage in this development preview.</Body>
    <View style={s.card}><Text style={s.cardTitle}>1. Choose your video</Text>
      <Body>MP4, MOV, WebM or M4V · up to 10 minutes · up to 300 MiB</Body>
      <Button title={asset?`Selected: ${asset.name}`:'Choose from phone'} onPress={pick} disabled={busy} secondary /></View>
    <View style={s.card}><Text style={s.cardTitle}>2. Name your project</Text>
      <TextInput style={s.input} editable={!busy} value={title} onChangeText={setTitle} maxLength={120} accessibilityLabel="Project name" /></View>
    <View style={s.card}><Text style={s.cardTitle}>3. Select future editing style</Text>
      <Body>Stage 1 is a baseline vertical render; all style-specific effects are coming later.</Body>
      {styles.map(([key,label])=><Pressable key={key} disabled={busy} onPress={()=>setStyle(key)} style={{backgroundColor:style===key?c.surface2:c.bg,padding:12,borderRadius:10,borderColor:style===key?c.accent:c.border,borderWidth:1}}>
        <Text style={{color:c.text,fontWeight:style===key?'800':'500'}}>{label}</Text></Pressable>)}
    </View>
    <View style={s.card}><Text style={s.cardTitle}>4. Maximum output length</Text>
      <View style={{flexDirection:'row',gap:8}}>{[15,30,45,60].map(n=><Pressable key={n} disabled={busy} onPress={()=>setSeconds(n)}
        style={{flex:1,backgroundColor:seconds===n?c.accent:c.surface2,borderRadius:10,paddingVertical:13,alignItems:'center'}}>
        <Text style={{color:seconds===n?c.bg:c.text,fontWeight:'800'}}>{n}s</Text></Pressable>)}</View>
    </View>
    <Button title={busy?'Uploading…':'Upload and start cloud render'} disabled={busy||!asset||!title.trim()} onPress={submit}/>
  </ScrollView></Page>;
}
