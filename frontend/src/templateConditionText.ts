import {fileTemplateScopeId} from './templateFile';
import {keyedTemplateSyntax,lineupName} from './templateV04';
import {effectiveExpression,lineupPlayer,type TemplateGroup} from './templates';

function topLevelTokens(text:string){
 const tokens=[];
 let depth=0;
 for(const token of text.matchAll(/"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[\p{L}\p{N}_]+|[()[\]]/gu)){
  const value=token[0];
  if(value===')'||value===']')depth--;
  if(depth===0)tokens.push(token);
  if(value==='('||value==='[')depth++;
 }
 return tokens;
}

function unwrap(text:string){
 if(!text.startsWith('(')||!text.endsWith(')'))return text;
 const tokens=topLevelTokens(text);
 return tokens.length===2&&tokens[1].index===text.length-1?text.slice(1,-1).trim():text;
}

export function parseFileConditionText(text:string,syntaxVersion?:string){
 const source=text.trim();
 const scope:{player:string|null;lineup:string|null}={player:null,lineup:null};
 const tokens=topLevelTokens(source).filter(token=>source[token.index-1]!=='.'&&source[token.index+token[0].length]!=='.');
 if(tokens.some(token=>token[0]==='or'))return {...scope,expression:source};

 const clauses=[];
 let start=0;
 for(const token of tokens){
  if(token[0]!=='and')continue;
  clauses.push(source.slice(start,token.index).trim());
  start=token.index+token[0].length;
 }
 clauses.push(source.slice(start).trim());
 if(clauses.length>1&&clauses.some(clause=>!clause))return {...scope,expression:source};

 const matcher=keyedTemplateSyntax(syntaxVersion)
  ? /^我方\s*\.\s*(棋手名称|阵容名称)\s*==\s*("(?:\\.|[^"\\])*")$/u
  : /^玩家\s*\.\s*(使用棋手|使用阵容)\s+is\s+("(?:\\.|[^"\\])*")$/u;
 const remaining=clauses.filter(clause=>{
  const match=matcher.exec(clause);
  if(!match)return true;
  const key=match[1].includes('棋手')?'player':'lineup';
  if(scope[key]!==null)return true;
  try{
   const name:string=JSON.parse(match[2]);
   if(!name.trim())return true;
   scope[key]=name;
   return false;
  }catch{return true;}
 });
 return {...scope,expression:remaining.length===1?unwrap(remaining[0]):remaining.join(' and ')};
}


export function resolveConditionEdit(value:string,group:TemplateGroup,name:(id:string)=>string,options:{
 fileMode?:boolean;players?:{id:string;name:string}[];lineups?:{id:string;title:string;player_id?:string}[];
}){
 const version=group.syntax_version,{player_id:player,lineup_note_id:lineup}=group.scope;
 const playerName=player&&name(player),currentLineup=lineup&&name(lineup);
 const canonicalLineup=(title:string)=>keyedTemplateSyntax(version)?lineupName(title):title;
 const original=effectiveExpression(playerName,currentLineup,group.expression??'',version);
 if(value.trim()===original.trim())return {scope:group.scope,expression:group.expression??''};
 const parsed=parseFileConditionText(value,version);
 const playerId=parsed.player===playerName?player:parsed.player===null?null:options.fileMode?fileTemplateScopeId('player',parsed.player):
  options.players?.find(row=>row.name===parsed.player)?.id??null;
 const compatibleLineups=options.lineups?.filter(row=>!playerId||lineupPlayer(row)===playerId)??[];
 const matches=compatibleLineups.filter(row=>canonicalLineup(row.title)===parsed.lineup);
 const currentCanonicalLineup=currentLineup===null?null:canonicalLineup(currentLineup);
 const lineupId=parsed.lineup===currentCanonicalLineup&&(options.fileMode||playerId===player||!lineup||compatibleLineups.some(row=>row.id===lineup))?lineup:
  parsed.lineup===null?null:options.fileMode?fileTemplateScopeId('lineup',parsed.lineup):matches.length===1?matches[0].id:null;
 const baseline=parseFileConditionText(original,version);
 const body=baseline.player===playerName&&baseline.lineup===currentCanonicalLineup&&baseline.expression===parsed.expression
  ?group.expression??'':parsed.expression;
 return {scope:{player_id:playerId,lineup_note_id:lineupId},
  expression:effectiveExpression(playerId?null:parsed.player,lineupId?null:parsed.lineup,body,version)};
}
