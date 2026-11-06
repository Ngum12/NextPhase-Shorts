// Secure storage and HTTP are injected so restart and stale-response races can be tested.
type Storage = { read(): Promise<string|null>; write(token:string): Promise<void>; remove(): Promise<void> };
type Remote = { validate(token:string): Promise<unknown>; revoke(token:string, all:boolean): Promise<void>;
  password(token:string, current:string, next:string): Promise<void> };
export class SessionController {
  token: string|null = null;
  private revision = 0;
  private writes: Promise<void> = Promise.resolve();
  constructor(private storage:Storage, private remote:Remote, private publish:(token:string|null)=>void) {}
  private persist(task:()=>Promise<void>) {
    const pending=this.writes.catch(()=>{}).then(task);
    this.writes=pending;return pending;
  }
  async restore() {
    const revision=this.revision;
    const saved=await this.storage.read();
    if(revision!==this.revision||!saved)return;
    this.token=saved;
    try {await this.remote.validate(saved);}
    catch(error:any) {
      if(error.status===401){await this.expire(saved);return;}
      // An outage does not destroy the saved credential; the server still enforces it.
    }
    if(revision===this.revision)this.publish(saved);
  }
  async signIn(token:string) {
    const revision=++this.revision;this.token=token;
    try {await this.persist(()=>this.storage.write(token));}
    catch(error) {if(revision===this.revision){this.token=null;this.publish(null);}throw error;}
    if(revision===this.revision)this.publish(token);
  }
  async expire(expected:string) {
    if(this.token!==expected)return;
    ++this.revision;this.token=null;this.publish(null);
    await this.persist(()=>this.storage.remove());
  }
  async signOut(all=false) {
    const token=this.token;if(!token)return;
    // Keep the credential if offline: don't claim the server session was revoked.
    await this.remote.revoke(token,all);
    await this.expire(token);
  }
  async changePassword(current:string,next:string) {
    const token=this.token;if(!token)throw new Error('Sign in again');
    await this.remote.password(token,current,next);
    await this.expire(token);
  }
}
