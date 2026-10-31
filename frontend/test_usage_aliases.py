"""External website names remain local until an explicit note edit."""
import unittest
import subprocess
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

    def knowledge(self):
        return {p.relative_to(self.root).as_posix():p.read_bytes() for p in (self.root/'knowledge').rglob('*.json')}

    def test_daily_publication_keeps_canonical_files_and_revision(self):
        self.prepare();before=self.knowledge()
        self.publish();self.publish()
        self.assertEqual(before,self.knowledge())
        self.assertEqual(usage.cached_snapshot(self.root)['pairs'][0]['source_name'],'网站名')

    def test_manual_mapping_and_restore_do_not_append_names(self):
        self.prepare();self.note('chosen');self.publish();before=self.knowledge()
        for nid in ('chosen',None):
            data=matches.editor(self.root);p=data['pairs'][0]
            matches.save(self.root,dict(revision=data['revision'],pair_id=p['id'],pair_revision=p['pair_revision'],note_id=nid))
            self.assertEqual(before,self.knowledge())

    def test_refresh_and_mapping_leave_git_clean(self):
        self.prepare();self.note('chosen')
        (self.root/'.gitignore').write_bytes((fixtures.ROOT/'.gitignore').read_bytes())
        def git(*args):
            return subprocess.check_output(['git','-C',str(self.root),*args],stderr=subprocess.STDOUT)
        git('init','-q');git('add','.')
        git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','baseline')
        self.publish()
        data=matches.editor(self.root);p=data['pairs'][0]
        matches.save(self.root,dict(revision=data['revision'],pair_id=p['id'],pair_revision=p['pair_revision'],note_id='chosen'))
        self.assertEqual(git('status','--porcelain'),b'')

    def test_alias_preview_is_read_only_and_legacy_write_is_rejected(self):
        self.prepare();self.publish();before=self.knowledge()
        self.assertEqual(aliases.backfill(self.root)['added'],1)
        self.assertEqual(before,self.knowledge())
        with self.assertRaisesRegex(ValueError,'笔记编辑'):aliases.backfill(self.root,dry_run=False)

    def test_alias_writer_failure_cannot_break_snapshot_or_mapping(self):
        self.prepare();self.publish()
        with patch.object(aliases,'sync_locked',side_effect=OSError('must not be called')):
            self.assertEqual(self.publish([fixtures.group('new')])['state'],'idle')
            data=matches.editor(self.root);p=data['pairs'][0]
            matches.save(self.root,dict(revision=data['revision'],pair_id=p['id'],pair_revision=p['pair_revision'],note_id='note1'))
        self.assertEqual(store.load_record(self.root,'note1')['metadata']['aliases'],[])

    def test_snapshot_publication_keeps_store_lock(self):
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

    def test_editor_still_saves_searchable_aliases(self):
        from reader_store import search,rebuild
        self.prepare()
        record=store.load_record(self.root,'note1')
        record['body']['semantics'].update(required_factions=[],core_heroes=[],compositions={k:[] for k in ('early','middle','late')},ban_conditions=[],matchups=[])
        (self.root/'entities').mkdir(exist_ok=True)
        store.write_file(self.root/'entities/players.json',[{'id':'player:1','name':'棋手甲'},{'id':'player:2','name':'棋手乙'}])
        saved=store.edit(self.root,'note1',{'revision':record['metadata']['revision'],'document':record['body'],'aliases':['人工别名']})
        self.assertEqual(saved['aliases'],['人工别名'])
        rebuild(self.root)
        self.assertIn('note1',search(self.root,'人工别名')['ids'])


if __name__=='__main__':unittest.main()
