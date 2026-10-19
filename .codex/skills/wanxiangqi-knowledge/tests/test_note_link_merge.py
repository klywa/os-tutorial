import unittest
import test_note_links as fixtures
from note_links import associate,auto_link
import workspace


class NoteLinkMergeTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.NoteLinkTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.cat=self.fixture.cat;self.root=self.fixture.root
 def merge(self,source,target):
  rows={r['id']:r for r in self.cat.roster()}
  return self.cat.merge({'source':source,'target':target,'source_revision':rows[source]['revision'],'target_revision':rows[target]['revision']})
 def test_merge_preserves_primary_variant_and_exclusions(self):
  f=self.fixture;a=f.lineup();f.note('one','主笔记甲');f.note('two','变体乙');f.note('three','禁止自动关联')
  associate(self.root,f.payload(a['id'],'one'));associate(self.root,f.payload(a['id'],'two','variant'))
  b=f.lineup('目标阵容','禁止自动关联')
  # Simulate manual exclusions before merging, including the target's original
  # automatic association so the source exclusions are the only protection.
  with self.cat.topics.db() as db:
   db.execute('DELETE FROM lineup_notes WHERE lineup=?',(b['id'],));db.execute('DELETE FROM lineup_note_roles WHERE lineup=?',(b['id'],))
   db.execute('INSERT INTO lineup_note_exclusions VALUES(?,?)',(a['id'],'three'))
  self.merge(a['id'],b['id']);auto_link(self.root)
  row=next(r for r in self.cat.roster() if r['id']==b['id'])
  self.assertEqual(row['note_links'],[{'note':'one','role':'primary'},{'note':'two','role':'variant'}])
  with self.cat.topics.db() as db:
   self.assertTrue(db.execute('SELECT 1 FROM lineup_note_exclusions WHERE lineup=? AND note=?',(b['id'],'three')).fetchone())
   self.assertFalse(db.execute('SELECT 1 FROM lineup_note_roles WHERE lineup=?',(a['id'],)).fetchone())
  # Removing the primary must not let the excluded exact-name note appear.
  associate(self.root,f.payload(b['id'],'one','unlink'));auto_link(self.root)
  self.assertNotIn('three',next(r for r in self.cat.roster() if r['id']==b['id'])['note_ids'])
 def test_distinct_primaries_reject_merge_without_changes(self):
  f=self.fixture;a=f.lineup();f.note('one','主笔记甲');associate(self.root,f.payload(a['id'],'one'))
  b=f.lineup('目标阵容','目标名称');f.note('two','主笔记乙');associate(self.root,f.payload(b['id'],'two'))
  before=self.cat.roster()
  with self.assertRaises(workspace.Conflict):self.merge(a['id'],b['id'])
  self.assertEqual(self.cat.roster(),before)
 def test_legacy_single_primary_is_preserved_when_adding_variants(self):
  f=self.fixture;a=f.lineup();f.note('one','原主笔记');b=f.lineup('目标阵容','目标名称');f.note('two','变体笔记')
  with self.cat.topics.db() as db:
   db.execute('INSERT INTO lineup_notes VALUES(?,?)',(a['id'],'one'))
   db.execute('INSERT INTO lineup_notes VALUES(?,?)',(b['id'],'two'))
   db.execute("INSERT INTO lineup_note_roles VALUES(?,?,'variant')",(b['id'],'two'))
  self.merge(a['id'],b['id'])
  self.assertEqual(next(r for r in self.cat.roster() if r['id']==b['id'])['primary_note_id'],'one')
