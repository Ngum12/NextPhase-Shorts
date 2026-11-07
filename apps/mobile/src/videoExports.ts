import {Platform} from 'react-native';
import * as FileSystem from 'expo-file-system/legacy';
import * as MediaLibrary from 'expo-media-library';
import * as Sharing from 'expo-sharing';
import {downloadUrl} from './api';
import {unauthorized} from './authEvents';

export async function exportVideo(action:'save'|'share',id:string,token:string):Promise<void> {
  if(action==='save' && !(Platform.OS==='android' && Number(Platform.Version)>=33)) {
    // Adding our own MediaStore video on Android 13+ needs no broad read access.
    const permission=await MediaLibrary.requestPermissionsAsync(true,[]);
    if(!permission.granted)throw new Error('Video saving permission was not granted. Allow it in Settings and try again.');
  }
  if(action==='share' && !await Sharing.isAvailableAsync())throw new Error('Sharing is unavailable on this device.');
  const root=FileSystem.cacheDirectory||FileSystem.documentDirectory;
  if(!root)throw new Error('App storage is unavailable.');
  const destination=root+`nextphase-${encodeURIComponent(id)}.mp4`;
  const result=await FileSystem.downloadAsync(downloadUrl(id),destination,{headers:{Authorization:`Bearer ${token}`}});
  if(result.status===401)unauthorized(token);
  if(result.status!==200)throw new Error('The video could not be downloaded. Refresh its status and try again.');
  const info=await FileSystem.getInfoAsync(result.uri);
  if(!info.exists||!('size' in info)||info.size===0)throw new Error('The downloaded video is empty or unavailable.');
  if(action==='save')await MediaLibrary.saveToLibraryAsync(result.uri);
  else await Sharing.shareAsync(result.uri,{mimeType:'video/mp4'});
}
