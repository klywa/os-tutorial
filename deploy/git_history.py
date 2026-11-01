"""Inspect every outgoing commit, including deletions and each merge parent."""
def history_paths(git, base, target):
    paths=set()
    for row in git('rev-list','--parents',f'{base}..{target}').splitlines():
        commit,*parents=row.split()
        if not parents:
            output=git('diff-tree','--root','--no-commit-id','--name-only','--no-renames','-r','-z',commit)
            paths.update(path for path in output.split('\0') if path)
        for parent in parents:
            output=git('diff','--name-only','--no-renames','-z',parent,commit)
            paths.update(path for path in output.split('\0') if path)
    return paths
