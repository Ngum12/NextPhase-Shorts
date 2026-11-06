import React, { createContext, useContext, useEffect, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
const KEY = 'nextphase_session';
type AuthValue = { token: string | null; ready: boolean; signIn: (token: string) => Promise<void>; signOut: () => Promise<void> };
const Auth = createContext<AuthValue | undefined>(undefined);
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => { SecureStore.getItemAsync(KEY).then(setToken).catch(() => {}).finally(() => setReady(true)); }, []);
  const signIn = async (next: string) => { await SecureStore.setItemAsync(KEY, next); setToken(next); };
  const signOut = async () => { await SecureStore.deleteItemAsync(KEY); setToken(null); };
  return <Auth.Provider value={{ token, ready, signIn, signOut }}>{children}</Auth.Provider>;
}
export function useAuth() {
  const value = useContext(Auth);
  if (!value) throw new Error('Missing AuthProvider');
  return value;
}
