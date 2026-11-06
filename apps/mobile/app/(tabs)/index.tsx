import React, { useEffect, useState } from 'react';
import { ScrollView, Text, View } from 'react-native';
import { router } from 'expo-router';
import { getStyles, ShortStyle } from '../../src/api';
import { colors as c } from '../../src/theme';
import { Body, Button, Page, Title, s } from '../../src/ui';
export default function Home() {
  const [styles, setStyles] = useState<ShortStyle[]>([]);
  useEffect(()=>{getStyles().then(setStyles).catch(()=>{});},[]);
  return <Page safeTop><ScrollView contentContainerStyle={{gap:18, paddingTop:24, paddingBottom:45}}>
    <Text style={{color:c.accent,fontWeight:'800',letterSpacing:3}}>NEXTPHASE SHORTS</Text>
    <Title>Your story. A better Short.</Title>
    <Body>Upload a recording. We handle rendering on the server — up to 60 seconds, always vertical.</Body>
    <View style={[s.card,{backgroundColor:'#1D393B', borderColor:'#3B6663', gap:12}]}>
      <Text style={{fontSize:35}}>✦</Text>
      <Text style={s.cardTitle}>Create your next video</Text>
      <Body>Automatic server processing, even on budget smartphones.</Body>
      <Button title="+ New Short" onPress={()=>router.push('/create')} />
    </View>
    <Text style={{color:c.text,fontSize:20,fontWeight:'800'}}>Creative styles</Text>
    <Body>These six styles are on our roadmap. In this first build, exports use the same baseline converter.</Body>
    {styles.map(item=><View key={item.id} style={s.card}>
      <Text style={s.cardTitle}>{item.name}  <Text style={{color:c.warning,fontSize:12}}>COMING SOON</Text></Text>
      <Body>{item.description}</Body>
    </View>)}
    <Body>Preview build • no AI processing or payment collection enabled</Body>
  </ScrollView></Page>;
}
