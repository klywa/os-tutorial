import {sessionExpired} from './urls';
let generation=0;
const resetListeners=new Set<()=>void>();
export function onSessionReset(listener:()=>void){resetListeners.add(listener);return ()=>{resetListeners.delete(listener);};}
export const requestGeneration=()=>generation;
export function resetSessionRequests(){generation++;for(const listener of resetListeners)listener();}
export function assertRequestGeneration(epoch:number){if(epoch!==generation)throw new Error('登录身份已变化，请重新加载');}
/** Shared by every content request, including cache, search and dashboard reads. */
export async function sessionFetch(input:RequestInfo|URL,init?:RequestInit){
 const epoch=generation,response=await fetch(input,init);
 assertRequestGeneration(epoch);
 if(response.status===401)sessionExpired();
 const parse=response.json.bind(response);
 response.json=async()=>{assertRequestGeneration(epoch);const value=await parse();assertRequestGeneration(epoch);return value;};
 return response;
}
