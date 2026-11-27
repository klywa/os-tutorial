import {keyedTemplateSyntax} from './templateV04';
import {fixedArguments,resolveTemplateEntities,type TemplateEntity,type TemplateEvent,type TemplateGroup,type TemplateParameter} from './templates';
export {fixedArguments} from './templates';

export function fileTriggerChanged(before:TemplateGroup,after:TemplateGroup,oldEvent?:TemplateEvent,nextEvent?:TemplateEvent){
 if(before.event_id!==after.event_id)return true;
 if(keyedTemplateSyntax(before.syntax_version)||keyedTemplateSyntax(after.syntax_version))
  return keyedTemplateSyntax(before.syntax_version)!==keyedTemplateSyntax(after.syntax_version)||before.extra_key!==after.extra_key;
 const a=fixedArguments(before),b=fixedArguments(after);
 if(a.size!==b.size||[...a].some(([key,value])=>b.get(key)!==value))return true;
 const used=(group:TemplateGroup)=>{
  const expression=(group.expression??'').replace(/"(?:[^"\\]|\\.)*"/g,'');
  const keys=new Set(expression.match(/[\p{L}_][\p{L}\p{N}_]*/gu)??[]);
  for(const condition of group.conditions)keys.add(condition.parameter_key);
  for(const row of group.utterances){
   for(const match of row.text.matchAll(/(?<!\{)\{([A-Za-z_]\w*)(?:\.[^{}]+)?\}(?!\})/g))keys.add(match[1]);
  }
  return keys;
 };
 const keys=new Set([...used(before),...used(after)]);
 return [...keys].some(key=>JSON.stringify(oldEvent?.parameters.find(parameter=>parameter.key===key))!==
  JSON.stringify(nextEvent?.parameters.find(parameter=>parameter.key===key)));
}

export function templateAction(group:TemplateGroup,event?:TemplateEvent,values=fixedArguments(group,event)):string {
 if(!event) return group.event_id;

 const [a,b,c]=['arg1','arg2','arg3'].map(key=>values.get(key));
 const actionName=event.name.replace(/^解释为何/,'');
 const auction=/^竞拍目标(英雄|效果牌)(（.+）)$/u.exec(actionName);
 if(auction)return '竞拍'+(a??auction[1])+auction[2];
 switch(actionName) {
  case '建议向某阵容发展': return '向'+(a??'建议的阵容')+'方向发展';
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
 '建议向某阵容发展':['建议发展的阵容'],
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

// A literal inherits the type of its argument. Only one catalogue category
// can supply a portrait, including when the event admits several categories.
export function argumentCardIds(parameter:TemplateParameter,value:string,cards:(TemplateEntity&{category:string;aliases?:string[]})[]){
 if(parameter.type!=='entity')return [];
 const refs=resolveTemplateEntities(value,cards,parameter.entity_categories);
 const ids=new Set(refs.map(ref=>ref.id));
 const categories=new Set(cards.filter(card=>ids.has(card.id)).map(card=>card.category));
 return categories.size===1?[...ids]:[];
}
