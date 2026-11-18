import type {TemplateEvent, TemplateGroup} from './templates';

// Only unconditional equalities identify an action's participants. Other facts
// (including entities mentioned under negation) belong in the trigger conditions.
export function fixedArguments(group: TemplateGroup) {
 const values = new Map<string,string>();
 const ambiguous = new Set<string>();
 function remember(key:string, value:string) {
  if(values.has(key) && values.get(key)!==value) ambiguous.add(key);
  values.set(key,value);
 }
 function visit(expression:string) {
  const source=expression.trim();
  let depth=0, start=0, outerEnd=-1;
  const parts:string[]=[];
  for(const match of source.matchAll(/"(?:\\.|[^"\\])*"|[()[\]{}]|\b(?:and|or)\b/gu)) {
   const token=match[0], index=match.index!;
   if(token.startsWith('"')) continue;
   if(['(','[','{'].includes(token)) depth++;
   else if([')',']','}'].includes(token)) {depth--; if(depth===0 && outerEnd<0) outerEnd=index;}
   else if(depth===0) {
    if(token==='or') return;
    parts.push(source.slice(start,index));start=index+token.length;
   }
  }
  if(parts.length) {parts.push(source.slice(start));parts.forEach(visit);return;}
  if(source.startsWith('(') && outerEnd===source.length-1) {visit(source.slice(1,-1));return;}
  const comparison=/^([a-z][a-z0-9_]*)(?:\.(?:名称|name))?\s*(?:\bis\b|==)\s*("(?:\\.|[^"\\])*"|-?\d+(?:\.\d+)?)$/u.exec(source);
  if(comparison) remember(comparison[1],comparison[2].startsWith('"')?JSON.parse(comparison[2]):comparison[2]);
 }
 if(group.expression?.trim()) visit(group.expression);
 else for(const condition of group.conditions) {
  if(condition.operator!=='eq') continue;
  const value=condition.value;
  if(typeof value==='string'||typeof value==='number') remember(condition.parameter_key,String(value));
  else if(value && typeof value==='object' && 'name' in value) remember(condition.parameter_key,String(value.name));
 }
 for(const key of ambiguous) values.delete(key);
 return values;
}

export function templateAction(group:TemplateGroup,event?:TemplateEvent,values=fixedArguments(group)):string {
 if(!event) return group.event_id;

 const [a,b,c]=['arg1','arg2','arg3'].map(key=>values.get(key));
 const actionName=event.name.replace(/^解释为何/,'');
 switch(actionName) {
  case '上阵英雄': return '上阵'+(a??'英雄');
  case '合成英雄': return '合成'+(a??'英雄');
  case '购买英雄': return '购买'+(a??'英雄');
  case '购买效果牌': return '购买'+(a??'效果牌');
  case '从手牌出售英雄': return '从手牌出售'+(a??'英雄');
  case '从战场出售英雄': return '从战场出售'+(a??'英雄');
  case '选择英雄': case '选择效果牌': case '选择棋手技能': case '选择天赋': return b?'选择'+b:actionName;
  case '使用无目标效果牌': case '使用棋手技能': return a?'使用'+a:actionName;
  case '棋手升级': return a?'棋手升到'+a+'级':actionName;
  case '穿戴装备': return '给'+(a??'英雄')+'穿戴'+(b??'装备');
  case '铸造装备': return '将'+(a??'英雄')+'的'+(b??'旧装备')+'铸造成'+(c??'新装备');
  case '转移装备': return '将'+(a??'原持有英雄')+'的'+(b??'装备')+'转移给'+(c??'接收英雄');
  case '对目标使用棋手技能': return '对'+(a??'目标')+'使用'+(b??'棋手技能');
  case '对目标使用效果牌': return '对'+(a??'目标')+'使用'+(b??'效果牌');
  default: return actionName;
 }
}
const parameterRoles:Record<string,readonly string[]>={
 '上阵英雄':['本次上阵的英雄'], '合成英雄':['本次合成的英雄'],
 '购买英雄':['买下的英雄','商店中未选择的牌'], '购买效果牌':['买下的效果牌','商店中未选择的牌'],
 '从手牌出售英雄':['从手牌卖出的英雄'], '从战场出售英雄':['从战场卖出的英雄'],
 '选择英雄':['候选英雄列表','选中的英雄'], '选择效果牌':['候选效果牌列表','选中的效果牌'],
 '选择天赋':['候选天赋列表','选中的天赋'], '选择棋手技能':['候选棋手技能列表','选中的棋手技能'],
 '使用棋手技能':['使用的棋手技能'], '使用无目标效果牌':['使用的效果牌'],
 '对目标使用棋手技能':['技能作用的目标','使用的棋手技能'], '对目标使用效果牌':['效果牌作用的目标','使用的效果牌'],
 '穿戴装备':['穿戴装备的英雄','穿上的装备'], '铸造装备':['持有装备的英雄','铸造前的装备','铸造后的装备'],
 '转移装备':['原持有英雄','被转移的装备','接收装备的英雄'], '棋手升级':['升级后的棋手等级'],
};

export function parameterRole(event:TemplateEvent,parameter:TemplateEvent['parameters'][number]){
 const match=/^arg([1-9]\d*)$/.exec(parameter.key);
 const role=match && parameterRoles[event.name.replace(/^解释为何/,'')]?.[Number(match[1])-1];
 return parameter.name!==parameter.key ? parameter.name : role || '';
}
