import {createContext,useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {apiUrl} from './urls';
import {syncPollMs,type SyncStatus} from './syncStatus';
export type Role='guest'|'admin'|'annotator';
export type Session={mode:'local'|'public';role:Role;account_role?:Role;allowed_roles?:Role[];username:string|null;base_path:string;sync?:SyncStatus;capabilities?:Record<string,boolean>};
const local:Session={mode:'local',role:'admin',username:null,base_path:'/'};
export function capabilitiesFor(session:Session){const admin=session.role==='admin',localTools=session.mode==='local'&&admin,writable=admin&&(session.mode==='local'||!session.sync||session.sync.state==='synced');return {localTools,editNotes:writable,manageMatches:writable,reviews:localTools,inlineEdit:admin||session.role==='annotator',proposeNotes:session.role==='annotator'};}

type Auth={session:Session;refresh:()=>Promise<void>;login:(username:string,password:string)=>Promise<void>;logout:()=>Promise<void>;openLogin?:()=>void;closeLogin?:()=>void;loginOpen?:boolean;switchRole?:(role:Role)=>Promise<void>};
export const AuthContext=createContext<Auth>({session:local,refresh:async()=>{},login:async()=>{},logout:async()=>{}});
export const useAuth=()=>useContext(AuthContext);
export const useCapabilities=()=>capabilitiesFor(useAuth().session);
async function request(path:string,body?:unknown):Promise<Session>{const response=await fetch(apiUrl('auth/'+path),{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',body:body===undefined?undefined:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw new Error(result.error??'登录失败');return result;}
export function AuthProvider({children}:{children:ReactNode}){
 const [session,setSession]=useState<Session|null>(null),[error,setError]=useState('');
 const sequence=useRef(0);
 const [loginOpen,setLoginOpen]=useState(()=>typeof window!=='undefined'&&window.location.pathname.replace(/\/+$/,'').endsWith('/admin'));
 const returnFocus=useRef<HTMLElement|null>(null);
 function closeLogin(){setLoginOpen(false);requestAnimationFrame(()=>returnFocus.current?.focus());}
 function openLogin(){returnFocus.current=document.activeElement as HTMLElement;setLoginOpen(true);}
 async function refresh(){const epoch=++sequence.current,value=await request('me');if(epoch!==sequence.current)return;setSession(value);setError('');}
 useEffect(()=>{
  void refresh().catch(e=>setError(e.message));
  const expired=()=>{sequence.current++;setSession(s=>s?.mode==='public'?{...s,role:'guest',account_role:'guest',allowed_roles:['guest'],username:null}:s);};
  const syncChanged=(event:Event)=>{const sync=(event as CustomEvent<SyncStatus|undefined>).detail;if(sync?.state){sequence.current++;setSession(s=>s?{...s,sync}:s);}else void refresh().catch(()=>{});};
  window.addEventListener('wxq:sync-changed',syncChanged);window.addEventListener('wxq:session-expired',expired);
  return()=>{sequence.current++;window.removeEventListener('wxq:sync-changed',syncChanged);window.removeEventListener('wxq:session-expired',expired);};
 },[]);
 const interval=syncPollMs(session);
 useEffect(()=>{const timer=setInterval(()=>void refresh().catch(()=>{}),interval);return()=>clearInterval(timer);},[interval]);
 if(!session)return <main className="empty" role="status">{error?<>{error}<button onClick={()=>void refresh().catch(e=>setError(e.message))}>重试</button></>:'正在确认访问权限…'}</main>;
 return <AuthContext.Provider value={{session,refresh,openLogin,closeLogin,loginOpen,login:async(username,password)=>{await request('login',{username,password});await refresh();closeLogin();},logout:async()=>{await request('logout',{});await refresh();},switchRole:async(role)=>{sequence.current++;const value=await request('role',{role});sequence.current++;setSession(value);}}}>{children}</AuthContext.Provider>;
}
export function AdminAccess(){
 const {session,login,loginOpen,closeLogin}=useAuth();
 const dialog=useRef<HTMLDialogElement>(null),input=useRef<HTMLInputElement>(null);
 const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const visible=session.mode==='public'&&session.role==='guest'&&loginOpen;
 useEffect(()=>{if(visible){dialog.current?.showModal();input.current?.focus();}else{dialog.current?.close();setPassword('');setError('');}},[visible]);
 return <dialog ref={dialog} className="login-dialog" aria-labelledby="login-title" onCancel={e=>{e.preventDefault();closeLogin?.();}} onClick={e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeLogin?.();}}}>
 <header><div><small>万象棋 · 战术手册</small><h2 id="login-title">账号登录</h2></div><button type="button" aria-label="关闭登录" onClick={closeLogin}>×</button></header>
 <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{await login(username,password);setPassword('');}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>
 <label>用户名<input ref={input} name="username" autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label>
 <label>密码<input name="password" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>
 {error&&<p className="error" role="alert">{error}</p>}<button className="primary" disabled={busy}>{busy?'登录中…':'登录'}</button></form></dialog>;
}
