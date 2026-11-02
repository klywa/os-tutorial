import {expect,it,vi,afterEach} from 'vitest';
import {locationCandidates,loadProposalLocation} from './proposalLocation';
import {api} from './model';
import type {Proposal} from './Proposals';
vi.mock('./model',()=>({api:vi.fn()}));
const item={note_id:'n',node_id:'entry',section_id:'chapter',after_id:'anchor',kind:'update'} as Proposal;
afterEach(()=>vi.resetAllMocks());
it('prioritizes canonical entries and only uses insertion anchors for insertions',()=>{
 expect(locationCandidates(item)).toEqual(['entry','chapter']);
 expect(locationCandidates({...item,kind:'delete'})).toEqual(['entry','chapter']);
 expect(locationCandidates({...item,kind:'insert'})).toEqual(['entry','anchor','chapter']);
 expect(locationCandidates({...item,kind:'insert',after_id:'chapter'})).toEqual(['entry','chapter']);
});
it('loads the exact player scope and rejects inconsistent reading revisions',async()=>{
 vi.mocked(api).mockResolvedValueOnce({id:'n',revision:'one'}).mockResolvedValueOnce({note_id:'n',revision:'two'})
 .mockResolvedValueOnce({id:'n',revision:'three'}).mockResolvedValueOnce({note_id:'n',revision:'three',sections:[]});
 const result=await loadProposalLocation(item,'p x');
 expect(result.note.revision).toBe('three');expect(result.reading.revision).toBe('three');
 expect(vi.mocked(api).mock.calls[0][0]).toBe('notes/n?player=p%20x');
 expect(vi.mocked(api).mock.calls[1][0]).toBe('notes/n/reading?player=p%20x');
});
it('fails closed when a note is missing or changes during both attempts',async()=>{
 vi.mocked(api).mockRejectedValueOnce(new Error('笔记不存在'));
 await expect(loadProposalLocation(item)).rejects.toThrow('笔记不存在');
 vi.mocked(api).mockImplementation(async url=>url.endsWith('/reading')?{note_id:'n',revision:'two',sections:[]}:{id:'n',revision:'one'});
 await expect(loadProposalLocation(item)).rejects.toThrow('笔记正在更新');
});
