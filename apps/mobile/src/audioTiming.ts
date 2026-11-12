export type AudioTiming={
  schema_version:'audio-timing-1';source_sha256:string;source_duration_ms:number;audio_duration_ms:number;
  alignment:'normalized_pcm_first_pts_zero';method:'pcm_window_energy';window_ms:20;
  threshold_dbfs:-40;minimum_quiet_ms:500;quiet_intervals:{start_ms:number;end_ms:number}[];
};
export function validAudioTiming(value:any,source:string,duration:number):value is AudioTiming {
  if(value?.schema_version!=='audio-timing-1'||value.source_sha256!==source||value.source_duration_ms!==duration||
      !Number.isInteger(duration)||duration<1||duration>180000||value.alignment!=='normalized_pcm_first_pts_zero'||value.method!=='pcm_window_energy'||
      value.window_ms!==20||value.threshold_dbfs!==-40||value.minimum_quiet_ms!==500||
      !Number.isInteger(value.audio_duration_ms)||value.audio_duration_ms<1||value.audio_duration_ms>duration||
      !Array.isArray(value.quiet_intervals)||value.quiet_intervals.length>360)return false;
  return value.quiet_intervals.every((interval:any,i:number)=>
    Number.isInteger(interval?.start_ms)&&Number.isInteger(interval?.end_ms)&&interval.start_ms>=0&&
    interval.end_ms-interval.start_ms>=500&&interval.end_ms<=value.audio_duration_ms&&
    (i===0||interval.start_ms>=value.quiet_intervals[i-1].end_ms));
}
export function quietMilliseconds(timing:AudioTiming,start:number,end:number) {
  return timing.quiet_intervals.reduce((total,interval)=>
    total+Math.max(0,Math.min(end,interval.end_ms)-Math.max(start,interval.start_ms)),0);
}
