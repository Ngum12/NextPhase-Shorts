let handler: ((token:string)=>void)|undefined;
export function onUnauthorized(next:(token:string)=>void) {
  handler=next;
  return ()=>{if(handler===next)handler=undefined;};
}
export function unauthorized(token:string) {handler?.(token);}

type Coordinator={prepare(token:string):Promise<string>; recover(token:string):Promise<string|null>};
let coordinator:Coordinator|undefined;
export function coordinateSession(next:Coordinator) {
  coordinator=next;return ()=>{if(coordinator===next)coordinator=undefined;};
}
export async function prepareToken(token:string) {return coordinator?coordinator.prepare(token):token;}
export async function recoverToken(token:string) {
  if(coordinator)return coordinator.recover(token);
  unauthorized(token);return null;
}
