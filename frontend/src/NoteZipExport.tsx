import {useState} from 'react';
import type {Season} from './seasons';
import {assertRequestGeneration,requestGeneration,sessionFetch} from './sessionRequest';
import {apiUrl} from './urls';

export default function NoteZipExport({season}:{season:Season}){
 const [downloading,setDownloading]=useState(false);
 const [error,setError]=useState('');
 async function download(){
  setDownloading(true);
  setError('');
  const epoch=requestGeneration();
  try{
   const response=await sessionFetch(apiUrl('notes/export.zip?season='+season),{cache:'no-store'});
   if(!response.ok){
    const result=await response.json().catch(()=>null);
    throw new Error(result?.error??'下载失败，请重试');
   }
   if(response.headers.get('Content-Type')!=='application/zip')throw new Error('下载失败，请重试');
   const blob=await response.blob();
   assertRequestGeneration(epoch);
   const url=URL.createObjectURL(blob);
   const link=document.createElement('a');
   link.href=url;
   link.download='wanxiangqi-notes-'+season+'.zip';
   link.click();
   window.setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){
   setError(e instanceof Error?e.message:'下载失败，请重试');
  }finally{
   setDownloading(false);
  }
 }
 return <div className="note-zip-export">
  <button type="button" disabled={downloading} onClick={()=>void download()}>
   {downloading?'正在打包笔记…':'导出当前赛季笔记 ZIP'}
  </button>
  {error&&<p className="error" role="alert">{error}</p>}
 </div>;
}
