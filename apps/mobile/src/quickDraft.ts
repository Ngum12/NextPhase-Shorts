/** One-action private preview from the highest-ranked *reviewed* English clip.
 *
 * The server already chooses the technical order. Never classify a clip as
 * semantically good or publish it; only render an owner-approved draft.
 */
import {ApiError,api,Job} from './api';
import {getEnglishAnalysis} from './analysis';
import {defaultPolish,getCaptionDraft,loadPolishPreset,PolishOptions,requestPolishedPreview} from './polish';

export type QuickDraftPlan={
  revision:string;
  candidate:1;
  duration_ms:number;
  options:PolishOptions;
  title:string;
  notice:string|null;
};
export type QuickDraftResult={needsReview:true}|{needsReview:false;plan:QuickDraftPlan};

export async function prepareQuickDraft(id:string,token:string):Promise<QuickDraftResult>{
  const analysis=await getEnglishAnalysis(id,token); // validated + owner scoped
  if(analysis.polished_preview_supported!==true)
    throw Error('The server does not support polished previews. Use Review English clips instead.');
  if(!analysis.review||!analysis.proposal.candidates.length)
    return {needsReview:true};
  // Candidates are already scored and ranked by the reviewed server plan.
  const best=analysis.proposal.candidates[0];
  const person=await api<{id:string}>('/api/v1/me',token);
  const saved=await loadPolishPreset(person.id);
  const options:PolishOptions={...defaultPolish,...(saved||{})};
  // Closed fallback choices avoid sending new settings to older servers.
  if(analysis.portrait_framing_supported!==true)options.framing='fit';
  else if(analysis.manual_crop_focus_supported!==true&&
    ['fill-left','fill-right'].includes(options.framing))options.framing='fill-center';
  if(analysis.soft_audio_edges_supported!==true)options.audio_edges='original';
  let notice:string|null=null;
  if(analysis.clean_captions_supported!==true) {
    options.captions=false;
    notice='This server cannot add clean captions to the draft.';
  }else if(options.captions) {
    // Preflight only. The backend builds the exact immutable caption cues.
    // 422 is a genuine caption layout limit, not a transient network problem.
    try{await getCaptionDraft(id,token,analysis.revision,1);}
    catch(e){
      if(!(e instanceof ApiError&&e.status===422))throw e;
      options.captions=false;
      notice='Captions do not fit this clip layout. The draft will use original video without captions.';
    }
  }
  return {needsReview:false,plan:{
    revision:analysis.revision,candidate:1,
    duration_ms:Math.floor(best.output_frames*1000/30),
    options,
    title:`Top reviewed clip · ${(best.output_frames/30).toFixed(1)} seconds`,
    notice,
  }};
}

export async function renderQuickDraft(id:string,token:string,plan:QuickDraftPlan):Promise<Job>{
  // The existing API preserves idempotency and checks the review revision.
  // A second tap/retry uses the same stable intent key.
  return requestPolishedPreview(id,token,plan.revision,plan.candidate,
    plan.options,null,plan.duration_ms,false);
}
