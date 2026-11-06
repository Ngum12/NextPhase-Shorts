let handler: ((token:string)=>void)|undefined;
export function onUnauthorized(next:(token:string)=>void) {
  handler=next;
  return ()=>{if(handler===next)handler=undefined;};
}
export function unauthorized(token:string) {handler?.(token);}
