/// <reference types="vite/client" />
import {seasonPath} from './seasons';
export function appUrl(path:string,base=import.meta.env.BASE_URL){
 if(/^(?:[a-z][a-z\d+.-]*:|\/\/|#)/i.test(path))return path;
 const prefix='/'+base.replace(/^\/+|\/+$/g,'');
 if(prefix==='/'||path===prefix||path.startsWith(prefix+'/'))return path.startsWith('/')?path:'/'+path;
 return prefix+'/'+path.replace(/^\/+/, '');
}
export const apiUrl=(path:string)=>appUrl('api/'+seasonPath(path));
export function sessionExpired(){window.dispatchEvent(new Event('wxq:session-expired'));}

