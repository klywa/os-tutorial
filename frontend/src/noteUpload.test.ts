import {expect,test} from 'vitest';
import {describeNewNoteJson,readNoteJson} from './noteUpload';

const body={schema_version:6,nodes:[{id:'heading',type:'heading',level:1,title:'战斗笔记'},
 {id:'entry',type:'entry',key:'说明',show_key:true,value:'观察前排。'}]};

test('describes a bare note and uses declared fields from a single-note package',()=>{
 expect(describeNewNoteJson(body)).toMatchObject({title:'战斗笔记',preview:'战斗笔记\n\n说明：观察前排。'});
 const item={body,metadata:{title:'已命名笔记',type:'other',seasons:['S2'],aliases:['别名']}};
 expect(describeNewNoteJson({notes:[item]})).toEqual(describeNewNoteJson(item));
 expect(describeNewNoteJson(item)).toMatchObject({title:'已命名笔记',metadata:item.metadata});
 expect(()=>describeNewNoteJson({notes:[item,item]})).toThrow('只含一篇');
});

test('reads UTF-8 BOM and rejects files past the upload limit or invalid JSON',async()=>{
 await expect(readNoteJson(new File(['\uFEFF'+JSON.stringify(body)],'笔记.json'))).resolves.toEqual(body);
 await expect(readNoteJson(new File(['x'.repeat(2_000_001)],'大文件.json'))).rejects.toThrow('2 MB');
 await expect(readNoteJson(new File(['{'],'损坏.json'))).rejects.toThrow('无法读取 JSON');
});
