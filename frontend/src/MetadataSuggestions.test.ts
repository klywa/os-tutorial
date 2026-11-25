import {expect,it} from 'vitest';
import {lastMetadataTerm,matchMetadataChoices,replaceLastMetadataTerm} from './MetadataSuggestions';

it('matches non-contiguous characters and brings recently clicked matches to the front',()=>{
 expect(matchMetadataChoices(['成长速度','长线速度','前期战力','长线速度'],'长速',['前期战力','长线速度']))
  .toEqual(['长线速度','成长速度']);
 expect(matchMetadataChoices(['复核 A01','复核 B01'],'复 ａ１',[])).toEqual(['复核 A01']);
});

it('matches and replaces the current term without disturbing earlier selections',()=>{
 const draft='前期、复核， 长速';
 expect(lastMetadataTerm(draft)).toBe('长速');
 expect(replaceLastMetadataTerm(draft,'成长速度')).toBe('前期、复核，成长速度');
});
