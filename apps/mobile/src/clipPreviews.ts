import * as SecureStore from 'expo-secure-store';
import * as FileSystem from 'expo-file-system/legacy';
import {randomUUID} from 'expo-crypto';
import {ApiError,authenticatedFetch,BASE,downloadUrl,extract,Job} from './api';
import {prepareToken,recoverToken} from './authEvents';

const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const digest=/^[0-9a-f]{64}$/;
const pending=new Map<string,Promise<Job>>();
const storageTasks=new Map<string,Promise<unknown>>();
type Intents={revision:string;keys:Record<string,string>};
export type PreviewFraming='fit'|'fill-center';
async function serial<T>(parent:string,action:()=>Promise<T>):Promise<T> {
  const task=(storageTasks.get(parent)||Promise.resolve()).catch(()=>{}).then(action);
  storageTasks.set(parent,task);
  try{return await task;}finally{if(storageTasks.get(parent)===task)storageTasks.delete(parent);}
}
async function readIntents(name:string):Promise<Intents|null> {
  const raw=await SecureStore.getItemAsync(name);
  if(!raw||raw.length>2048)return null;
  try{const value=JSON.parse(raw);
    if(!digest.test(value.revision)||!value.keys||typeof value.keys!=='object'||Array.isArray(value.keys)||
        Object.keys(value.keys).length>20||Object.entries(value.keys).some(([k,v])=>!(/^[1-5](?:-clean-1)?(?:-fill-center)?$/).test(k)||typeof v!=='string'||!uuid.test(v)))return null;
    return value as Intents;
  }catch{return null;}
}

export async function requestClipPreview(parent:string,token:string,revision:string,candidate:number,captionStyle:'none'|'clean-1'='none',framing:PreviewFraming='fit'):Promise<Job> {
  if(!uuid.test(parent)||!digest.test(revision)||!Number.isInteger(candidate)||candidate<1||candidate>5||!['none','clean-1'].includes(captionStyle)||!['fit','fill-center'].includes(framing))
    throw new Error('Refresh the review before choosing a clip.');
  const scope=`${token}:${parent}:${revision}:${candidate}:${captionStyle}:${framing}`;
  const option=(captionStyle==='none'?String(candidate):`${candidate}-clean-1`)+(framing==='fit'?'':'-fill-center');
  const existing=pending.get(scope);if(existing)return existing;
  const task=(async()=>{
    // One durable key per reviewed option survives lost responses/app restarts.
    const name=`nextphase.preview.${parent}`;
    const key=await serial(parent,async()=>{
      const old=await readIntents(name);
      const intent:Intents=old?.revision===revision?old:{revision,keys:{}};
      const key=intent.keys[option]||randomUUID();intent.keys[option]=key;
      await SecureStore.setItemAsync(name,JSON.stringify(intent));return key;
    });
    const response=await authenticatedFetch(token,`${BASE}/api/v1/jobs/${parent}/analysis/previews`,{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,
        candidate_number:candidate,idempotency_key:key,acknowledged_preview:true,
        ...(captionStyle==='clean-1'?{caption_style:captionStyle}:{}),
        ...(framing!=='fit'?{framing}:{})}),
    });
    if(response.status===410){await serial(parent,async()=>{
      const intent=await readIntents(name);
      if(intent?.revision===revision&&intent.keys[option]===key){delete intent.keys[option];
        await SecureStore.setItemAsync(name,JSON.stringify(intent));}
    });
      throw new ApiError(410,'This preview was deleted. Tap Render preview again to create another.');}
    const value=await extract(response);
    if(!uuid.test(value.id)||value.preview_parent_id!==parent||
        !['queued','processing','succeeded','failed','cancelled'].includes(value.status))
      throw new Error('Preview confirmation was invalid. Retry the same option.');
    return value as Job;
  })();
  pending.set(scope,task);
  try{return await task;}finally{if(pending.get(scope)===task)pending.delete(scope);}
}

export async function forgetPreviewIntents(parent:string) {
  if(uuid.test(parent))await serial(parent,()=>SecureStore.deleteItemAsync(`nextphase.preview.${parent}`));
}

export async function loadPreviewFile(id:string,token:string):Promise<{uri:string;remove:()=>Promise<void>}> {
  if(!uuid.test(id))throw new Error('Preview is unavailable.');
  const root=FileSystem.cacheDirectory;
  if(!root)throw new Error('Private preview storage is unavailable.');
  const path=root+`nextphase-preview-${id}-${randomUUID()}.mp4`;
  const remove=async()=>{await FileSystem.deleteAsync(path,{idempotent:true});};
  try {
    const actual=await prepareToken(token);
    let response=await FileSystem.downloadAsync(downloadUrl(id),path,{headers:{Authorization:`Bearer ${actual}`}});
    if(response.status===401){const next=await recoverToken(actual);
      if(next)response=await FileSystem.downloadAsync(downloadUrl(id),path,{headers:{Authorization:`Bearer ${next}`}});}
    if(response.status!==200)throw new Error('Preview download failed. Refresh the project and retry.');
    const info=await FileSystem.getInfoAsync(path);
    if(!info.exists||!('size' in info)||info.size<=0||info.size>64*1024*1024)
      throw new Error('Preview file failed validation.');
    return {uri:path,remove};
  }catch(error){await remove().catch(()=>{});throw error;}
}
