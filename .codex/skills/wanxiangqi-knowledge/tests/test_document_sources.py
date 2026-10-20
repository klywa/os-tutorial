from pathlib import Path
import sys,tempfile,unittest,zipfile
sys.path.insert(0,str(Path(__file__).parents[1]/'scripts'))
import wxq
import document_sources as ds

class DocumentSourcesTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);wxq.init_store(self.root)
        self.doc=self.root/'教程.docx'
        with zipfile.ZipFile(self.doc,'w') as z:
            z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>机制</w:t></w:r></w:p><w:p><w:r><w:t>操作</w:t></w:r></w:p></w:body></w:document>')
    def test_register_is_content_addressed_and_evidence_is_real(self):
        first=ds.register(self.root,self.doc);self.assertEqual(first,ds.register(self.root,self.doc))
        ds.validate_evidence(self.root,{'source':first['id'],'type':'document','paragraph_start':1,'paragraph_end':2})
        self.assertFalse((self.root/'raw/sources').glob('*/asr.raw.json').__next__() if list((self.root/'raw/sources').glob('*/asr.raw.json')) else False)
    def test_invalid_ranges_and_missing_source_rejected(self):
        row=ds.register(self.root,self.doc)
        for start,end in [(0,1),(2,1),(1,3),(True,1)]:
            with self.assertRaises(ValueError):ds.validate_evidence(self.root,{'source':row['id'],'type':'document','paragraph_start':start,'paragraph_end':end})
        with self.assertRaises(ValueError):ds.validate_evidence(self.root,{'source':'doc-missing','type':'document','paragraph_start':1,'paragraph_end':1})
    def test_snapshot_tampering_rejected(self):
        row=ds.register(self.root,self.doc);(self.root/row['artifact']).write_bytes(b'changed')
        with self.assertRaises(ValueError):ds.validate_evidence(self.root,{'source':row['id'],'type':'document','paragraph_start':1,'paragraph_end':1})
    def test_commit_validate_and_replay_document_claim(self):
        row=ds.register(self.root,self.doc)
        note={'id':'mechanic','type':'other','title':'机制','entities':[],'core':[],'claims':[{'section':'知识内容','text':'操作','kind':'mechanic','inference':False,'condition':'','version':None,'evidence':[{'source':row['id'],'type':'document','paragraph_start':2,'paragraph_end':2}]}]}
        wxq.commit_notes(self.root,[note]);wxq.commit_notes(self.root,[note])
        self.assertEqual(len(wxq.read_json(self.root/'knowledge/index.json')['notes'][0]['claims']),1)
        self.assertEqual(wxq.validate_store(self.root)['errors'],[])

if __name__=='__main__':unittest.main()
