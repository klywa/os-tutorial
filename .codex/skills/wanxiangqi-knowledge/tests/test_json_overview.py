import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import json_document as doc


class OverviewTests(unittest.TestCase):
    def test_stages_use_current_nodes_and_stop_at_chapter_boundaries(self):
        body = doc.parse('# 阵容\n\n## 阵容组成与运营节奏\n\n### 前期英雄组成与运营\n\n**开局：** 当前建议\n\n#### 补充\n\n隐藏段落\n\n### 中期英雄组成与运营\n\n中期建议\n\n### 后期英雄组成与运营\n\n后期建议\n\n### 后期提升思路\n\n提升建议\n\n## 拍卖\n\n不要混入阶段\n')
        entry = next(n for n in body['nodes'] if n.get('key') == '开局')
        note = {'id':'lineup', 'revision':'r', 'type':'lineup',
                'claims':[{'id':'c1', 'text_ref':entry['id'], 'text':'过期旧建议'}],
                'meta':{'operation_routes':[{'id':'r1','name':'路线一','phases':{'early':['c1']}}]}}
        before = doc.markdown(body)
        result = doc.reading(body, note)
        rows = result['overview_operations']
        self.assertEqual(rows['early'][0]['node_id'], entry['id'])
        self.assertTrue(all(row['node_id'] in {n['id'] for n in body['nodes']}
                            for group in rows.values() for row in group))
        self.assertEqual([r['markdown'] for r in rows['early']], ['**开局：** 当前建议', '隐藏段落'])
        self.assertEqual(rows['early'][0]['claim_refs'], ['c1'])
        self.assertEqual(rows['early'][0]['route_ids'], ['r1'])
        self.assertEqual([r['markdown'] for r in rows['improvement']], ['提升建议'])
        self.assertEqual([r['markdown'] for r in rows['late']], ['后期建议'])
        self.assertEqual(doc.markdown(body), before)
        entry['value'] = '修改后的建议'
        self.assertIn('修改后的建议', doc.reading(body, note)['overview_operations']['early'][0]['markdown'])

    def test_non_lineup_has_no_overview(self):
        body = doc.parse('# 棋手\n\n## 前期\n\n说明\n')
        result = doc.reading(body, {'id':'player','revision':'r','type':'player'})
        self.assertNotIn('overview_operations', result)

    def test_supporting_claim_route_maps_to_visible_node(self):
        body = doc.parse('# 阵容\n\n## 前期\n\n**开局：** 路线建议\n')
        entry = body['nodes'][-1]
        note = {'id':'n','revision':'r','type':'lineup','claims':[{'id':'c','text_ref':'support-c','text':'路线建议'}],
                'meta':{'operation_routes':[{'id':'r','name':'路线','phases':{'early':['c']}}]}}
        row = doc.reading(body, note)['overview_operations']['early'][0]
        self.assertEqual(row['route_ids'], ['r'])
        note['claims'][0]['display_ref'] = entry['id']
        entry['value'] = '修改后的路线建议'
        row = doc.reading(body, note)['overview_operations']['early'][0]
        self.assertEqual(row['route_ids'], ['r'])
        self.assertEqual(row['markdown'], '**开局：** 修改后的路线建议')
        body['nodes'][1]['title'] = '中期'
        row = doc.reading(body, note)['overview_operations']['middle'][0]
        self.assertEqual(row['route_ids'], ['r'])
