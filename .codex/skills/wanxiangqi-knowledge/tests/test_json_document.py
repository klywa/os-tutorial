import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import json_document as doc


class DocumentTests(unittest.TestCase):
    def test_lossless_markdown_and_stable_ids(self):
        text = '# 标题\n\n## 推荐天赋\n\n无标题说明。\n\n**暴君归来：** 内容 **强调**。\n\n### 补充\n\n|甲|乙|\n|--|--|\n|1|2|\n\n```md\n## 不是章节\n```\n'
        body = doc.parse(text)
        self.assertEqual(doc.markdown(body), text)
        self.assertEqual(body, doc.parse(text))
        self.assertEqual(len([n for n in body['nodes'] if n['type'] == 'heading']), 3)
        entry = next(n for n in body['nodes'] if n.get('key') == '暴君归来')
        self.assertEqual(doc.copy_entry(entry), '**暴君归来：** 内容 **强调**。')
        intro = next(n for n in body['nodes'] if n.get('value') == '无标题说明。')
        self.assertFalse(intro['show_key'])
        self.assertEqual(doc.copy_entry(intro), '**正文：** 无标题说明。')

    def test_section_includes_descendants_only(self):
        body = doc.parse('# 题\n\n## 一\n\na\n\n### 子\n\nb\n\n#### 孙\n\nc\n\n## 二\n\nd\n')
        chapter = next(n for n in body['nodes'] if n.get('title') == '一')
        self.assertEqual(doc.section(body, chapter['id']), '## 一\n\na\n\n### 子\n\nb\n\n#### 孙\n\nc\n\n')

    def test_duplicate_keys_and_validation(self):
        body = doc.parse('# 题\n\n**甲：** 一\n\n**甲：** 二\n')
        ids = [n['id'] for n in body['nodes']]
        self.assertEqual(len(ids), len(set(ids)))
        body['nodes'][1]['id'] = body['nodes'][0]['id']
        with self.assertRaises(ValueError):
            doc.validate(body)

    def test_plain_labels_and_ascii_colons_keep_original_format(self):
        text='# 棋手\n\n## 选择\n\n采用信号：已经成型。\n\n**优势:** 控制稳定。\n'
        body=doc.parse(text)
        self.assertEqual(doc.markdown(body),text)
        self.assertEqual(doc.copy_entry(body['nodes'][2]),'**采用信号：** 已经成型。')
        self.assertEqual(doc.copy_entry(body['nodes'][3]),'**优势：** 控制稳定。')


if __name__ == '__main__':
    unittest.main()
