import React, {useState} from 'react';
import { Alert, Text, View } from 'react-native';
import { router } from 'expo-router';
import { useAuth } from '../../src/auth';
import { Body, Button, Page, Title, s } from '../../src/ui';
export default function Account() {
  const {signOut}=useAuth();const [busy,setBusy]=useState(false);
  const leave=async(all=false)=>{
    setBusy(true);
    try{await signOut(all);router.replace('/login');}
    catch(error:any){Alert.alert('Could not sign out',error.message||'Connect to the server and retry.');}
    finally{setBusy(false);}
  };
  return <Page safeTop><View style={{paddingTop:28,gap:18}}>
    <Title>Account</Title>
    <View style={s.card}><Text style={s.cardTitle}>Preview access</Text>
      <Body>Monthly Mobile Money subscriptions, quotas and invoices are planned, but no payments are currently collected.</Body></View>
    <View style={s.card}><Text style={s.cardTitle}>Your privacy matters</Text>
      <Body>Only your account can access your video download. Production retention and deletion controls must be completed before launch.</Body></View>
    <Button title="Change password" onPress={()=>router.push('/security')} disabled={busy} secondary/>
    <Button title={busy?'Please wait…':'Sign out'} onPress={()=>leave()} disabled={busy} secondary/>
    <Button title="Sign out all sessions" disabled={busy} secondary onPress={()=>Alert.alert('Sign out everywhere?',
      'All sessions for this account will be revoked. Your projects and saved uploads remain.',[
        {text:'Keep sessions',style:'cancel'},{text:'Sign out all',style:'destructive',onPress:()=>leave(true)},
      ])}/>
    <Body>Signing out requires a connection to the server.</Body>
  </View></Page>;
}
