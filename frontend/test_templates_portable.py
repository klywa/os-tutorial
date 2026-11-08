"""Pure portable conversion tests: no workspace or service writes."""
import copy
import unittest

import templates_entities as entities
import templates_portable as portable


CATALOG = {
    'h2': {'id': 'h2', 'name': '英雄甲', 'category': 'heroes', 'aliases': ['甲']},
    'h1': {'id': 'h1', 'name': '英雄甲', 'category': 'heroes', 'aliases': ['甲']},
    'e1': {'id': 'e1', 'name': '英雄甲', 'category': 'equipment'},
}


def library():
    return {'schema_version': 1, 'events': [{'id': 'ev', 'name': '购买', 'category': '英雄', 'parameters': [
        {'id': 'p', 'key': 'hero', 'name': '英雄', 'type': 'entity', 'entity_categories': ['heroes'],
         'suggestions': [{'id': 'h1', 'name': '英雄甲'}]}]}], 'groups': [
        {'id': 'g', 'name': '购买话术', 'event_id': 'ev', 'scope': {'player_id': None, 'lineup_note_id': None},
         'conditions': [{'id': 'c', 'parameter_key': 'hero', 'operator': 'eq', 'value': {'id': 'h1', 'name': '英雄甲'}}],
         'utterances': [{'id': 'u1', 'text': '你好'}, {'id': 'u2', 'text': '你好'}, {'id': 'u3', 'text': '再见'}],
         'related_entities': [{'id': 'h2', 'name': '英雄甲'}]}]}


class EntityTests(unittest.TestCase):
    def test_alias_versions_and_category(self):
        self.assertEqual([e['id'] for e in entities.resolve(' 甲 ', {'key': 'hero', 'entity_categories': ['heroes']}, CATALOG)], ['h1', 'h2'])
        with self.assertRaisesRegex(ValueError, 'hero'):
            entities.resolve('英雄甲', {'key': 'hero'}, CATALOG)
        with self.assertRaisesRegex(ValueError, '不存在'):
            entities.resolve('不存在', {'key': 'hero'}, CATALOG)

    def test_exact_precedes_alias(self):
        catalog = {**CATALOG, 'h3': {'id': 'h3', 'name': '甲', 'category': 'heroes'}}
        self.assertEqual([e['id'] for e in entities.resolve('甲', {'key': 'hero', 'entity_categories': ['heroes']}, catalog)], ['h3'])

    def test_alias_expands_other_versions_with_same_canonical_name(self):
        catalog = copy.deepcopy(CATALOG); catalog['h2']['aliases'] = []
        self.assertEqual([e['id'] for e in entities.resolve('甲', {'key': 'hero', 'entity_categories': ['heroes']}, catalog)], ['h1', 'h2'])


class PortableTests(unittest.TestCase):
    def test_roundtrip_preserves_canonical_ids_and_archive(self):
        original = library()
        external = portable.encode(original)
        self.assertEqual(external['schema_version'], 2)
        group = external['groups'][0]
        self.assertEqual(group['utterances'], ['你好', '你好', '再见'])
        self.assertNotIn('related_entities', group)
        self.assertNotIn('id', group['conditions'][0])
        self.assertEqual(group['conditions'][0]['value'], '英雄甲')
        self.assertNotIn('id', external['events'][0]['parameters'][0])
        actual = portable.decode(external, original, CATALOG, {})
        self.assertEqual(actual['events'], original['events'])
        self.assertEqual(actual['groups'], original['groups'])

    def test_reorder_duplicates_and_replacement_keep_ids(self):
        original = library(); external = portable.encode(original)
        external['groups'][0]['utterances'] = ['再见', '你好', '改写']
        actual = portable.decode(external, original, CATALOG, {})['groups'][0]['utterances']
        self.assertEqual([u['id'] for u in actual], ['u3', 'u1', 'u2'])

    def test_event_name_fallback_and_new_ids(self):
        external = portable.encode(library())
        del external['events'][0]['id']; del external['groups'][0]['id']
        del external['groups'][0]['event_id']
        external['groups'][0]['event_name'] = '购买'
        actual = portable.decode(external, library(), CATALOG, {})
        self.assertNotEqual(actual['events'][0]['id'], 'ev')
        self.assertEqual(actual['groups'][0]['event_id'], actual['events'][0]['id'])
        self.assertEqual(actual['groups'][0]['related_entities'], [])

    def test_strict_fields_and_reference_ambiguity(self):
        for field, value in [('related_entities', []), ('hidden', True)]:
            external = portable.encode(library()); external['groups'][0][field] = value
            with self.assertRaises(ValueError): portable.decode(external, library(), CATALOG, {})
        external = portable.encode(library()); external['groups'][0]['conditions'][0]['id'] = 'bad'
        with self.assertRaises(ValueError): portable.decode(external, library(), CATALOG, {})
        external = portable.encode(library()); external['groups'][0]['event_name'] = '错误'
        with self.assertRaises(ValueError): portable.decode(external, library(), CATALOG, {})
        external = portable.encode(library()); second = copy.deepcopy(external['events'][0]); second['id'] = 'ev2'
        external['events'].append(second); del external['groups'][0]['event_id']; external['groups'][0]['event_name'] = '购买'
        with self.assertRaises(ValueError): portable.decode(external, library(), CATALOG, {})

    def test_v1_missing_ids_and_existing_ids(self):
        external = {'kind': 'speech-template-library', **library()}
        self.assertEqual(portable.decode(external, library(), CATALOG, {})['groups'], library()['groups'])
        del external['groups'][0]['conditions'][0]['id']
        self.assertTrue(portable.decode(external, library(), CATALOG, {})['groups'][0]['conditions'][0]['id'])

    def test_preserved_retired_manual_archive_is_not_revalidated(self):
        original = library(); original['groups'][0]['related_entities'] = [{'id': 'retired', 'name': '旧卡'}]
        external = portable.encode(original)
        self.assertEqual(portable.decode(external, original, CATALOG, {})['groups'][0]['related_entities'], original['groups'][0]['related_entities'])

    def test_insert_delete_reorder_and_condition_replacement(self):
        original = library()
        for texts, expected in [(['插入', '你好', '你好', '再见'], [None, 'u1', 'u2', 'u3']),
                                (['你好', '再见'], ['u1', 'u3']),
                                (['再见', '你好', '你好'], ['u3', 'u1', 'u2']),
                                (['修改', '你好', '再见'], ['u2', 'u1', 'u3'])]:
            external = portable.encode(original); external['groups'][0]['utterances'] = texts
            actual = portable.decode(external, original, CATALOG, {})['groups'][0]['utterances']
            for row, identity in zip(actual, expected):
                if identity is None: self.assertNotIn(row['id'], ['u1', 'u2', 'u3'])
                else: self.assertEqual(row['id'], identity)
        external = portable.encode(original); external['groups'][0]['conditions'][0]['operator'] = 'ne'
        self.assertEqual(portable.decode(external, original, CATALOG, {})['groups'][0]['conditions'][0]['id'], 'c')

    def test_v2_entity_id_objects_and_utterance_objects_reject(self):
        for path in ('condition', 'suggestion', 'utterance'):
            external = portable.encode(library())
            if path == 'condition': external['groups'][0]['conditions'][0]['value'] = {'id': 'h1', 'name': '英雄甲'}
            elif path == 'suggestion': external['events'][0]['parameters'][0]['suggestions'] = [{'id': 'h1', 'name': '英雄甲'}]
            else: external['groups'][0]['utterances'] = [{'id': 'u1', 'text': '你好'}]
            with self.assertRaises(ValueError): portable.decode(external, library(), CATALOG, {})

    def test_typed_values_use_canonical_validation(self):
        for kind, value, valid in [('number', True, False), ('number', 2, True), ('boolean', 1, False),
                                   ('boolean', False, True), ('text', {}, False), ('text', '文本', True)]:
            external = portable.encode(library()); parameter = external['events'][0]['parameters'][0]
            parameter['type'] = kind; parameter.pop('entity_categories'); parameter.pop('suggestions')
            external['groups'][0]['conditions'][0]['value'] = value
            if valid: portable.decode(external, library(), CATALOG, {})
            else:
                with self.assertRaises(ValueError): portable.decode(external, library(), CATALOG, {})

    def test_alias_selector_is_preserved_and_resolves_all_versions(self):
        external = portable.encode(library()); external['groups'][0]['conditions'][0]['value'] = ' 甲 '
        decoded = portable.decode(external, library(), CATALOG, {})
        self.assertEqual(decoded['groups'][0]['conditions'][0]['value'], {'id': 'h1', 'name': '甲'})
        self.assertEqual(portable.encode(decoded)['groups'][0]['conditions'][0]['value'], '甲')

    def test_invalid_identity_key_and_explicit_event_name_reject_cleanly(self):
        for location in ('event_id', 'group_id', 'parameter_key', 'event_name'):
            external = portable.encode(library())
            if location == 'event_id': external['events'][0]['id'] = []
            elif location == 'group_id': external['groups'][0]['id'] = []
            elif location == 'parameter_key': external['events'][0]['parameters'][0]['key'] = []
            else: external['groups'][0]['event_name'] = None
            with self.assertRaises(ValueError): portable.decode(external, library(), CATALOG, {})

    def test_existing_nonprimary_entity_anchors_survive_roundtrip(self):
        original = library()
        original['groups'][0]['conditions'][0]['value']['id'] = 'h2'
        original['events'][0]['parameters'][0]['suggestions'][0]['id'] = 'h2'
        catalog = {**CATALOG, 'h0': {'id': 'h0', 'name': '英雄甲', 'category': 'heroes'}}
        decoded = portable.decode(portable.encode(original), original, catalog, {})
        self.assertEqual(decoded['groups'], original['groups'])
        self.assertEqual(decoded['events'], original['events'])

    def test_renamed_and_retired_group_anchors_survive_roundtrip(self):
        original = library(); external = portable.encode(original)
        renamed = copy.deepcopy(CATALOG); renamed['h1']['name'] = '改名'
        decoded = portable.decode(external, original, renamed, {})
        self.assertEqual(decoded['groups'], original['groups'])
        deleted = {key: row for key, row in CATALOG.items() if key != 'h1'}
        retired = {'g': {'h1': CATALOG['h1']}}
        retired_suggestions = {'ev': {'p': {'h1': CATALOG['h1']}}}
        decoded = portable.decode(external, original, deleted, {}, retired_entities=retired, retired_suggestions=retired_suggestions)
        self.assertEqual(decoded['groups'], original['groups'])
        self.assertEqual(decoded['events'], original['events'])

    def test_retired_selector_is_scoped_and_new_values_still_reject(self):
        original = library(); external = portable.encode(original)
        deleted = {'e1': CATALOG['e1']}
        retired = {'g': {'h1': CATALOG['h1']}}
        suggestions = {'ev': {'p': {'h1': CATALOG['h1']}}}
        decoded = portable.decode(external, original, deleted, {}, retired_entities=retired, retired_suggestions=suggestions)
        self.assertEqual(decoded['groups'], original['groups'])
        external['groups'][0]['id'] = 'new_group'
        with self.assertRaises(ValueError): portable.decode(external, original, deleted, {}, retired_entities=retired, retired_suggestions=suggestions)
        external = portable.encode(original); external['events'][0]['id'] = 'new_event'
        external['groups'] = []
        with self.assertRaises(ValueError): portable.decode(external, original, deleted, {}, retired_entities=retired, retired_suggestions=suggestions)
        external = portable.encode(original); external['groups'][0]['conditions'][0]['value'] = '未知新值'
        with self.assertRaises(ValueError): portable.decode(external, original, deleted, {}, retired_entities=retired, retired_suggestions=suggestions)

    def test_v1_retired_roundtrip_is_scoped_to_existing_records(self):
        original = library(); external = {'kind': 'speech-template-library', **copy.deepcopy(original)}
        deleted = {'h2': CATALOG['h2'], 'e1': CATALOG['e1']}
        retired = {'g': {'h1': CATALOG['h1']}}
        suggestions = {'ev': {'p': {'h1': CATALOG['h1']}}}
        decoded = portable.decode(external, original, deleted, {}, retired_entities=retired, retired_suggestions=suggestions)
        self.assertEqual(decoded['groups'], original['groups'])
        self.assertEqual(decoded['events'], original['events'])
        external['groups'][0]['id'] = 'new_group'
        with self.assertRaises(ValueError): portable.decode(external, original, deleted, {}, retired_entities=retired, retired_suggestions=suggestions)

        external['groups'] = []; external['events'][0]['id'] = 'new_event'
        with self.assertRaises(ValueError): portable.decode(external, original, deleted, {}, retired_entities=retired, retired_suggestions=suggestions)

    def test_operator_only_edit_preserves_nonprimary_and_retired_anchor(self):
        original = library(); original['groups'][0]['conditions'][0]['value']['id'] = 'h2'
        external = portable.encode(original); external['groups'][0]['conditions'][0]['operator'] = 'ne'
        decoded = portable.decode(external, original, CATALOG, {})
        self.assertEqual(decoded['groups'][0]['conditions'][0]['value']['id'], 'h2')
        deleted = {key: row for key, row in CATALOG.items() if key != 'h2'}
        decoded = portable.decode(external, original, deleted, {}, retired_entities={'g': {'h2': CATALOG['h2']}})
        self.assertEqual(decoded['groups'][0]['conditions'][0]['value']['id'], 'h2')

    def test_changed_operator_does_not_steal_later_exact_anchor(self):
        original = library(); conditions = original['groups'][0]['conditions']
        conditions.append({'id': 'c2', 'parameter_key': 'hero', 'operator': 'ne', 'value': {'id': 'h2', 'name': '英雄甲'}})
        external = portable.encode(original); external['groups'][0]['conditions'][0]['operator'] = 'ne'
        # The later unchanged ne occurrence owns h2; the changed occurrence
        # falls back to the remaining eq anchor h1.
        decoded = portable.decode(external, original, CATALOG, {})
        self.assertEqual([row['value']['id'] for row in decoded['groups'][0]['conditions']], ['h1', 'h2'])


if __name__ == '__main__': unittest.main()
