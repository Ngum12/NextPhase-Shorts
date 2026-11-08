// One durable journal entry and one in-flight rotation per signed-in generation.
export type TokenPair = {access_token:string; refresh_token:string; expires_in:number; refresh_expires_in:number};
type RecordV2 = {version:2; access:string; refresh:string; expiresAt:number; pending?:string};
type Storage = {read():Promise<string|null>; write(value:string):Promise<void>; remove():Promise<void>};
type Remote = {validate(token:string):Promise<unknown>; refresh(token:string,key:string):Promise<TokenPair>;
  revokeRefresh(token:string):Promise<void>; revoke(token:string,all:boolean):Promise<void>;
  password(token:string,current:string,next:string):Promise<void>};
export function validPair(value:any):value is TokenPair {
  return typeof value?.access_token==='string' && value.access_token.length>0 && value.access_token.length<=4096
    && typeof value.refresh_token==='string' && /^[A-Za-z0-9_-]{43}$/.test(value.refresh_token)
    && Number.isFinite(value.expires_in) && value.expires_in>0 && value.expires_in<=3600
    && Number.isFinite(value.refresh_expires_in) && value.refresh_expires_in>0;
}
export class RefreshSessionController {
  token:string|null=null;
  private record:RecordV2|null=null;
  private revision=0;
  private origins=new Set<string>();
  private writes:Promise<void>=Promise.resolve();
  private flight:{revision:number; promise:Promise<string>}|null=null;
  constructor(private storage:Storage,private remote:Remote,private publish:(token:string|null)=>void,
    private uuid:()=>string,private now:()=>number=Date.now) {}
  private persist(revision:number,task:()=>Promise<void>) {
    const pending=this.writes.catch(()=>{}).then(async()=>{if(revision===this.revision)await task();});
    this.writes=pending;return pending;
  }
  private fromPair(pair:TokenPair):RecordV2 {
    if(!validPair(pair))throw new Error('Invalid session response. Sign in again.');
    return {version:2,access:pair.access_token,refresh:pair.refresh_token,expiresAt:this.now()+pair.expires_in*1000};
  }
  async signIn(value:TokenPair|string) {
    const record=typeof value==='string'?null:this.fromPair(value);
    const token=typeof value==='string'?value:value.access_token;
    const revision=++this.revision;
    this.token=token;this.record=record;this.origins=new Set([token]);
    try {await this.persist(revision,()=>this.storage.write(record?JSON.stringify(record):token));}
    catch(error) {if(revision===this.revision){this.token=null;this.record=null;this.origins.clear();this.publish(null);}throw error;}
    if(revision===this.revision)this.publish(token);
  }
  async restore() {
    const revision=this.revision,saved=await this.storage.read();
    if(revision!==this.revision||!saved)return;
    let record:RecordV2|null=null,token=saved;
    if(saved.startsWith('{')) {
      try {
        const parsed=JSON.parse(saved);
        if(parsed.version!==2||typeof parsed.access!=='string'||!parsed.access||parsed.access.length>4096
          ||typeof parsed.refresh!=='string'||!/^[A-Za-z0-9_-]{43}$/.test(parsed.refresh)
          ||!Number.isFinite(parsed.expiresAt)||(parsed.pending!==undefined&&
            (typeof parsed.pending!=='string'||!/^[0-9a-f-]{36}$/i.test(parsed.pending))))throw Error('Invalid session');
        record=parsed;token=parsed.access;
      } catch {await this.persist(revision,()=>this.storage.remove());return;}
    }
    this.token=token;this.record=record;this.origins=new Set([token]);
    try {const current=await this.prepare(token);await this.remote.validate(current);}
    catch(error:any) {if(error.status===401){await this.expire(token);return;}}
    // Offline startup retains the journal; requests still require server authorization.
    if(revision===this.revision)this.publish(this.token);
  }
  async prepare(origin:string):Promise<string> {
    if(!this.origins.has(origin))throw new Error('Session changed. Retry from the current account.');
    if(this.record&&(this.record.pending||this.record.expiresAt<=this.now()+30000))return this.renew(origin);
    return this.token!;
  }
  async recover(actual:string):Promise<string|null> {
    if(!this.origins.has(actual))return null;
    if(this.token!==actual && !this.record?.pending && (this.record?.expiresAt??0)>this.now()+30000)return this.token;
    if(!this.record){await this.expire(actual);return null;}
    return this.renew(actual);
  }
  private async renew(origin:string):Promise<string> {
    const revision=this.revision;
    if(this.flight?.revision===revision)return this.flight.promise;
    const promise=this.rotate(revision,origin);
    this.flight={revision,promise};
    try {return await promise;}finally {if(this.flight?.promise===promise)this.flight=null;}
  }
  private async rotate(revision:number,origin:string) {
    const record=this.record;
    if(!record)throw new Error('Sign in again.');
    // Save the retry key BEFORE sending anything. Ambiguous failures keep this record.
    const intent={...record,pending:record.pending||this.uuid()};
    await this.persist(revision,()=>this.storage.write(JSON.stringify(intent)));
    if(revision!==this.revision)throw new Error('Session changed. Retry from the current account.');
    this.record=intent;
    let pair:TokenPair;
    try {pair=await this.remote.refresh(intent.refresh,intent.pending);}
    catch(error:any) {if(error.status===401&&revision===this.revision)await this.expire(origin);throw error;}
    const next=this.fromPair(pair);
    // If this write fails the old durable retry key recovers the same server result.
    await this.persist(revision,()=>this.storage.write(JSON.stringify(next)));
    if(revision!==this.revision)throw new Error('Session changed. Retry from the current account.');
    this.record=next;this.token=next.access;this.origins.add(next.access);
    // Keep the UI's generation handle stable. Changing it would abort the upload
    // screen's account-change effect during an otherwise successful rotation.
    return next.access;
  }
  async expire(expected:string) {
    if(!this.origins.has(expected))return;
    const revision=++this.revision;this.token=null;this.record=null;this.origins.clear();this.publish(null);
    await this.persist(revision,()=>this.storage.remove());
  }
  async signOut(all=false) {
    const origin=this.token,record=this.record;if(!origin)return;
    if(record&&!all)await this.remote.revokeRefresh(record.refresh);
    else await this.remote.revoke(await this.prepare(origin),all);
    await this.expire(origin);
  }
  async changePassword(current:string,next:string) {
    const origin=this.token;if(!origin)throw new Error('Sign in again.');
    await this.remote.password(await this.prepare(origin),current,next);
    await this.expire(origin);
  }
}
