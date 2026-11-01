import {it,expect} from 'vitest';
import {capabilitiesFor} from './auth';
import {replaceScope} from './noteReviewModel';
import type {KnowledgeDocument} from './types';
it('effective annotator hides formal and local tools while allowing proposals during sync',()=>{
 expect(capabilitiesFor({mode:'local',role:'annotator',account_role:'admin',allowed_roles:['admin','annotator'],username:'a',base_path:'/',sync:{state:'pending'}})).toMatchObject({localTools:false,editNotes:false,manageMatches:false,reviews:false,inlineEdit:true,proposeNotes:true});
 expect(capabilitiesFor({mode:'public',role:'admin',username:'a',base_path:'/'})).toMatchObject({inlineEdit:true,proposeNotes:false});
});
it('scoped replacement retains insertions and deletions without touching outside headings or semantic data',()=>{
 const body:KnowledgeDocument={schema_version:6,semantics:{keep:1},supporting_nodes:[],nodes:[{id:'h',type:'heading',title:'一',level:2},{id:'a',type:'entry',key:'甲',show_key:true,value:'旧'},{id:'h2',type:'heading',title:'二',level:2}]};
 const added={id:'new',type:'entry' as const,key:'乙',show_key:true,value:'新增'};
 const result=replaceScope(body,'h',[body.nodes[0],added]);
 expect(result.nodes.map(n=>n.id)).toEqual(['h','new','h2']);expect(result.semantics).toBe(body.semantics);expect(result.supporting_nodes).toBe(body.supporting_nodes);expect(body.nodes[1].id).toBe('a');
});
import {renderToStaticMarkup} from 'react-dom/server';
import {AuthContext} from './auth';
import {ReviewProvider} from './NoteReview';
import JsonReading from './JsonReading';
import {ProposalCard,AccountControls} from './Proposals';
import type {Note} from './types';
it('annotator inline UI offers proposals without old comments or title fields',()=>{
 const session={mode:'public' as const,role:'annotator' as const,username:'writer',base_path:'/'};
 const note={id:'n',title:'文',revision:'r',related:[],document:{schema_version:6,nodes:[{id:'h',type:'heading',title:'章',level:2},{id:'p',type:'entry',key:'甲',show_key:true,value:'正文'}]}} as unknown as Note;
 const html=renderToStaticMarkup(<AuthContext.Provider value={{session,refresh:async()=>{},login:async()=>{},logout:async()=>{}}}><ReviewProvider note={note} onSaved={()=>{}} onDirty={()=>{}}><JsonReading note={note} body={note.document!} nodes={note.document!.nodes} onNote={()=>{}}/></ReviewProvider></AuthContext.Provider>);
 expect(html).toContain('编辑章节：章');expect(html).not.toContain('批注：');
});
it('private proposal card names the author and distinguishes pending insertions without canonical mutation',()=>{
 const html=renderToStaticMarkup(<ProposalCard item={{id:'1',note_id:'n',note_title:'笔记',author:'writer',kind:'insert',node_id:'p',section_id:'h',after_id:'h',base_node:null,proposed_node:{id:'p',type:'entry',key:'新增',show_key:true,value:'候选正文'},revision:1,status:'pending',created_at:'',updated_at:''}} onChanged={()=>{}}/>);
 expect(html).toContain('writer');expect(html).toContain('暂存待确认');expect(html).toContain('<ins');
});
it('topbar exposes both role directions only for an admin account',()=>{
 const html=renderToStaticMarkup(<AuthContext.Provider value={{session:{mode:'local',role:'annotator',account_role:'admin',allowed_roles:['admin','annotator'],username:'a',base_path:'/'},refresh:async()=>{},login:async()=>{},logout:async()=>{}}}><AccountControls beforeChange={()=>true}/></AuthContext.Provider>);
 expect(html).toContain('管理员');expect(html).toContain('编写员');expect(html).toContain('提案');
});
import {ProposalOverlay,type Proposal} from './Proposals';
import {proposalEditPayload} from './Proposals';
import {documentMarkdown} from './jsonDocument';
it('renders separate pending cards for multiple authors at one insertion anchor without modifying canonical export',()=>{
 const canonical:KnowledgeDocument={schema_version:6,nodes:[{id:'h',type:'heading',level:2,title:'章节'}]};
 const proposal={id:'1',note_id:'n',note_title:'笔记',author:'甲',kind:'insert',node_id:'p',section_id:'h',after_id:'h',base_node:null,proposed_node:{id:'p',type:'entry',key:'提议',show_key:true,value:'私有待审核'},revision:1,status:'pending',created_at:'',updated_at:''} as Proposal;
 const html=renderToStaticMarkup(<ProposalOverlay nodeId="h" items={[proposal,{...proposal,id:'2',author:'乙'}]}/>);
 expect(html.match(/class="proposal-card"/g)).toHaveLength(2);expect(html).toContain('甲');expect(html).toContain('乙');expect(documentMarkdown(canonical)).not.toContain('私有待审核');
});
import {vi,afterEach} from 'vitest';
import {api} from './model';
afterEach(()=>vi.unstubAllGlobals());
it('private proposal requests bypass the browser cache',async()=>{
 const request=vi.fn().mockResolvedValue(new Response('{"items":[]}',{status:200}));vi.stubGlobal('fetch',request);
 await api('proposals?note_id=n');expect(request.mock.calls[0][1]).toMatchObject({cache:'no-store'});
});
it('keeps chained new entries visible before any insertion is approved',()=>{
 const base={note_id:'n',note_title:'笔记',author:'甲',kind:'insert',section_id:'h',base_node:null,revision:1,status:'pending',created_at:'',updated_at:''} as const;
 const first={...base,id:'1',node_id:'p1',after_id:'h',proposed_node:{id:'p1',type:'entry',key:'一',show_key:true,value:'提议一'}} as Proposal;
 const second={...first,id:'2',node_id:'p2',after_id:'p1',proposed_node:{...first.proposed_node!,id:'p2'}} as Proposal;
 expect(renderToStaticMarkup(<ProposalOverlay nodeId="h" items={[first,second]}/>).match(/class="proposal-card"/g)).toHaveLength(2);
});
it('rebases the latest stored proposal rather than a canceled or stale local draft',()=>{
 const latest={revision:4,proposed_node:{id:'n',type:'entry',key:'策略',show_key:true,value:'作者最新改稿'}} as Proposal;
 const abandoned={...latest.proposed_node!,value:'已取消的本地改稿'};
 expect(proposalEditPayload(latest,abandoned,2,false,true)).toEqual({revision:4,proposed_node:latest.proposed_node,rebase:true});
});
it('preserves an active draft revision so a remote edit produces a conflict instead of being overwritten',()=>{
 const latest={revision:4,proposed_node:{id:'n',type:'entry',key:'策略',show_key:true,value:'远端改稿'}} as Proposal;
 const draft={...latest.proposed_node!,value:'本地正在编辑的改稿'};
 expect(proposalEditPayload(latest,draft,2,true,true)).toEqual({revision:2,proposed_node:draft,rebase:true});
});
