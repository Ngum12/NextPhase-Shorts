import React, { createContext, useContext, useEffect, useRef, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { api, changePassword, logoutSession, refreshSession, revokeRefreshSession } from './api';
import { coordinateSession, onUnauthorized } from './authEvents';
import { RefreshSessionController, TokenPair } from './refreshSession';
import {randomUUID} from 'expo-crypto';
const KEY = 'nextphase_session';
type AuthValue = { token:string|null; ready:boolean; signIn:(token:TokenPair|string)=>Promise<void>;
  signOut:(all?:boolean)=>Promise<void>; changePassword:(current:string,next:string)=>Promise<void>;
  expireSession:(expected:string)=>Promise<void> };
const Auth=createContext<AuthValue|undefined>(undefined);
export function AuthProvider({children}:{children:React.ReactNode}) {
  const [token,setToken]=useState<string|null>(null);const [ready,setReady]=useState(false);
  const ref=useRef<RefreshSessionController|null>(null);
  if(!ref.current)ref.current=new RefreshSessionController({read:()=>SecureStore.getItemAsync(KEY),
    write:next=>SecureStore.setItemAsync(KEY,next),remove:()=>SecureStore.deleteItemAsync(KEY)},
    {validate:next=>api('/api/v1/me',next),revoke:logoutSession,password:changePassword,
      refresh:refreshSession,revokeRefresh:revokeRefreshSession},setToken,randomUUID);
  const session=ref.current;
  useEffect(()=>{
    const unsubscribe=onUnauthorized(next=>{session.expire(next).catch(()=>{});});
    const uncoordinate=coordinateSession({prepare:next=>session.prepare(next),recover:next=>session.recover(next)});
    session.restore().catch(()=>{}).finally(()=>setReady(true));
    return ()=>{unsubscribe();uncoordinate();};
  },[session]);
  return <Auth.Provider value={{token,ready,signIn:next=>session.signIn(next),signOut:all=>session.signOut(all),
    changePassword:(current,next)=>session.changePassword(current,next),expireSession:expected=>session.expire(expected)}}>{children}</Auth.Provider>;
}
export function useAuth(){const value=useContext(Auth);if(!value)throw new Error('Missing AuthProvider');return value;}
