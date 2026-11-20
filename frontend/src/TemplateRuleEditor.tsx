import {TemplateConditionPreview} from './TemplateConditionPreview';
import {useEffect,useId,useMemo,useRef,useState} from 'react';
import {compatibleRight,completeTree,countPath,emptyTree,findPathOption,listPaths,members,newLeaf,numeric,operatorsFor,readCountFilter,renderRule,switchToText,type ConditionCatalog,type ConditionNode,type PathOption} from './templateRules';
import type {TemplateEvent,TemplateGroup} from './templates';

type Leaf=Extract<ConditionNode,{kind:'leaf'}>;
const names:Record<string,string>={all:'全部满足',any:'任一满足',not:'取反'};
const operatorNames:Record<string,string>={'':'为真',is:'等于名称 / 文本',has:'包含',in:'属于', '==':'等于'};
function Literal({node,type,choices,unitTypes,onChange}:{node:Leaf;type:string;choices?:string[];unitTypes:string[];onChange:(right:string)=>void}){
 const id=useId();
 const isArray=type.startsWith('Array<'),declared=isArray?members(type):type.split('|');
 const includesUnit=declared.includes('单位')&&unitTypes.length>0;
 const unitVariants=declared.length===1?['string',...unitTypes]:unitTypes;
 const variants=includesUnit?[...new Set(declared.flatMap(t=>t==='单位'?unitVariants:[t]))]:isArray||declared.length>1?declared:[];
 let parsed:unknown;
 try{parsed=JSON.parse(node.right);}catch{parsed=undefined;}
 const object=parsed&&typeof parsed==='object'&&!Array.isArray(parsed)?parsed as Record<string,string>:undefined;
 if(node.operator==='in')return <label>候选值列表<input aria-label="候选值列表" value={node.right} placeholder='["小乔","弈星"]' onChange={e=>onChange(e.target.value)}/></label>;
 const literalType=typeof parsed==='string'?'string':typeof parsed==='boolean'?'bool':typeof parsed==='number'?variants.find(numeric):object?.类型;
 const active=variants.length?(literalType??variants[0]??'string'):type;
 const typed=variants.length>0&&!numeric(active)&&active!=='bool'&&active!=='string';
 function initialValue(t:string){
  if(numeric(t))return '0';
  if(t==='bool')return 'true';
  const name=object?.名称??(typeof parsed==='string'?parsed:'');
  return JSON.stringify(t==='string'?name:{类型:t,名称:name});
 }
 return <>{variants.length>1&&<label>成员类型<select value={active} onChange={e=>onChange(initialValue(e.target.value))}>{variants.map(t=><option key={t} value={t}>{t==='string'&&includesUnit?'按名称':t}</option>)}</select></label>}
  {active==='bool'?<label>布尔值<select value={node.right} onChange={e=>onChange(e.target.value)}><option value="">选择值</option><option>true</option><option>false</option></select></label>
  :numeric(active)?<label>数值<input type="number" step={active==='int'?'1':'any'} value={node.right} onChange={e=>onChange(e.target.value)}/></label>
  :<label htmlFor={id}>{active==='string'&&!includesUnit?'文本值':'实体名称'}<input id={id} list={choices?.length?id+'-values':undefined} value={object?.名称??(typeof parsed==='string'?parsed:node.right)} onChange={e=>onChange(typed?JSON.stringify({类型:active,名称:e.target.value}):JSON.stringify(e.target.value))}/>{!!choices?.length&&<datalist id={id+'-values'}>{choices.map(v=><option key={v} value={v}/>)}</datalist>}</label>}</>;

}
function FilterInput({filter,path,label,onChange}:{filter:NonNullable<PathOption['filter']>;path:string;label:string;onChange:(path:string)=>void}){
 const id=useId();
 const {field,choices}=filter;
 return <label htmlFor={id}>{label}{field}<input id={id} list={choices?.length?id+'-choices':undefined} value={readCountFilter(path)?.value??''} onChange={e=>onChange(countPath(filter,e.target.value))}/>
  {!!choices?.length&&<datalist id={id+'-choices'}>{choices.map(choice=><option key={choice} value={choice}/>)}</datalist>}
 </label>;
}
function pathLabel({path,filter}:PathOption){return filter?`${filter.source}.计数(${filter.field})`:path;}
function Branch({node,paths,catalog,onChange,onRemove}:{node:ConditionNode;paths:PathOption[];catalog?:ConditionCatalog;onChange:(node:ConditionNode)=>void;onRemove?:()=>void}){
 const remove=onRemove&&<button type="button" onClick={onRemove} aria-label="删除此条件节点">删除</button>;
 if(node.kind==='leaf'){
  const knownLeft=findPathOption(paths,node.left),right=findPathOption(paths,node.right);
  const left=knownLeft??{path:node.left,type:'string'},unitTypes=catalog?.unit_types??[];
  const ops=operatorsFor(left),matches=paths.filter(p=>compatibleRight(left.type,p.type,node.operator,catalog?.aliases,unitTypes)&&(!p.operations||p.operations.includes(node.operator)));
  return <div className="rule-leaf"><label>条件属性<select value={left.path} onChange={e=>{const p=paths.find(p=>p.path===e.target.value)!;onChange({...node,left:p.path,operator:operatorsFor(p)[0],right:''});}}>{!knownLeft&&<option>{node.left}</option>}{paths.map(p=><option key={p.path} value={p.path}>{pathLabel(p)} · {p.type}</option>)}</select></label>
   {left.filter&&<FilterInput filter={left.filter} path={node.left} label="统计" onChange={path=>onChange({...node,left:path})}/>}
   <label>比较方式<select value={node.operator} onChange={e=>onChange({...node,operator:e.target.value,right:''})}>{[...new Set([...ops,node.operator])].map(op=><option key={op} value={op}>{operatorNames[op]??op}</option>)}</select></label>
   {node.operator&&<><label>比较值来源<select value={right?'path':'literal'} onChange={e=>onChange({...node,right:e.target.value==='path'?matches.find(p=>p.path!==left.path)?.path??matches[0]?.path??'':''})}><option value="literal">固定值</option><option value="path" disabled={!matches.length}>另一个属性</option></select></label>
    {right?<><label>比较属性<select value={right.path} onChange={e=>onChange({...node,right:e.target.value})}>{!matches.includes(right)&&<option value={right.path}>{pathLabel(right)}</option>}{matches.map(p=><option key={p.path} value={p.path}>{pathLabel(p)}</option>)}</select></label>
     {right.filter&&<FilterInput filter={right.filter} path={node.right} label="比较" onChange={path=>onChange({...node,right:path})}/>}</>:<Literal node={node} type={left.type} choices={left.choices} unitTypes={unitTypes} onChange={right=>onChange({...node,right})}/>}</>}{remove}</div>;
 }
 const canAdd=node.kind!=='not'||node.children.length===0;
 function append(child:ConditionNode){if(node.kind!=='leaf')onChange({...node,children:[...node.children,child]});}
 return <fieldset className="rule-branch"><legend>{names[node.kind]}</legend><div className="rule-tools"><label>逻辑关系<select value={node.kind} onChange={e=>{const kind=e.target.value as 'not'|'all'|'any';onChange({kind,children:kind==='not'&&node.children.length>1?[node]:node.children});}}>{Object.entries(names).map(([k,v])=><option key={k} value={k}>{v}</option>)}</select></label>{remove}</div>
  {node.children.map((child,i)=><Branch key={i} node={child} paths={paths} catalog={catalog} onChange={value=>onChange({...node,children:node.children.map((old,j)=>i===j?value:old)})} onRemove={()=>onChange({...node,children:node.children.filter((_,j)=>i!==j)})}/>)}
  {canAdd&&<div className="rule-tools"><button type="button" disabled={!paths.length} onClick={()=>append(newLeaf(paths))}>＋ 添加条件</button><button type="button" onClick={()=>append(emptyTree())}>＋ 添加条件组</button></div>}</fieldset>;
}
export default function TemplateRuleEditor({draft,event,catalog,patch,preview}:{preview:string;draft:TemplateGroup;event?:TemplateEvent;catalog?:ConditionCatalog;patch:(p:Partial<TemplateGroup>)=>void}){
 const [restoring,setRestoring]=useState(false),[confirmPartial,setConfirmPartial]=useState(false);
 const lastComplete=useRef<ConditionNode|null>(null);
 useEffect(()=>{
  if(draft.condition_tree&&completeTree(draft.condition_tree))lastComplete.current=draft.condition_tree;
 },[draft.condition_tree]);
 const saved=draft.condition_tree??emptyTree();
 const tree:ConditionNode=saved.kind==='leaf'?{kind:'all',children:[saved]}:saved,treeText=renderRule(tree),text=draft.expression??treeText;
 const paths=useMemo(()=>listPaths(event,catalog),[event,catalog]),isText=draft.editor_mode==='text';
 function update(tree:ConditionNode){patch({condition_tree:tree,expression:renderRule(tree),editor_mode:'tree',conditions:[]});setRestoring(false);setConfirmPartial(false);}
 function enterText(){patch(switchToText(tree,lastComplete.current,text));setConfirmPartial(false);}
 return <section><h3>触发条件</h3><div className="rule-tools">
  <button type="button" aria-pressed={!isText} onClick={()=>{if(isText){if(treeText!==text)setRestoring(true);else update(tree);}}}>可视化树</button>
  <button type="button" aria-pressed={isText} onClick={()=>{if(!isText){if(completeTree(tree))enterText();else setConfirmPartial(true);}}}>文本编辑</button></div>
  {confirmPartial&&!isText&&<div className="rule-restore"><p>条件树还有未填完的节点。切换后可继续编辑当前文本，恢复树稿时将使用最近一份完整条件树。</p><button type="button" onClick={enterText}>保留完整树稿并切换到文本</button><button type="button" onClick={()=>setConfirmPartial(false)}>继续填写条件树</button></div>}
  {isText?<label>正式条件表达式<textarea value={text} rows={4} spellCheck={false} onChange={e=>patch({expression:e.target.value,conditions:[]})}/></label>:<Branch node={tree} paths={paths} catalog={catalog} onChange={update}/>}
  <TemplateConditionPreview expression={preview}/>
  {/\.标签|\.计数\s*\(\s*标签/.test(text)&&<p className="muted">请逐一核对命中标签的卡牌和形态，确认提供者、受益者和触发时机都符合整句话。</p>}
  {restoring&&<div className="rule-restore"><h4>恢复最近的树稿？</h4><p>恢复后将使用树稿生成的表达式。</p><div><section><strong>当前正式文本</strong><pre>{text||'无条件限制'}</pre></section><section><strong>恢复后的条件</strong><pre>{treeText||'无条件限制'}</pre></section></div><button type="button" onClick={()=>update(tree)}>确认恢复树稿</button><button type="button" onClick={()=>setRestoring(false)}>保留当前文本</button></div>}
 </section>;
}
