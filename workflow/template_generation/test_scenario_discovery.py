from copy import deepcopy
import unittest

from workflow.template_generation import base_library, nodes
from workflow.template_generation.test_base_library import EVENT, EXPR, group, library


class ScenarioDiscoveryTest(unittest.TestCase):
    def test_every_source_segment_needs_an_auditable_disposition(self):
        from workflow.template_generation import scenario_discovery

        source = '# 说明\n\n购买韩信。\n'
        segments = scenario_discovery.source_segments(source)
        self.assertEqual([row['line'] for row in segments], [1, 3])
        dispositions = [{'segment_id': segments[0]['id'], 'point_ids': [], 'reason': '章节标题'}]
        with self.assertRaisesRegex(ValueError, '第 3 行'):
            scenario_discovery.validate_coverage(dispositions, segments, {})
        dispositions.append({'segment_id': segments[1]['id'], 'point_ids': [], 'reason': '已有基础组'})
        scenario_discovery.validate_coverage(dispositions, segments, {})

    def test_existing_base_is_accepted_only_with_reproducible_fallback(self):
        seed = group('seed')
        refinement = group('specific', EXPR + ' and 我方.等级 == 4')
        positive = {'我方': {'阵容名称': '开备韩信', '等级': 4}, '动作': {'选中': {'名称': '韩信'}}}
        negative, missing = deepcopy(positive), deepcopy(positive)
        negative['我方']['等级'] = 5
        del missing['我方']['等级']
        cases = [{'kind': kind, 'reason': '棋手等级', 'state': state, 'fallback': kind != 'positive'}
                 for kind, state in [('positive', positive), ('negative', negative), ('missing', missing)]]
        row = {**refinement, 'event_id': 'e1', 'layer': 'refinement', 'base_group_id': 'seed', 'cases': cases,
               'priority': 1, 'reason': '四级能找续牌', 'expected': '理由', 'limited': '四级',
               'not_limited': '能量', 'wording': '解释四级的收益'}
        previous = {'point': {'id': 'p1'}, 'events': {'events': [
            {'id': 'e1', 'event': EVENT, 'base': {'fields': ['我方.阵容名称', '动作.选中.名称']}}]},
            'base_groups': {'seed': seed}}
        result = {'point_id': 'p1', 'conditions': [row]}
        nodes.validate('conditions', result, previous)
        document = base_library.migrate(library(seed, {**refinement, 'priority': 1}))
        base_library.check_playability(document, {'specific': cases}, {'specific': 'seed'})
        document['groups'][1]['priority'] = 0
        with self.assertRaisesRegex(ValueError, '细分组'):
            base_library.check_playability(document, {'specific': cases}, {'specific': 'seed'})


if __name__ == '__main__':
    unittest.main()
