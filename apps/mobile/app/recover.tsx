import React,{useEffect,useState} from 'react';
import {Alert,ScrollView,TextInput} from 'react-native';
import {router,useLocalSearchParams} from 'expo-router';
import {useAuth} from '../src/auth';
import {api} from '../src/api';
import {recoveryCapabilities,requestPasswordReset,confirmPasswordReset,requestEmailVerification,confirmEmail,RecoveryCapabilities} from '../src/emailActions';
import {Body,Button,Page,Title,s} from '../src/ui';
import {colors} from '../src/theme';

export default function Recover(){
  const params=useLocalSearchParams<{mode?:string}>(),verify=params.mode==='verify';
  const {token}=useAuth();
  const [caps,setCaps]=useState<RecoveryCapabilities|null>(null),[email,setEmail]=useState('');
  const [code,setCode]=useState(''),[password,setPassword]=useState(''),[confirm,setConfirm]=useState('');
  const [busy,setBusy]=useState(false),[status,setStatus]=useState('');
  const real=caps?.delivery==='email',enabled=real||caps?.delivery==='local_file';
  useEffect(()=>{
    let active=true;setCaps(null);setStatus('');setCode('');setPassword('');setConfirm('');
    recoveryCapabilities().then(value=>{if(active)setCaps(value);}).catch(error=>{if(active)setStatus(error.message);});
    return()=>{active=false;};
  },[verify]);
  const act=async(redeem=false)=>{
    if(busy)return;setBusy(true);setStatus('');const captured=token;
    try{
      if(redeem){
        if(verify)await confirmEmail(code);
        else await confirmPasswordReset(code,password);
        if(captured)await api('/api/v1/me',captured).catch(()=>{});
        Alert.alert(verify?(real?'Email confirmed':'Local email check complete'):'Password changed',verify?
          (real?'Your email address is confirmed.':
          'The private test code was accepted. Real email ownership is not established by this local preview.'):
          'All sessions for that account were revoked. Sign in again using the new password.');
        router.replace('/');
      }else{
        if(verify){if(!captured)throw Error('Sign in to request your email confirmation.');await requestEmailVerification(captured);}
        else await requestPasswordReset(email);
        setStatus(real?'If eligible, a code has been queued for email delivery. Check your inbox and spam folder. Delivery can be delayed.':
          'If eligible, a code was prepared in the private development inbox. This does not confirm that an account exists.');
      }
    }catch(error:any){setStatus(error.message||'Could not confirm the action. Connect and retry.');}
    finally{if(redeem){setCode('');setPassword('');setConfirm('');}setBusy(false);}
  };
  return <Page safeTop><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{gap:18,paddingVertical:24}}>
    <Title>{verify?'Email confirmation':'Reset password'}</Title>
    <Body>{caps?real?'Request a one-use code by email. Delivery may be delayed; requesting a code does not confirm that an account exists.':enabled?'Local testing only: no outgoing email is sent. Use a disposable test account and the private development inbox code.':
      'Email delivery is disabled in this preview. Password recovery and email confirmation cannot send a code yet.':'Checking email action availability…'}</Body>
    {!!status&&<Body>{status}</Body>}
    {verify?!token&&<Body>Sign in before requesting a confirmation code.</Body>:<TextInput style={s.input} placeholder="Account email"
      placeholderTextColor={colors.muted} keyboardType="email-address" autoCapitalize="none" autoCorrect={false}
      value={email} onChangeText={setEmail} accessibilityLabel="Account email"/>}
    <Button title={busy?'Please wait…':real?'Request email code':'Request private test code'} disabled={busy||!enabled||(verify?!token:!email.trim())} onPress={()=>act()}/>
    <TextInput style={s.input} placeholder={real?'Email code':'Private development code'} placeholderTextColor={colors.muted} secureTextEntry
      autoCapitalize="none" autoCorrect={false} maxLength={43} value={code} onChangeText={setCode} accessibilityLabel={real?'Email code':'Private development code'}/>
    {!verify&&<><TextInput style={s.input} placeholder="New password (12+ characters)" placeholderTextColor={colors.muted}
      secureTextEntry autoCapitalize="none" autoCorrect={false} maxLength={128} value={password} onChangeText={setPassword} accessibilityLabel="New password"/>
      <TextInput style={s.input} placeholder="Confirm new password" placeholderTextColor={colors.muted} secureTextEntry
      autoCapitalize="none" autoCorrect={false} maxLength={128} value={confirm} onChangeText={setConfirm} accessibilityLabel="Confirm new password"/></>}
    <Button title={verify?(real?'Confirm email':'Confirm local test code'):'Reset password and revoke sessions'} disabled={busy||!enabled||!/^[-A-Za-z0-9_]{43}$/.test(code.trim())||(!verify&&(password.length<12||password!==confirm))}
      onPress={()=>act(true)}/>
    <Body>Codes expire and work once. If a response is lost, do not assume success: try signing in with the new password or request another code. Never share codes publicly.</Body>
    <Button title="Back" secondary disabled={busy} onPress={()=>router.replace(token?'/(tabs)/account':'/login')}/>
  </ScrollView></Page>;
}
