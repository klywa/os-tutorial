import {createContext,useContext,useEffect,useState,type ReactNode} from 'react';
import {apiUrl} from './urls';
export type Session={mode:'local'|'public';role:'guest'|'admin';username:string|null;base_path:string;sync?:{state:string;message?:string};capabilities?:Record<string,boolean>};
const local:Session={mode:'local',role:'admin',username:null,base_path:'/'};
export function capabilitiesFor(session:Session){const localTools=session.mode==='local',writable=localTools||(session.role==='admin'&&(!session.sync||session.sync.state==='synced'));return {localTools,editNotes:writable,manageMatches:writable,reviews:localTools};}
type Auth={session:Session;refresh:()=>Promise<void>;login:(username:string,password:string)=>Promise<void>;logout:()=>Promise<void>};
export const AuthContext=createContext<Auth>({session:local,refresh:async()=>{},login:async()=>{},logout:async()=>{}});
export const useAuth=()=>useContext(AuthContext);
export const useCapabilities=()=>capabilitiesFor(useAuth().session);
async function request(path:string,body?:unknown):Promise<Session>{const response=await fetch(apiUrl('auth/'+path),{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',body:body===undefined?undefined:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw new Error(result.error??'登录失败');return result;}
export function AuthProvider({children}:{children:ReactNode}){
 const [session,setSession]=useState<Session|null>(null),[error,setError]=useState('');
 async function refresh(){const value=await request('me');setSession(value);setError('');}
 useEffect(()=>{void refresh().catch(e=>setError(e.message));const expired=()=>setSession(s=>s?.mode==='public'?{...s,role:'guest',username:null}:s);const syncChanged=()=>void refresh().catch(()=>expired());const timer=setInterval(syncChanged,60000);window.addEventListener('wxq:sync-changed',syncChanged);window.addEventListener('wxq:session-expired',expired);return()=>{clearInterval(timer);window.removeEventListener('wxq:sync-changed',syncChanged);window.removeEventListener('wxq:session-expired',expired);};},[]);
 if(!session)return <main className="empty" role="status">{error?<>{error}<button onClick={()=>void refresh().catch(e=>setError(e.message))}>重试</button></>:'正在确认访问权限…'}</main>;
 return <AuthContext.Provider value={{session,refresh,login:async(username,password)=>{await request('login',{username,password});await refresh();},logout:async()=>{await request('logout',{});await refresh();}}}>{children}</AuthContext.Provider>;
}
export function AdminAccess(){
 const {session,login,logout}=useAuth();const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 if(session.mode!=='public')return null;
 if(session.role==='admin')return <div className="admin-access"><span>管理员 {session.username}</span><button onClick={()=>void logout().catch(e=>setError(e.message))}>退出登录</button>{session.sync&&<small role="status">{session.sync.message??(session.sync.state==='synced'?'修改已同步。':`编辑已暂停，正在等待同步或发布（${session.sync.state}）。`)}</small>}{error&&<span role="alert">{error}</span>}</div>;
 if(!window.location.pathname.replace(/\/+$/,'').endsWith('/admin'))return null;
 return <form className="admin-access" onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{await login(username,password);setPassword('');}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}><strong>管理员登录</strong><label>用户名<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label><label>密码<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label><button disabled={busy}>{busy?'登录中…':'登录'}</button>{error&&<span role="alert">{error}</span>}</form>;
}
