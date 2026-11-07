import React,{useEffect,useState} from 'react';
import {Alert,ScrollView,TextInput} from 'react-native';
import {router} from 'expo-router';
import {useAuth} from '../src/auth';
import {api} from '../src/api';
import {accountDeletion} from '../src/accountDeletion';
import {Body,Button,Page,Title,s} from '../src/ui';
import {colors} from '../src/theme';

export default function DeleteAccount(){
  const {token,expireSession}=useAuth();
  const [owner,setOwner]=useState(''),[password,setPassword]=useState('');
  const [pending,setPending]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState('');
  const refresh=async()=>setPending(!!await accountDeletion.pending());
  useEffect(()=>{
    let active=true;setOwner('');
    accountDeletion.pending().then(value=>{if(active)setPending(!!value);}).catch(e=>{if(active)setError(e.message);});
    if(token)api<{id:string}>('/api/v1/me',token).then(value=>{if(active)setOwner(value.id);})
      .catch(e=>{if(active)setError(e.message);});
    return()=>{active=false;};
  },[token]);
  const run=async(recover=false)=>{
    if(busy)return;setBusy(true);setError('');const captured=token;
    try{
      if(recover)await accountDeletion.recover(async()=>{
        // Only the originating token's 401 may expire it; a newer login survives.
        if(captured)await api('/api/v1/me',captured).catch(()=>{});
      });
      else if(captured&&owner)await accountDeletion.submit(owner,captured,password,expireSession);
      else throw Error('Sign in to request account deletion.');
      Alert.alert('Account disabled','Sign-in is disabled. Server media cleanup is scheduled. Saved/shared videos, backups and operational records are outside this cleanup.');
      router.replace('/');
    }catch(e:any){setError(e.message||'Request not confirmed. Check confirmation before retrying.');}
    finally{setPassword('');await refresh().catch(()=>{});setBusy(false);}
  };
  return <Page safeTop><ScrollView contentContainerStyle={{gap:18,paddingVertical:24}}>
    <Title>Delete account</Title>
    <Body>This permanently disables sign-in and revokes all sessions. Your projects become unavailable immediately. Server media removal runs later and retries failures.</Body>
    <Body>Original phone videos, saved/shared exports, download caches and backups remain. Operational records are retained. This is not complete personal-data erasure.</Body>
    {!!error&&<Body>{error}</Body>}
    {pending&&<><Body>A deletion request is saved on this phone. Check its confirmation after an interrupted connection. Keep app data until confirmed; recovery is available for seven days.</Body>
      <Button title="Check deletion confirmation" disabled={busy} onPress={()=>run(true)}/></>}
    {!!token&&<><TextInput style={s.input} secureTextEntry autoCapitalize="none" autoCorrect={false}
      placeholder="Current password" placeholderTextColor={colors.muted} maxLength={128}
      accessibilityLabel="Current password" value={password} onChangeText={setPassword}/>
      <Button title={busy?'Please wait…':'Delete my account'} secondary disabled={busy||!owner||!password}
        onPress={()=>Alert.alert('Permanently delete this account?','Sign-in and project access will stop. This cannot be undone in the app.',[
          {text:'Keep account',style:'cancel'},{text:'Delete account',style:'destructive',onPress:()=>run()},
        ])}/></>}
    {!token&&!pending&&<Body>Sign in to request deletion. No saved request is available on this phone.</Body>}
    <Button title="Back" secondary disabled={busy} onPress={()=>router.replace(token?'/(tabs)/account':'/login')}/>
  </ScrollView></Page>;
}
