"""Read-only validation and public projection regression checks."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import website_data
import json_store as store
import website_server
import reader_store


class ValidationPerformanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'knowledge').mkdir()
        (self.root/'knowledge/index.meta.json').write_text('{"notes":[]}',encoding='utf-8')
        record={'body':{'schema_version':6,'nodes':[{'id':'h','type':'heading','level':1,'title':'样例'},
                    {'id':'e','type':'entry','key':'名称','show_key':True,'value':'正文'}]},
                'metadata':{'id':'sample','type':'other','title':'样例','path':'knowledge/other/样例.json',
                            'aliases':[],'history':[{'private':'private history'}]}}
        store.save(self.root,[record],partial=True)
        website_data.export(self.root)

    def test_validation_never_clones_all_history_or_private_projection(self):
        records=store.records;project=store.project
        def readonly_records(root,clone=True):
            self.assertFalse(clone,'validation deep-copies every historical record')
            return records(root,clone=clone)
        def public_projection(record,public=False):
            self.assertTrue(public,'validation copies private history into its projection')
            return project(record,public=public)
        before=store.records(self.root)
        with patch.object(store,'records',side_effect=readonly_records),patch.object(store,'project',side_effect=public_projection):
            self.assertEqual(website_data.validate(self.root)['notes'],1)
        self.assertEqual(store.records(self.root),before)

    def test_combined_sync_check_recovers_prepares_and_validates(self):
        self.assertEqual(website_data.sync_check(self.root),{'valid':True,'notes':1})
        self.assertTrue((self.root/'entities/heroes.json').exists())

    def test_fast_validation_still_rejects_package_corruption(self):
        (self.root/'website-data/cards.json').write_text('corrupt',encoding='utf-8')
        with self.assertRaises(ValueError):website_data.validate(self.root)

    def test_fast_validation_still_rejects_invalid_canonical_reference(self):
        path=self.root/'knowledge/other/样例.json'
        body=store.read(path);body['semantics']={'broken':{'$text':'missing'}}
        store.write_file(path,body)
        meta=store.read(path.with_suffix('.meta.json'));meta['body_sha256']=store.digest(body)
        store.write_file(path.with_suffix('.meta.json'),meta)
        with self.assertRaises(ValueError):website_data.validate(self.root)

    def test_warm_public_catalog_never_loads_whole_canonical_records(self):
        with patch.object(store,'load_record',side_effect=AssertionError('warm catalog loads history')):
            catalog,projections=website_server.public_catalog(self.root)
        self.assertEqual(catalog['notes'][0]['title'],'样例')
        self.assertNotIn('private history',json.dumps([catalog,projections]))

    def test_public_projection_miss_rebuilds_only_once(self):
        (self.root/reader_store.FOLDER/'notes/sample.json').unlink()
        with patch.object(store,'load_record',wraps=store.load_record) as load:
            website_server.public_catalog(self.root)
            website_server.public_catalog(self.root)
        self.assertEqual(load.call_count,1)


if __name__=='__main__':unittest.main()
