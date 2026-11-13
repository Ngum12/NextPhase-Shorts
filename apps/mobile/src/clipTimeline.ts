/** Source-relative, read-only evidence for reviewed clip boundaries.
 * All inputs come from the already validated, owner-scoped English analysis.
 * No timestamps are snapped, scored or sent to the renderer from this module.
 */
import type {ClipCandidate} from './analysis';
import type {AudioTiming} from './audioTiming';
import type {SceneAnalysis} from './sceneAnalysis';

export type TimelineBand = {left:`${number}%`;width:`${number}%`};
export type ClipTimelineData = {
  selection:TimelineBand;
  quiet:TimelineBand[];
  visualTicks:`${number}%`[];
  audioCoverage:`${number}%`|null;
  visualCoverage:`${number}%`|null;
  audioCoverageMs:number|null;
  visualCoverageMs:number|null;
};

const percent=(value:number,duration:number):`${number}%`=>
  `${Math.round(Math.min(100,Math.max(0,value/duration*100))*1000)/1000}%`;

function band(start:number,end:number,duration:number):TimelineBand {
  return {left:percent(start,duration),width:percent(end-start,duration)};
}

export function timelineTime(milliseconds:number):string {
  if(!Number.isFinite(milliseconds)||milliseconds<0)return '—';
  const seconds=Math.floor(milliseconds/1000);
  return `${Math.floor(seconds/60)}:${String(seconds%60).padStart(2,'0')}`;
}

export function clipTimeline(
  candidate:ClipCandidate,sourceDurationMs:number,
  audio:AudioTiming|null|undefined,scene:SceneAnalysis|null|undefined,
):ClipTimelineData|null {
  if(!Number.isInteger(sourceDurationMs)||sourceDurationMs<=0||sourceDurationMs>600000||
     !Number.isInteger(candidate?.source_start_ms)||!Number.isInteger(candidate?.source_end_ms)||
     candidate.source_start_ms<0||candidate.source_end_ms<=candidate.source_start_ms||
     candidate.source_end_ms>sourceDurationMs)return null;
  const audioReady=audio?.source_duration_ms===sourceDurationMs&&
    Number.isInteger(audio?.audio_duration_ms)&&audio!.audio_duration_ms>0&&
    audio!.audio_duration_ms<=sourceDurationMs&&Array.isArray(audio!.quiet_intervals);
  const sceneReady=scene?.source_duration_ms===sourceDurationMs&&scene?.status==='available'&&
    Number.isInteger(scene?.analyzed_duration_ms)&&scene!.analyzed_duration_ms>0&&
    scene!.analyzed_duration_ms<=sourceDurationMs&&Array.isArray(scene!.changes);
  return {
    selection:band(candidate.source_start_ms,candidate.source_end_ms,sourceDurationMs),
    quiet:audioReady?audio!.quiet_intervals.slice(0,360).flatMap(interval=>{
      const start=Math.max(0,interval.start_ms),end=Math.min(audio!.audio_duration_ms,sourceDurationMs,interval.end_ms);
      return Number.isInteger(start)&&Number.isInteger(end)&&end>start?[band(start,end,sourceDurationMs)]:[];
    }):[],
    visualTicks:sceneReady?scene!.changes.slice(0,180)
      .filter(change=>Number.isInteger(change.at_ms)&&change.at_ms>=0&&change.at_ms<=scene!.analyzed_duration_ms)
      .map(change=>percent(change.at_ms,sourceDurationMs)):[],
    audioCoverage:audioReady?percent(audio!.audio_duration_ms,sourceDurationMs):null,
    visualCoverage:sceneReady?percent(scene!.analyzed_duration_ms,sourceDurationMs):null,
    audioCoverageMs:audioReady?audio!.audio_duration_ms:null,
    visualCoverageMs:sceneReady?scene!.analyzed_duration_ms:null,
  };
}
