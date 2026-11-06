import React, {useState} from 'react';
import {Alert,TextInput,ScrollView} from 'react-native';
import {router} from 'expo-router';
import {useAuth} from '../src/auth';
import {Body,Button,Page,s} from '../src/ui';
import {colors} from '../src/theme';
export default function Security() {
  const {changePassword}=useAuth();
  const [current,setCurrent]=useState(''),[next,setNext]=useState(''),[confirm,setConfirm]=useState('');
  const [busy,setBusy]=useState(false);
  const submit=async()=>{
    setBusy(true);
    try {await changePassword(current,next);router.replace('/login');Alert.alert('Password changed','All sessions have been signed out. Sign in with your new password.');}
    catch(error:any){Alert.alert('Could not change password',error.message||'Try again');}
    finally{setBusy(false);}
  };
  return <Page><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{paddingTop:24,paddingBottom:32,gap:18}}>
    <Body>Changing your password signs out every session. Your projects and saved uploads remain in your account.</Body>
    <TextInput style={s.input} placeholder="Current password" placeholderTextColor={colors.muted} secureTextEntry autoCapitalize="none" autoCorrect={false} maxLength={128}
      value={current} onChangeText={setCurrent} accessibilityLabel="Current password"/>
    <TextInput style={s.input} placeholder="New password (12+ characters)" placeholderTextColor={colors.muted} secureTextEntry autoCapitalize="none" autoCorrect={false} maxLength={128}
      value={next} onChangeText={setNext} accessibilityLabel="New password"/>
    <TextInput style={s.input} placeholder="Confirm new password" placeholderTextColor={colors.muted} secureTextEntry autoCapitalize="none" autoCorrect={false} maxLength={128}
      value={confirm} onChangeText={setConfirm} accessibilityLabel="Confirm new password"/>
    <Button title={busy?'Changing…':'Change password and sign out'} onPress={submit} disabled={busy||!current||next.length<12||next!==confirm}/>
  </ScrollView></Page>;
}
