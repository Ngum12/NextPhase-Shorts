import { unauthorized } from './authEvents';
export const BASE = (process.env.EXPO_PUBLIC_API_URL || 'http://10.0.2.2:8000').replace(/\/$/, '');

export type ShortStyle = { id: string; name: string; description: string; available: boolean };
export type Job = {
  id: string; title: string; status: string; style: string;
  desired_seconds: number; source_duration_seconds: number;
  output_duration_seconds: number | null; error_code: string | null;
  created_at: string; finished_at: string | null; attempt_count: number;
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

export async function login(email: string, password: string, register = false): Promise<string> {
  const response = await fetch(`${BASE}/api/v1/auth/${register ? 'register' : 'login'}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: email.trim(), password }),
  });
  const body = await extract(response);
  return body.access_token as string;
}

export async function authenticatedFetch(token:string, url:string, init:RequestInit={}) {
  const headers=new Headers(init.headers);headers.set('Authorization',`Bearer ${token}`);
  const response=await fetch(url,{...init,headers});
  if(response.status===401)unauthorized(token);
  return response;
}
export async function logoutSession(token:string, all=false) {
  const response=await authenticatedFetch(token,`${BASE}/api/v1/auth/${all?'logout-all':'logout'}`,{method:'POST'});
  if(response.status!==204&&response.status!==401)await extract(response);
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
                                  style: string, title: string, seconds: number, idempotencyKey: string): Promise<Job> {
  const form = new FormData();
  form.append('file', { uri: selected.uri, name: selected.name, type: selected.mimeType || 'video/mp4' } as any);
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
