import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import workspace
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'frontend'))
import crawler


class RegistrationLockTests(unittest.TestCase):
    def test_connection_reset_is_network_failure_and_automatically_requeued(self):
        from acquisition_errors import describe_error
        error = 'Unable to download JSON metadata: [WinError 10054] 远程主机强迫关闭了一个现有的连接。 (caused by TransportError)'
        self.assertEqual(describe_error(error)['category'], 'network')
        temp_root = Path(__file__).resolve().parents[4] / '.wxq-runtime/test-temp'
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as folder:
            store = crawler.Store(Path(folder))
            job = store.new_job({})
            store.discover(job['id'], {'bvid': 'BV1234567890'}, '', True)
            task = store.claim()
            store.finish_task(task['bvid'], 'failed', error, generation=task['generation'])
            store.adopt_network_failures()
            self.assertEqual(store.tasks()[0]['state'], 'queued')

    def test_registration_does_not_project_knowledge_under_writer_lock(self):
        temp_root = Path(__file__).resolve().parents[4] / '.wxq-runtime/test-temp'
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as folder:
            root = Path(folder)
            metadata = {'id': 'BV1234567890:p1', 'url': 'https://www.bilibili.com/video/BV1234567890?p=1', 'title': 'Imported title'}
            path = root / 'raw/sources/BV1234567890_p1/metadata.json'
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(metadata), encoding='utf-8')
            with patch.object(workspace, 'notes', side_effect=AssertionError('full knowledge scan')):
                crawler.register_discovered(root, {'url': metadata['url'], 'title': 'Search title'})
                row = json.loads((root / 'knowledge/source-registry.json').read_text(encoding='utf-8'))[0]
                self.assertEqual(row['id'], metadata['id'])
                self.assertEqual(row['title'], 'Imported title')
                workspace.register_source(root, {'url': metadata['url'], 'title': 'Manual title'}, _metadata=metadata)
                crawler.register_discovered(root, {'url': metadata['url'], 'title': 'Search title'})
                row = json.loads((root / 'knowledge/source-registry.json').read_text(encoding='utf-8'))[0]
                self.assertEqual(row['title'], 'Manual title')


if __name__ == '__main__':
    unittest.main()
