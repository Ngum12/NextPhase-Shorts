import {api,ApiError,authenticatedFetch,BASE,extract,Job} from './api';
export type EnglishState={source_id:string;ready:boolean;eligible:boolean;requested:boolean;task:Job|null};
export async function englishCapability(token:string):Promise<{available:boolean;automatic_clips?:boolean;gemini_planning_available?:boolean;documentary_available?:boolean}> {
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


export async function createDocumentary(id:string,token:string,approved:boolean):Promise<Job> {
  if(approved!==true)throw Error('Confirm transcript sharing and public research first.');
  const job=await extract(await authenticatedFetch(token,`${BASE}/api/v1/jobs/${encodeURIComponent(id)}/analysis/documentary`,{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
      consent_version:'documentary-research-v1',acknowledged_google_transcript_sharing:true,acknowledged_public_research:true}),
  }));
  if(!job.id||job.preview_parent_id!==id||job.documentary!==true)throw Error('Documentary confirmation was invalid. Retry the same project.');
  return job;
}

const documentaryFailures:Record<string,string>={
  DOCUMENTARY_RESEARCH_UNAVAILABLE:'Public research could not be reached. Your original recording is preserved.',
  DOCUMENTARY_RIGHTS_UNCONFIRMED:'No suitable public-domain or CC0 photographs passed the documentary checks. Your original recording is preserved.',
  DOCUMENTARY_PLAN_INVALID:'Gemini could not complete a valid, relevant visual plan, or an interrupted call was stopped from repeating. Your original recording is preserved.',
  DOCUMENTARY_CONSENT_REQUIRED:'Documentary processing was stopped because its configuration or operator controls changed. Your original recording is preserved.',
  DOCUMENTARY_DOWNLOAD_REJECTED:'An external photograph exceeded its download checks. Your original recording is preserved.',
  DOCUMENTARY_ASSET_UNSUPPORTED:'A researched photograph did not pass safe media inspection. Your original recording is preserved.',
  DOCUMENTARY_SOURCE_INVALID:'The source identity could not be verified. Your original recording is preserved.',
  DOCUMENTARY_RENDER_FAILED:'The documentary could not complete its render checks. Your original recording is preserved.',
};
export function documentaryFailure(code:string):string|null {
  return Object.hasOwn(documentaryFailures,code)?documentaryFailures[code]:null;
}
