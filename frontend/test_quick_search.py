import unittest
from unittest.mock import Mock

from quick_search import search


class QuickSearchTest(unittest.TestCase):
    def test_filters_inclusive_and_resumes_mid_page(self):
        upstream = Mock()
        def page(keyword, number, order):
            return [
                dict(bvid=f'BV{number}{i:02}', published='2026-11-13' if number == 1 else '2026-11-14',
                     author='UP', title='标题', url='https://www.bilibili.com/video/BV', view_count=1)
                for i in range(19)
            ], number < 3
        upstream.search_page.side_effect = page
        first = search(upstream, '万象棋', '2026-11-14', '')
        second = search(upstream, '万象棋', '2026-11-14', first['next_cursor'])
        self.assertEqual(len(first['items']), 20)
        self.assertEqual(first['items'][0]['bvid'], 'BV200')
        self.assertEqual(second['items'][0]['bvid'], 'BV301')
        self.assertEqual(len(second['items']), 18)
        self.assertIsNone(second['next_cursor'])

    def test_bounded_scan_keeps_continuation_and_surfaces_errors(self):
        upstream = Mock()
        upstream.search_page.return_value = ([], True)
        result = search(upstream, '万象棋', '', '')
        self.assertEqual(upstream.search_page.call_count, 3)
        self.assertEqual(result, {'items': [], 'next_cursor': '4:0'})
        upstream.search_page.side_effect = OSError('offline')
        with self.assertRaises(OSError):
            search(upstream, '万象棋', '', result['next_cursor'])
