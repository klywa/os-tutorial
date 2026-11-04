import './login.css';
import {createContext,useContext,useEffect,useRef,useState,type ReactNode} from 'react';
import {apiUrl} from './urls';
import {syncPollMs,type SyncStatus} from './syncStatus';
import {configureReaderCache} from './readerCache';
export type Role='guest'|'admin'|'annotator'|'viewer';
export type Session={mode:'local'|'public';role:Role;account_role?:Role;allowed_roles?:Role[];username:string|null;base_path:string;sync?:SyncStatus;capabilities?:Record<string,boolean>};
const local:Session={mode:'local',role:'admin',username:null,base_path:'/'};
export function capabilitiesFor(session:Session){const admin=session.role==='admin',localTools=session.mode==='local'&&admin,writable=admin&&(session.mode==='local'||!session.sync||session.sync.state!=='conflict');return {localTools,editNotes:writable,manageMatches:writable,reviews:localTools,inlineEdit:admin||session.role==='annotator',proposeNotes:session.role==='annotator'};}

export function canEditNote(session:Session,noteId?:string){return capabilitiesFor(session).editNotes&&(!noteId||!session.sync?.conflict_note_ids?.includes(noteId));}
export function useCanEditNote(noteId?:string){return canEditNote(useAuth().session,noteId);}

type Auth={session:Session;refresh:()=>Promise<void>;login:(username:string,password:string)=>Promise<void>;logout:()=>Promise<void>;openLogin?:()=>void;closeLogin?:()=>void;loginOpen?:boolean;switchRole?:(role:Role)=>Promise<void>};
export const AuthContext=createContext<Auth>({session:local,refresh:async()=>{},login:async()=>{},logout:async()=>{}});
export const useAuth=()=>useContext(AuthContext);
export const useCapabilities=()=>capabilitiesFor(useAuth().session);
async function request(path:string,body?:unknown):Promise<Session>{const response=await fetch(apiUrl('auth/'+path),{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',cache:'no-store',body:body===undefined?undefined:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw new Error(result.error??'登录失败');return result;}
export function AuthProvider({children}:{children:ReactNode}){
 const [session,setSession]=useState<Session|null>(null),[error,setError]=useState('');
 const sequence=useRef(0),transition=useRef(false),acceptedIdentity=useRef('');
 const [loginOpen,setLoginOpen]=useState(()=>typeof window!=='undefined'&&window.location.pathname.replace(/\/+$/,'').endsWith('/admin'));
 const returnFocus=useRef<HTMLElement|null>(null),currentMode=useRef<Session['mode']|null>(null);
 function closeLogin(){setLoginOpen(false);requestAnimationFrame(()=>returnFocus.current?.focus());}
 function openLogin(){returnFocus.current=document.activeElement as HTMLElement;setLoginOpen(true);}
 async function accept(value:Session,epoch:number){if(epoch!==sequence.current)return;const key=value.mode+'|'+value.username+'|'+value.role;if(key!==acceptedIdentity.current)setSession(null);currentMode.current=value.mode;await configureReaderCache(value.mode,value.role==='guest'?null:(value.username??'local')+'|'+value.role);if(epoch!==sequence.current)return;acceptedIdentity.current=key;setSession(value);setError('');}
 async function refresh(){if(transition.current)return;const epoch=++sequence.current,value=await request('me');await accept(value,epoch);}
 useEffect(()=>{
  void refresh().catch(e=>setError(e.message));
  const expired=()=>{if(currentMode.current!=='public')return;sequence.current++;void configureReaderCache('public',null);setSession(s=>s?.mode==='public'?{...s,role:'guest',account_role:'guest',allowed_roles:[],username:null}:s);};
  const syncChanged=(event:Event)=>{if(transition.current)return;const sync=(event as CustomEvent<SyncStatus|undefined>).detail;if(sync?.state){sequence.current++;setSession(s=>s?{...s,sync}:s);}else void refresh().catch(()=>{});};
  window.addEventListener('wxq:sync-changed',syncChanged);window.addEventListener('wxq:session-expired',expired);
  return()=>{sequence.current++;window.removeEventListener('wxq:sync-changed',syncChanged);window.removeEventListener('wxq:session-expired',expired);};
 },[]);
 const interval=syncPollMs(session);
 useEffect(()=>{const timer=setInterval(()=>void refresh().catch(()=>{}),interval);return()=>clearInterval(timer);},[interval]);
 if(!session)return <main className="empty" role="status">{error?<>{error}<button onClick={()=>void refresh().catch(e=>setError(e.message))}>重试</button></>:'正在确认访问权限…'}</main>;
 return <AuthContext.Provider value={{session,refresh,openLogin,closeLogin,loginOpen,login:async(username,password)=>{transition.current=true;sequence.current++;try{await request('login',{username,password});}finally{transition.current=false;}await refresh();closeLogin();},logout:async()=>{transition.current=true;sequence.current++;setSession(null);await configureReaderCache('public',null);try{await request('logout',{});}finally{transition.current=false;await refresh();}},switchRole:async(role)=>{transition.current=true;const epoch=++sequence.current;setSession(null);await configureReaderCache(session.mode,null);try{await accept(await request('role',{role}),epoch);}catch(e){transition.current=false;await refresh();throw e;}finally{transition.current=false;}}}}><SessionGate key={session.mode+'|'+session.username+'|'+session.role} session={session}>{children}</SessionGate></AuthContext.Provider>;
}
export function SessionGate({session,children}:{session:Session;children:ReactNode}){
 return session.mode==='public'&&session.role==='guest'?<LoginScreen/>:<>{children}</>;
}
// Kept for existing app composition; public access is now gated before App mounts.
export function AdminAccess(){return null;}
export function LoginScreen(){
 const {login}=useAuth();
 const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 return <main className="login-screen"><section className="login-panel" aria-labelledby="login-title">
 <header><span className="brand-mark" aria-hidden="true">象</span><div><p>万象棋 · 战术手册</p><h1 id="login-title">账号登录</h1></div></header><p className="muted">请使用已有账号登录后阅读。</p>
 <form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{await login(username,password);setPassword('');}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}>
 <label>用户名<input autoFocus name="username" autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required/></label>
 <label>密码<input name="password" type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required/></label>
 {error&&<p className="error" role="alert">{error}</p>}<button className="primary" disabled={busy}>{busy?'登录中…':'登录'}</button></form></section></main>;
}
