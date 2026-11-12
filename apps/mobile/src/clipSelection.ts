import type {EnglishAnalysis} from './analysis';
const clip=(text:string,limit:number)=>text.length>limit?text.slice(0,limit-1)+'…':text;
export function clipContext(data:EnglishAnalysis,index:number) {
  const candidate=data.proposal.candidates[index];if(!candidate)return null;
  const words=data.transcript.words;
  const text=(first:number,last:number,limit=160)=>clip(words.slice(first,last).map(w=>w.text).join(' '),limit);
  const overlapOptions=data.proposal.candidates.flatMap((other,i)=>i!==index&&
    Math.min(other.source_end_ms,candidate.source_end_ms)>Math.max(other.source_start_ms,candidate.source_start_ms)?[i+1]:[]);
  const first=words[candidate.first_word]?.text.toLowerCase().replace(/^[^a-z]+|[^a-z]+$/g,'')||'';
  return {
    opening:text(candidate.first_word,Math.min(candidate.last_word+1,candidate.first_word+8),96),
    before:text(Math.max(0,candidate.first_word-8),candidate.first_word),
    after:text(candidate.last_word+1,Math.min(words.length,candidate.last_word+9)),
    contextOpening:['but','however','therefore','so','this','that','these','those','it','they','he','she','because'].includes(first),
    confirmedWords:(data.review?.confirmed_low_confidence_words||[]).filter(n=>n>candidate.first_word&&n<=candidate.last_word+1).length,
    overlapOptions,
  };
}
