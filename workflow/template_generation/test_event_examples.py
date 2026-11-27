import unittest
from unittest.mock import patch

from workflow.template_generation import nodes, run, seed_nodes


FIRST = '解释为何竞拍目标英雄（第1次拍卖）'
SECOND = '解释为何竞拍目标英雄（第2次拍卖）'
BUY = '解释为何购买英雄'
FIRST_EXAMPLE = {'condition': '首拍选择貂蝉，阵容需要法系输出。',
                 'utterance': '貂蝉能补法系输出，建议在3能量内拿下。'}
SECOND_EXAMPLE = {'condition': '二拍选择赵云，阵容需要能抗伤的前排。',
                  'utterance': '赵云能扛伤，建议不超过3能量。'}


class EventExamplesTest(unittest.TestCase):
    def test_standalone_examples_validate_two_fields_and_auction_budget(self):
        from workflow.template_generation import event_examples

        definitions = {FIRST: {}, SECOND: {}, BUY: {}}
        event_examples.validate({FIRST: [FIRST_EXAMPLE], SECOND: [SECOND_EXAMPLE]}, definitions)
        with self.assertRaisesRegex(ValueError, '条件和话术'):
            event_examples.validate({FIRST: [{**FIRST_EXAMPLE, 'id': 'metadata'}]}, definitions)
        with self.assertRaisesRegex(ValueError, '拍卖预算'):
            event_examples.validate({SECOND: [{'condition': '二拍赵云。', 'utterance': '登场后能回3能量。'}]}, definitions)

    def test_prompt_uses_only_events_with_conditions_for_both_paths(self):
        from workflow.template_generation import event_examples

        previous = {'enrich': {}, 'events': {'events': [{'id': 'first', 'event': FIRST},
                                                        {'id': 'second', 'event': SECOND},
                                                        {'id': 'buy', 'event': BUY}]},
                    'conditions': {'conditions': [{'event_id': 'first'}, {'event_id': 'buy'}]},
                    'seed': {'event_name': FIRST, 'extra_key': '貂蝉', 'expression': '', 'instruction': '解释竞拍'}}
        with patch.object(event_examples, 'load', return_value={FIRST: [FIRST_EXAMPLE], SECOND: [SECOND_EXAMPLE], BUY: []}):
            for prepare in (nodes.prepare, seed_nodes.prepare):
                prompt = prepare('phrases', '', None, previous)
                self.assertIn(FIRST_EXAMPLE['condition'], prompt)
                self.assertIn(FIRST_EXAMPLE['utterance'], prompt)
                self.assertNotIn(SECOND_EXAMPLE['utterance'], prompt)
            self.assertNotIn(FIRST_EXAMPLE['utterance'], nodes.prepare('conditions', '', None, previous))
            previous['conditions']['conditions'].append({'event_id': 'second'})
            prompt = nodes.prepare('phrases', '', None, previous)
            self.assertIn(FIRST_EXAMPLE['utterance'], prompt)
            self.assertIn(SECOND_EXAMPLE['utterance'], prompt)
            previous['conditions']['conditions'] = [{'event_id': 'buy'}]
            self.assertNotIn('人工话术样例', nodes.prepare('phrases', '', None, previous))

    def test_shipped_resource_is_valid_and_versioned(self):
        from workflow.template_generation import event_examples

        definitions = nodes._json(nodes.REF / 'events.json')
        event_examples.validate(event_examples.load(), definitions)
        self.assertIn('references/event-examples.json', run.resource_versions())


if __name__ == '__main__':
    unittest.main()
