import {templateAction} from './templateAction';
import {renderRule} from './templateRules';
import {catalogV04,readV04Condition,validateExtraKey,validateV04,validateV04Template,v04ConditionKey,wildcardKey} from './templateV04';
import {actionArgumentFields,fixedArguments,templateId,type TemplateEvent,type TemplateGroup,type TemplateParameter} from './templates';

export function copyConditionExpression(group:TemplateGroup,event:TemplateEvent){
 if(group.editor_mode==='tree'&&group.condition_tree)return renderRule(group.condition_tree);
 if(group.expression!==undefined)return group.expression;
 return group.conditions.flatMap(({parameter_key:key,operator,value})=>{
  if(operator==='between'&&Array.isArray(value))return [key+' >= '+JSON.stringify(value[0]),key+' <= '+JSON.stringify(value[1])];
  const parameter=event.parameters.find(row=>row.key===key);
  const entity=parameter?.type==='entity'&&value&&typeof value==='object'&&'name' in value;
  const left=entity?key+'.名称':key;
  const right=JSON.stringify(entity?value.name:value);
  const equality=entity||parameter?.type==='text'?'is':'==';
  const comparison=({gt:'>',gte:'>=',lt:'<',lte:'<='} as Record<string,string>)[operator]??equality;
  const expression=[left,comparison,right].join(' ');
  return [operator==='ne'?'not ('+expression+')':expression];
 }).join(' and ');
}

export function sameCopyCondition(left:string,right:string,v04:boolean){
 const key=(value:string)=>JSON.stringify(value.match(/"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[\p{L}\p{N}_]+|>=|<=|==|!=|[^\s]/gu)??[]);
 if(v04){try{return v04ConditionKey(left)===v04ConditionKey(right);}catch{/* Invalid drafts are validated on save. */}}
 return key(left)===key(right);
}

export function canonicalTemplateName(group:TemplateGroup,event?:TemplateEvent){
 if(!event)return undefined;
 const definition=catalogV04.events[event.name];
 if(!definition)return undefined;
 const values=fixedArguments(group,event);
 if(group.syntax_version==='0.4'){
  try{validateExtraKey(event.name,group.extra_key??'');}catch{return undefined;}
 }else if(!definition.key.length||definition.key.some(field=>!values.has('arg'+(actionArgumentFields(event).indexOf(field)+1))))return undefined;
 const action=event.name.replace(/^解释为何/u,'');
 if(!event.name.startsWith('解释为何'))return event.name;
 if(action==='建议向某阵容发展')return '解释为何建议向'+(values.get('arg1')??'建议发展的阵容')+'发展';
 if(action==='移动主C和主T'||action==='移动前后排')return '解释为何移动'+(values.get('arg1')??action.slice(2));
 if(action==='使用关键效果牌'&&values.has('arg1'))return '解释为何使用'+values.get('arg1');
 if(action==='棋手升级')return '解释为何棋手升到'+(values.get('arg1')??'目标等级')+'级';
 if(action==='对目标使用效果牌'||action==='对目标使用棋手技能')
  return '解释为何对目标使用'+(values.get('arg2')??action.slice('对目标使用'.length));
 return '解释为何'+templateAction(group,event,values);
}

export function templateCardGroups(groups:TemplateGroup[],events:ReadonlyMap<string,TemplateEvent>){
 const buckets=new Map<string,TemplateGroup[]>();
 for(const group of groups){
  const event=events.get(group.event_id),name=canonicalTemplateName(group,event);
  const key=name?JSON.stringify([event!.name,name]):group.id;
  const bucket=buckets.get(key)??[];
  if(!bucket.length)buckets.set(key,bucket);
  bucket.push(group);
 }
 return [...buckets.values()];
}

export function moveTemplateEvent(group:TemplateGroup,before:TemplateEvent,after:TemplateEvent){
 if(group.event_id===after.id)return group;
 let next={...group,event_id:after.id};
 if(group.syntax_version==='0.4'){
  const source=catalogV04.events[before.name],target=catalogV04.events[after.name];
  if(!source||!target)throw new Error('请选择已注册的解释事件');
  validateExtraKey(before.name,group.extra_key??'');
  const values=(group.extra_key??'').split('-');
  if(source.key.some((field,index)=>values[index]!=='*'&&!target.key.includes(field)))
   throw new Error('目标事件无法保留原有固定参数');
  const extra_key=target.key.map(field=>values[source.key.indexOf(field)]??'*').join('-');
  validateExtraKey(after.name,extra_key);
  validateV04(after.name,group.expression??'');
  group.utterances.forEach(row=>validateV04Template(after.name,row.text));
  next={...next,extra_key};
 }else{
  const definitions=new Map(after.parameters.map(parameter=>[parameter.key,parameter]));
  const used=new Set([...group.conditions.map(condition=>condition.parameter_key),...fixedArguments(group).keys()]);
  const rule=(group.expression??'').replace(/"(?:[^"\\]|\\.)*"/g,'');
  for(const parameter of before.parameters){
   if(rule.match(/[\p{L}_][\p{L}\p{N}_]*/gu)?.includes(parameter.key)||group.utterances.some(row=>row.text.includes('{'+parameter.key)))used.add(parameter.key);
   const target=definitions.get(parameter.key);
   if(used.has(parameter.key)&&(!target||target.type!==parameter.type||target.dsl_type!==parameter.dsl_type))
    throw new Error('目标事件无法保留参数 '+parameter.name);
  }
 }
 return {...next,name:canonicalTemplateName(next,after)??after.name};
}

export function canEditTemplateArgument(group:TemplateGroup,event:TemplateEvent,parameter:TemplateParameter){
 if(group.syntax_version!=='0.4')return parameter.type!=='boolean'&&!parameter.dsl_type?.startsWith('Array<');
 const field=actionArgumentFields(event)[Number(parameter.key.slice(3))-1];
 return !!catalogV04.events[event.name]?.key.includes(field);
}

export function templateTriggerParameters(group:TemplateGroup,event:TemplateEvent):TemplateParameter[]{
 if(group.syntax_version!=='0.4')return event.parameters;
 const definition=catalogV04.events[event.name];
 if(!definition)return event.parameters;
 const fields=actionArgumentFields(event);
 const action=catalogV04.actions[definition.action];
 const missing=definition.key.flatMap(field=>{
  const key='arg'+(fields.indexOf(field)+1);
  if(event.parameters.some(parameter=>parameter.key===key))return [];
  const dsl_type=action[field];
  const type=dsl_type==='卡牌'?'entity':dsl_type==='int'?'number':'text';
  const category=field.includes('装备')?'equipment':field.includes('英雄')||event.name.includes('英雄')||event.name.includes('移动')?'heroes':
   event.name.includes('效果牌')?'effect-cards':event.name.includes('天赋')?'talents':undefined;
  return [{id:key,key,name:field,type,dsl_type,entity_categories:type==='entity'&&category?[category]:undefined} satisfies TemplateParameter];
 });
 return [...event.parameters,...missing];
}

function editConjuncts(source:string,edit:(term:string)=>string,removeEmpty=false):string{
 let depth=0,start=0,outerEnd=-1;
 const terms:string[]=[];
 for(const match of source.matchAll(/"(?:\\.|[^"\\])*"|[()[\]{}]|(?<![\p{L}\p{N}_])(?:and|or)(?![\p{L}\p{N}_])/gu)){
  const [token]=match,index=match.index;
  if(token.startsWith('"'))continue;
  if('([{'.includes(token))depth++;
  else if(')]}'.includes(token)){
   if(--depth===0&&outerEnd<0)outerEnd=index;
  }else if(!depth){
   if(token==='or')return source;
   terms.push(source.slice(start,index));start=index+token.length;
  }
 }
 if(terms.length){
  const updated=[...terms,source.slice(start)].map(term=>editConjuncts(term,edit,removeEmpty));
  return removeEmpty?updated.map(term=>term.trim()).filter(Boolean).join(' and '):updated.join('and');
 }
 const trimmed=source.trim();
 const offset=source.indexOf(trimmed);
 if(trimmed.startsWith('(')&&outerEnd===offset+trimmed.length-1){
  const inner=editConjuncts(source.slice(offset+1,outerEnd),edit,removeEmpty);
  return removeEmpty&&!inner.trim()?'':source.slice(0,offset+1)+inner+source.slice(outerEnd);
 }
 const next=edit(trimmed);
 return next===trimmed?source:source.slice(0,offset)+next+source.slice(offset+trimmed.length);
}

export function startTemplateEventCopy(group:TemplateGroup,before:TemplateEvent,after:TemplateEvent){
 const v04=group.syntax_version==='0.4';
 const definition=catalogV04.events[before.name];
 const values=(group.extra_key??'').split('-');
 const fixed=fixedArguments(group,before);
 const expression=editConjuncts(copyConditionExpression(group,before),term=>{
  if(!v04){
   const binding=fixedArguments({...group,expression:term,conditions:[]},before);
   return [...binding].some(([key,value])=>fixed.get(key)===value)?'':term;
  }
  const node=readV04Condition(term);
  if(!definition||node?.kind!=='binary'||node.op!=='==')return term;
  const [path,literal]=node.left.kind==='path'?[node.left,node.right]:[node.right,node.left];
  if(path.kind!=='path'||path.parts[0]!=='动作'||literal.kind!=='literal')return term;
  const index=definition.key.indexOf(path.parts[1]);
  const isFixedPath=path.parts.length===2||path.parts.length===3&&path.parts[2]==='名称';
  return isFixedPath&&values[index]===literal.value?'':term;
 },true);
 const next:TemplateGroup={...group,event_id:after.id,extra_key:v04?wildcardKey(after.name):undefined,
  conditions:[],expression,condition_tree:null,editor_mode:'text'};
 return {...next,name:canonicalTemplateName(next,after)??after.name};
}

export function changeTemplateArgument(group:TemplateGroup,event:TemplateEvent,parameter:TemplateParameter,input:string|null,entityId?:string){
 const value=input?.trim()??null;
 if(value==='')throw new Error('请填写参数值');
 let next=group;
 if(group.syntax_version==='0.4'){
  const field=actionArgumentFields(event)[Number(parameter.key.slice(3))-1];
  const index=catalogV04.events[event.name].key.indexOf(field);
  const values=(group.extra_key??'').split('-');
  if(index<0||value?.includes('-'))throw new Error('此参数无法用作固定值');
  values[index]=value??'*';
  const extra_key=values.join('-');
  validateExtraKey(event.name,extra_key);
  const old=(group.extra_key??'').split('-')[index];
  if(value===null&&old==='*')return group;
  const expression=group.expression===undefined?undefined:editConjuncts(group.expression,term=>{
   const node=readV04Condition(term);
   if(node?.kind!=='binary'||node.op!=='==')return term;
   const [path,literal]=node.left.kind==='path'?[node.left,node.right]:[node.right,node.left];
   const expectedPath=['动作',field,...(parameter.type==='entity'?['名称']:[])].join('.');
   if(path.kind!=='path'||path.parts.join('.')!==expectedPath||literal.kind!=='literal'||literal.value!==old)return term;
   return value===null?'':expectedPath+' == '+(literal.type==='int'?value:JSON.stringify(value));
  },value===null);
  if(expression!==undefined)validateV04(event.name,expression);
  next={...group,extra_key,expression};
 }else{
  const old=fixedArguments(group).get(parameter.key);
  if(value===null){
   if(old===undefined)return group;
   const conditions=group.conditions.filter(condition=>condition.parameter_key!==parameter.key||condition.operator!=='eq');
   if(!group.expression?.trim())next={...group,conditions};
   else{
    const expression=editConjuncts(group.expression,term=>
     fixedArguments({...group,expression:term,conditions:[]}).get(parameter.key)===old?'':term,true);
    next={...group,conditions,expression,editor_mode:'text',condition_tree:null};
   }
   return {...next,name:canonicalTemplateName(next,event)??group.name};
  }
  const valueToSave=parameter.type==='entity'?{id:entityId,name:value}:parameter.type==='number'?Number(value):value;
  if(parameter.type==='number'&&!Number.isFinite(valueToSave))throw new Error('请输入有效数字');
  if(parameter.type==='entity'&&!entityId)throw new Error('请从候选中选择卡牌');
  if(group.expression===undefined||!group.expression&&group.conditions.length){
   const existing=group.conditions.find(condition=>condition.parameter_key===parameter.key&&condition.operator==='eq');
   const condition={id:existing?.id??templateId('conditions'),parameter_key:parameter.key,operator:'eq' as const,value:valueToSave};
   next={...group,conditions:existing?group.conditions.map(row=>row.id===existing.id?condition:row):[...group.conditions,condition]};
  }else{
   const literal=parameter.type==='number'?String(valueToSave):JSON.stringify(value);
   const binding=parameter.key+(parameter.type==='entity'?'.名称':'')+' == '+literal;
   let expression=group.expression;
   if(old!==undefined){
    const escaped=parameter.key.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
    const term=new RegExp('\\b'+escaped+'(?:\\.(?:名称|name))?\\s*(?:is|==)\\s*("(?:[^"\\\\]|\\\\.)*"|-?\\d+(?:\\.\\d+)?)','gu');
    expression=editConjuncts(expression,value=>{
     const match=[...value.matchAll(term)].find(item=>item[0]===value);
     return match&&String(JSON.parse(match[1]))===old?binding:value;
    });
    if(expression===group.expression&&old!==value)throw new Error('请在完整触发条件中修改这个参数');
   }else expression=expression.trim()?'('+expression+') and '+binding:binding;
   next={...group,expression,editor_mode:'text',condition_tree:null};
  }
 }
 return {...next,name:canonicalTemplateName(next,event)??group.name};
}
