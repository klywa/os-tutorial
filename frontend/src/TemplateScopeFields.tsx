import {useId} from 'react';
import {lineupPlayer,selectTemplateScope,type TemplateGroup} from './templates';
import {fileTemplateScopeId,fileTemplateScopeName} from './templateFile';

type Scope=TemplateGroup['scope'];
export type TemplateScopeOptions={
 players:{id:string;name:string}[];
 lineups:{id:string;title:string;player_id?:string}[];
 scopeName:(id:string)=>string;
 localFile?:boolean;
};

export default function TemplateScopeFields({scope,options,onChange,disabled=false}:{scope:Scope;options:TemplateScopeOptions;onChange:(scope:Scope)=>void;disabled?:boolean}){
 const {players,lineups,scopeName,localFile}=options;
 const uid=useId(),player=scope.player_id,lineup=scope.lineup_note_id;
 const matchingLineups=lineups.filter(note=>lineupPlayer(note)&&(!player||lineupPlayer(note)===player));
 if(localFile){
  const playerName=player?(fileTemplateScopeName('player',player)??scopeName(player)):'';
  const lineupName=lineup?(fileTemplateScopeName('lineup',lineup)??scopeName(lineup)):'';
  return <>
   <label>适用棋手<input list={uid+'-players'} value={playerName} placeholder="通用棋手" disabled={disabled} onChange={e=>{
    const name=e.target.value;
    onChange({...scope,player_id:players.find(row=>row.name===name)?.id??fileTemplateScopeId('player',name)});
   }}/></label>
   <datalist id={uid+'-players'}>{[...new Set(players.map(row=>row.name))].map(name=><option key={name} value={name}/>)}</datalist>
   <label>阵容棋手组合<input list={uid+'-lineups'} value={lineupName} placeholder="通用组合" disabled={disabled} onChange={e=>{
    const name=e.target.value;
    onChange({...scope,lineup_note_id:matchingLineups.find(row=>row.title===name)?.id??fileTemplateScopeId('lineup',name)});
   }}/></label>
   <datalist id={uid+'-lineups'}>{[...new Set(matchingLineups.map(row=>row.title))].map(title=><option key={title} value={title}/>)}</datalist>
  </>;
 }
 return <>
  <label>适用棋手<select value={player??''} disabled={disabled} onChange={e=>onChange(selectTemplateScope(scope,'player',e.target.value,lineups))}>
   <option value="">通用棋手</option>
   {player&&!players.some(row=>row.id===player)&&<option value={player} disabled>{scopeName(player)}（资料暂缺/已下架）</option>}
   {players.map(row=><option key={row.id} value={row.id}>{row.name}</option>)}
  </select></label>
  <label>阵容棋手组合<select value={lineup??''} disabled={disabled} onChange={e=>onChange(selectTemplateScope(scope,'lineup',e.target.value,lineups))}>
   <option value="">通用组合</option>
   {lineup&&!matchingLineups.some(row=>row.id===lineup)&&<option value={lineup} disabled>{scopeName(lineup)}（资料暂缺/已下架）</option>}
   {matchingLineups.map(row=><option key={row.id} value={row.id}>{row.title}</option>)}
  </select></label>
 </>;
}
