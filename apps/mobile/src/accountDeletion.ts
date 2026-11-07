import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import {api,requestAccountDeletion,accountDeletionReceipt} from './api';
import {clearDeletedAccountUpload} from './uploads';
import {AccountDeletionFlow} from './accountDeletionFlow';
const KEY='nextphase_account_deletion';
export const accountDeletion=new AccountDeletionFlow({read:()=>SecureStore.getItemAsync(KEY),
  write:value=>SecureStore.setItemAsync(KEY,value),remove:()=>SecureStore.deleteItemAsync(KEY)},
  {me:token=>api<{id:string}>('/api/v1/me',token),request:requestAccountDeletion,receipt:accountDeletionReceipt},
  clearDeletedAccountUpload,Crypto.randomUUID);
