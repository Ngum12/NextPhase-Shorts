import React, {useEffect} from 'react';
import { Stack, useSegments, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { AuthProvider, useAuth } from '../src/auth';
import { colors } from '../src/theme';
function SessionGuard() {
  const {token,ready}=useAuth();const segments=useSegments();const router=useRouter();
  useEffect(()=>{if(ready&&!token&&segments.length&&segments[0]!=='login')router.replace('/login');},[ready,token,segments]);
  return null;
}
export default function RootLayout() {
  return <AuthProvider><StatusBar style="light"/><Stack screenOptions={{ headerStyle:{ backgroundColor:colors.bg }, headerTintColor:colors.text,
    contentStyle:{ backgroundColor:colors.bg }, headerShadowVisible:false }}>
    <Stack.Screen name="index" options={{headerShown:false}}/>
    <Stack.Screen name="login" options={{headerShown:false}}/>
    <Stack.Screen name="(tabs)" options={{headerShown:false}}/>
    <Stack.Screen name="security" options={{title:'Account security'}}/>
    <Stack.Screen name="create" options={{title:'Create a Short'}}/>
    <Stack.Screen name="project/[id]" options={{title:'Your Short'}}/>
  </Stack><SessionGuard/></AuthProvider>;
}
