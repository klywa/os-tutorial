import source from '../../src/condition/catalog-v04.json?raw';

type Registry = {
 events:Record<string,{action:string;key:string[]}>;
 actions:Record<string,Record<string,string>>;
 roots:Record<string,string>;
 types:Record<string,Record<string,string>>;
 lineup_aliases:Record<string,string>;
 hero_fields:string[];
 hero_paths:string[];
};

export const catalogV04:Registry=JSON.parse(source);
export const currentTemplateSyntax='0.5' as const;
export type KeyedTemplateSyntax='0.4'|typeof currentTemplateSyntax;
export const keyedTemplateSyntax=(version:unknown):version is KeyedTemplateSyntax=>
 version==='0.4'||version===currentTemplateSyntax;
export const registeredEvent=(name:string)=>Object.hasOwn(catalogV04.events,name);
export const lineupName=(name:string)=>catalogV04.lineup_aliases[name]??name;
const eventKeyParts=(event:string)=>catalogV04.events[event]?.key;
export const wildcardKey=(event:string)=>eventKeyParts(event)?.map(()=>'*').join('-')??'';
export const slotToken=(path:string,v04:boolean)=>v04?'{{'+path+'}}':'{'+path+'}';

export function validateExtraKey(event:string,key:string){
 const expected=eventKeyParts(event),parts=key?key.split('-'):[];
 if(!expected)throw new Error('未注册解释类型：'+event);
 const fields=catalogV04.actions[catalogV04.events[event].action];
 if(parts.length!==expected.length||parts.some((part,index)=>!part||part.trim()!==part||
  part!=='*'&&(part.includes('*')||fields[expected[index]]==='int'&&!/^(0|[1-9]\d*)$/.test(part))))
  throw new Error('额外信息键应为 '+(expected.length?expected.join('-')+'，每段可用 *':'空串'));
}

const scalarTypes=['int','string','bool'];
const listMember=(kind:string)=>kind.startsWith('Array<')?kind.slice(6,-1):undefined;
const valueType=(kind:string)=>kind.replace(/\?$/,'');
const outputs=[...scalarTypes,'Array<string>','Array<卡牌>'];
const functions=new Set(['any','all','none','count','sum','len','filter']);
export type ConditionNodeV04=
 | {kind:'path';parts:string[]}
 | {kind:'literal';type:string;value?:string}
 | {kind:'negation';child:ConditionNodeV04}
 | {kind:'binary';op:string;left:ConditionNodeV04;right:ConditionNodeV04}
 | {kind:'call';name:string;args:ConditionNodeV04[]};
type Node=ConditionNodeV04;

function tokenize(source:string){
 const lexer=/\s+|"(?:[^"\\]|\\.)*"|[\p{L}_][\p{L}\p{N}_]*|[0-9]+|==|!=|<=|>=|[().\[\],<>+*%\-]/guy;
 const tokens:string[]=[];
 for(let offset=0;offset<source.length;){
  lexer.lastIndex=offset;
  const match=lexer.exec(source);
  if(!match)throw new Error('第 '+(offset+1)+' 列有无效字符');
  if(!/^\s$/u.test(match[0][0]))tokens.push(match[0]);
  offset=lexer.lastIndex;
 }
 return tokens;
}

export function v04ConditionKey(source:string){
 function parts(node:Node,operator:string):string[]{
  return node.kind==='binary'&&node.op===operator?[...parts(node.left,operator),...parts(node.right,operator)]:[signature(node)];
 }
 function signature(node:Node):string{
  return node.kind==='binary'&&(node.op==='and'||node.op==='or')?JSON.stringify([node.op,parts(node,node.op).sort()]):JSON.stringify(node);
 }
 return source.trim()?signature(parse(source)):'';
}

const precedence:Record<string,number>={or:1,and:2,'==':4,'!=':4,'<':4,'>':4,'<=':4,'>=':4,in:4,'not in':4,'+':5,'-':5,'*':6,'%':6};
const identifier=/^\p{L}[\p{L}\p{N}_]*$/u;
function parse(source:string):Node{
 const tokens=tokenize(source);
 let index=0;
 function demand(token:string){
  if(tokens[index++]!==token)throw new Error('预期 '+token);
 }
 function parseNode(min=1,depth=0):Node{
  if(depth>64)throw new Error('表达式嵌套过深');
  let left=start(depth);
  while(index<tokens.length){
   const op=tokens[index]==='not'&&tokens[index+1]==='in'?'not in':tokens[index];
   const rank=precedence[op];
   if(!rank||rank<min)break;
   index+=op==='not in'?2:1;
   left={kind:'binary',op,left,right:parseNode(rank+1,depth+1)};
  }
  return left;
 }
 function textLiteral(token:string){
  if(!token?.startsWith('"'))throw new Error('列表只支持文本字面量');
  JSON.parse(token);
 }
 function start(depth:number):Node{
  const token=tokens[index++];
  if(token==='('){const node=parseNode(1,depth+1);demand(')');return node;}
  if(token==='not')return {kind:'negation',child:parseNode(3,depth+1)};
  if(/^\d+$/.test(token??'')||token==='-'&&/^\d+$/.test(tokens[index]??'')){
   const value=token==='-'?tokens[index++]:token;
   if(!/^(?:0|[1-9]\d*)$/.test(value))throw new Error('数值须为十进制整数');
   return {kind:'literal',type:'int',value:token==='-'?'-'+value:value};
  }
  if(token?.startsWith('"')){textLiteral(token);return {kind:'literal',type:'string',value:JSON.parse(token)};}
  if(token==='['){
   const values:string[]=[];
   const consume=()=>{const token=tokens[index++];textLiteral(token);values.push(JSON.parse(token));};
   if(tokens[index]!==']'){
    consume();
    while(tokens[index]===','){index++;consume();}
   }
   demand(']');
   return {kind:'literal',type:'Array<string>',value:JSON.stringify(values)};
  }
  if(token==='nil')return {kind:'literal',type:'nil'};
  if(identifier.test(token??'')&&tokens[index]==='('){
   index++;
   const args=[parseNode(1,depth+1)];
   while(tokens[index]===','){index++;args.push(parseNode(1,depth+1));}
   demand(')');
   return {kind:'call',name:token,args};
  }
  if(token!=='.'&&!identifier.test(token??''))throw new Error('缺少值或命名属性');
  if(token==='.'&&!identifier.test(tokens[index]??''))throw new Error('谓词需要元素属性');
  const parts=token==='.'?['#',tokens[index++]]:[token];
  while(tokens[index]==='.'&&identifier.test(tokens[index+1]??'')){index++;parts.push(tokens[index++]);}
  return {kind:'path',parts};
 }
 const node=parseNode();
 if(index!==tokens.length)throw new Error('表达式有多余标记');
 return node;
}

export function readV04Condition(source?:string):ConditionNodeV04|undefined{
 if(!source?.trim())return;
 try{return parse(source);}catch{return undefined;}
}

export function namedConditionValues(node:ConditionNodeV04){
 if(node.kind!=='binary')return;
 const {op,left,right}=node;
 const value=left.kind==='literal'&&op==='=='?left:right;
 const path=value===right?left:right;
 if(path.kind!=='path'||value.kind!=='literal'||value.value===undefined)return;
 if(op==='=='&&value.type==='string')return {path:path.parts,values:[value.value]};
 if(op==='in'&&value.type==='Array<string>')return {path:path.parts,values:JSON.parse(value.value) as string[]};
}

function facts(node:Node,when:boolean):string[]{
 if(node.kind==='negation')return facts(node.child,!when);
 if(node.kind!=='binary')return [];
 if(node.op===(when?'and':'or'))return [...facts(node.left,when),...facts(node.right,when)];
 if(node.op===(when?'==':'!=')&&node.right.kind==='literal'&&node.right.value==='英雄'&&node.left.kind==='path'&&node.left.parts.at(-1)==='卡牌类型')
  return [node.left.parts.slice(0,-1).join('.')+'.#hero'];
 return node.op===(when?'!=':'==')&&node.right.kind==='literal'&&node.right.type==='nil'&&node.left.kind==='path'
  ?[node.left.parts.join('.')]:[];
}

function typeOf(node:Node,event:string,slot:boolean,guards=new Set<string>(),item?:string,nilCheck=false):string{
 function require(child:Node,kind:string,available=guards){
  if(typeOf(child,event,slot,available,item)!==kind)throw new Error('表达式需要 '+kind);
 }
 if(node.kind==='literal')return node.type;
 if(node.kind==='path'){
  const [root,...fields]=node.parts;
  let kind=root==='#'?(item==='英雄元素'?'卡牌':item):Object.hasOwn(catalogV04.roots,root)?catalogV04.roots[root]:undefined;
  if(!kind)throw new Error('未声明根对象：'+(root==='#'?'.':root));
  for(const [index,field] of fields.entries()){
   if(field==='阵容英雄名列表'&&item)throw new Error('阵容英雄名列表只能在谓词外使用');
   const prefix=node.parts.slice(0,index+1).join('.');
   if(kind.endsWith('?')&&!guards.has(prefix)&&(!slot||item))throw new Error('可空路径缺少前置守卫：'+prefix);
   if(valueType(kind)==='卡牌'&&catalogV04.hero_fields.includes(field)&&
    !catalogV04.hero_paths.includes(node.parts[index])&&!(prefix==='#'&&item==='英雄元素')&&!guards.has(prefix+'.#hero'))
    throw new Error('英雄专属属性需要卡牌类型守卫：'+prefix+'.'+field);
   const table:Record<string,string>|undefined=kind==='动作'?catalogV04.actions[catalogV04.events[event].action]:catalogV04.types[valueType(kind)];
   kind=table&&Object.hasOwn(table,field)?table[field]:undefined;
   if(!kind)throw new Error('未声明属性：'+node.parts.slice(0,index+2).join('.'));
  }
  const guarded=guards.has(node.parts.join('.'));
  if(item&&root!=='#'&&!nilCheck&&!scalarTypes.includes(valueType(kind))&&!guarded)
   throw new Error('谓词只能读取外部标量');
  return guarded&&!nilCheck?valueType(kind):kind;
 }
 if(node.kind==='negation'){require(node.child,'bool');return 'bool';}
 if(node.kind==='call'){
  const {name,args}=node;
  if(!functions.has(name)||args.length!==(name==='len'?1:2)||item)throw new Error('函数、参数个数或嵌套聚合无效：'+name);
  const list=typeOf(args[0],event,slot,guards),member=listMember(list);
  if(!member)throw new Error(name+' 需要列表');
  if(name==='len')return 'int';
  if(name==='sum'&&(args[1].kind!=='path'||args[1].parts[0]!=='#'))throw new Error('sum 需要元素数值字段');
  let source=args[0];
  while(source.kind==='call'&&source.name==='filter')source=source.args[0];
  const predicate=typeOf(args[1],event,slot,guards,source.kind==='path'&&source.parts.at(-1)==='场上英雄列表'?'英雄元素':member);
  if(predicate!==(name==='sum'?'int':'bool'))throw new Error('聚合参数类型不匹配');
  return name==='filter'?list:name==='count'||name==='sum'?'int':'bool';
 }
 const {left,right,op}=node;
 if(op==='and'||op==='or'){
  require(left,'bool');
  require(right,'bool',new Set([...guards,...facts(left,op==='and')]));
  return 'bool';
 }
 if(right.kind==='literal'&&right.type==='nil'){
  if(left.kind!=='path'||(!item&&slot)||!['==','!='].includes(op))throw new Error('nil 只能用于可空路径的守卫');
  if(!typeOf(left,event,slot,guards,item,true).endsWith('?'))throw new Error('nil 只能用于可空路径的守卫');
  return 'bool';
 }
 const a=typeOf(left,event,slot,guards,item),b=typeOf(right,event,slot,guards,item);
 if(['+','-','*','%'].includes(op)){
  if(slot&&a==='int'&&b==='int')return 'int';
 }else if(op==='in'||op==='not in'){
  if(a==='string'&&b==='Array<string>')return 'bool';
 }else if(op==='=='||op==='!='){
  if(a===b&&scalarTypes.includes(a))return 'bool';
 }else if(a==='int'&&b==='int')return 'bool';
 throw new Error('操作符或类型不兼容：'+op);
}

export function validateV04(event:string,expression:string,slot=false){
 if(!registeredEvent(event))throw new Error('未注册解释类型：'+event);
 if(!expression.trim()&&!slot)return;
 if(expression.length>100000)throw new Error('表达式过长');
 const result=typeOf(parse(expression),event,slot);
 if(slot?!outputs.includes(result):result!=='bool')
  throw new Error(slot?'槽位必须是可播报的值，单卡请引用 .名称':'条件必须返回布尔值');
}

type Literal=Extract<Node,{kind:'literal'}>;
const comparisons=new Set(['==','!=','<','>','<=','>=','in','not in']);
function visitKeyComparisons(event:string,key:string,expression:string,compare:(left:Literal,right:Literal,op:string)=>Node){
 const fields=catalogV04.actions[catalogV04.events[event].action];
 const locked=new Map<string,Literal>(eventKeyParts(event)?.flatMap((field,index)=>{
  const value=key.split('-')[index];
  const type=fields[field]==='int'?'int':'string';
  return value==='*'?[]:[['动作.'+field+(valueType(fields[field])==='卡牌'?'.名称':''),{kind:'literal',type,value:field==='阵容'?lineupName(value):value}]];
 }));
 const substitute=(node:Node)=>node.kind==='path'?locked.get(node.parts.join('.'))??node:node;
 function visit(node:Node):Node{
  if(node.kind==='binary'){
   if(comparisons.has(node.op)){
    const left=substitute(node.left),right=substitute(node.right);
    if(left.kind==='literal'&&right.kind==='literal'&&(left!==node.left||right!==node.right))
     return compare(left,right,node.op);
   }
   const left=visit(node.left),right=visit(node.right);
   if(left!==node.left||right!==node.right)return {...node,left,right};
  }
  if(node.kind==='negation'){
   const child=visit(node.child);
   if(child!==node.child)return {...node,child};
  }
  if(node.kind==='call'){
   const args=node.args.map(visit);
   if(args.some((arg,index)=>arg!==node.args[index]))return {...node,args};
  }
  return node;
 }
 if(!expression.trim()||!locked.size)return;
 const original=parse(expression),updated=visit(original);
 return updated!==original?updated:undefined;
}

export function validateKeyedCondition(event:string,key:string,expression:string,syntax:KeyedTemplateSyntax){
 validateExtraKey(event,key);
 validateV04(event,expression);
 if(syntax===currentTemplateSyntax)visitKeyComparisons(event,key,expression,()=>{
  throw new Error('额外信息键已锁定事件参数，条件中重复判断该参数');
 });
}

export function migrateKeyedCondition(event:string,key:string,expression:string){
 validateKeyedCondition(event,key,expression,'0.4');
 const constant=(value:boolean):Node=>({kind:'literal',type:'keyed-constant',value:String(value)});
 const migrated=visitKeyComparisons(event,key,expression,(left,right,op)=>{
  if(op==='in'||op==='not in'){
   const contained=(JSON.parse(right.value!) as string[]).includes(left.value!);
   return constant(op==='in'?contained:!contained);
  }
  if(op==='=='||op==='!='){
   const equal=left.type==='int'?BigInt(left.value!)===BigInt(right.value!):left.value===right.value;
   return constant(op==='=='?equal:!equal);
  }
  const a=BigInt(left.value!),b=BigInt(right.value!);
  return constant(op==='<'?a<b:op==='>'?a>b:op==='<='?a<=b:a>=b);
 });
 if(!migrated)return expression;
 const boolean=(node:Node)=>node.kind==='literal'&&node.type==='keyed-constant'?node.value==='true':undefined;
 function simplify(node:Node):Node{
  if(node.kind==='negation'){
   const child=simplify(node.child),result=boolean(child);
   return result===undefined?{...node,child}:constant(!result);
  }
  if(node.kind==='call')return {...node,args:node.args.map(simplify)};
  if(node.kind!=='binary')return node;
  const left=simplify(node.left),right=simplify(node.right);
  if(node.op==='and'||node.op==='or'){
   const lhs=boolean(left),rhs=boolean(right),identity=node.op==='and';
   if(lhs!==undefined)return lhs===identity?right:left;
   if(rhs===identity)return left;
  }
  return {...node,left,right};
 }
 function format(node:Node,min=1):string{
  if(node.kind==='path')return node.parts.join('.').replace(/^#/, '');
  if(node.kind==='literal'){
   if(node.type==='keyed-constant')return node.value==='true'?'(0 == 0)':'(0 == 1)';
   return node.type==='string'?JSON.stringify(node.value):node.value??'nil';
  }
  if(node.kind==='negation'){
   const source='not '+format(node.child,3);
   return min>3?'('+source+')':source;
  }
  if(node.kind==='call')return node.name+'('+node.args.map(arg=>format(arg)).join(', ')+')';
  const rank=precedence[node.op];
  const source=format(node.left,rank)+' '+node.op+' '+format(node.right,rank+1);
  return rank<min?'('+source+')':source;
 }
 const simplified=simplify(migrated);
 return boolean(simplified)===true?'':format(simplified);
}

export function validateV04Template(event:string,text:string,syntax:KeyedTemplateSyntax='0.4'){
 let cursor=0;
 for(const token of text.matchAll(/\{\{(.*?)\}\}/gsu)){
  if(/\{\{|\}\}/u.test(text.slice(cursor,token.index))||/\{\{|\}\}/u.test(token[1]))
   throw new Error('槽位括号不配对或嵌套');
  if(syntax===currentTemplateSyntax){
   if(!registeredEvent(event))throw new Error('未注册解释类型：'+event);
   if(token[1].length>100000)throw new Error('表达式过长');
   const result=typeOf(parse(token[1]),event,true);
   if(!outputs.includes(result)&&valueType(result)!=='卡牌')throw new Error('槽位必须是可播报的值');
  }else validateV04(event,token[1],true);
  cursor=token.index+token[0].length;
 }
 if(/\{\{|\}\}/u.test(text.slice(cursor)))throw new Error('槽位括号不配对');
}

export function v04Paths(event:string){
 const definition=catalogV04.events[event];
 const result:string[]=[];
 function add(path:string,kind:string,ancestors:string[]){
  const type=valueType(kind);
  if(outputs.includes(type)){result.push(path);return;}
  if(ancestors.includes(type))return;
  for(const [field,child] of Object.entries(type==='动作'?catalogV04.actions[definition?.action]??{}:catalogV04.types[type]??{}))
   add(path+'.'+field,child,[...ancestors,type]);
 }
 for(const [root,kind] of Object.entries(catalogV04.roots))add(root,kind,[]);
 return result;
}
