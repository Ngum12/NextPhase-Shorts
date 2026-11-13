/** Review shortcuts only. No automatic transcript, source, or cut approval.
 * These are unverified cues and must be checked against the original recording.
 */
import type {ReviewWord} from './analysis';

export type EndingCue = {wordNumber:number;reason:'punctuation'|'pause'|'last-word'};
const ending=/[.!?]+[)"'\]\u2019\u201d]*$/u;
const abbreviation=/^(?:mr|mrs|ms|dr|prof|sr|jr|vs|etc|e\.g|i\.e)\.$/i;

export function endingCues(words:ReadonlyArray<ReviewWord>):EndingCue[]{
  if(!Array.isArray(words)||!words.length||words.length>1000)return [];
  const result:EndingCue[]=[];
  for(let i=0;i<words.length;i++){
    const word=words[i],next=words[i+1];
    if(!word||typeof word.text!=='string'||!Number.isInteger(word.end_ms)||
       (next&&!Number.isInteger(next.start_ms)))return [];
    const punct=ending.test(word.text)&&!(next&&abbreviation.test(word.text));
    const pause=!!next && next.start_ms-word.end_ms>=900;
    if(punct)result.push({wordNumber:i+1,reason:'punctuation'});
    else if(pause)result.push({wordNumber:i+1,reason:'pause'});
    else if(!next)result.push({wordNumber:i+1,reason:'last-word'});
  }
  return result;
}

export function previewTranscript(words:ReadonlyArray<ReviewWord>,limit=100):string{
  if(!Array.isArray(words)||!words.length)return '';
  const checked=Math.min(Math.max(1,Math.floor(limit)),1000);
  return words.slice(0,checked).map(word=>word.text).join(' ')+(words.length>checked?' …':'');
}
