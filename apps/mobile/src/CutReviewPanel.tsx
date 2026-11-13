import React from 'react';
import {Text,View} from 'react-native';
import type {EnglishAnalysis} from './analysis';
import {cutReview,type CutCheckpoint} from './cutReview';
import {colors as c} from './theme';

function Boundary({value}:{value:CutCheckpoint}) {
  const content=value.cues.length?value.cues:[{
    type:'context' as const,
    message:'No nearby flags in the available evidence. This is not proof of a good cut; watch and listen.',
  }];
  return <View style={{gap:7,padding:12,backgroundColor:c.surface2,borderRadius:12}}>
    <View style={{flexDirection:'row',alignItems:'center',justifyContent:'space-between'}}>
      <Text style={{color:c.text,fontSize:15,fontWeight:'700'}}>{value.title} checkpoint</Text>
      <Text style={{color:c.accent,fontSize:13,fontWeight:'700'}}>{(value.atMs/1000).toFixed(1)}s</Text>
    </View>
    {content.map((item,i)=><View key={i} style={{flexDirection:'row',gap:8}}>
      <Text accessibilityElementsHidden style={{color:item.type==='coverage'?c.warning:c.blue}}>•</Text>
      <Text style={{color:c.muted,fontSize:14,lineHeight:20,flex:1}}>{item.message}</Text>
    </View>)}
  </View>;
}

/** Read-only cut checkpoints for the selected saved source interval.
 * They do not certify quality, mutate a review or invoke video rendering. */
export function CutReviewPanel({analysis,index}:{analysis:EnglishAnalysis;index:number}) {
  const guide=cutReview(analysis,index);
  if(!guide)return null;
  return <View style={{gap:9}}>
    <Text style={{color:c.text,fontSize:18,fontWeight:'700'}}>Check the cut points</Text>
    <Boundary value={guide.opening}/>
    <Boundary value={guide.ending}/>
    <Text style={{color:c.muted,fontSize:13,lineHeight:19}}>{guide.disclosure}</Text>
  </View>;
}
