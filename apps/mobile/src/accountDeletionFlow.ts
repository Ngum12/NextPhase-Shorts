export type DeletionIntent={version:1;ownerId:string;key:string;sent:boolean};
type Storage={read():Promise<string|null>;write(value:string):Promise<void>;remove():Promise<void>};
type Remote={me(token:string):Promise<{id:string}>;request(token:string,password:string,key:string):Promise<any>;receipt(key:string):Promise<any>};
export class AccountDeletionFlow {
  private busy=false;
  constructor(private storage:Storage,private remote:Remote,private cleanup:(owner:string)=>Promise<void>,private uuid:()=>string){}
  async pending():Promise<DeletionIntent|null>{
    const raw=await this.storage.read();if(!raw)return null;
    const value=JSON.parse(raw);
    if(value.version!==1||!this.validId(value.ownerId)||!this.validId(value.key)||typeof value.sent!=='boolean')
      throw new Error('Saved deletion confirmation is damaged. Keep app data and contact support.');
    return value;
  }
  private validId(value:any){return typeof value==='string'&&/^[a-f0-9-]{36}$/i.test(value);}
  private async exclusive<T>(action:()=>Promise<T>){
    if(this.busy)throw new Error('A deletion request is already finishing.');
    this.busy=true;try{return await action();}finally{this.busy=false;}
  }
  private async finish(record:DeletionIntent,confirmation:any,forget:()=>Promise<void>){
    if(confirmation.status!=='account_disabled')throw new Error('Account deletion was not confirmed.');
    const current=await this.pending();
    if(current?.key!==record.key||current.ownerId!==record.ownerId)throw new Error('Saved deletion request changed.');
    await this.cleanup(record.ownerId);await forget();await this.storage.remove();
    return confirmation;
  }
  submit(ownerId:string,token:string,password:string,forget:(expected:string)=>Promise<void>){return this.exclusive(async()=>{
    const me=await this.remote.me(token);
    if(me.id!==ownerId)throw new Error('Account changed. Reopen Account before continuing.');
    let record=await this.pending();
    if(record&&record.ownerId!==ownerId)throw new Error('Finish the previous deletion confirmation first.');
    record=record||{version:1,ownerId,key:this.uuid(),sent:false};
    const previouslySent=record.sent;
    record={...record,sent:true};await this.storage.write(JSON.stringify(record));
    let confirmed;
    try{confirmed=await this.remote.request(token,password,record.key);}
    catch(error:any){
      try{confirmed=await this.remote.receipt(record.key);}
      catch{
        // A definitive first rejection cannot have deleted the account. After an
        // ambiguous earlier request, never discard its recovery capability.
        if(!previouslySent&&[400,409,422,429].includes(error.status))await this.storage.remove();
        throw error;
      }
    }
    return this.finish(record,confirmed,()=>forget(token));
  });}
  recover(afterConfirmed:()=>Promise<void>=async()=>{}){return this.exclusive(async()=>{
    const record=await this.pending();if(!record)throw new Error('No saved deletion request.');
    const confirmation=await this.remote.receipt(record.key);
    return this.finish(record,confirmation,afterConfirmed);
  });}
}
