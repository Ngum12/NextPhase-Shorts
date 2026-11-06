import { File } from 'expo-file-system';
import * as FileSystem from 'expo-file-system/legacy';
import * as Crypto from 'expo-crypto';
import { api, ApiError, Job, BASE, extract, authenticatedFetch } from './api';

export type PendingUpload = {
  version: 1; revision: number; ownerId: string; key: string; localName: string;
  fileName: string; totalBytes: number; title: string; style: string; seconds: number;
  sessionId?: string;
};
type Session = {
  id: string; status: string; total_bytes: number; received_bytes: number;
  chunk_bytes: number; job_id: string|null;
};
const MAX_BYTES = 314572800;
function root() {
  if(!FileSystem.documentDirectory)throw new Error('Private app storage is unavailable');
  return FileSystem.documentDirectory+'nextphase-uploads/';
}
function slot(ownerId:string, number:number) {
  if(!/^[a-zA-Z0-9-]{1,64}$/.test(ownerId))throw new Error('Invalid account identifier');
  return root()+ownerId+`-${number}.json`;
}
function valid(value:any, ownerId:string): value is PendingUpload {
  return value?.version===1 && value.ownerId===ownerId && Number.isSafeInteger(value.revision) &&
    value.revision>0 && /^[a-f0-9-]{36}\.(mp4|mov|webm|m4v)$/i.test(value.localName) &&
    typeof value.key==='string' && /^[a-f0-9-]{36}$/i.test(value.key) &&
    Number.isSafeInteger(value.totalBytes) && value.totalBytes>0 && value.totalBytes<=MAX_BYTES &&
    typeof value.fileName==='string' && typeof value.title==='string' && typeof value.style==='string' &&
    Number.isInteger(value.seconds) && value.seconds>=5 && value.seconds<=60 &&
    (value.sessionId===undefined || /^[a-f0-9-]{36}$/i.test(value.sessionId));
}
export async function loadPending(ownerId:string):Promise<PendingUpload|null> {
  const records:PendingUpload[]=[];
  let exists=false;
  for(const index of [0,1]) {
    const path=slot(ownerId,index);
    if((await FileSystem.getInfoAsync(path)).exists) {
      exists=true;
      try {
        const value=JSON.parse(await FileSystem.readAsStringAsync(path));
        if(valid(value,ownerId))records.push(value);
      } catch { /* The other journal slot can recover an interrupted metadata write. */ }
    }
  }
  if(exists&&!records.length)throw new Error('Saved upload metadata is damaged. Keep app data and contact support.');
  return records.sort((a,b)=>b.revision-a.revision)[0]||null;
}
async function savePending(record:PendingUpload):Promise<PendingUpload> {
  await FileSystem.makeDirectoryAsync(root(),{intermediates:true});
  const previous=await loadPending(record.ownerId);
  const next={...record,revision:(previous?.revision||0)+1};
  // Alternating journal slots retain the previous valid intent if a write is interrupted.
  await FileSystem.writeAsStringAsync(slot(record.ownerId,next.revision%2),JSON.stringify(next));
  return next;
}
async function clearPending(record:PendingUpload) {
  // Keep the intent until local cleanup succeeds. If metadata cleanup fails after
  // deleting the copy, completed/aborted server state still makes retry safe.
  await FileSystem.deleteAsync(root()+record.localName,{idempotent:true});
  for(const index of [0,1])await FileSystem.deleteAsync(slot(record.ownerId,index),{idempotent:true});
}
async function prepareUploadImpl(ownerId:string, selected:{uri:string;name:string},
    title:string,style:string,seconds:number):Promise<PendingUpload> {
  if(await loadPending(ownerId))throw new Error('Resume or discard your pending upload first');
  const extension=selected.name.match(/\.(mp4|mov|webm|m4v)$/i)?.[0].toLowerCase();
  if(!extension)throw new Error('Choose MP4, MOV, M4V or WebM');
  await FileSystem.makeDirectoryAsync(root(),{intermediates:true});
  const localName=Crypto.randomUUID()+extension;
  const localUri=root()+localName;
  try {
    await FileSystem.copyAsync({from:selected.uri,to:localUri});
    const totalBytes=new File(localUri).size;
    if(!Number.isSafeInteger(totalBytes)||totalBytes<=0||totalBytes>MAX_BYTES)
      throw new Error('Video must be nonempty and no larger than 300 MiB');
    return await savePending({version:1,revision:0,ownerId,key:Crypto.randomUUID(),localName,
      fileName:selected.name,totalBytes,title:title.trim(),style,seconds});
  } catch(error) {
    await FileSystem.deleteAsync(localUri,{idempotent:true});
    throw error;
  }
}
async function requestSession(record:PendingUpload,token:string,signal?:AbortSignal):Promise<Session> {
  return extract(await authenticatedFetch(token,`${BASE}/api/v1/upload-sessions`,{
    method:'POST',signal,headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/json','Idempotency-Key':record.key},
    body:JSON.stringify({file_name:record.fileName,total_bytes:record.totalBytes,title:record.title,
      style:record.style,desired_seconds:record.seconds}),
  })) as Promise<Session>;
}
function paused(signal?:AbortSignal) {
  if(signal?.aborted)throw new Error('Upload paused');
}
async function resumeUploadImpl(record:PendingUpload,token:string,onProgress:(sent:number,total:number)=>void,
    signal?:AbortSignal):Promise<Job> {
  paused(signal);
  if(!record.sessionId) {
    const created=await requestSession(record,token,signal);
    record=await savePending({...record,sessionId:created.id});
  }
  let session=await extract(await authenticatedFetch(token,`${BASE}/api/v1/upload-sessions/${record.sessionId}`,{
    signal,headers:{Authorization:`Bearer ${token}`},
  })) as Session;
  if(session.status==='completed'&&session.job_id) {
    const job=await api<Job>(`/api/v1/jobs/${session.job_id}`,token);
    await clearPending(record);return job;
  }
  if(session.status!=='uploading')throw new ApiError(410,'This upload expired or was discarded. Discard it here and start a new upload.');
  if(session.total_bytes!==record.totalBytes||!Number.isSafeInteger(session.chunk_bytes)||
      session.chunk_bytes<1||session.chunk_bytes>8388608)throw new Error('Upload metadata does not match');
  const source=new File(root()+record.localName);
  if(!source.exists||source.size!==record.totalBytes)throw new Error('Saved video is missing or changed. Discard this upload and choose the file again.');
  onProgress(session.received_bytes,record.totalBytes);
  const handle=source.open();
  try {
    while(session.received_bytes<record.totalBytes) {
      paused(signal);
      const offset=session.received_bytes;
      handle.offset=offset;
      const bytes=handle.readBytes(Math.min(session.chunk_bytes,record.totalBytes-offset));
      if(bytes.length!==Math.min(session.chunk_bytes,record.totalBytes-offset))throw new Error('Could not read the next video chunk');
      const digest=await Crypto.digest(Crypto.CryptoDigestAlgorithm.SHA256,bytes);
      const checksum=Array.from(new Uint8Array(digest),n=>n.toString(16).padStart(2,'0')).join('');
      paused(signal);
      session=await extract(await authenticatedFetch(token,`${BASE}/api/v1/upload-sessions/${record.sessionId}/parts?offset=${offset}`,{
        method:'PUT',signal,headers:{Authorization:`Bearer ${token}`,'Content-Type':'application/octet-stream','X-Chunk-SHA256':checksum},
        body:bytes.slice().buffer,
      })) as Session;
      if(session.received_bytes<offset+bytes.length||session.received_bytes>record.totalBytes)
        throw new Error('Server returned invalid upload progress');
      onProgress(session.received_bytes,record.totalBytes);
    }
  } finally {handle.close();}
  paused(signal);
  const job=await extract(await authenticatedFetch(token,`${BASE}/api/v1/upload-sessions/${record.sessionId}/complete`,{
    method:'POST',signal,headers:{Authorization:`Bearer ${token}`},
  })) as Job;
  await clearPending(record);
  return job;
}
async function discardUploadImpl(record:PendingUpload,token:string):Promise<Job|null> {
  // Recover a session whose create response was lost before its ID was saved.
  const session=record.sessionId ? await api<Session>(`/api/v1/upload-sessions/${record.sessionId}`,token)
    : await requestSession(record,token);
  let job:Job|null=null;
  if(session.status==='completed'&&session.job_id)job=await api<Job>(`/api/v1/jobs/${session.job_id}`,token);
  else await extract(await authenticatedFetch(token,`${BASE}/api/v1/upload-sessions/${session.id}/abort`,{
    method:'POST',headers:{Authorization:`Bearer ${token}`},
  }));
  await clearPending(record);
  return job;
}

const actions=new Set<string>();
async function exclusively<T>(ownerId:string,action:()=>Promise<T>):Promise<T> {
  if(actions.has(ownerId))throw new Error('Another upload action is finishing. Please try again.');
  actions.add(ownerId);
  try{return await action();}finally{actions.delete(ownerId);}
}
export const prepareUpload=(...args:Parameters<typeof prepareUploadImpl>)=>exclusively(args[0],()=>prepareUploadImpl(...args));
export const resumeUpload=(...args:Parameters<typeof resumeUploadImpl>)=>exclusively(args[0].ownerId,()=>resumeUploadImpl(...args));
export const discardUpload=(...args:Parameters<typeof discardUploadImpl>)=>exclusively(args[0].ownerId,()=>discardUploadImpl(...args));
