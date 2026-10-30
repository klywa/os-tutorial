"""Manual intent overrides inference, but never crosses player identity silently."""
import json
import unittest
import test_lineup_usage as fixtures
import usage_matches as matches
import dashboard
import lineup_usage as usage
from workspace import Conflict


class ManualMatchTests(unittest.TestCase):
    setUp=fixtures.WorkspaceTests.setUp
    index=fixtures.WorkspaceTests.index
    note=fixtures.WorkspaceTests.note
    lineup=fixtures.WorkspaceTests.lineup
    link=fixtures.WorkspaceTests.link
    publish=fixtures.WorkspaceTests.publish

    def test_manual_assignment_after_tenth_place_is_shared_by_larger_scopes(self):
        self.note();self.note('chosen');self.lineup();self.link()
        self.publish([fixtures.group(str(i),rate=.9-i*.01) for i in range(30)])
        data=matches.editor(self.root)
        pair=next(p for p in data['pairs'][20:] if p['player_id']=='player:1')
        matches.save(self.root,{'revision':data['revision'],'pair_id':pair['id'],
                              'pair_revision':pair['pair_revision'],'note_id':'chosen'})
        rows=dashboard.snapshot(self.root,scope='usage_top50')['notes']
        row=next(r for r in rows if r['id']==pair['id'])
        self.assertEqual(row['note_id'],'chosen');self.assertEqual(row['match_basis'],'manual')
        self.assertNotIn(pair['id'],[r['id'] for r in dashboard.snapshot(self.root,scope='usage_top10')['notes']])

    def prepare(self):
        self.note();self.note('chosen');self.note('other-player','player:2')
        self.lineup();self.link();self.publish()

    def payload(self,note_id='chosen'):
        data=matches.editor(self.root);pair=data['pairs'][0]
        return {'revision':data['revision'],'pair_id':pair['id'],'pair_revision':pair['pair_revision'],'note_id':note_id}

    def test_editor_lists_source_compositions_and_current_knowledge_notes(self):
        self.prepare();data=matches.editor(self.root)
        self.assertEqual(len(data['pairs']),2);self.assertEqual(len(data['notes']),3)
        self.assertEqual(data['pairs'][0]['heroes'],['card:1','card:2'])
        self.assertIsNone(data['pairs'][0]['manual_note_id'])
        self.assertTrue(data['pairs'][0]['pair_revision'])

    def test_save_overrides_inference_immediately_and_restore_uses_automatic_again(self):
        self.prepare();matches.save(self.root,self.payload())
        r=dashboard.snapshot(self.root,scope='usage_top10')['notes'][0]
        self.assertEqual(r['note_id'],'chosen');self.assertEqual(r['match_basis'],'manual');self.assertEqual(r['manual_status'],'valid')
        matches.save(self.root,self.payload(None))
        self.assertEqual(dashboard.snapshot(self.root,scope='usage_top10')['notes'][0]['note_id'],'note1')

    def test_different_player_and_nonexistent_note_are_rejected_without_writing(self):
        self.prepare()
        for note_id in ('other-player','not-existing'):
            with self.assertRaises(ValueError):matches.save(self.root,self.payload(note_id))
        self.assertFalse((self.root/matches.FILE).exists())

    def test_stale_file_revision_conflicts_and_keeps_the_existing_choice(self):
        self.prepare();stale=self.payload();matches.save(self.root,stale)
        with self.assertRaises(Conflict):matches.save(self.root,{**stale,'note_id':'note1'})
        self.assertEqual(matches.editor(self.root)['pairs'][0]['manual_note_id'],'chosen')

    def test_source_change_while_dialog_is_open_conflicts_before_saving(self):
        self.prepare();payload=self.payload();path=self.root/usage.SNAPSHOT
        source=json.loads(path.read_text('utf-8'));source['pairs'][0]['heroes']=['card:9'];path.write_text(json.dumps(source),encoding='utf-8')
        with self.assertRaises(Conflict):matches.save(self.root,payload)
        self.assertFalse((self.root/matches.FILE).exists())

    def test_source_change_or_deleted_target_does_not_silently_revert_to_inference(self):
        self.prepare();matches.save(self.root,self.payload())
        path=self.root/usage.SNAPSHOT;source=json.loads(path.read_text('utf-8'));source['pairs'][0]['heroes']=['card:9'];path.write_text(json.dumps(source),encoding='utf-8')
        row=dashboard.snapshot(self.root,scope='usage_top10')['notes'][0]
        self.assertEqual(row['manual_status'],'invalid');self.assertEqual(row['match_status'],'ambiguous');self.assertIsNone(row['rate']);self.assertIn('组成',row['manual_error'])
        matches.save(self.root,self.payload())
        self.rows=[r for r in self.rows if r['id']!='chosen'];self.index()
        row=dashboard.snapshot(self.root,scope='usage_top10')['notes'][0]
        self.assertEqual(row['manual_note_id'],'chosen');self.assertEqual(row['manual_status'],'invalid');self.assertNotIn('note_id',row)

    def test_new_daily_snapshot_and_note_rename_preserve_manual_choice(self):
        self.prepare();matches.save(self.root,self.payload());self.publish()
        next(r for r in self.rows if r['id']=='chosen')['title']='改名后的笔记';self.index()
        row=dashboard.snapshot(self.root,scope='usage_top10')['notes'][0]
        self.assertEqual(row['note_id'],'chosen');self.assertEqual(row['manual_status'],'valid')

    def test_pair_leaving_top10_does_not_delete_saved_mapping(self):
        self.prepare();matches.save(self.root,self.payload());self.publish([fixtures.group('new')])
        self.assertIn('g@player:1',matches.read(self.root)['assignments'])
        self.publish();self.assertEqual(dashboard.snapshot(self.root,scope='usage_top10')['notes'][0]['note_id'],'chosen')

    def test_only_target_alias_metadata_changes_and_old_roster_is_untouched(self):
        self.prepare();before={str(p):p.read_bytes() for p in (self.root/'knowledge/lineups').glob('*.json') if not p.name.endswith('.meta.json')}
        roster=list(self.db.execute('SELECT * FROM topic_lineups'));links=list(self.db.execute('SELECT * FROM lineup_note_roles'))
        matches.save(self.root,self.payload())
        self.assertEqual(before,{str(p):p.read_bytes() for p in (self.root/'knowledge/lineups').glob('*.json') if not p.name.endswith('.meta.json')})
        self.assertIn('网站名',fixtures.usage.store.load_record(self.root,'chosen')['metadata']['aliases'])
        self.assertEqual(roster,list(self.db.execute('SELECT * FROM topic_lineups')));self.assertEqual(links,list(self.db.execute('SELECT * FROM lineup_note_roles')))

if __name__=='__main__':unittest.main()
