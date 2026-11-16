"""Regression coverage for multi-note sync using canonical files and leases."""
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'frontend'), str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]

import json_store
import section_sync
from edit_locks import EditLocked
from site_access import proposal_store
from workspace import Conflict


ADMIN = {'role': 'admin', 'username': 'admin'}


def heading(nid, title, level):
    return {'id': nid, 'type': 'heading', 'level': level, 'title': title}


def entry(nid, value, key='策略'):
    return {'id': nid, 'type': 'entry', 'show_key': True, 'key': key, 'value': value}


class SectionSyncTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(dir=ROOT/'temp')
        self.addCleanup(tmp.cleanup)
        self.server = SimpleNamespace(root=Path(tmp.name))
        self.root = self.server.root
        self.add('src', '甲', [heading('h', '运营', 2), heading('sub', '前期', 3), entry('e', '旧内容'), entry('neighbor', '不要复制', '搭配')])
        self.add('same', '乙', [heading('h2', '运营', 2), heading('s2', '前期', 3), entry('e2', '旧内容')])
        self.add('conflict', '丙', [heading('h3', '运营', 2), heading('s3', '前期', 3), entry('e3', '独立内容')])
        self.add('missing', '丁', [heading('keep', '附录', 2), entry('k', '原有段落')])
        self.add('other', '戊', [entry('other', '其他阵容')], lineup='另一阵容')
        self.change('src', 'e', '新内容')

    def add(self, nid, player, nodes, lineup='阵容'):
        title = lineup + '-' + player
        player_id = 'pending:' + player
        json_store.save(self.root, [{'metadata': {
            'id': nid, 'title': title, 'type': 'lineup', 'player_id': player_id,
            'path': 'knowledge/lineups/' + nid + '.json',
        }, 'body': {'schema_version': 6, 'nodes': [heading('title', title, 1), *nodes],
                    'semantics': {'players': [player_id], 'required_factions': [], 'core_heroes': [],
                                  'compositions': {'early': [], 'middle': [], 'late': []},
                                  'ban_conditions': [], 'matchups': []}}}], partial=True)

    def record(self, nid):
        return json_store.load_record(self.root, nid)

    def change(self, nid, node_id, value):
        record = self.record(nid)
        next(node for node in record['body']['nodes'] if node['id'] == node_id)['value'] = value
        json_store.edit(self.root, nid, {'revision': record['metadata']['revision'], 'document': record['body']})

    def request(self, targets=None, actor=ADMIN, node='e'):
        data = {'node_id': node, 'revision': self.record('src')['metadata']['revision']}
        if targets is not None:
            data['targets'] = targets
        return section_sync.run(self.server, actor, 'src', data, 'S1', apply=targets is not None)

    def test_preview_and_apply_use_previous_content_and_insert_missing_path(self):
        preview = self.request()
        rows = {row['id']: row for row in preview['candidates']}
        self.assertEqual({nid: row['status'] for nid, row in rows.items()},
                         {'same': 'same', 'conflict': 'conflict', 'missing': 'missing'})
        self.assertTrue(preview['historical'])
        self.assertEqual(preview['baseline'], '旧内容')
        self.assertEqual(rows['conflict']['text'], '独立内容')
        result = self.request({nid: rows[nid]['revision'] for nid in ('same', 'missing')})
        self.assertTrue(all(row['status'] == 'saved' for row in result['results']))
        self.assertEqual(self.record('same')['body']['nodes'][-1], entry('e2', '新内容'))
        self.assertEqual(self.record('conflict')['body']['nodes'][-1], entry('e3', '独立内容'))
        inserted = self.record('missing')['body']['nodes']
        self.assertEqual([node.get('title') for node in inserted if node['type'] == 'heading'],
                         ['阵容-丁', '附录', '运营', '前期'])
        self.assertEqual([node['value'] for node in inserted if node['type'] == 'entry'],
                         ['原有段落', '新内容'])
        self.assertTrue(next(row for row in self.request()['candidates'] if row['id'] == 'same')['latest'])

    def test_stale_or_locked_target_prevents_all_writes(self):
        targets = {row['id']: row['revision'] for row in self.request()['candidates']}
        self.change('same', 'e2', '并发修改')
        with self.assertRaises(Conflict):
            self.request(targets)
        self.assertEqual(self.record('missing')['metadata']['revision'], targets['missing'])
        targets['same'] = self.record('same')['metadata']['revision']
        service = proposal_store(self.server)
        service.edit_locks.acquire(ADMIN, {'note_id': 'same', 'client_id': 'other-tab',
            'resource': {'kind': 'entry', 'id': 'e2'}})
        with self.assertRaises(EditLocked):
            self.request(targets)
        self.assertEqual(self.record('conflict')['metadata']['revision'], targets['conflict'])
        with self.assertRaises(PermissionError):
            self.request(actor={'role': 'annotator', 'username': 'writer'})

    def test_chapter_replacement_preserves_matching_ids_and_avoids_ambiguity(self):
        self.add('ambiguous', '己', [heading('ha', '运营', 2), heading('hb', '运营', 2)])
        rows = {row['id']: row for row in self.request(node='h')['candidates']}
        self.assertEqual(rows['ambiguous']['status'], 'ambiguous')
        self.request({'conflict': rows['conflict']['revision']}, node='h')
        nodes = self.record('conflict')['body']['nodes']
        self.assertEqual([node['id'] for node in nodes[:4]], ['title', 'h3', 's3', 'e3'])
        self.assertEqual([node['value'] for node in nodes[3:]], ['新内容', '不要复制'])

    def test_missing_entry_stays_in_parent_before_unrelated_subheading(self):
        self.add('nested', '庚', [heading('nh', '运营', 2), heading('ns', '前期', 3),
                                heading('extra', '额外子章节', 4), entry('unrelated', '保留')])
        row = next(row for row in self.request()['candidates'] if row['id'] == 'nested')
        self.assertEqual(row['status'], 'missing')
        self.request({'nested': row['revision']})
        nodes = self.record('nested')['body']['nodes']
        self.assertEqual(nodes[3]['value'], '新内容')
        self.assertEqual([node['id'] for node in nodes[4:]], ['extra', 'unrelated'])
