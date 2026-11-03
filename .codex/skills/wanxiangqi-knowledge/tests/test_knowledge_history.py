import sys, unittest, shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_json_store as fixtures
import json_store as s
import note_review as review
class ExternalHistoryTests(unittest.TestCase):
    setUp=fixtures.StoreTests.setUp
    tearDown=fixtures.StoreTests.tearDown
    def test_external_history_is_portable_and_revision_ignores_audit(self):
        s.write_file(self.root/s.INDEX, {'schema_version':6,'storage_version':2,'notes':[],'aliases':{}})
        self.record['metadata']['history']=[{'body':{'old':'evidence'}}]
        s.save(self.root,[self.record])
        record=s.records(self.root)[0]
        self.assertNotIn('history',record['metadata'])
        from knowledge_history import history_entries
        self.assertEqual(history_entries(self.root,record)[0]['body'],{'old':'evidence'})
        revision=record['metadata']['revision']
        record['metadata']['history']=[{'body':{'older':'proof'}}]
        s.save(self.root,[record])
        self.assertEqual(s.records(self.root)[0]['metadata']['revision'],revision)
        vid=review.versions(self.root,'test')[0]['id']
        shutil.rmtree(self.root/'raw')
        self.assertEqual(review.version(self.root,'test',vid)['record']['body'],record['body'])
        files=list((self.root/'knowledge-history').rglob('*.json'))
        s.save(self.root,s.records(self.root))
        self.assertEqual(files,list((self.root/'knowledge-history').rglob('*.json')))

    def test_migration_dry_run_and_old_versions_survive_clone(self):
        s.save(self.root,[self.record])
        vid=review.versions(self.root,'test')[0]['id']
        from migrate_knowledge_history import migrate
        report=migrate(self.root)
        self.assertEqual(report['notes'],1)
        self.assertNotIn('storage_version',s.read(self.root/s.INDEX))
        migrate(self.root,apply=True)
        shutil.rmtree(self.root/'raw')
        self.assertEqual(review.version(self.root,'test',vid)['id'],vid)
        files=list((self.root/'knowledge-history').rglob('*.json'))
        migrate(self.root,apply=True)
        self.assertEqual(files,list((self.root/'knowledge-history').rglob('*.json')))

    def test_archive_record_plans_portable_snapshot_without_writing(self):
        from knowledge_history import archive_record, immutable
        self.record['metadata']['history']=[{'body':{'old':'evidence'}}]
        planned=archive_record(self.record,origin='merge')
        self.assertFalse((self.root/'knowledge-history').exists())
        for entry in planned['writes']: immutable(self.root,entry['path'],entry['value'])
        saved=s.read(self.root/planned['ref'])
        self.assertEqual(saved['record']['metadata']['id'],'test')
        self.assertNotIn('history',saved['record']['metadata'])
        self.assertIn('history_head',saved['record']['metadata'])
        self.assertEqual(planned,archive_record(self.record,origin='merge'))

    def test_archive_failure_keeps_pair_and_recovery_is_idempotent(self):
        from unittest.mock import patch
        s.write_file(self.root/s.INDEX, {'schema_version':6,'storage_version':2,'notes':[],'aliases':{}})
        s.save(self.root,[self.record])
        before=s.records(self.root)[0]
        changed=s.editable_record(before)
        changed['body']['nodes'][-1]['value']='changed'
        changed['metadata']['history']=[{'previous':s.snapshot(before)}]
        write=s.write_file
        def fail(path,value):
            if 'knowledge-history' in Path(path).parts: raise OSError('interrupted archive')
            return write(path,value)
        with patch.object(s,'write_file',side_effect=fail):
            with self.assertRaises(OSError): s.save(self.root,[changed])
        self.assertEqual(s.read(self.root/before['metadata']['path']),before['body'])
        s.recover(self.root)
        files=list((self.root/'knowledge-history').rglob('*.json'))
        s.recover(self.root)
        self.assertEqual(files,list((self.root/'knowledge-history').rglob('*.json')))
        from knowledge_history import history_entries
        self.assertEqual(history_entries(self.root,s.records(self.root)[0])[0]['previous']['body'],before['body'])

    def test_corrupt_archive_and_traversal_are_rejected(self):
        from knowledge_history import archive_record,immutable,version_entries
        planned=archive_record(self.record)
        entry=planned['writes'][-1]
        with self.assertRaises(ValueError): immutable(self.root,entry['path'].replace('/versions/','/versions/../versions/'),entry['value'])
        immutable(self.root,entry['path'],entry['value'])
        value=s.read(self.root/entry['path']);value['origin']='tampered'
        s.write_file(self.root/entry['path'],value)
        with self.assertRaises(ValueError): version_entries(self.root,'test')

    def test_retired_claim_indices_follow_external_history_count(self):
        import json_document
        from knowledge_history import history_entries
        s.write_file(self.root/s.INDEX, {'schema_version':6,'storage_version':2,'notes':[],'aliases':{}})
        record=self.record
        record['body']=json_document.parse('# 测试\n\nfirst\n\nsecond\n')
        record['metadata']['claim_annotations']=[{'id':str(i),'text_ref':node['id'],'evidence':[]} for i,node in enumerate(record['body']['nodes'][1:])]
        s.save(self.root,[record])
        for expected in range(2):
            current=s.records(self.root)[0]
            current['body']['nodes'].pop()
            s.edit(self.root,'test',{'revision':current['metadata']['revision'],'document':current['body']})
            saved=s.records(self.root)[0]
            retired=saved['metadata']['retired_claim_annotations'][-1]
            self.assertEqual(retired['history_index'],expected)
            historical=history_entries(self.root,saved)[expected]['previous']
            self.assertIn(retired['id'],[a['id'] for a in historical['metadata']['claim_annotations']])

    def test_import_preserves_existing_archive_head(self):
        from unittest.mock import patch
        from knowledge_history import history_entries
        s.write_file(self.root/s.INDEX, {'schema_version':6,'storage_version':2,'notes':[],'aliases':{}})
        self.record['metadata']['history']=[{'old':'evidence'}]
        s.save(self.root,[self.record])
        incoming=s.records(self.root)[0]
        incoming['metadata'].pop('history_head');incoming['metadata'].pop('history_count')
        incoming['body']['nodes'].pop()
        with patch.object(s,'check_evidence'),patch('wxq.entities',return_value=[]): s.commit(self.root,[incoming])
        self.assertEqual(history_entries(self.root,s.records(self.root)[0])[0],{'old':'evidence'})

    def test_migration_size_includes_audit_and_mapping_without_versions(self):
        from migrate_knowledge_history import migrate
        self.record['metadata']['history']=[{'body':{'old':'evidence'}}]
        s.save(self.root,[self.record])
        shutil.rmtree(self.root/'raw/knowledge/versions')
        report=migrate(self.root)
        self.assertGreater(report['archive_bytes'],0)
        self.assertFalse((self.root/'knowledge-history').exists())

    def test_storage2_override_on_initial_note_save(self):
        s.initialize(self.root)
        s.save(self.root,[self.record],storage_version=2)
        self.assertEqual(s.read(self.root/s.INDEX)['storage_version'],2)
        self.assertEqual(s.load_record(self.root,'test')['body'],self.record['body'])
