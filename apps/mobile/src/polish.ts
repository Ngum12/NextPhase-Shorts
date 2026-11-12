import * as SecureStore from 'expo-secure-store';
import {digestStringAsync,CryptoDigestAlgorithm,randomUUID} from 'expo-crypto';
import {api,authenticatedFetch,BASE,extract,Job,ApiError} from './api';

export type Cue={text:string;start_ms:number;end_ms:number};
export type PolishOptions={framing:'fit'|'fill-center';captions:boolean;
  caption_size:'standard'|'large';caption_color:'white'|'yellow';
  caption_position:'lower'|'middle';voice:'original'|'level'};
export const defaultPolish:PolishOptions={framing:'fit',captions:true,caption_size:'standard',
  caption_color:'white',caption_position:'lower',voice:'original'};
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const hash=/^[0-9a-f]{64}$/;
const pending=new Map<string,Promise<Job>>(),writes=new Map<string,Promise<unknown>>();
async function serial<T>(key:string,fn:()=>Promise<T>):Promise<T>{
  const next=(writes.get(key)||Promise.resolve()).catch(()=>{}).then(fn);writes.set(key,next);
  try{return await next;}finally{if(writes.get(key)===next)writes.delete(key);}
}
export function validateOptions(value:any):PolishOptions{
  if(!value||Object.keys(value).sort().join(',')!==Object.keys(defaultPolish).sort().join(',')||
    !['fit','fill-center'].includes(value.framing)||typeof value.captions!=='boolean'||
    !['standard','large'].includes(value.caption_size)||!['white','yellow'].includes(value.caption_color)||
    !['lower','middle'].includes(value.caption_position)||!['original','level'].includes(value.voice))
    throw Error('Choose valid appearance and voice settings.');
  return {...value};
}
export function wrapCaption(text:string):string{
  const words=text.trim().split(/\s+/u);const lines:string[]=[];let line='';
  for(const word of words){
    let chars=Array.from(word);
    if(line&&Array.from(line).length+1+chars.length<=26){line+=' '+word;continue;}
    if(line){lines.push(line);line='';}
    while(chars.length>26){lines.push(chars.slice(0,26).join(''));chars=chars.slice(26);}
    line=chars.join('');
  }
  if(line)lines.push(line);
  if(!lines.length||lines.length>2||/[\x00-\x08\x0b-\x1f\x7f]/.test(text))
    throw Error('Keep each caption to two lines of up to 26 characters.');
  return lines.join('\n');
}
export function validateCues(cues:Cue[],duration:number):Cue[]{
  if(!Number.isInteger(duration)||duration<1||duration>60000||!Array.isArray(cues)||!cues.length||cues.length>80)
    throw Error('Caption draft is unavailable. Refresh the clip.');
  let cursor=0;
  return cues.map(cue=>{
    if(!cue||typeof cue.text!=='string'||Array.from(cue.text).length>160||
      !Number.isInteger(cue.start_ms)||!Number.isInteger(cue.end_ms)||
      cue.start_ms<cursor||cue.end_ms<=cue.start_ms||cue.end_ms>duration)
      throw Error('Caption times must be ordered, non-overlapping and inside the clip.');
    cursor=cue.end_ms;return {text:wrapCaption(cue.text),start_ms:cue.start_ms,end_ms:cue.end_ms};
  });
}
export function captionMilliseconds(text:string):number{
  const value=text.trim().replace(',','.');
  if(!/^(?:\d{1,2}(?:\.\d{0,3})?|\.\d{1,3})$/.test(value))
    throw Error('Enter caption times in seconds, such as 1.250.');
  const ms=Math.round(Number(value)*1000);
  if(ms>60000)throw Error('Caption times must stay inside the clip.');
  return ms;
}
export async function getCaptionDraft(id:string,token:string,revision:string,candidate:number){
  if(!uuid.test(id)||!hash.test(revision)||!Number.isInteger(candidate)||candidate<1||candidate>5)
    throw Error('Refresh and select a clip.');
  const result=await api<any>(`/api/v1/jobs/${id}/analysis/captions?revision=${revision}&candidate_number=${candidate}`,token);
  if(result.job_id!==id||result.revision!==revision||result.candidate_number!==candidate)
    throw Error('This caption draft belongs to another clip.');
  return {duration_ms:result.duration_ms,cues:validateCues(result.cues,result.duration_ms)};
}
export async function savePolishPreset(owner:string,options:PolishOptions){
  if(!uuid.test(owner))throw Error('Sign in again before saving your preset.');
  await SecureStore.setItemAsync(`nextphase.polish.preset.${owner}`,JSON.stringify(validateOptions(options)));
}
export async function loadPolishPreset(owner:string):Promise<PolishOptions|null>{
  if(!uuid.test(owner))throw Error('Sign in again before loading your preset.');
  const raw=await SecureStore.getItemAsync(`nextphase.polish.preset.${owner}`);
  if(!raw)return null;
  if(raw.length>512)throw Error('Saved preset is invalid. Save a new one.');
  try{return validateOptions(JSON.parse(raw));}catch{throw Error('Saved preset is invalid. Save a new one.');}
}
type Intent={fingerprint:string;key:string};
async function intents(name:string):Promise<Intent[]>{
  const raw=await SecureStore.getItemAsync(name);if(!raw||raw.length>2048)return [];
  try{const value=JSON.parse(raw);
    if(!Array.isArray(value)||value.length>5||value.some(i=>!hash.test(i.fingerprint)||!uuid.test(i.key)))return [];
    return value;
  }catch{return [];}
}
export async function requestPolishedPreview(id:string,token:string,revision:string,candidate:number,
  options:PolishOptions,edits:Cue[]|null,duration:number,acknowledgedEdits:boolean):Promise<Job>{
  if(!uuid.test(id)||!hash.test(revision)||!Number.isInteger(candidate)||candidate<1||candidate>5)
    throw Error('Refresh the review before rendering.');
  const chosen=validateOptions(options);
  if(edits!==null&&(!chosen.captions||acknowledgedEdits!==true))throw Error('Compare caption edits with the recording and confirm them.');
  const body={revision,candidate_number:candidate,acknowledged_preview:true,
    caption_style:chosen.captions?'clean-1':'none',framing:chosen.framing,
    polish:{caption_size:chosen.caption_size,caption_color:chosen.caption_color,
      caption_position:chosen.caption_position,voice:chosen.voice},
    ...(edits!==null?{caption_edits:validateCues(edits,duration),acknowledged_caption_edits:true}:{})};
  const fingerprint=await digestStringAsync(CryptoDigestAlgorithm.SHA256,JSON.stringify(body));
  const scope=`${token}:${id}:${fingerprint}`,name=`nextphase.polish.intent.${id}`;
  const existing=pending.get(scope);if(existing)return existing;
  const task=(async()=>{
    const key=await serial(name,async()=>{
      const old=await intents(name);const known=old.find(i=>i.fingerprint===fingerprint);
      if(known)return known.key;
      const key=randomUUID();await SecureStore.setItemAsync(name,JSON.stringify([...old,{fingerprint,key}].slice(-5)));return key;
    });
    const response=await authenticatedFetch(token,`${BASE}/api/v1/jobs/${id}/analysis/previews`,{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,idempotency_key:key})});
    if(response.status===410){await serial(name,async()=>{
      await SecureStore.setItemAsync(name,JSON.stringify((await intents(name)).filter(i=>i.key!==key)));});
      throw new ApiError(410,'That preview was deleted. Tap Render again for a new one.');}
    const result=await extract(response);
    if(!uuid.test(result.id)||result.preview_parent_id!==id||!['queued','processing','succeeded','failed','cancelled'].includes(result.status))
      throw Error('Preview confirmation was invalid. Retry the same settings.');
    return result;
  })();
  pending.set(scope,task);try{return await task;}finally{if(pending.get(scope)===task)pending.delete(scope);}
}
export async function forgetPolishIntents(id:string){
  if(uuid.test(id))await serial(`nextphase.polish.intent.${id}`,()=>SecureStore.deleteItemAsync(`nextphase.polish.intent.${id}`));
}
