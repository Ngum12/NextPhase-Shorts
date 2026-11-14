/** Owner-confirmed preview from one of up to three already-reviewed ranked clips.
 *
 * Candidate order is technical, not semantic. Listing options never queues
 * renders or stores transcript text. Preflight only the user's selected option
 * to conserve mobile requests, storage and cloud compute.
 */
import {ApiError,api,Job} from './api';
import {getEnglishAnalysis,type EnglishAnalysis} from './analysis';
import {defaultPolish,getCaptionDraft,loadPolishPreset,PolishOptions,requestPolishedPreview} from './polish';

export type QuickDraftChoice={
  revision:string;
  candidate:number;
  duration_ms:number;
  source_start_ms:number;
  source_end_ms:number;
  title:string;
  opening:string|null;
  ending:string|null;
  context_warning:string|null;
  boundary_cues:string[];
};
export type QuickDraftPlan=QuickDraftChoice & {
  options:PolishOptions;
  notice:string|null;
};
export type QuickDraftChoices={needsReview:true}|{needsReview:false;choices:QuickDraftChoice[]};
export type QuickDraftResult={needsReview:true}|{needsReview:false;plan:QuickDraftPlan};


// Read-only, bounded snippets from the owner's verified transcript. Never write
// them to a preview intent, cloud log, or analytics event.
function phrase(words:EnglishAnalysis['transcript']['words'],first:number,last:number):string|null{
  if(!Number.isInteger(first)||!Number.isInteger(last)||first<0||last<first||last>words.length)
    return null;
  const plain=words.slice(first,last).map(w=>w.text.replace(/[\x00-\x1f\x7f]/g,' ').trim()).filter(Boolean).join(' ');
  if(!plain)return null;
  const characters=Array.from(plain);
  return characters.length>96?characters.slice(0,95).join('')+'…':plain;
}

function technicalBoundaryCues(analysis:EnglishAnalysis,start:number,end:number):string[]{
  const cues:string[]=[];
  const audio=analysis.audio_timing;
  if(audio){
    // PCM energy is a hint, not a verified silence or a transcript cut.
    const nearQuiet=(at:number)=>audio.quiet_intervals.some(interval=>
      interval.start_ms<=at+250&&interval.end_ms>=at-250);
    if(nearQuiet(start))cues.push('Low-volume audio near opening cut — verify playback.');
    if(nearQuiet(end))cues.push('Low-volume audio near ending cut — verify playback.');
  }
  const visual=analysis.scene_analysis;
  if(visual?.status==='available'){
    const nearChange=(at:number)=>visual.changes.some(change=>
      Math.abs(change.at_ms-at)<=750);
    if(nearChange(start))cues.push('Possible visual change near opening cut.');
    if(nearChange(end))cues.push('Possible visual change near ending cut.');
    if(end>visual.analyzed_duration_ms)
      cues.push('Visual samples do not cover this clip’s full ending.');
  }
  return cues.slice(0,4); // fixed-size, local-only evidence
}

function choiceFrom(analysis:EnglishAnalysis,index:number):QuickDraftChoice{
  const best=analysis.proposal.candidates[index];
  const words=analysis.transcript?.words||[];
  const first=best.first_word,last=best.last_word;
  const complete=Number.isInteger(first)&&Number.isInteger(last)&&first>=0&&last>=first&&last<words.length;
  const firstWord=complete?words[first].text.toLowerCase().replace(/^[^a-z]+|[^a-z]+$/g,''):'';
  const contextWarning=['but','however','therefore','so','this','that','these','those',
    'it','they','he','she','because'].includes(firstWord);
  return {
    revision:analysis.revision,candidate:index+1,
    duration_ms:Math.floor(best.output_frames*1000/30),
    source_start_ms:best.source_start_ms,source_end_ms:best.source_end_ms,
    title:`Option ${index+1} · ${(best.output_frames/30).toFixed(1)}s · source ${(best.source_start_ms/1000).toFixed(1)}s–${(best.source_end_ms/1000).toFixed(1)}s`,
    opening:complete?phrase(words,first,Math.min(last+1,first+8)):null,
    ending:complete&&last-first>=8?phrase(words,Math.max(first+8,last-7),last+1):null,
    context_warning:contextWarning?
      'The opening may depend on earlier speech. Listen to the source before choosing.':null,
    boundary_cues:technicalBoundaryCues(analysis,best.source_start_ms,best.source_end_ms),
  };
}

/** This is an option list, not a request for 3 render jobs. */
export async function listQuickDrafts(id:string,token:string):Promise<QuickDraftChoices>{
  const analysis=await getEnglishAnalysis(id,token); // already owner- and source-validated
  if(analysis.polished_preview_supported!==true)
    throw Error('The server does not support polished previews. Use Review English clips instead.');
  if(!analysis.review||!analysis.proposal.candidates.length)return {needsReview:true};
  const choices=analysis.proposal.candidates.slice(0,3).map((_,index)=>choiceFrom(analysis,index));
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
  return {needsReview:false,plan:{...choiceFrom(analysis,candidate-1),options,notice}};
}

export async function renderQuickDraft(id:string,token:string,plan:QuickDraftPlan):Promise<Job>{
  // The existing API still checks review revision and idempotency; no batch jobs.
  return requestPolishedPreview(id,token,plan.revision,plan.candidate,
    plan.options,null,plan.duration_ms,false);
}
