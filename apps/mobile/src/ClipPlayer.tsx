import React,{useCallback,useEffect,useRef,useState} from 'react';
import {Text,View} from 'react-native';
import {useVideoPlayer,VideoView} from 'expo-video';
import {useFocusEffect} from 'expo-router';
import {Body,Button,Loading} from './ui';
import {loadPreviewFile} from './clipPreviews';
import {colors as c} from './theme';

function LocalVideo({uri}:{uri:string}) {
  const player=useVideoPlayer({uri},instance=>{instance.loop=false;});
  const [failed,setFailed]=useState(false);
  useEffect(()=>{
    const listener=player.addListener('statusChange',event=>setFailed(event.status==='error'));
    return()=>{listener.remove();};
  },[player]);
  return <View style={{gap:10}}>
    <VideoView player={player} nativeControls contentFit="contain" style={{width:'100%',aspectRatio:9/16,backgroundColor:'#000'}}/>
    {failed&&<Text accessibilityRole="alert" style={{color:c.warning}}>The preview could not play. Refresh the project and try again.</Text>}
  </View>;
}

export function ClipPlayer({id,token}:{id:string;token:string}) {
  const [file,setFile]=useState<{uri:string;scope:string}|null>(null),[loading,setLoading]=useState(false);
  const [error,setError]=useState('');const sequence=useRef(0),cleanup=useRef<(()=>Promise<void>)|null>(null),inFlight=useRef(false);
  const scope=`${id}:${token}`;
  useFocusEffect(useCallback(()=>{
    setLoading(false);setError('');
    return()=>{sequence.current++;inFlight.current=false;cleanup.current?.().catch(()=>{});
      cleanup.current=null;setFile(null);setLoading(false);};
  },[id,token]));
  const open=async()=>{
    if(inFlight.current)return;
    inFlight.current=true;const request=++sequence.current;setLoading(true);setError('');
    try{
      const next=await loadPreviewFile(id,token);
      if(request!==sequence.current){await next.remove();return;}
      await cleanup.current?.().catch(()=>{});cleanup.current=next.remove;
      setFile({uri:next.uri,scope});
    }catch{if(request===sequence.current)setError('Could not load the preview. Check your connection, refresh the project and retry.');}
    finally{if(request===sequence.current){inFlight.current=false;setLoading(false);}}
  };
  return <View style={{gap:12}}>
    <Body>Watch the first and last words, check voice synchronization, and confirm the clip preserves your meaning.</Body>
    {file?.scope===scope?<>
      <LocalVideo key={file.uri} uri={file.uri}/>
      <Button title="Reload preview" secondary onPress={()=>{setFile(null);cleanup.current?.().catch(()=>{});cleanup.current=null;open();}} disabled={loading}/>
    </>:<Button title={loading?'Loading preview…':'Watch preview'} onPress={open} disabled={loading}/>}
    {loading&&<Loading/>}
    {!!error&&<Text accessibilityRole="alert" style={{color:c.warning}}>{error}</Text>}
  </View>;
}
