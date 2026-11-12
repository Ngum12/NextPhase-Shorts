import {RIGHTS_VERSION} from './uploadRights';
import { prepareToken, recoverToken } from './authEvents';
import {validPair, TokenPair} from './refreshSession';
export const BASE = (process.env.EXPO_PUBLIC_API_URL || 'http://10.0.2.2:8000').replace(/\/$/, '');

export type ShortStyle = { id: string; name: string; description: string; available: boolean };
export type Job = {
  id: string; title: string; status: string; style: string;
  desired_seconds: number; source_duration_seconds: number;
  output_duration_seconds: number | null; error_code: string | null;
  created_at: string; finished_at: string | null; attempt_count: number;
  preview_parent_id?: string|null; operation?: 'render'|'preview'|'analysis';
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function extract(res: Response) {
  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const message = typeof json.detail === 'string' ? json.detail : 'Request failed. Please retry.';
    throw new ApiError(res.status, message);
  }
  return json;
}

export async function login(email: string, password: string, register = false): Promise<TokenPair|string> {
  const response = await fetch(`${BASE}/api/v1/auth/${register ? 'register' : 'login'}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: email.trim(), password }),
  });
  const body = await extract(response);
  if(validPair(body))return body;
  if(typeof body.access_token==='string'&&!body.refresh_token)return body.access_token;
  throw new Error('Invalid session response. Try again.');
}

export async function refreshSession(refresh_token:string,rotation_key:string):Promise<TokenPair> {
  const body=await extract(await fetch(`${BASE}/api/v1/auth/refresh`,{method:'POST',credentials:'omit',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({refresh_token,rotation_key})}));
  if(!validPair(body))throw new Error('Invalid session response. Try again.');return body;
}
export async function revokeRefreshSession(refresh_token:string):Promise<void> {
  const response=await fetch(`${BASE}/api/v1/auth/refresh/logout`,{method:'POST',credentials:'omit',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({refresh_token})});
  if(response.status!==204)await extract(response);
}

export async function authenticatedFetch(token:string, url:string, init:RequestInit={}) {
  if(!url.startsWith(BASE+'/'))throw new Error('Authenticated requests must stay on the API origin.');
  const actual=await prepareToken(token);
  const headers=new Headers(init.headers);headers.set('Authorization',`Bearer ${actual}`);
  let response=await fetch(url,{...init,headers});
  if(response.status===401) {
    const next=await recoverToken(actual);
    // Do not automatically replay writes or native multipart streams.
    if(next&&['GET','HEAD'].includes((init.method||'GET').toUpperCase())) {
      headers.set('Authorization',`Bearer ${next}`);response=await fetch(url,{...init,headers});
    }
  }
  return response;
}
export async function logoutSession(token:string, all=false) {
  const response=await authenticatedFetch(token,`${BASE}/api/v1/auth/${all?'logout-all':'logout'}`,{method:'POST'});
  // A 401 can have renewed this family's access without executing logout-all.
  // Require server confirmation; do not clear storage and claim all devices left.
  if(response.status!==204)await extract(response);
}
export async function changePassword(token:string,current:string,next:string) {
  const response=await authenticatedFetch(token,`${BASE}/api/v1/auth/password`,{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:current,new_password:next})});
  if(response.status!==204)await extract(response);
}

export async function api<T>(path: string, token: string): Promise<T> {
  return extract(await authenticatedFetch(token,`${BASE}${path}`, { headers: { Authorization: `Bearer ${token}` } })) as Promise<T>;
}

export async function getStyles(): Promise<ShortStyle[]> {
  return extract(await fetch(`${BASE}/api/v1/styles`)) as Promise<ShortStyle[]>;
}

export async function uploadVideo(token: string, selected: { uri: string; name: string; mimeType?: string },
                                  style: string, title: string, seconds: number, idempotencyKey: string, rightsConfirmed=false): Promise<Job> {
  if(rightsConfirmed!==true)throw new Error('Confirm upload rights and server processing first.');
  const form = new FormData();
  form.append('file', { uri: selected.uri, name: selected.name, type: selected.mimeType || 'video/mp4' } as any);
  form.append('rights_confirmed','true');form.append('consent_version',RIGHTS_VERSION);
  form.append('style', style);
  form.append('title', title);
  form.append('desired_seconds', String(seconds));
  // Do not manually set multipart Content-Type; React Native supplies the boundary.
  return extract(await authenticatedFetch(token,`${BASE}/api/v1/jobs`, {
    method: 'POST', headers: { Authorization: `Bearer ${token}`, 'Idempotency-Key': idempotencyKey }, body: form,
  })) as Promise<Job>;
}

export function downloadUrl(id: string) { return `${BASE}/api/v1/jobs/${encodeURIComponent(id)}/download`; }

export async function cancelJob(id: string, token: string): Promise<Job> {
  return extract(await authenticatedFetch(token,`${BASE}/api/v1/jobs/${encodeURIComponent(id)}/cancel`, {
    method: 'POST', headers: { Authorization: `Bearer ${token}` },
  })) as Promise<Job>;
}

export async function deleteJob(id:string,token:string):Promise<void> {
  const response=await authenticatedFetch(token,`${BASE}/api/v1/jobs/${encodeURIComponent(id)}`,{method:'DELETE'});
  const body=await extract(response);
  if(response.status!==202||body.status!=='deleted')throw new Error('Deletion was not confirmed. Please retry.');
}

export async function requestAccountDeletion(token:string,password:string,key:string) {
  const response=await authenticatedFetch(token,`${BASE}/api/v1/account/delete`,{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password:password,receipt_key:key})});
  const body=await extract(response);
  if(response.status!==202||body.status!=='account_disabled')throw new Error('Account deletion was not confirmed');
  return body;
}
export async function accountDeletionReceipt(key:string) {
  // Recovery does not use a login token and must never expire a newer session.
  return extract(await fetch(`${BASE}/api/v1/account/deletion-receipt`,{method:'POST',credentials:'omit',
    headers:{'Content-Type':'application/json'},body:JSON.stringify({receipt_key:key})}));
}
