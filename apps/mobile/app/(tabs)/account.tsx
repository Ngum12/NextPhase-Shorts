import React, {useCallback, useState} from 'react';
import { Alert, ScrollView, Text, View } from 'react-native';
import { router, useFocusEffect } from 'expo-router';
import {api} from '../../src/api';
import { useAuth } from '../../src/auth';
import { Body, Button, Page, Title, s } from '../../src/ui';
export default function Account() {
  const {signOut,token}=useAuth();
  const [storage,setStorage]=useState<{limit_bytes:number;known_reserved_bytes:number;uninventoried_count:number}|null>(null);
  const [storageError,setStorageError]=useState('');
  const [emailCheck,setEmailCheck]=useState<string>('Loading email status…');
  useFocusEffect(useCallback(()=>{
    let active=true;setStorage(null);setEmailCheck('Loading email status…');
    if(token)api<{email_verified_at:string|null;email_verification_method:string|null}>('/api/v1/me',token)
      .then(value=>{if(active)setEmailCheck(value.email_verification_method==='local_file'&&value.email_verified_at?'Local test confirmed; real email delivery is not enabled.':'Email confirmation has not been completed.');})
      .catch(()=>{if(active)setEmailCheck('Email status unavailable. Reopen Account to retry.');});
    if(token)api<any>('/api/v1/me/storage',token).then(value=>{if(active){setStorage(value);setStorageError('');}})
      .catch(()=>{if(active)setStorageError('Storage usage is unavailable. Reopen Account to retry.');});
    return()=>{active=false;};
  },[token]));const [busy,setBusy]=useState(false);
  const leave=async(all=false)=>{
    setBusy(true);
    try{await signOut(all);router.replace('/login');}
    catch(error:any){Alert.alert('Could not sign out',error.message||'Connect to the server and retry.');}
    finally{setBusy(false);}
  };
  return <Page safeTop><ScrollView contentContainerStyle={{paddingTop:28,paddingBottom:32,gap:18}}>
    <Title>Account</Title>
    <View style={s.card}><Text style={s.cardTitle}>Preview access</Text>
      <Body>Monthly Mobile Money subscriptions, quotas and invoices are planned, but no payments are currently collected.</Body></View>
    <View style={s.card}><Text style={s.cardTitle}>Your privacy matters</Text>
      <Body>Only your account can access your video download. Production retention and deletion controls must be completed before launch.</Body></View>
    <View style={s.card}><Text style={s.cardTitle}>Server storage</Text>
      {storageError?<Body>{storageError}</Body>:storage?<>
        <Body>{(storage.known_reserved_bytes/1048576).toFixed(1)} MiB used or reserved / {(storage.limit_bytes/1048576).toFixed(0)} MiB budget</Body>
        <Body>{storage.uninventoried_count?'Storage usage is being verified. New uploads are temporarily unavailable.':'Includes reserved rendering space. Deleting projects reclaims it after server cleanup.'}</Body>
      </>:<Body>Loading storage usage…</Body>}
    </View>
    <View style={s.card}><Text style={s.cardTitle}>Email confirmation</Text><Body>{emailCheck}</Body></View>
    <Button title="Email confirmation (local preview)" secondary onPress={()=>router.push({pathname:'/recover',params:{mode:'verify'}})}/>
    <Button title="Change password" onPress={()=>router.push('/security')} disabled={busy} secondary/>
    <Button title={busy?'Please wait…':'Sign out'} onPress={()=>leave()} disabled={busy} secondary/>
    <Button title="Sign out all sessions" disabled={busy} secondary onPress={()=>Alert.alert('Sign out everywhere?',
      'All sessions for this account will be revoked. Your projects and saved uploads remain.',[
        {text:'Keep sessions',style:'cancel'},{text:'Sign out all',style:'destructive',onPress:()=>leave(true)},
      ])}/>
    <Button title="Delete account" secondary disabled={busy} onPress={()=>router.push('/delete-account')}/>
    <Body>Signing out requires a connection to the server.</Body>
  </ScrollView></Page>;
}
