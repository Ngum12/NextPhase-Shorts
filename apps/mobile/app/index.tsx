import React from 'react';
import { Redirect } from 'expo-router';
import { Page, Loading } from '../src/ui';
import { useAuth } from '../src/auth';
export default function Index() {
  const {token, ready} = useAuth();
  if (!ready) return <Page><Loading /></Page>;
  return <Redirect href={token ? '/(tabs)' : '/login'} />;
}
