"""Commit an exact allowlisted selection without operating-system argv limits."""
from pathlib import Path
import tempfile

def commit_selected(root,paths,message,run):
    parent=Path(root)/'raw/git-pathspec';parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=parent) as temporary:
        path=Path(temporary)/'paths'
        path.write_bytes(('\0'.join(paths)+'\0').encode('utf-8'))
        options=['--pathspec-from-file='+str(path),'--pathspec-file-nul']
        run('--literal-pathspecs','add','--all',*options)
        run('--literal-pathspecs','commit','--only','-m',message,*options)
