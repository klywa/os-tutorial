import {afterEach,expect,it} from 'vitest';
import {seasonPath,setCurrentSeason} from './seasons';

afterEach(()=>setCurrentSeason('S1'));
it('separates season reads and writes while preserving shared workspace APIs',()=>{
 expect(seasonPath('notes/catalog')).toBe('notes/catalog');
 setCurrentSeason('S2');
 expect(seasonPath('notes/x/reading?player=p')).toBe('notes/x/reading?player=p&season=S2');
 expect(seasonPath('dashboard?scope=all')).toBe('dashboard?scope=all&season=S2');
 expect(seasonPath('templates/changes')).toBe('templates/changes?season=S2');
 expect(seasonPath('sources')).toBe('sources');
 expect(seasonPath('cards?season=S1')).toBe('cards?season=S1');
});
