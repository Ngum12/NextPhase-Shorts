import React from 'react';
import { Alert, Text, View } from 'react-native';
import { router } from 'expo-router';
import { useAuth } from '../../src/auth';
import { Body, Button, Page, Title, s } from '../../src/ui';
export default function Account() {
  const {signOut}=useAuth();
  return <Page><View style={{paddingTop:28,gap:18}}>
    <Title>Account</Title>
    <View style={s.card}><Text style={s.cardTitle}>Preview access</Text>
      <Body>Monthly Mobile Money subscriptions, quotas and invoices are planned, but no payments are currently collected.</Body></View>
    <View style={s.card}><Text style={s.cardTitle}>Your privacy matters</Text>
      <Body>Only your account can access your video download. Production retention and deletion controls must be completed before launch.</Body></View>
    <Button title="Sign out" onPress={()=>{signOut().then(()=>router.replace('/login')).catch(()=>Alert.alert('Error','Could not sign out'));}} secondary />
  </View></Page>;
}
