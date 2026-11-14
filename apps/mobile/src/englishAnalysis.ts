import {api,ApiError,authenticatedFetch,BASE,extract,Job} from './api';
export type EnglishState={source_id:string;ready:boolean;eligible:boolean;requested:boolean;task:Job|null};
export async function englishCapability(token:string):Promise<{available:boolean;automatic_clips?:boolean;gemini_planning_available?:boolean}> {
  try{return await api('/api/v1/english-analysis/capabilities',token);}
  catch(e){if(e instanceof ApiError&&e.status===404)return {available:false};throw e;}
}
export const englishState=(id:string,token:string)=>api<EnglishState>(`/api/v1/english-analysis/jobs/${encodeURIComponent(id)}`,token);
export async function startEnglish(id:string,token:string,previous:EnglishState):Promise<EnglishState> {
  const retry=!!previous.task&&['failed','cancelled'].includes(previous.task.status);
  // Stable source/terminal-attempt UUID recovers lost replies after restart.
  const key=retry?previous.task!.id:id;
  return extract(await authenticatedFetch(token,`${BASE}/api/v1/english-analysis/jobs/${encodeURIComponent(id)}`,{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      idempotency_key:key,acknowledged_server_analysis:true,retry_failed:retry}),
  })) as Promise<EnglishState>;
}
export async function cancelEnglish(id:string,token:string):Promise<EnglishState> {
  return extract(await authenticatedFetch(token,`${BASE}/api/v1/english-analysis/jobs/${encodeURIComponent(id)}/cancel`,{method:'POST'})) as Promise<EnglishState>;
}
