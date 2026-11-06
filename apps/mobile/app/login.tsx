import React, { useState } from 'react';
import { Alert, KeyboardAvoidingView, Platform, Text, TextInput, View } from 'react-native';
import { router } from 'expo-router';
import { login } from '../src/api';
import { useAuth } from '../src/auth';
import { colors } from '../src/theme';
import { Body, Button, Page, Title, s } from '../src/ui';
export default function LoginScreen() {
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [isNew, setIsNew] = useState(false); const [busy, setBusy] = useState(false);
  const { signIn } = useAuth();
  const submit = async () => {
    setBusy(true);
    try { await signIn(await login(email, password, isNew)); router.replace('/(tabs)'); }
    catch (err: any) { Alert.alert('Could not continue', err.message || 'Try again'); }
    finally { setBusy(false); }
  };
  return <Page safeTop><KeyboardAvoidingView behavior={Platform.OS==='ios'?'padding':undefined} style={{flex:1, justifyContent:'center', gap:18}}>
    <Text style={{color:colors.accent, fontSize:18, fontWeight:'800', letterSpacing:2}}>NEXTPHASE</Text>
    <Title>Your Shorts editor preview.</Title>
    <Body>Baseline 9:16 trimming on the server. AI editing is planned; no heavy editing runs on your phone.</Body>
    <TextInput style={s.input} placeholder="Email" placeholderTextColor={colors.muted} value={email} autoCapitalize="none"
      keyboardType="email-address" onChangeText={setEmail} accessibilityLabel="Email address" />
    <TextInput style={s.input} placeholder="Password (10+ characters)" placeholderTextColor={colors.muted} value={password}
      secureTextEntry onChangeText={setPassword} accessibilityLabel="Password" />
    <Button title={busy ? 'Please wait…' : isNew ? 'Create account' : 'Sign in'} onPress={submit} disabled={busy || !email || password.length<10}/>
    <Button title={isNew ? 'Already have an account? Sign in' : 'New here? Create an account'} onPress={()=>setIsNew(!isNew)} secondary />
    <Body>Preview build: cloud trimming is functional; AI style effects and subscriptions will be added in later stages.</Body>
  </KeyboardAvoidingView></Page>;
}
