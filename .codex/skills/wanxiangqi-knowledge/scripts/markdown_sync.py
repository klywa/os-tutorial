"""Reversible Markdown synchronization, sharing the knowledge save transaction."""
from copy import deepcopy
from difflib import SequenceMatcher
from pathlib import Path
import hashlib
import threading
import time
import wxq
import player_branches as branches


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def status(root):
    import json_store
    if json_store.enabled(root):
        return {'version': 6, 'files': {}, 'issues': [], 'message': '知识库已使用JSON，Markdown仅用于导出'}
    return wxq.read_json(Path(root)/'knowledge/markdown-sync.json', {'version':1,'files':{},'issues':[]})


def three_way(base, saved, external):
    if saved == external or external == base:return saved
    if saved == base:return external
    source = base.splitlines(keepends=True)
    def changes(value):
        dest=value.splitlines(keepends=True)
        return [(a0,a1,dest[b0:b1]) for op,a0,a1,b0,b1 in SequenceMatcher(None,source,dest,autojunk=False).get_opcodes() if op!='equal']
    accepted=changes(saved)
    for edit in changes(external):
        if edit in accepted:continue
        a,b,_=edit
        for x,y,_ in accepted:
            if max(a,x)<min(b,y) or (a==b and x<=a<=y) or (x==y and a<=x<=b):
                raise ValueError('同一段内容被不同方式修改')
        accepted.append(edit)
    for a,b,text in sorted(accepted,key=lambda x:(x[0],x[1]),reverse=True):source[a:b]=text
    return ''.join(source)


def outputs(root, items, ignore_issues=()):
    """Return every derived file and its baseline as one recoverable transaction."""
    import workspace
    prior=status(root);state={'version':1,'files':{},'issues':prior.get('issues',[])};files={}
    previous={n['id']:n for n in workspace.notes(root)}
    blocked={x['note'] for x in state['issues']} - set(ignore_issues)
    for note in items:
        if not branches.enabled(note):continue
        if note['id'] in blocked:
            if note != previous.get(note['id']):raise workspace.Conflict('请先处理该打法的Markdown同步问题')
            state['files'].update({p:v for p,v in prior['files'].items() if v['note']==note['id']});continue
        for path,text in branches.documents(note).items():
            b=next(b for b in note['meta']['player_branches'] if branches.document_path(note,b)==path)
            files[path]=text
            state['files'][path]={'note':note['id'],'branch':b['id'],'hash':digest(text),'document':text,'parsed':branches.parse_document(text,note,b['id']),'revision':note.get('revision','')}
    state['issues']=[i for i in state['issues'] if i['note'] not in ignore_issues]
    return files,state,blocked


def current_sections(note, bid):
    doc=branches.documents(note)[branches.document_path(note,branches.branch(note,bid))]
    return branches.parse_document(doc,note,bid)


def scan(root, _locked=False):
    import json_store
    if json_store.enabled(root):
        return status(root)
    import workspace
    if not _locked:
        with workspace.store_lock(root):
            workspace.recover(root)
            return scan(root,True)
    root=Path(root);state=status(root)
    if not state['files']:return state
    items=deepcopy(workspace.notes(root));notes={n['id']:n for n in items};proposals={};issues=[];inputs={};observed={}
    for path,base in state['files'].items():
        note=notes.get(base['note'])
        if not note or not branches.enabled(note):continue
        try:
            target=(root/path).resolve()
            if not target.is_relative_to((root/'knowledge').resolve()):raise ValueError('同步路径超出知识目录')
            text=target.read_text('utf-8-sig')
            observed[path]=digest(text)
            if digest(text)==base['hash']:continue
            inputs.setdefault(note['id'],{})[path]=text
            note['entity_names'].update({e['id']:e['name'] for e in wxq.entities(root)})
            parsed=branches.parse_document(text,note,base['branch'])
            saved=current_sections(note,base['branch'])
            for group in ('common','branch'):
                scope='common' if group=='common' else base['branch']
                old=base['parsed'][group];new=parsed[group];current=saved[group]
                for section in old.keys()|new.keys():
                    if new.get(section,'')==old.get(section,''):continue
                    key=(scope,section)
                    candidate=three_way(old.get(section,''),current.get(section,''),new.get(section,''))
                    changes=proposals.setdefault(note['id'],{})
                    if key in changes:
                        candidate=three_way(old.get(section,''),changes[key],candidate)
                    changes[key]=candidate
        except (OSError,UnicodeError,ValueError,KeyError) as exc:
            if not (root/path).exists():observed[path]=None
            issues.append({'note':note['id'],'path':path,'kind':'conflict' if isinstance(exc,ValueError) and '不同方式' in str(exc) else 'format','message':str(exc),'base':base['document'],'external':inputs.get(note['id'],{}).get(path),'saved':branches.documents(note).get(path)})
    blocked={i['note'] for i in issues};changed=False
    for nid,updates in proposals.items():
        if nid in blocked:continue
        before=deepcopy(notes[nid]);scopes={scope for scope,_ in updates}
        try:
            notes[nid]['entity_names'].update({e['id']:e['name'] for e in wxq.entities(root)})
            for scope in scopes:
                branches.apply_sections(notes[nid],scope,{s:t for (g,s),t in updates.items() if g==scope})
            branches.validate(notes[nid])
            workspace.validate_meta(root,notes[nid]['meta'])
        except (ValueError,KeyError,TypeError) as exc:
            notes[nid].clear();notes[nid].update(before)
            for path,text in inputs.get(nid,{}).items():
                issues.append({'note':nid,'path':path,'kind':'format','message':str(exc),'base':state['files'][path]['document'],'external':text,'saved':branches.documents(before).get(path)})
            continue
        notes[nid].setdefault('history',[]).append({'at':wxq.now(),'origin':'manual','reason':'Markdown直接编辑自动同步','previous':{'claims':before['claims'],'meta':before['meta']},'markdown_inputs':inputs.get(nid,{})})
        changed=True
    for issue in issues:
        issue['id']=digest(str({k:v for k,v in issue.items() if k!='id'}))[:20]
    state['issues']=issues
    state['observed']=observed
    wxq.atomic_json(root/'knowledge/markdown-sync.json',state)
    if changed:
        workspace.persist(root,items,_sync=False,_expected_markdown=observed)
        state=status(root)
    return state


def assert_clean(root):
    """Direct persist callers must not overwrite edits that have not been imported."""
    import workspace
    root=Path(root);state=status(root)
    blocked={x['note'] for x in state.get('issues',[])}
    for path,base in state['files'].items():
        if base['note'] in blocked:continue
        try:text=(root/path).read_text('utf-8-sig')
        except OSError:raise workspace.Conflict('Markdown文件缺失，请先检查同步状态')
        if digest(text)!=base['hash']:raise workspace.Conflict('Markdown有未同步修改，请先同步后重试')


def resolve(root,nid,payload):
    import workspace
    with workspace.store_lock(root):
        workspace.recover(root);scan(root,_locked=True);state=status(root);items=deepcopy(workspace.notes(root));note=next((n for n in items if n['id']==nid),None)
        if note is None:raise KeyError('笔记不存在')
        if note.get('revision')!=payload.get('revision'):raise workspace.Conflict('笔记已更新，请重新载入冲突')
        issues=[x for x in state['issues'] if x['note']==nid]
        if not issues:raise ValueError('没有待处理同步问题')
        if 'issue_ids' in payload and set(payload['issue_ids'])!={i['id'] for i in issues}:raise workspace.Conflict('外部文件再次变化，请重新载入同步问题')
        # Retain the current external bytes even when the human elects to restore.
        snapshots={p:(Path(root)/p).read_text('utf-8-sig') for p,b in state['files'].items() if b['note']==nid and (Path(root)/p).exists()}
        before=deepcopy(note)
        action=payload.get('action')
        if action=='apply':
            changes=payload.get('changes',[])
            if payload.get('document'):
                doc=payload['document'];base=state['files'].get(doc.get('path'))
                if not base or base['note']!=nid:raise ValueError('所选文件不属于当前打法')
                parsed=branches.parse_document(doc['text'],note,base['branch'])
                changes=[{'scope':'common','sections':parsed['common']},{'scope':base['branch'],'sections':parsed['branch']}]
            if not changes:raise ValueError('请提供要合并的章节或文件内容')
            for change in changes:
                branches.apply_sections(note,change['scope'],change['sections'])
            branches.validate(note)
            workspace.validate_meta(root,note['meta'])
        elif action!='use_saved':raise ValueError('无效同步处理方式')
        note.setdefault('history',[]).append({'at':wxq.now(),'origin':'manual','reason':'处理Markdown同步冲突','previous':{'claims':before['claims'],'meta':before['meta']},'markdown_inputs':snapshots,'sync_issues':issues})
        workspace.persist(root,items,_sync=False,_ignore_issues={nid},_expected_markdown=state.get('observed',{}))
        return status(root)


class Watcher:
    def __init__(self,root):
        self.root=Path(root);self.stop_event=threading.Event();self.thread=None;self.last_error=None
    def start(self):
        # startup reconciliation also works after the service was stopped during edits
        try:scan(self.root)
        except Exception as exc:self.last_error=str(exc)
        self.thread=threading.Thread(target=self.run,name='knowledge-markdown-sync',daemon=True);self.thread.start()
    def run(self):
        previous=None;processed=None
        while not self.stop_event.wait(1):
            try:
                fingerprint=self.fingerprint()
                if fingerprint==previous and fingerprint!=processed:
                    scan(self.root)
                    processed=fingerprint
                previous=fingerprint;self.last_error=None
            except Exception as exc:self.last_error=str(exc)
    def fingerprint(self):
        state=status(self.root)
        paths=[*state['files'],'knowledge/index.json',
               'knowledge/pending-save.json','knowledge/pending-cards.json',
               'knowledge/pending-note-link.json','raw/transcript-edit-pending.json']
        def stamp(path):
            try:
                stat=(self.root/path).stat()
                return path,stat.st_mtime_ns,stat.st_size
            except FileNotFoundError:return path,None
        # Compare baseline identity, not its mtime: scan itself rewrites that
        # manifest. A document changed during scan must still be seen next poll.
        baseline=tuple((p,b['hash'],b.get('revision')) for p,b in state['files'].items())
        return baseline,tuple(stamp(p) for p in paths)
    def close(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=3)
