/** Owner-confirmed preview from one of up to three already-reviewed ranked clips.
 *
 * Candidate order is technical, not semantic. Listing options never queues
 * renders or stores transcript text. Preflight only the user's selected option
 * to conserve mobile requests, storage and cloud compute.
 */
import {ApiError,api,Job} from './api';
import {getEnglishAnalysis} from './analysis';
import {defaultPolish,getCaptionDraft,loadPolishPreset,PolishOptions,requestPolishedPreview} from './polish';

export type QuickDraftChoice={
  revision:string;
  candidate:number;
  duration_ms:number;
  source_start_ms:number;
  source_end_ms:number;
  title:string;
};
export type QuickDraftPlan=QuickDraftChoice & {
  options:PolishOptions;
  notice:string|null;
};
export type QuickDraftChoices={needsReview:true}|{needsReview:false;choices:QuickDraftChoice[]};
export type QuickDraftResult={needsReview:true}|{needsReview:false;plan:QuickDraftPlan};

/** This is an option list, not a request for 3 render jobs. */
export async function listQuickDrafts(id:string,token:string):Promise<QuickDraftChoices>{
  const analysis=await getEnglishAnalysis(id,token); // already owner- and source-validated
  if(analysis.polished_preview_supported!==true)
    throw Error('The server does not support polished previews. Use Review English clips instead.');
  if(!analysis.review||!analysis.proposal.candidates.length)return {needsReview:true};
  const choices=analysis.proposal.candidates.slice(0,3).map((best,index):QuickDraftChoice=>({
    revision:analysis.revision,
    candidate:index+1,
    duration_ms:Math.floor(best.output_frames*1000/30),
    source_start_ms:best.source_start_ms,
    source_end_ms:best.source_end_ms,
    title:`Option ${index+1} · ${(best.output_frames/30).toFixed(1)}s · source ${(best.source_start_ms/1000).toFixed(1)}s–${(best.source_end_ms/1000).toFixed(1)}s`,
  }));
  return {needsReview:false,choices};
}

/** Runs only after the owner selects one option. */
export async function prepareQuickDraft(id:string,token:string,candidate=1):Promise<QuickDraftResult>{
  if(!Number.isInteger(candidate)||candidate<1||candidate>3)
    throw Error('Choose one of the offered Short drafts.');
  const analysis=await getEnglishAnalysis(id,token);
  if(analysis.polished_preview_supported!==true)
    throw Error('The server does not support polished previews. Use Review English clips instead.');
  if(!analysis.review||!analysis.proposal.candidates.length)return {needsReview:true};
  const best=analysis.proposal.candidates[candidate-1];
  if(!best)throw Error('That clip is no longer available. Refresh your Short choices.');
  const person=await api<{id:string}>('/api/v1/me',token);
  const saved=await loadPolishPreset(person.id);
  const options:PolishOptions={...defaultPolish,...(saved||{})};
  if(analysis.portrait_framing_supported!==true)options.framing='fit';
  else if(analysis.manual_crop_focus_supported!==true&&
    ['fill-left','fill-right'].includes(options.framing))options.framing='fill-center';
  if(analysis.soft_audio_edges_supported!==true)options.audio_edges='original';
  let notice:string|null=null;
  if(analysis.clean_captions_supported!==true){
    options.captions=false;
    notice='This server cannot add clean captions to the draft.';
  }else if(options.captions){
    // Only preflight the chosen clip, never spend capacity rendering alternatives.
    try{await getCaptionDraft(id,token,analysis.revision,candidate);}
    catch(e){
      if(!(e instanceof ApiError&&e.status===422))throw e;
      options.captions=false;
      notice='Captions do not fit this clip layout. The draft will use original video without captions.';
    }
  }
  return {needsReview:false,plan:{
    revision:analysis.revision,
    candidate,
    duration_ms:Math.floor(best.output_frames*1000/30),
    source_start_ms:best.source_start_ms,
    source_end_ms:best.source_end_ms,
    options,
    title:`Option ${candidate} · ${(best.output_frames/30).toFixed(1)}s · source ${(best.source_start_ms/1000).toFixed(1)}s–${(best.source_end_ms/1000).toFixed(1)}s`,
    notice,
  }};
}

export async function renderQuickDraft(id:string,token:string,plan:QuickDraftPlan):Promise<Job>{
  // The existing API still checks review revision and idempotency; no batch jobs.
  return requestPolishedPreview(id,token,plan.revision,plan.candidate,
    plan.options,null,plan.duration_ms,false);
}
