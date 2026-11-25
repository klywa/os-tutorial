from pathlib import Path
from subprocess import CompletedProcess, TimeoutExpired
import sys
import tempfile
import unittest
from unittest.mock import patch
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.codex/skills/wanxiangqi-knowledge/scripts'))
from gemini_generate import generate


def reply(value):
    return CompletedProcess([], 0, json.dumps({'status':'completed','steps':[
        {'type':'thought','content':[{'type':'text','text':'ignored'}]},
        {'type':'model_output','content':[{'type':'text','text':json.dumps(value, ensure_ascii=False)}]},
    ]}).encode('utf-8'), b'')


class GeminiGenerateTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(dir=ROOT/'temp')
        self.addCleanup(directory.cleanup)
        self.state = Path(directory.name)/'generation.json'
        self.request = {'context':{'task':'根据已核实证据写笔记'},'fields':{'paragraph':'text'}}
        found = patch('gemini_generate.shutil.which', return_value='gemini-api.exe')
        self.which = found.start()
        self.addCleanup(found.stop)

    @patch('gemini_generate.subprocess.run')
    def test_success_uses_utf8_and_saved_draft(self, run):
        run.return_value = reply({'paragraph':'实战正文'})
        result = generate(self.request,self.state)
        self.assertEqual(result,{'status':'ok','failures':0,'content':{'paragraph':'实战正文'}})
        self.assertEqual(generate(self.request,self.state),result)
        command = run.call_args.args[0]
        request = json.loads(run.call_args.kwargs['input'].decode('utf-8'))
        self.assertIn('--stream=false',command)
        self.assertIn('根据已核实证据写笔记',request['input'])
        self.assertFalse(request['store'])
        self.assertEqual(run.call_count,1)

    @patch('gemini_generate.subprocess.run')
    def test_timeout_bad_schema_and_review_use_same_failure_budget(self, run):
        run.side_effect = [TimeoutExpired([],1),reply({'paragraph':[]}),reply({'paragraph':'改稿'})]
        result = generate(self.request,self.state)
        self.assertEqual(result['failures'],2)
        result = generate(self.request,self.state,feedback='依据不足')
        self.assertEqual((result['status'],result['failures']),('fallback',3))
        self.assertEqual(run.call_count,3)
        self.assertEqual(generate(self.request,self.state)['status'],'fallback')

    @patch('gemini_generate.subprocess.run')
    def test_missing_cli_and_three_process_failures(self, run):
        self.which.return_value = None
        self.assertEqual(generate(self.request,self.state)['reason'],'missing_cli')
        run.assert_not_called()
        self.which.return_value = 'gemini-api.exe'
        run.return_value = CompletedProcess([], 1, b'', b'private value')
        self.assertEqual(generate(self.request,self.state),{'status':'fallback','reason':'attempts_exhausted','failures':3})
        self.assertEqual(run.call_count,3)

    @patch('gemini_generate.subprocess.run')
    def test_feedback_and_verified_post_review_stage(self, run):
        run.side_effect = [reply({'utterances':['初稿']}),reply({'utterances':['核实后话术']}),reply({'explanation_after':'实际检查通过'})]
        draft = {'context':{},'fields':{'utterances':'lines'}}
        generate(draft,self.state)
        revised = generate(draft,self.state,feedback='确认实际触发条件')
        self.assertIn('确认实际触发条件',json.loads(run.call_args.kwargs['input'])['input'])
        self.assertEqual(revised['failures'],1)
        final = generate({'context':{'review':'实际检查通过'},'fields':{'explanation_after':'text'}},
                         self.state,phase='post-review')
        self.assertEqual(final['failures'],1)
