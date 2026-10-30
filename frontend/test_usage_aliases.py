"""Website aliases change metadata through canonical saves, never the strategy body."""
import json
import unittest
from unittest.mock import patch
import test_lineup_usage as fixtures
import json_store as store
import usage_aliases as aliases
import usage_matches as matches
import lineup_usage as usage


class AliasTests(unittest.TestCase):
    setUp=fixtures.WorkspaceTests.setUp
    index=fixtures.WorkspaceTests.index
    note=fixtures.WorkspaceTests.note
    lineup=fixtures.WorkspaceTests.lineup
    link=fixtures.WorkspaceTests.link
    publish=fixtures.WorkspaceTests.publish

    def prepare(self):
        self.note();self.note('other','player:2');self.lineup();self.link()

    def names(self,nid='note1'):
        return store.load_record(self.root,nid)['metadata']['aliases']

    def test_backfill_initializes_all_lineups_and_adds_only_confirmed_names(self):
        self.prepare();self.publish()
        result=aliases.backfill(self.root)
        self.assertIn('网站名',self.names());self.assertEqual(self.names('other'),[])
        self.assertEqual(result['changed'],0) # daily publishing already appended it

    def test_sync_preserves_body_existing_names_and_is_idempotent(self):
        self.prepare()
        record=store.load_record(self.root,'note1');record['metadata']['aliases']=['旧名']
        from workspace import store_lock
        with store_lock(self.root):store.save(self.root,[record],partial=True)
        path=self.root/self.rows[0]['path'];before=path.read_bytes()
        self.publish();first=store.load_record(self.root,'note1')
        self.publish();second=store.load_record(self.root,'note1')
        self.assertEqual(self.names(),['旧名','网站名']);self.assertEqual(before,path.read_bytes())
        self.assertEqual(first,second)

    def test_multiple_names_trim_dedupe_and_keep_history_after_restore(self):
        self.prepare();self.publish()
        data=matches.editor(self.root);pair=data['pairs'][0]
        payload=dict(revision=data['revision'],pair_id=pair['id'],pair_revision=pair['pair_revision'],note_id='note1')
        matches.save(self.root,payload)
        g=fixtures.group();g['name']=' 新网站名 ';self.publish([g])
        data=matches.editor(self.root);payload.update(revision=data['revision'],note_id=None)
        matches.save(self.root,payload)
        self.publish([g]);self.assertEqual(self.names(),['网站名','新网站名'])

    def test_invalid_manual_and_ambiguous_matches_do_not_append(self):
        self.prepare();self.note('second');self.link('second');self.publish()
        self.assertEqual(self.names(),[]);self.assertEqual(self.names('second'),[])
        data=matches.editor(self.root);p=data['pairs'][0]
        matches.save(self.root,dict(revision=data['revision'],pair_id=p['id'],pair_revision=p['pair_revision'],note_id='second'))
        g=fixtures.group(heroes=['card:9']);g['name']='不应写入';self.publish([g])
        self.assertNotIn('不应写入',self.names('second'));self.assertEqual(self.names('other'),[])

    def test_alias_failure_does_not_publish_new_usage_snapshot(self):
        self.prepare();self.publish();before=(self.root/usage.SNAPSHOT).read_bytes()
        with patch.object(aliases,'sync_locked',side_effect=OSError('模拟写入失败')):
            result=self.publish([fixtures.group('new')])
        self.assertEqual(result['state'],'failed');self.assertIn('别名',result['error'])
        self.assertEqual(before,(self.root/usage.SNAPSHOT).read_bytes())

    def test_snapshot_publication_cannot_interleave_with_manual_reassignment(self):
        from workspace import store_lock,Busy
        import threading
        self.prepare();observed=[];write=usage.wxq.atomic_json
        def publish(path,value):
            if path==self.root/usage.SNAPSHOT:
                def probe():
                    try:
                        with store_lock(self.root):observed.append(False)
                    except Busy:observed.append(True)
                thread=threading.Thread(target=probe);thread.start();thread.join(2)
            return write(path,value)
        with patch.object(usage.wxq,'atomic_json',side_effect=publish):self.publish()
        self.assertEqual(observed,[True])

    def test_transient_windows_journal_sharing_violation_is_retried(self):
        self.prepare();unlink=type(self.root).unlink;blocked=[]
        def busy_once(path,*args,**kwargs):
            if path==self.root/store.JOURNAL and not blocked:
                blocked.append(True);error=PermissionError('模拟Windows共享冲突');error.winerror=32;raise error
            return unlink(path,*args,**kwargs)
        with patch.object(type(self.root),'unlink',busy_once):result=self.publish()
        self.assertEqual(result['state'],'idle');self.assertEqual(blocked,[True])
        self.assertFalse((self.root/store.JOURNAL).exists());self.assertIn('网站名',self.names())

    def test_missing_alias_list_is_initialized_even_without_a_source_match(self):
        self.note()
        record=store.load_record(self.root,'note1');meta=record['metadata'];meta.pop('aliases')
        meta['revision']=store.digest({'body':record['body'],'metadata':{k:v for k,v in meta.items() if k!='revision'}})[:20]
        row=self.rows[0];row['revision']=meta['revision']
        store.write_file(self.root/store.meta_path(row['path']),meta)
        store.write_file(self.root/store.INDEX,{'notes':self.rows})
        preview=aliases.backfill(self.root,dry_run=True)
        self.assertEqual(preview['changed'],1)
        self.assertNotIn('aliases',store.load_record(self.root,'note1')['metadata'])
        self.assertEqual(aliases.backfill(self.root)['changed'],1)
        self.assertEqual(self.names(),[]);self.assertEqual(aliases.backfill(self.root)['changed'],0)

    def test_aliases_are_searchable_and_stale_editor_conflicts(self):
        from workspace import Conflict
        from reader_store import search
        self.prepare()
        path=self.root/self.rows[0]['path'];body=store.read(path)
        body['semantics'].update(required_factions=[],core_heroes=[],compositions={k:[] for k in ('early','middle','late')},ban_conditions=[],matchups=[])
        store.write_file(path,body);self.index()
        old=store.load_record(self.root,'note1')['metadata']['revision']
        self.publish()
        self.assertIn('note1',search(self.root,'网站名')['ids'])
        record=store.load_record(self.root,'note1')
        with self.assertRaises(Conflict):
            store.edit(self.root,'note1',{'revision':old,'document':record['body']})
        (self.root/'entities').mkdir(exist_ok=True)
        store.write_file(self.root/'entities/players.json',[{'id':'player:1','name':'棋手甲'},{'id':'player:2','name':'棋手乙'}])
        saved=store.edit(self.root,'note1',{'revision':record['metadata']['revision'],'document':record['body']})
        self.assertIn('网站名',saved['aliases'])

    def test_new_name_for_other_player_does_not_leak_and_blank_is_ignored(self):
        self.prepare();self.publish()
        group=fixtures.group();group['name']='  '
        self.publish([group]);self.assertEqual(self.names(),['网站名']);self.assertEqual(self.names('other'),[])

    def test_manual_failure_retains_mapping_revision_and_can_retry(self):
        self.prepare();self.note('chosen');self.publish()
        d=matches.editor(self.root);p=d['pairs'][0]
        payload=dict(revision=d['revision'],pair_id=p['id'],pair_revision=p['pair_revision'],note_id='chosen')
        with patch.object(aliases,'sync_locked',side_effect=OSError('模拟写入失败')):
            with self.assertRaisesRegex(ValueError,'别名'):matches.save(self.root,payload)
        self.assertEqual(matches.editor(self.root)['revision'],d['revision'])
        matches.save(self.root,payload);self.assertIn('网站名',self.names('chosen'))

if __name__=='__main__':unittest.main()
