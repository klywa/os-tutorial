import {it,expect} from 'vitest';
import {overviewFor,membersFor,compatibleRoute,moveHero} from './overview';
import type {Meta} from './types';
it('keeps alternative members separate and only merges compatible route advice',()=>{
 const meta={players:[],compositions:{early:[],middle:[],late:[]},late_variants:[{id:'one',name:'甲',members:[{hero:'a',necessity:'required'}]},{id:'two',name:'乙',members:[{hero:'b',necessity:'required'}]}],operation_routes:[{id:'route',variant_ids:['one']}]} as unknown as Meta;
 const data=overviewFor(meta);
 expect(data.presets).toHaveLength(2);
 expect(membersFor(meta,data.presets[0],'late').map(m=>m.hero)).toEqual(['a']);
 expect(compatibleRoute(meta,data.presets[1],'route')).toBe(false);
 expect(data.presets[0].placements).toEqual([]);
 expect(meta.overview).toBeUndefined();
 const p=data.presets[0];p.placements=[{hero:'a',row:0,col:0,equipment:['equipment']}];
 expect(moveHero(p,27,'a')).toEqual([{hero:'a',row:3,col:6,equipment:['equipment']}]);
});
