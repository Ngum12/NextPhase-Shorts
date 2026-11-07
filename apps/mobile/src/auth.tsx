import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { api, changePassword, logoutSession } from './api';
import { onUnauthorized } from './authEvents';
import { SessionController } from './session';
const KEY = 'nextphase_session';
type AuthValue = { token:string|null; ready:boolean; signIn:(token:string)=>Promise<void>;
  signOut:(all?:boolean)=>Promise<void>; changePassword:(current:string,next:string)=>Promise<void>;
  expireSession:(expected:string)=>Promise<void> };
const Auth=createContext<AuthValue|undefined>(undefined);
export function AuthProvider({children}:{children:React.ReactNode}) {
  const [token,setToken]=useState<string|null>(null);const [ready,setReady]=useState(false);
  const ref=useRef<SessionController|null>(null);
  if(!ref.current)ref.current=new SessionController({read:()=>SecureStore.getItemAsync(KEY),
    write:next=>SecureStore.setItemAsync(KEY,next),remove:()=>SecureStore.deleteItemAsync(KEY)},
    {validate:next=>api('/api/v1/me',next),revoke:logoutSession,password:changePassword},setToken);
  const session=ref.current;
  useEffect(()=>{
    const unsubscribe=onUnauthorized(next=>{session.expire(next).catch(()=>{});});
    session.restore().catch(()=>{}).finally(()=>setReady(true));
    return unsubscribe;
  },[session]);
  return <Auth.Provider value={{token,ready,signIn:next=>session.signIn(next),signOut:all=>session.signOut(all),
    changePassword:(current,next)=>session.changePassword(current,next),expireSession:expected=>session.expire(expected)}}>{children}</Auth.Provider>;
}
export function useAuth(){const value=useContext(Auth);if(!value)throw new Error('Missing AuthProvider');return value;}
