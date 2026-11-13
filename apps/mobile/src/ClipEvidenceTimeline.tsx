import React from 'react';
import {Text,View} from 'react-native';
import type {ClipCandidate} from './analysis';
import type {AudioTiming} from './audioTiming';
import type {SceneAnalysis} from './sceneAnalysis';
import {clipTimeline,timelineTime} from './clipTimeline';
import {colors as c} from './theme';

/** Private, non-interactive edit evidence. Rendering still uses only the saved
 * reviewed candidate and unchanged source timestamps. */
export function ClipEvidenceTimeline({candidate,duration,audio,scene}:{
  candidate:ClipCandidate;duration:number;
  audio?:AudioTiming|null;scene?:SceneAnalysis|null;
}) {
  const data=clipTimeline(candidate,duration,audio,scene);
  if(!data)return null;
  const text={color:c.muted,fontSize:13,lineHeight:19};
  const heading={color:c.text,fontWeight:'700' as const,fontSize:16};
  const track={height:18,backgroundColor:c.surface2,borderRadius:7,overflow:'hidden' as const,position:'relative' as const};
  const absolute={position:'absolute' as const,top:0,bottom:0};
  const preview=`${timelineTime(candidate.source_start_ms)}–${timelineTime(candidate.source_end_ms)}`;
  return <View style={{backgroundColor:c.surface2,borderRadius:14,padding:14,gap:10,borderWidth:1,borderColor:c.border}}>
    <View style={{flexDirection:'row',justifyContent:'space-between',alignItems:'center',gap:10}}>
      <Text style={heading}>Clip timeline</Text>
      <Text style={{...text,color:c.accent,fontWeight:'700'}}>{preview}</Text>
    </View>
    <Text style={text}>Selected excerpt within the original recording</Text>
    <View accessible accessibilityLabel={`Original duration ${timelineTime(duration)}. Selected excerpt from ${timelineTime(candidate.source_start_ms)} to ${timelineTime(candidate.source_end_ms)}.`}
      style={track}>
      <View accessible={false} style={{...absolute,left:data.selection.left,width:data.selection.width,backgroundColor:c.accent}}/>
    </View>
    <View style={{flexDirection:'row',justifyContent:'space-between'}}>
      <Text style={text}>0:00</Text>
      <Text style={text}>Original {timelineTime(duration)}</Text>
    </View>
    {data.audioCoverage!==null&&<View style={{gap:5}}>
      <Text style={text}>Low-volume passages · checked through {timelineTime(data.audioCoverageMs!)}</Text>
      <View accessible accessibilityLabel={`Audio checked through ${timelineTime(data.audioCoverageMs!)}. ${data.quiet.length} low-volume passages marked.`} style={track}>
        <View accessible={false} style={{...absolute,left:0,width:data.audioCoverage,backgroundColor:c.border}}/>
        {data.quiet.map((quiet,i)=><View key={i} accessible={false} style={{...absolute,left:quiet.left,width:quiet.width,backgroundColor:c.warning}}/>)}
      </View>
    </View>}
    {data.visualCoverage!==null&&<View style={{gap:5}}>
      <Text style={text}>Possible visual changes · sampled through {timelineTime(data.visualCoverageMs!)}</Text>
      <View accessible accessibilityLabel={`Visual samples checked through ${timelineTime(data.visualCoverageMs!)}. ${data.visualTicks.length} possible changes marked.`} style={track}>
        <View accessible={false} style={{...absolute,left:0,width:data.visualCoverage,backgroundColor:c.border}}/>
        {data.visualTicks.map((left,i)=><View key={i} accessible={false} style={{...absolute,left,width:2,backgroundColor:c.blue}}/>)}
      </View>
    </View>}
    {data.audioCoverage===null&&data.visualCoverage===null&&
      <Text style={text}>Optional audio and visual guides are unavailable for this recording.</Text>}
    <View style={{flexDirection:'row',gap:14,flexWrap:'wrap'}}>
      {([{color:c.accent,label:'Selected clip'},
        ...(data.audioCoverage!==null?[{color:c.warning,label:'Quiet estimates'}]:[]),
        ...(data.visualCoverage!==null?[{color:c.blue,label:'Possible changes'}]:[])]).map(item=>
        <View key={item.label} style={{flexDirection:'row',alignItems:'center',gap:6}}>
          <View style={{width:9,height:9,borderRadius:2,backgroundColor:item.color}}/>
          <Text style={text}>{item.label}</Text>
        </View>)}
    </View>
    {((data.audioCoverageMs!==null&&data.audioCoverageMs<duration)||
       (data.visualCoverageMs!==null&&data.visualCoverageMs<duration))&&
      <Text style={{...text,color:c.warning}}>Some analysis covers only part of the recording. Unchecked sections are not evidence of silence or no scene changes.</Text>}
    <Text style={text}>Guide markers are estimates, not editing commands. Compare the original recording and rendered preview before sharing.</Text>
  </View>;
}
