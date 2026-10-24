"""Content-addressed local DOCX evidence; never pretend document paragraphs are ASR."""
from pathlib import Path
import hashlib,re,zipfile,xml.etree.ElementTree as ET
import wxq
from functools import lru_cache

REGISTRY='knowledge/document-sources.json'


@lru_cache(maxsize=32)
def _verified_snapshot(artifact, artifact_hash, artifact_stamp, paragraphs, paragraph_hash, paragraph_stamp):
    # The stat stamps form part of the cache key: changed files must be hashed
    # again. Never cache a validation failure or a paragraph-range decision.
    for filename,digest in [(artifact,artifact_hash),(paragraphs,paragraph_hash)]:
        if hashlib.sha256(Path(filename).read_bytes()).hexdigest()!=digest:
            raise ValueError('Document snapshot changed')
    return wxq.read_json(Path(paragraphs))

def paragraphs(path):
    with zipfile.ZipFile(path) as archive:
        node=ET.fromstring(archive.read('word/document.xml'))
    ns={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    return [{'id':i+1,'text':''.join(t.text or '' for t in p.findall('.//w:t',ns))}
            for i,p in enumerate(node.findall('.//w:p',ns))]

def register(root,path):
    from workspace import store_lock
    root=Path(root);path=Path(path)
    if path.name.startswith('~$'):raise ValueError('Word临时锁文件不是知识来源')
    content=path.read_bytes();digest=hashlib.sha256(content).hexdigest();sid='doc-'+digest
    rows=paragraphs(path)
    if not any(p['text'].strip() for p in rows):raise ValueError('文档没有可读正文')
    with store_lock(root,wait=True):
        registry=wxq.read_json(root/REGISTRY,{'documents':[]})
        old=next((r for r in registry['documents'] if r['id']==sid),None)
        if old:return old
        folder=root/'raw/documents'/sid;folder.mkdir(parents=True,exist_ok=True)
        artifact=folder/'original.docx';artifact.write_bytes(content)
        wxq.atomic_json(folder/'paragraphs.json',rows)
        row={'id':sid,'type':'document','title':path.stem,'sha256':digest,
             'original_path':str(path),'artifact':artifact.relative_to(root).as_posix(),
             'paragraphs':(folder/'paragraphs.json').relative_to(root).as_posix(),
             'paragraph_sha256':hashlib.sha256((folder/'paragraphs.json').read_bytes()).hexdigest(),
             'imported_at':wxq.now(),'version':None}
        registry['documents'].append(row);wxq.atomic_json(root/REGISTRY,registry)
        return row

def validate_evidence(root,evidence):
    root=Path(root);sid=evidence.get('source','')
    if not re.fullmatch(r'doc-[a-f0-9]{64}',sid):raise ValueError('Invalid document source')
    row=next((r for r in wxq.read_json(root/REGISTRY,{'documents':[]})['documents'] if r['id']==sid),None)
    if not row:raise ValueError('Unknown document source: '+sid)
    paths={}
    for key in ('artifact','paragraphs'):
        path=(root/row[key]).resolve()
        if not path.is_relative_to((root/'raw/documents'/sid).resolve()) or not path.is_file():raise ValueError('Missing document artifact: '+sid)
        stat=path.stat();paths[key]=(str(path),(stat.st_mtime_ns,stat.st_ctime_ns,stat.st_size))
    rows=_verified_snapshot(paths['artifact'][0],row['sha256'],paths['artifact'][1],paths['paragraphs'][0],row['paragraph_sha256'],paths['paragraphs'][1])
    start=evidence.get('paragraph_start');end=evidence.get('paragraph_end')
    if type(start) is not int or type(end) is not int or not 1<=start<=end<=len(rows):raise ValueError('Invalid document paragraph range')
    if not any(p['text'].strip() for p in rows[start-1:end]):raise ValueError('Empty document evidence')
    if any(k in evidence for k in ('start','end','frame')):raise ValueError('Document evidence cannot use video timestamps or frames')
