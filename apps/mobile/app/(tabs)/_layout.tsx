import React from 'react';
import { Tabs } from 'expo-router';
import { Text } from 'react-native';
import { colors as c } from '../../src/theme';
export default function TabsLayout() {
  return <Tabs screenOptions={{headerShown:false, tabBarActiveTintColor:c.accent, tabBarInactiveTintColor:c.muted,
    tabBarStyle:{backgroundColor:c.surface, borderTopColor:c.border, height:65}}}>
    <Tabs.Screen name="index" options={{title:'Home', tabBarIcon:()=> <Text style={{fontSize:21}}>⌂</Text>}} />
    <Tabs.Screen name="projects" options={{title:'My Shorts',tabBarIcon:()=> <Text style={{fontSize:21}}>▤</Text>}} />
    <Tabs.Screen name="account" options={{title:'Account',tabBarIcon:()=> <Text style={{fontSize:21}}>◉</Text>}} />
  </Tabs>;
}
