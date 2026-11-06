import React from 'react';
import { Stack } from 'expo-router';
import { AuthProvider } from '../src/auth';
import { colors } from '../src/theme';
export default function RootLayout() {
  return <AuthProvider><Stack screenOptions={{ headerStyle:{ backgroundColor:colors.bg }, headerTintColor:colors.text,
    contentStyle:{ backgroundColor:colors.bg }, headerShadowVisible:false }}>
    <Stack.Screen name="index" options={{headerShown:false}}/>
    <Stack.Screen name="login" options={{headerShown:false}}/>
    <Stack.Screen name="(tabs)" options={{headerShown:false}}/>
    <Stack.Screen name="create" options={{title:'Create a Short'}}/>
    <Stack.Screen name="project/[id]" options={{title:'Your Short'}}/>
  </Stack></AuthProvider>;
}
