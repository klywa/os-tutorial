import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'frontend'),str(ROOT/'.codex/skills/wanxiangqi-knowledge/scripts')]
import lineup_usage as usage
import lineup_website as website
import dashboard

def group(key='g',heroes=None,rate=.4,count=1000,commanders=None):
    return {'id':key,'name':'网站名','heroes':heroes or ['card:1','card:2'],'count':count,'usage':rate,
            'commanders':commanders if commanders is not None else [{'id':'player:1','name':'棋手甲','count':600},{'id':'player:2','name':'棋手乙','count':400}]}

class RankingTests(unittest.TestCase):
    def test_top20_and_top50_keep_stable_prefixes(self):
        groups=[group(str(i),rate=.9-i*.01) for i in range(35)]
        fifty=usage.rank_pairs(groups,limit=50)
        self.assertEqual(len(fifty),50)
        self.assertEqual(usage.rank_pairs(groups,limit=20),fifty[:20])
        self.assertEqual(usage.rank_pairs(groups),fifty[:10])

    def test_joint_usage_not_conditional_share_or_sample_count(self):
        groups=[group('popular',rate=.4),group('rare',rate=.01,commanders=[{'id':'player:3','name':'棋手丙','count':1000}])]
        pairs=usage.rank_pairs(groups)
        self.assertEqual([x['player_id'] for x in pairs],['player:1','player:2','player:3'])
        self.assertAlmostEqual(pairs[0]['usage'],.24)

    def test_top10_precedes_local_matching_and_filters_each_pair_at_50_games(self):
        groups=[group(str(i),rate=.8-i*.02,commanders=[{'id':'player:1','name':'棋手甲','count':1000}]) for i in range(12)]
        groups.insert(0,group('under50',rate=1,commanders=[{'id':'player:1','name':'棋手甲','count':49}]))
        pairs=usage.rank_pairs(groups)
        self.assertEqual(len(pairs),10);self.assertEqual(pairs[0]['source_id'],'0')
        self.assertEqual([p['rank'] for p in pairs],list(range(1,11)))

    def test_fourth_commander_is_eligible_and_ties_are_stable(self):
        commanders=[{'id':'player:'+str(i),'name':str(i),'count':100} for i in [4,3,2,1]]
        a=usage.rank_pairs([group(commanders=commanders)])
        b=usage.rank_pairs([group(commanders=list(reversed(commanders)))])
        self.assertEqual([x['id'] for x in a],[x['id'] for x in b]);self.assertEqual(len(a),4)

class SourceTests(unittest.TestCase):
    def test_twenty_limit_does_not_prune_at_ten_pairs(self):
        detailed=[]
        def read(url,payload=None):
            if payload is None:
                if url.endswith('/lineups'):return '<script src="/assets/index-test.js"></script>'
                if 'index-test' in url:return 'assets/desktop-main-test.js'
                return '[{value:"v1",label:"v1"}]'
            if url.endswith('/search'):
                return json.dumps({'total':3,'lineups':[{'lineupKey':str(i),'heroes':[{'id':'1','name':'甲'}],'count':1000,'appearanceRate':rate} for i,rate in enumerate([.5,.02,.0001])]})
            detailed.append(payload['lineupKey'])
            return json.dumps({'count':1000,'commanders':[{'id':str(i),'count':50,'name':str(i)} for i in range(10)]})
        result=website.fetch_usage(ROOT,read=read,pause=lambda:None,limit=20)
        self.assertEqual(detailed,['0','1'])
        self.assertEqual(len(usage.rank_pairs(result['groups'],limit=20)),20)

    def test_current_site_name_uses_level_carries_not_only_three_item_units(self):
        heroes=[{'id':'card:1','name':'公孙离','properties':{'relationName':'大河流域'}},{'id':'card:2','name':'虞姬','properties':{'relationName':'大河流域'}}]
        row={'heroes':[{'id':'1','name':'公孙离'},{'id':'2','name':'虞姬'}],
             'heroEquipment':[{'heroId':'1','avgLevel':180,'appearanceRate':1,'count':100},{'heroId':'2','avgLevel':98,'appearanceRate':1,'count':100}],
             'recommendedUnits':[{'heroId':'1','itemIds':['a','b','c'],'appearanceRate':1,'count':100}]}
        self.assertEqual(website.display_name(row,heroes),'大河流域 · 公孙离 · 虞姬')

    def test_changed_total_across_pages_is_rejected_instead_of_publishing_a_skipped_row(self):
        def read(url,payload=None):
            if payload is None:
                if url.endswith('/lineups'):return '<script src="/assets/index-test.js"></script>'
                if 'index-test' in url:return 'assets/desktop-main-test.js'
                return '[{value:"v1",label:"v1"}]'
            if url.endswith('/search'):
                page=payload['page'];return json.dumps({'total':3 if page==1 else 2,'lineups':[{'lineupKey':'A' if page==1 else 'C','heroes':[{'id':'1','name':'甲'}],'count':1000,'appearanceRate':.5}]})
            return json.dumps({'count':1000,'commanders':[]})
        with self.assertRaisesRegex(ValueError,'总数变化'):website.fetch_usage(ROOT,read=read,pause=lambda:None)

    def test_parent_usage_upper_bound_safely_avoids_irrelevant_low_sample_details(self):
        detailed=[]
        def read(url,payload=None):
            if payload is None:
                if url.endswith('/lineups'):return '<script src="/assets/index-test.js"></script>'
                if 'index-test' in url:return 'assets/desktop-main-test.js'
                return '[{value:"v1",label:"v1"}]'
            if url.endswith('/search'):
                return json.dumps({'total':2,'lineups':[{'lineupKey':key,'heroes':[{'id':'1','name':'英雄甲'}],'count':1000,'appearanceRate':rate} for key,rate in [('large',.5),('tiny',.001)]]})
            detailed.append(payload['lineupKey'])
            if payload['lineupKey']=='tiny':raise ValueError('该阵容的数据样本过少')
            return json.dumps({'count':1000,'appearanceRate':.5,'commanders':[{'id':str(i),'count':50,'name':str(i)} for i in range(10)]})
        result=website.fetch_usage(ROOT,read=read,pause=lambda:None)
        self.assertEqual(detailed,['large']);self.assertEqual(len(usage.rank_pairs(result['groups'])),10)

    def test_equal_upper_bound_is_not_pruned_and_can_win_a_tie(self):
        detailed=[]
        def read(url,payload=None):
            if payload is None:
                if url.endswith('/lineups'):return '<script src="/assets/index-test.js"></script>'
                if 'index-test' in url:return 'assets/desktop-main-test.js'
                return '[{value:"v1",label:"v1"}]'
            if url.endswith('/search'):
                return json.dumps({'total':2,'lineups':[{'lineupKey':key,'heroes':[{'id':'1','name':'英雄甲'}],'count':1000,'appearanceRate':rate} for key,rate in [('large',.5),('tie',.025)]]})
            detailed.append(payload['lineupKey'])
            people=[{'id':str(i),'count':50,'name':str(i)} for i in range(10)] if payload['lineupKey']=='large' else [{'id':'winner','count':1000,'name':'全场棋手'}]
            return json.dumps({'count':1000,'commanders':people})
        pairs=usage.rank_pairs(website.fetch_usage(ROOT,read=read,pause=lambda:None)['groups'])
        self.assertEqual(detailed,['large','tie']);self.assertEqual(pairs[0]['source_id'],'tie')

    def test_all_pages_and_full_dimensions_are_used(self):
        calls=[]
        def read(url,payload=None):
            calls.append((url,payload))
            if payload is None:
                if url.endswith('/lineups'):return '<script src="/assets/index-test.js"></script>'
                if 'index-test' in url:return 'assets/desktop-main-test.js'
                return '[{value:"v261022",label:"v261022"},{value:"v261029",label:"v261029"}]'
            if url.endswith('/search'):
                n=payload['page']
                return json.dumps({'data':{'total':2,'lineups':[{'lineupKey':str(n),'heroes':[{'id':'1','name':'英雄甲'}], 'count':100,'appearanceRate':.2,'commanders':[]} ]}})
            self.assertIn('dimensions',payload['detailSections'])
            return json.dumps({'data':{'count':100,'appearanceRate':.2,'commanders':[{'id':str(i),'name':str(i),'count':25} for i in range(4)]}})
        result=website.fetch_usage(ROOT,read=read,pause=lambda:None)
        self.assertEqual(len(result['groups']),2);self.assertEqual(len(result['groups'][0]['commanders']),4)
        self.assertEqual(result['scope']['version'],'v261022')
        self.assertEqual(len([x for x,p in calls if x.endswith('/search')]),2)

    def test_incomplete_pagination_or_missing_commanders_fails(self):
        def read(url,payload=None):
            if payload is None:
                if url.endswith('/lineups'):return '<script src="/assets/index-test.js"></script>'
                if 'index-test' in url:return 'assets/desktop-main-test.js'
                return '[{value:"v1",label:"v1"}]'
            if url.endswith('/search'):return json.dumps({'data':{'total':2,'lineups':[]}})
        with self.assertRaises(ValueError):website.fetch_usage(ROOT,read=read,pause=lambda:None)

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'temp/usage-tests';folder.mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir=folder);self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        (self.root/'knowledge/lineups').mkdir(parents=True);(self.root/'raw/crawler').mkdir(parents=True)
        self.rows=[]
        self.db=sqlite3.connect(self.root/'raw/crawler/topics.sqlite3')
        self.addCleanup(self.db.close)
        self.db.executescript('''CREATE TABLE topic_lineups(id TEXT,name TEXT,common_name TEXT,heroes TEXT,sources TEXT,enabled INTEGER,merged_into TEXT,deleted_at TEXT);
        CREATE TABLE lineup_variants(id TEXT,heroes TEXT);CREATE TABLE lineup_variant_links(lineup TEXT,variant TEXT,sources TEXT,manual INTEGER);
        CREATE TABLE lineup_notes(lineup TEXT,note TEXT);CREATE TABLE lineup_note_roles(lineup TEXT,note TEXT,role TEXT);''')
        self.now=datetime(2026,10,29,9,5,tzinfo=timezone(timedelta(hours=8)))
        self.index()

    def index(self):
        # Real sync now saves canonical aliases; keep simulated edits coherent.
        for row in self.rows:
            path=self.root/row['path']
            if not path.exists():continue
            body=json.loads(path.read_text('utf-8'));body.setdefault('schema_version',6)
            headings=[n for n in body['nodes'] if n['type']=='heading' and n['level']==1]
            if headings:headings[0]['title']=row['title']
            else:body['nodes'].insert(0,{'id':'title','type':'heading','level':1,'title':row['title']})
            body.setdefault('semantics',{})['players']=[row['player_id']]
            for node in body['nodes']:
                if node['type']=='entry':node.setdefault('show_key',node['key']!='正文')
            meta=usage.store.read(path.with_suffix('.meta.json'),{})
            meta.update({k:row[k] for k in ('id','type','title','player_id','path')})
            meta.setdefault('aliases',[]);meta['body_sha256']=usage.store.digest(body)
            meta['revision']=usage.store.digest({'body':body,'metadata':{k:v for k,v in meta.items() if k!='revision'}})[:20]
            row['revision']=meta['revision']
            usage.store.write_file(path,body);usage.store.write_file(path.with_suffix('.meta.json'),meta)
        (self.root/'knowledge/index.meta.json').write_text(json.dumps({'notes':self.rows}),encoding='utf-8')

    def note(self,nid='note1',player='player:1'):
        self.rows.append({'id':nid,'title':'本地阵容-'+player,'type':'lineup','player_id':player,'revision':nid,'path':f'knowledge/lineups/{nid}.json'})
        body={'nodes':[{'id':'h','type':'heading','level':2,'title':'英雄'},{'id':'e','type':'entry','key':'正文','value':'英雄甲承担前排。'}]}
        (self.root/self.rows[-1]['path']).write_text(json.dumps(body),encoding='utf-8');self.index()

    def lineup(self,uid='local',heroes=None,sources=None):
        self.db.execute('INSERT INTO topic_lineups VALUES(?,?,?,?,?,1,"","")',(uid,'外站旧名','本地常用名',json.dumps(heroes or ['card:1','card:2']),json.dumps(sources or [])));self.db.commit()

    def link(self,nid='note1',uid='local',role='primary'):
        self.db.execute('INSERT INTO lineup_notes VALUES(?,?)',(uid,nid));self.db.execute('INSERT INTO lineup_note_roles VALUES(?,?,?)',(uid,nid,role));self.db.commit()

    def publish(self,groups=None):
        self.index()
        return usage.run(self.root,fetcher=lambda root:{'groups':groups or [group()], 'scope':{'version':'vtest','gameType':'2','time':7,'minimumCount':50},'raw':{}},current=self.now)

    def test_scopes_slice_same_snapshot_and_recompute_denominator(self):
        self.note();self.lineup();self.link()
        self.publish([group(str(i),rate=.9-i*.01) for i in range(30)])
        for limit in (10,20,50):
            result=dashboard.snapshot(self.root,scope=f'usage_top{limit}')
            self.assertEqual(len(result['notes']),limit)
            self.assertEqual(result['summary']['total'],limit*7)
            self.assertEqual(result['summary']['covered'],sum(p['player_id']=='player:1' for p in result['notes']))
            self.assertEqual(result['usage']['selected_count'],limit)

    def test_legacy_ten_cache_triggers_refresh_without_fake_larger_rankings(self):
        self.publish()
        path=self.root/usage.SNAPSHOT
        value=json.loads(path.read_text(encoding='utf-8'));value.pop('capacity')
        path.write_text(json.dumps(value),encoding='utf-8')
        self.assertTrue(usage.due(self.root,self.now))
        self.assertTrue(dashboard.snapshot(self.root,scope='usage_top10')['usage']['ready'])
        for scope in ('usage_top20','usage_top50'):
            result=dashboard.snapshot(self.root,scope=scope)
            self.assertFalse(result['usage']['ready']);self.assertIsNone(result['summary']['rate'])
            self.assertEqual(result['notes'],[])

    def test_no_snapshot_is_not_a_zero_percent_ranking(self):
        result=dashboard.snapshot(self.root,scope='usage_top10')
        self.assertFalse(result['usage']['ready']);self.assertIsNone(result['summary']['rate']);self.assertEqual(result['notes'],[])

    def test_exact_composition_and_player_match_without_renaming_any_data(self):
        self.note();self.note('note2','player:2');self.lineup();self.link();self.link('note2')
        before=list(self.db.execute('SELECT * FROM topic_lineups'))
        self.publish();result=dashboard.snapshot(self.root,scope='usage_top10')
        self.assertEqual(result['counts']['lineup'],2);self.assertEqual(len(result['notes']),2)
        self.assertEqual([x['note_id'] for x in result['notes']],['note1','note2'])
        self.assertEqual(result['notes'][0]['local_name'],'本地常用名');self.assertEqual(result['summary']['total'],14)
        self.assertEqual(result['summary']['covered'],2)
        self.assertEqual(before,list(self.db.execute('SELECT * FROM topic_lineups')))

    def test_missing_notes_and_ambiguous_compositions_stay_in_ranking(self):
        self.lineup();self.lineup('another');self.publish()
        result=dashboard.snapshot(self.root,scope='usage_top10')
        self.assertEqual(result['usage']['ambiguous'],2);self.assertEqual(result['notes'][0]['match_status'],'ambiguous');self.assertIsNone(result['notes'][0]['rate'])
        self.assertEqual(result['summary']['total'],14);self.assertEqual(result['summary']['covered'],0)
        self.db.execute('DELETE FROM topic_lineups WHERE id="another"');self.db.commit()
        result=dashboard.snapshot(self.root,scope='usage_top10')
        self.assertEqual(result['notes'][0]['match_status'],'missing_note');self.assertEqual(result['notes'][0]['rate'],0)

    def test_known_variant_can_match_and_primary_is_preferred_within_same_player(self):
        self.note();self.note('variant-note');self.lineup(heroes=['card:7'])
        self.db.execute('INSERT INTO lineup_variants VALUES(?,?)',('v',json.dumps(['card:1','card:2'])))
        self.db.execute('INSERT INTO lineup_variant_links VALUES("local","v","[]",1)');self.db.commit()
        self.link();self.link('variant-note',role='variant');self.publish()
        result=dashboard.snapshot(self.root,scope='usage_top10');self.assertEqual(result['notes'][0]['note_id'],'note1')

    def test_changed_composition_for_old_source_id_requires_confirmation(self):
        self.note();self.lineup(sources=[{'heroes':['card:9'],'raw':{'lineupKey':'g'}}]);self.link();self.publish()
        result=dashboard.snapshot(self.root,scope='usage_top10');self.assertEqual(result['notes'][0]['match_status'],'ambiguous')

    def test_two_primary_notes_for_same_player_are_ambiguous(self):
        self.note();self.note('second');self.lineup();self.link();self.link('second');self.publish()
        result=dashboard.snapshot(self.root,scope='usage_top10');self.assertEqual(result['notes'][0]['match_status'],'ambiguous')

    def test_daily_window_catchup_failure_retains_good_snapshot_and_retries(self):
        self.assertTrue(usage.due(self.root,self.now));self.publish();self.assertFalse(usage.due(self.root,self.now))
        tomorrow=self.now+timedelta(days=1);self.assertTrue(usage.due(self.root,tomorrow))
        good=(self.root/usage.SNAPSHOT).read_bytes()
        def fail(root):raise ValueError('远端响应不完整')
        usage.run(self.root,fetcher=fail,current=tomorrow)
        self.assertEqual((self.root/usage.SNAPSHOT).read_bytes(),good)
        state=usage.status(self.root,tomorrow);self.assertEqual(state['state'],'failed');self.assertTrue(state['stale'])
        self.assertFalse(usage.due(self.root,tomorrow+timedelta(minutes=29)))
        self.assertTrue(usage.due(self.root,tomorrow+timedelta(minutes=31)))
        self.assertEqual(usage.window(datetime(2026,10,29,0,59,tzinfo=timezone.utc)), '2026-10-28T09:00:00+08:00')

    def test_cross_process_lock_prevents_second_fetch(self):
        from processing_lock import file_lock
        with file_lock(self.root/usage.LOCK):
            with patch.object(website,'fetch_usage',side_effect=AssertionError('must not fetch')):
                usage.run(self.root,current=self.now)

    def test_worker_coalesces_tick_and_manual_requests_without_blocking_caller(self):
        import threading
        entered=threading.Event();release=threading.Event()
        def slow(root):entered.set();release.wait(3)
        worker=usage.UsageWorker(self.root)
        try:
            with patch.object(usage,'run',side_effect=slow) as run:
                worker.tick();self.assertTrue(entered.wait(1));worker.request();worker.next_poll=0;worker.tick()
                self.assertEqual(run.call_count,1)
        finally:release.set();worker.close()

    def test_retry_delay_is_measured_from_failure_not_start_of_slow_fetch(self):
        finished=self.now+timedelta(minutes=8)
        def fail(root):raise ValueError('慢请求失败')
        with patch.object(usage,'now',side_effect=[self.now,finished,finished]):
            usage.run(self.root,fetcher=fail)
        state=usage.status(self.root,finished)
        self.assertEqual(state['retry_at'],(finished+timedelta(minutes=30)).isoformat())

    def test_completed_worker_is_not_misreported_interrupted_during_lock_probe(self):
        self.publish()
        (self.root/usage.STATE).write_text(json.dumps({'state':'running'}),encoding='utf-8')
        original=usage.cached_snapshot
        def finishing(root):
            (self.root/usage.STATE).write_text(json.dumps({'state':'idle','error':''}),encoding='utf-8')
            return original(root)
        with patch.object(usage,'cached_snapshot',side_effect=finishing):
            state=usage.status(self.root,self.now)
        self.assertEqual(state['state'],'idle');self.assertFalse(state.get('interrupted',False))

    def test_manually_merged_source_redirects_to_active_target_without_losing_composition(self):
        self.note();self.lineup('source',sources=[{'heroes':['card:1','card:2'],'raw':{'lineupKey':'g'}}])
        self.lineup('target',heroes=['card:9']);self.link(uid='target')
        self.db.execute('UPDATE topic_lineups SET enabled=0,merged_into="target" WHERE id="source"');self.db.commit()
        self.publish();r=dashboard.snapshot(self.root,scope='usage_top10')
        self.assertEqual(r['notes'][0]['note_id'],'note1');self.assertEqual(r['notes'][0]['lineup_id'],'target')

    def test_canonical_note_formation_matches_when_old_roster_has_no_links(self):
        self.note();path=self.root/self.rows[0]['path'];body=json.loads(path.read_text('utf-8'))
        body['semantics']={'compositions':{'middle':[{'hero':'card:1'},{'hero':'card:2'}]}}
        path.write_text(json.dumps(body),encoding='utf-8')
        path.with_suffix('.meta.json').write_text(json.dumps({'lineup_name':'现行阵容'}),encoding='utf-8')
        self.publish();r=dashboard.snapshot(self.root,scope='usage_top10')
        self.assertEqual(r['notes'][0]['note_id'],'note1');self.assertEqual(r['notes'][0]['local_name'],'现行阵容')

    def test_similar_canonical_formation_is_pending_not_falsely_missing_or_auto_matched(self):
        self.note();path=self.root/self.rows[0]['path'];body=json.loads(path.read_text('utf-8'))
        body['semantics']={'compositions':{'late':[{'hero':'card:'+str(i)} for i in [1,2,3,4]]}}
        path.write_text(json.dumps(body),encoding='utf-8')
        self.publish([group(heroes=['card:1','card:2','card:3','card:5'])]);r=dashboard.snapshot(self.root,scope='usage_top10')
        self.assertEqual(r['notes'][0]['match_status'],'ambiguous');self.assertIsNone(r['notes'][0]['rate'])

    def test_unchanged_note_formations_do_not_reparse_large_history_metadata_every_poll(self):
        self.note();path=self.root/self.rows[0]['path'];body=json.loads(path.read_text('utf-8'))
        body['semantics']={'compositions':{'middle':[{'hero':'card:1'},{'hero':'card:2'}]}}
        path.write_text(json.dumps(body),encoding='utf-8')
        first=usage.note_formations(self.root,self.rows)
        with patch.object(usage.store,'read',side_effect=AssertionError('reparsed unchanged notes')),patch.object(usage.store,'cached_read',side_effect=AssertionError('reloaded unchanged notes')):
            self.assertEqual(usage.note_formations(self.root,self.rows),first)
        body['semantics']['compositions']['middle'].append({'hero':'card:3'});path.write_text(json.dumps(body),encoding='utf-8')
        self.assertIn('card:3',usage.note_formations(self.root,self.rows)[0]['formations'][0])

if __name__=='__main__':unittest.main()
