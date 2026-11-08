import * as DocumentPicker from 'expo-document-picker';
import { Platform } from 'react-native';

export async function pickVideo(): Promise<DocumentPicker.DocumentPickerAsset|null> {
  // SDK 58 Expo Go's Android DocumentPicker cache is outside the experience's
  // sandbox. Keep the user-granted provider URI and copy it into private storage
  // before creating an upload intent. iOS still needs the picker-owned cache copy.
  const result=await DocumentPicker.getDocumentAsync({
    type:'video/*',copyToCacheDirectory:Platform.OS!=='android',multiple:false,
  });
  return result.canceled?null:result.assets[0]??null;
}
