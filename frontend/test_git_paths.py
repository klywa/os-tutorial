from pathlib import Path
import tempfile,subprocess,unittest,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from git_paths import commit_selected

class SelectedPathsTests(unittest.TestCase):
 def test_large_selection_is_literal_and_keeps_unrelated_staged_content(self):
  folder=Path(__file__).resolve().parents[1]/'raw/reports/knowledge-sync-20261103/test-temp';folder.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=folder) as temporary:
   root=Path(temporary)
   def git(*args):
    result=subprocess.run(['git','-C',str(root),*args],capture_output=True,text=True,encoding='utf-8')
    if result.returncode:raise RuntimeError(result.stderr)
    return result.stdout.strip()
   git('init','-b','master');git('config','user.name','Test');git('config','user.email','test@example.invalid')
   (root/'.gitignore').write_text('raw/\n');(root/'private.txt').write_text('before')
   git('add','.');git('commit','-m','initial')
   (root/'private.txt').write_text('unrelated staged change');git('add','private.txt')
   paths=['history/'+str(i)+'[中文]'+('x'*70)+'.json' for i in range(600)]
   (root/'history').mkdir()
   for path in paths:(root/path).write_text('{}')
   commit_selected(root,paths,'selected only',git)
   self.assertEqual(git('show','HEAD:private.txt'),'before')
   self.assertEqual(git('diff','--cached','--name-only'),'private.txt')
   self.assertEqual(len(git('ls-tree','-r','--name-only','HEAD','history').splitlines()),600)
