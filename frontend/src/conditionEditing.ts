import {listPaths,type ConditionCatalog} from './templateRules';
import {catalogV04,slotToken,v04Paths} from './templateV04';
import rawCatalog from '../../src/condition/catalog.json?raw';
import type {TemplateEvent} from './templates';

export type ConditionEditingConfig={event?:TemplateEvent;catalog?:ConditionCatalog;v04?:boolean};
type Field={label:string;type:string;guard?:boolean;insert?:string;selection?:{start:number;end:number}};
const defaultCatalog:ConditionCatalog=JSON.parse(rawCatalog);
const brackets:Record<string,string>={'(':')','[':']','{':'}'};
const closing=new Set(Object.values(brackets));
const tokens=(value:string)=>[...value.matchAll(/"(?:\\[\s\S]|[^"\\])*(?:"|\\?$)|'(?:\\[\s\S]|[^'\\])*(?:'|\\?$)|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|[\p{L}_][\p{L}\p{N}_]*|[^\s]/gu)];
const quoted=(token:string)=>token.startsWith('"')||token.startsWith("'");
const inQuotedText=(value:string,offset:number)=>tokens(value).some(token=>quoted(token[0])&&token.index<offset&&offset<=token.index+token[0].length);
const stringOrWhitespace=/"(?:\\[\s\S]|[^"\\])*(?:"|\\?$)|'(?:\\[\s\S]|[^'\\])*(?:'|\\?$)|\s+/gu;

export function normalizeConditionInput(value:string){
 // A complete literal may contain smart quotes that belong to the card name.
 const normalized=value.replace(/("(?:\\[\s\S]|[^"\\])*"|'(?:\\[\s\S]|[^'\\])*(?:'|\\?$))|("(?:\\[\s\S]|[^"\\“”])*)?[“”]/gu,
  (_match,literal,opening)=>literal??(opening??'')+'"');
 return normalized.replace(/"(?:\\[\s\S]|[^"\\])*(?:"|\\?$)|'(?:\\[\s\S]|[^'\\])*(?:'|\\?$)|。/gu,token=>token==='。'?'.':token);
}

export function conditionBracketRanges(value:string){
 const stack:{token:string;start:number;depth:number}[]=[],ranges:{start:number;end:number;depth:number}[]=[],unmatched:number[]=[];
 for(const token of tokens(value)){
  const [entry]=token;
  if(brackets[entry])stack.push({token:entry,start:token.index,depth:stack.length});
  if(!closing.has(entry))continue;
  const open=stack.at(-1);
  if(open&&brackets[open.token]===entry){stack.pop();ranges.push({start:open.start,end:token.index,depth:open.depth});}
  else unmatched.push(token.index);
 }
 return {ranges:ranges.sort((a,b)=>a.start-b.start),unmatched:[...unmatched,...stack.map(item=>item.start)]};
}

export function conditionPair(value:string,caret:number){
 const {ranges,unmatched}=conditionBracketRanges(value);
 for(const position of [caret,caret-1]){
  if(unmatched.includes(position))return [position];
  const pair=ranges.find(range=>range.start===position||range.end===position);
  if(pair)return [pair.start,pair.end];
 }
 const active=ranges.reverse().find(range=>range.start<caret&&range.end>=caret);
 return active?[active.start,active.end]:[];
}

export const compactCondition=(value:string)=>value.trim().replace(stringOrWhitespace,part=>quoted(part)?part:' ');

const own=<T,>(table:Record<string,T>,key:string)=>Object.hasOwn(table,key)?table[key]:undefined;

function v04Type(path:string,event?:TemplateEvent,item?:string){
 const [root,...fields]=path.split('.');
 let type=root?own(catalogV04.roots,root):item;
 let guard=false;
 for(const label of fields){
  if(!type)break;
  guard||=type.endsWith('?');
  const table=type==='动作'?own(catalogV04.actions,own(catalogV04.events,event?.name??'')?.action??''):own(catalogV04.types,type.replace(/\?$/u,''));
  type=table&&Object.hasOwn(table,label)?table[label]:undefined;
 }
 return {type,guard};
}

function predicateSource(value:string,dot:number){
 const stack:{opener:string;name?:string;start:number;source?:string}[]=[];
 let previous='';
 for(const token of tokens(value.slice(0,dot))){
  const [part]=token;
  if(brackets[part])stack.push({opener:part,name:part==='('?previous:undefined,start:token.index+1});
  if(closing.has(part))stack.pop();
  if(part===','){
   const frame=stack.at(-1);
   if(frame?.opener==='('&&!frame.source)frame.source=value.slice(frame.start,token.index);
  }
  previous=part;
 }
 const call=stack.reverse().find(frame=>frame.name&&/^(any|all|none|count|sum|filter)$/u.test(frame.name));
 return call?.source?.trim().replace(/^(?:filter\s*\(\s*)+/u,'').split(',')[0].trim().replace(/\s+/gu,'');
}

function v04Fields(parent:string,value:string,dot:number,event?:TemplateEvent):Field[]{
 const source=parent.startsWith('.')||!parent?predicateSource(value,dot):undefined;
 const item=source?v04Type(source,event).type?.match(/^Array<(.+)>$/u)?.[1]:undefined;
 const {type,guard}=parent?v04Type(parent,event,item):{type:item,guard:false};
 if(!type)return [];
 const bare=type.replace(/\?$/u,'');
 const table=bare==='动作'?own(catalogV04.actions,own(catalogV04.events,event?.name??'')?.action??''):own(catalogV04.types,bare);
 return Object.entries(table??{}).map(([label,kind])=>({label,type:kind,guard:guard||type.endsWith('?')||
  bare==='卡牌'&&catalogV04.hero_fields.includes(label)&&!catalogV04.hero_paths.includes(parent.split('.').at(-1)??'')&&!(item&&source?.endsWith('.场上英雄列表')&&!parent)}));
}

function legacyFields(parent:string,config:ConditionEditingConfig):Field[]{
 if(!parent)return [];
 return listPaths(config.event,config.catalog??defaultCatalog).flatMap(({path,type})=>{
  if(!path.startsWith(parent+'.'))return [];
  const label=path.slice(parent.length+1);
  if(!/^[\p{L}_][\p{L}\p{N}_]*(?:\(.*\))?$/u.test(label))return [];
  return [{label,type}];
 });
}

const normalize=(value:string)=>value.normalize('NFKC').toLowerCase();
function fieldRank(label:string,query:string){
 const value=normalize(label);
 if(value===query)return 0;
 if(value.startsWith(query))return 1;
 if(value.includes(query))return 2;
 let offset=0;
 for(const char of query){const next=value.indexOf(char,offset);if(next<0)return Infinity;offset=next+char.length;}
 return 3;
}

const fieldPath=/(?:(?:\.?[\p{L}_][\p{L}\p{N}_]*)(?:[ \t]*\.[ \t]*[\p{L}_][\p{L}\p{N}_]*)*[ \t]*)?\.[ \t]*([\p{L}\p{N}_]*)$/u;
// The first marked value is selected after insertion. Each insertion is valid v0.4.
const conditionSnippets=[
 ['场上有英雄','any(我方.场上英雄列表, .名称 == "«孙尚香»")','英雄在场','上阵'],
 ['手牌有英雄','any(我方.手牌列表, .卡牌类型 == "英雄" and .名称 == "«蔡文姬»")','手牌中有英雄','手中有英雄','持有'],
 ['我方主C等级','(我方.主C != nil and 我方.主C.等级 >= «40»)','主力等级','己方主C'],
 ['对手主C等级','(对手 != nil and 对手.主C != nil and 对手.主C.等级 >= «100»)','敌方主力等级','对方主C'],
 ['英雄未上场','none(我方.场上英雄列表, .名称 == "«蔡文姬»")','场上没有指定英雄','不在场'],
 ['场上英雄等级','any(我方.场上英雄列表, .名称 == "«孙尚香»" and .等级 >= 20)','指定英雄等级'],
 ['手牌没有英雄','none(我方.手牌列表, .卡牌类型 == "英雄" and .名称 == "«蔡文姬»")','手中缺英雄'],
 ['场上英雄人数','len(我方.场上英雄列表) >= «2»','人数','上阵人数'],
 ['场上没有英雄','len(我方.场上英雄列表) == 0','空场'],
 ['场上没有其他英雄','none(我方.场上英雄列表, .名称 != "«孙尚香»")','无其他英雄'],
 ['场上某阵营人数','count(我方.场上英雄列表, .阵营 == "«三分之地»") >= 2','阵营计数'],
 ['商店有英雄','any(我方.商店列表, .卡牌类型 == "英雄" and .名称 == "«曹操»")','商店刷到'],
 ['手牌有效果牌','any(我方.手牌列表, .卡牌类型 == "效果牌" and .名称 == "«换帅»")','手中有效果牌'],
 ['手牌有装备','any(我方.手牌列表, .卡牌类型 == "装备" and .名称 == "«驱雷»")','手中有装备'],
 ['我方阵容名称','我方.阵容名称 == "«三分登场»"','当前阵容'],
 ['棋手等级','我方.等级 >= «4»','玩家等级'],
 ['当前阶段','对局.当前阶段 == "«前期»"','前中后期'],
 ['当前回合数','对局.当前回合数 <= «3»','回合上限','前三回合'],
 ['容错数','我方.容错数 <= «1»','剩余容错'],
 ['剩余能量','我方.剩余能量 >= «3»','能量足够'],
].map(([label,pattern,...aliases])=>{
 const slot=/«([^»]+)»/u.exec(pattern);
 const insert=slot?pattern.replace(slot[0],slot[1]):pattern;
 const selection=slot?{start:slot.index,end:slot.index+slot[1].length}:undefined;
 const field:Field={label,type:'',insert,selection};
 return {field,aliases};
});

function snippetCompletion(value:string,caret:number){
 const match=/[*＊]([\p{L}\p{N}_]*)$/u.exec(value.slice(0,caret));
 if(!match||inQuotedText(value,match.index))return null;
 const prefix=value.slice(0,match.index).trimEnd();
 if(prefix&&!/(?:\(|\b(?:and|or|not))$/u.test(prefix))return null;
 const query=normalize(match[1]),suffix=value.slice(caret).match(/^[\p{L}\p{N}_]*/u)?.[0]??'';
 const choices=conditionSnippets.map(({field,aliases})=>({
  field,rank:Math.min(fieldRank(field.label,query),...aliases.map(alias=>fieldRank(alias,query))),
 })).filter(item=>Number.isFinite(item.rank)).sort((a,b)=>a.rank-b.rank).map(({field})=>field);
 return {start:match.index,end:caret+suffix.length,dot:match.index,choices,snippet:true};
}
export function conditionCompletion(value:string,caret:number,config:ConditionEditingConfig){
 const snippet=config.v04?snippetCompletion(value,caret):null;
 if(snippet)return snippet;
 const variable=utteranceSlotCompletion(value,caret,config,false);
 if(variable)return variable;
 const before=value.slice(0,caret),match=fieldPath.exec(before);
 if(!match||inQuotedText(value,caret))return null;
 const start=caret-match[1].length,dot=before.lastIndexOf('.');
 const prior=value.slice(match.index,dot);
 const prefix=/^(?:and|or|not|in|is|has)\s+$/u.test(prior)?'':prior.replace(/\s+/gu,'');
 if(!prefix&&/[\p{L}\p{N}_.)\]]/u.test(value[dot-1]??''))return null;
 const suffix=value.slice(caret).match(/^[\p{L}\p{N}_]*/u)?.[0]??'';
 const fields=config.v04?v04Fields(prefix,value,dot,config.event):legacyFields(prefix,config);
 if(!fields.length)return null;
 const query=normalize(match[1]);
 const choices=fields.map(field=>({field,rank:fieldRank(field.label,query)})).filter(item=>isFinite(item.rank))
  .sort((a,b)=>a.rank-b.rank).map(({field})=>field);
 return {start,end:caret+suffix.length,dot,choices};
}

export function utteranceSlotInput(value:string,caret:number,slots=true){
 const before=value.slice(0,caret),trigger=/(?:\{+|「)([\p{L}\p{N}_.。]*」?)$/u.exec(before);
 if(!trigger||!slots&&inQuotedText(value,trigger.index))return {value,caret};
 const prefix=before.slice(0,trigger.index)+'{{'+trigger[1].replaceAll('。','.');
 return {value:prefix+value.slice(caret),caret:prefix.length};
}

export function utteranceSlotCompletion(value:string,caret:number,config:ConditionEditingConfig,slots=true){
 const before=value.slice(0,caret),start=before.lastIndexOf('{{');
 if(start<0||!slots&&inQuotedText(value,start))return null;
 const match=/^([\p{L}\p{N}_.]*)(」?)$/u.exec(before.slice(start+2));
 if(!match)return null;
 const query=normalize(match[1]);
 const suffix=match[2]?'':value.slice(caret).match(/^[\p{L}\p{N}_.。]*(?:\}\}|」)/u)?.[0]??'';
 const insert=(path:string)=>slots?slotToken(path,!!config.v04):path;
 const fields:Field[]=config.v04
  ? v04Paths(config.event?.name??'').map(label=>({label,type:'',insert:insert(label)}))
  : listPaths(config.event,config.catalog??defaultCatalog).filter(({path,type})=>
   /^[\p{L}_][\p{L}\p{N}_]*(?:\.[\p{L}_][\p{L}\p{N}_]*)*$/u.test(path)&&
   !type.startsWith('Array<')&&!['对局','商店'].includes(type)).map(({path:label,type})=>({label,type,insert:insert(label)}));
 const choices=fields.map(field=>({field,rank:fieldRank(field.label,query)})).filter(item=>isFinite(item.rank))
  .sort((a,b)=>a.rank-b.rank).map(({field})=>field);
 return {start,end:caret+suffix.length,dot:start,choices,variable:true};
}
