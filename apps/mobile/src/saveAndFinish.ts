/** Save a finished Short before requesting durable server-side project cleanup.
 * This function never deletes the source on a failed native Gallery save.
 * A successful DELETE tombstones the source and its preview children, then the
 * existing cleanup supervisor removes their private media trees asynchronously.
 * It does NOT erase encrypted historical backups or third-party API copies.
 */
import * as FileSystem from 'expo-file-system/legacy';
import {deleteJob} from './api';
import {exportVideo} from './videoExports';
import {forgetPreviewIntents} from './clipPreviews';

export class SavedButCleanupPending extends Error {
  constructor() {
    super('The Short was saved to your phone, but server deletion could not be confirmed. Use Delete project to request cleanup again.');
    this.name='SavedButCleanupPending';
  }
}

export async function saveAndFinish(renderId:string,sourceId:string,token:string):Promise<void> {
  if(!renderId||!sourceId||!token)throw new Error('An authenticated project is required.');
  // Gallery save is the only confirmation we can receive from the native API.
  // Never revoke server access merely because an HTTP download completed.
  await exportVideo('save',renderId,token);
  const root=FileSystem.cacheDirectory||FileSystem.documentDirectory;
  try {
    // If saving a preview child, delete the ORIGINAL source: this tombstones
    // associated previews and analysis tasks, not just the last rendered child.
    await deleteJob(sourceId,token);
  } catch {
    throw new SavedButCleanupPending();
  } finally {
    // Once the native library acknowledged a save, no temporary app copy is
    // needed, whether or not server cleanup was successfully scheduled.
    if(root)await FileSystem.deleteAsync(root+`nextphase-${encodeURIComponent(renderId)}.mp4`,
      {idempotent:true}).catch(()=>{});
  }
  await forgetPreviewIntents(sourceId).catch(()=>{});
}
