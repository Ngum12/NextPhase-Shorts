import {validAudioTiming,type AudioTiming} from './audioTiming';
import {api, authenticatedFetch, BASE, extract} from './api';

export const englishReviewVisible = process.env.EXPO_PUBLIC_ENGLISH_REVIEW === 'true';
export type ReviewWord = {text:string; start_ms:number; end_ms:number; confidence:number|null};
export type TranscriptReview = {
  schema_version:'transcript-review-1'; source_sha256:string; transcript_sha256:string;
  acknowledged_original_recording:true; sentence_end_words:number[];
  confirmed_low_confidence_words:number[];
};
export type ClipCandidate = {
  first_word:number; last_word:number; source_start_ms:number; source_end_ms:number;
  output_frames:number;
};
export type EnglishAnalysis = {
  job_id:string; revision:string; transcript_sha256:string; render_enabled:false;
  queued_preview_supported?:boolean;
  clean_captions_supported?:boolean;
  portrait_framing_supported?:boolean;
  polished_preview_supported?:boolean;
  audio_timing?:AudioTiming|null;
  transcript:{language:'en'; source_sha256:string; source_duration_ms:number; words:ReviewWord[]};
  review:TranscriptReview|null;
  proposal:{algorithm?:string; requested_seconds:number; candidates:ClipCandidate[]; warnings:string[]};
};

function validated(value:any):EnglishAnalysis {
  const digest=(v:unknown)=>typeof v==='string' && /^[0-9a-f]{64}$/.test(v);
  const words=value?.transcript?.words, candidates=value?.proposal?.candidates;
  const duration=value?.transcript?.source_duration_ms,cap=value?.proposal?.requested_seconds;
  if (!digest(value?.revision) || !digest(value?.transcript_sha256) ||
      !digest(value?.transcript?.source_sha256) || value?.transcript?.language!=='en' ||
      !Number.isInteger(duration) || duration<1 || duration>600000 ||
      !Number.isInteger(cap) || cap<5 || cap>60 ||
      value?.render_enabled!==false || !Array.isArray(words) || !words.length || words.length>1000 ||
      (value.queued_preview_supported!==undefined && typeof value.queued_preview_supported!=='boolean') ||
      (value.clean_captions_supported!==undefined && typeof value.clean_captions_supported!=='boolean') ||
      (value.portrait_framing_supported!==undefined && typeof value.portrait_framing_supported!=='boolean') ||
      (value.polished_preview_supported!==undefined && typeof value.polished_preview_supported!=='boolean') ||
      words.some((w:any,i:number)=>typeof w?.text!=='string' || !w.text.length || w.text.length>160 ||
        !Number.isInteger(w.start_ms) || !Number.isInteger(w.end_ms) || w.end_ms<=w.start_ms ||
        w.start_ms<0 || w.end_ms>duration || (i>0 && w.start_ms<words[i-1].end_ms) ||
        !(w.confidence===null || (typeof w.confidence==='number' && w.confidence>=0 && w.confidence<=1))) ||
      !Array.isArray(candidates) || candidates.length>5 || candidates.some((c:any)=>
        !Number.isInteger(c?.first_word) || !Number.isInteger(c.last_word) ||
        c.first_word<0 || c.last_word<c.first_word || c.last_word>=words.length ||
        !Number.isInteger(c.output_frames) || c.output_frames<150 || c.output_frames>cap*30 ||
        !Number.isInteger(c.source_start_ms) || !Number.isInteger(c.source_end_ms) ||
        c.source_start_ms<0 || c.source_end_ms<=c.source_start_ms || c.source_end_ms>duration ||
        c.source_end_ms-c.source_start_ms>cap*1000 ||
        c.output_frames!==Math.floor((c.source_end_ms-c.source_start_ms)*30/1000))) {
    throw new Error('The review could not be loaded. Refresh and try again.');
  }
  if(value.audio_timing!=null&&!validAudioTiming(value.audio_timing,value.transcript.source_sha256,duration))
    throw new Error('Audio timing could not be verified. Refresh and try again.');
  if(value.review!==null) {
    const review=value.review;
    if(review?.schema_version!=='transcript-review-1' ||
        review.source_sha256!==value.transcript.source_sha256 ||
        review.transcript_sha256!==value.transcript_sha256 ||
        review.acknowledged_original_recording!==true ||
        [review.sentence_end_words,review.confirmed_low_confidence_words].some(list=>
          !Array.isArray(list) || list.length>words.length || list.some((n:any,i:number)=>
            !Number.isInteger(n) || n<1 || n>words.length || (i>0 && n<=list[i-1]))) ||
        review.confirmed_low_confidence_words.some((n:number)=>
          words[n-1].confidence===null || words[n-1].confidence>=.45)) {
      throw new Error('The saved review could not be loaded. Refresh and try again.');
    }
  }
  return value as EnglishAnalysis;
}

export async function getEnglishAnalysis(id:string,token:string):Promise<EnglishAnalysis> {
  const value=validated(await api(`/api/v1/jobs/${encodeURIComponent(id)}/analysis`,token));
  if(value.job_id!==id)throw new Error('This review belongs to a different project.');
  return value;
}

export async function saveEnglishReview(id:string,token:string,revision:string,review:TranscriptReview):Promise<EnglishAnalysis> {
  const result=await authenticatedFetch(token,`${BASE}/api/v1/jobs/${encodeURIComponent(id)}/analysis/review`,{
    method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision,review}),
  });
  const value=validated(await extract(result));
  if(value.job_id!==id)throw new Error('This review belongs to a different project.');
  return value;
}
