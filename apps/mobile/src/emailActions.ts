import {BASE,extract,authenticatedFetch} from './api';
export type RecoveryCapabilities={delivery:'disabled'|'local_file';verification_enforced:false};
export async function recoveryCapabilities():Promise<RecoveryCapabilities>{
  const body=await extract(await fetch(`${BASE}/api/v1/auth/recovery-capabilities`,{credentials:'omit'}));
  if(!['disabled','local_file'].includes(body.delivery)||body.verification_enforced!==false)
    throw Error('Email action settings are unavailable.');
  return body;
}
async function publicAction(path:string,body:unknown,expected:number){
  const response=await fetch(`${BASE}/api/v1/auth/${path}`,{method:'POST',credentials:'omit',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const result=response.status===204?null:await extract(response);
  if(response.status!==expected||(expected===202&&result?.status!=='accepted'))
    throw Error('Email action was not confirmed. Please retry.');
}
export const requestPasswordReset=(email:string)=>publicAction('password-reset/request',{email:email.trim()},202);
export const confirmPasswordReset=(code:string,newPassword:string)=>publicAction('password-reset/confirm',
  {code:code.trim(),new_password:newPassword},204);
export const confirmEmail=(code:string)=>publicAction('email-verification/confirm',{code:code.trim()},204);
export async function requestEmailVerification(token:string){
  const response=await authenticatedFetch(token,`${BASE}/api/v1/auth/email-verification/request`,{method:'POST'});
  const result=await extract(response);
  if(response.status!==202||result.status!=='accepted')throw Error('Email request was not confirmed.');
}
