export type SceneAnalysis={
  schema_version:'scene-analysis-1';source_sha256:string;source_duration_ms:number;
  status:'available'|'unavailable';issue:'decode_or_resource_limit'|'insufficient_samples'|null;
  method:'sampled_rgb_difference';alignment:'ffmpeg_fps_start_zero';sample_interval_ms:500;
  proxy_width:64;proxy_height:36;threshold_milli:180;minimum_gap_ms:1000;
  sample_count:number;analyzed_duration_ms:number;changes:{at_ms:number;delta_milli:number}[];
};
export function validSceneAnalysis(value:any,source:string,duration:number):value is SceneAnalysis {
  if(value?.schema_version!=='scene-analysis-1'||value.source_sha256!==source||value.source_duration_ms!==duration||
      !Number.isInteger(duration)||duration<1||duration>180000||value.method!=='sampled_rgb_difference'||
      value.alignment!=='ffmpeg_fps_start_zero'||value.sample_interval_ms!==500||value.proxy_width!==64||value.proxy_height!==36||
      value.threshold_milli!==180||value.minimum_gap_ms!==1000||
      !Number.isInteger(value.sample_count)||value.sample_count<0||value.sample_count>361||
      !Number.isInteger(value.analyzed_duration_ms)||value.analyzed_duration_ms<0||value.analyzed_duration_ms>duration||
      !Array.isArray(value.changes)||value.changes.length>180)return false;
  if(value.status==='unavailable')return ['decode_or_resource_limit','insufficient_samples'].includes(value.issue)&&
    value.sample_count===0&&value.analyzed_duration_ms===0&&value.changes.length===0;
  if(value.status!=='available'||value.issue!==null||duration<500||value.sample_count<2||
      value.sample_count>Math.ceil(duration/500)+1||value.analyzed_duration_ms!==Math.min(value.sample_count*500,duration))return false;
  return value.changes.every((change:any,i:number)=>Number.isInteger(change?.at_ms)&&change.at_ms>=500&&
    change.at_ms%500===0&&change.at_ms<duration&&change.at_ms<=(value.sample_count-1)*500&&
    Number.isInteger(change.delta_milli)&&change.delta_milli>=180&&change.delta_milli<=1000&&
    (i===0||change.at_ms-value.changes[i-1].at_ms>=1000));
}
export function sceneContext(analysis:SceneAnalysis|null|undefined,start:number,end:number) {
  if(!analysis||analysis.status!=='available')return null;
  const near=(boundary:number)=>analysis.changes.reduce<number|null>((best,event)=>
    Math.abs(event.at_ms-boundary)<=1000&&(best===null||Math.abs(event.at_ms-boundary)<Math.abs(best-boundary))?event.at_ms:best,null);
  return {inside:analysis.changes.filter(change=>change.at_ms>start&&change.at_ms<end).length,
    nearStart:near(start),nearEnd:near(end),partial:end>analysis.analyzed_duration_ms};
}
