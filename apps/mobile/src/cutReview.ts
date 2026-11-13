/** Conservative, source-bound guidance for reviewing the beginning and end
 * of a proposed short. This does not rank clips or modify any edit boundary.
 * Only analyzed evidence tied to the original recording may create a cue.
 */
import type {EnglishAnalysis} from './analysis';

export type CutCue={type:'visual'|'quiet'|'context'|'coverage';message:string};
export type CutCheckpoint={title:'Opening'|'Ending';atMs:number;cues:CutCue[]};
export type CutReview={
  opening:CutCheckpoint;ending:CutCheckpoint;
  disclosure:string;
};
const NEAR_MS=1000;
const oneDecimal=(ms:number)=>(ms/1000).toFixed(1);
const cue=(type:CutCue['type'],message:string):CutCue=>({type,message});

export function cutReview(data:EnglishAnalysis,index:number):CutReview|null {
  if(!Number.isInteger(index)||index<0||index>=data.proposal.candidates.length)return null;
  const candidate=data.proposal.candidates[index],source=data.transcript;
  const start=candidate.source_start_ms,end=candidate.source_end_ms;
  if(!Number.isInteger(source.source_duration_ms)||source.source_duration_ms<1||
    !Number.isInteger(start)||!Number.isInteger(end)||start<0||end<=start||
    end>source.source_duration_ms)return null;

  const audio=data.audio_timing?.source_sha256===source.source_sha256&&
    data.audio_timing?.source_duration_ms===source.source_duration_ms?
    data.audio_timing:null;
  const scene=data.scene_analysis?.source_sha256===source.source_sha256&&
    data.scene_analysis?.source_duration_ms===source.source_duration_ms?
    data.scene_analysis:null;

  function boundary(title:'Opening'|'Ending',atMs:number):CutCheckpoint {
    const cues:CutCue[]=[];
    if(title==='Opening'&&candidate.first_word>0){
      const opening=source.words[candidate.first_word]?.text?.toLowerCase()
        .replace(/^[^a-z]+|[^a-z]+$/g,'');
      if(['but','however','therefore','so','this','that','these','those',
           'it','they','he','she','because'].includes(opening||'')){
        cues.push(cue('context','The first words may refer to an earlier point. Check that the opening makes sense on its own.'));
      }
    }

    if(audio&&Array.isArray(audio.quiet_intervals)){
      if(atMs>audio.audio_duration_ms) {
        cues.push(cue('coverage','The audio scan did not reach this cut; quiet passages here are unknown.'));
      } else {
        let nearest:{distance:number;start:number;end:number}|null=null;
        for(const interval of audio.quiet_intervals){
          const distance=atMs<interval.start_ms?interval.start_ms-atMs:
            atMs>interval.end_ms?atMs-interval.end_ms:0;
          if(distance<=NEAR_MS&&(!nearest||distance<nearest.distance)){
            nearest={distance,start:interval.start_ms,end:interval.end_ms};
          }
        }
        if(nearest){
          cues.push(cue('quiet',nearest.distance===0?
            'A measured low-volume passage touches this cut. Listen for a smooth transition.':
            `A measured low-volume passage is ${oneDecimal(nearest.distance)}s from this cut. Check the audio transition.`));
        }
      }
    }

    if(scene?.status==='available'&&Array.isArray(scene.changes)){
      if(atMs>scene.analyzed_duration_ms){
        cues.push(cue('coverage','Visual sampling did not reach this cut; changes here are unknown.'));
      }else{
        let nearest:{distance:number;time:number}|null=null;
        for(const item of scene.changes){
          const distance=Math.abs(item.at_ms-atMs);
          if(distance<=NEAR_MS&&(!nearest||distance<nearest.distance||
            (distance===nearest.distance&&item.at_ms<nearest.time))){
            nearest={distance,time:item.at_ms};
          }
        }
        if(nearest) cues.push(cue('visual',
          `A possible sampled visual change is ${oneDecimal(nearest.distance)}s from this cut (source ${oneDecimal(nearest.time)}s). Check it in playback.`));
      }
    }
    return {title,atMs,cues};
  }
  return {
    opening:boundary('Opening',start),
    ending:boundary('Ending',end),
    disclosure:'Guidance is approximate, not a quality score or a suggested new cut. Silence and visual changes may be missed. Always review the original and rendered preview.',
  };
}
