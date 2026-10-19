"""Validate resume objects before yt-dlp appends bytes; preserve rejected fragments."""
import json,re,uuid
from pathlib import Path
import wxq

class ObjectChanged(ConnectionError):
    pass

class ResumeGuard:
    def __init__(self,options):
        template=options.get('outtmpl')
        if isinstance(template,dict):template=template.get('default')
        self.folder=Path(template).parent if isinstance(template,str) else None
        self.path=self.folder/'download-object.json' if self.folder else None
        self.identity=wxq.read_json(self.path,{}) if self.path else {}
    def quarantine(self,reason):
        if not self.folder:return
        files=list(self.folder.glob('*.part'))+list(self.folder.glob('*.ytdl'))
        if not files:return
        target=self.folder/'failed-downloads'/uuid.uuid4().hex;target.mkdir(parents=True)
        for file in files:file.replace(target/file.name)
        wxq.atomic_json(target/'reason.json',{'reason':reason,'at':wxq.now()})
    def begin(self,info):
        identity={'id':info.get('id'),'format_id':info.get('format_id')}
        if not self.identity:self.quarantine('旧分片缺少可核验的下载身份')
        if self.identity and any(self.identity.get(k)!=v for k,v in identity.items()):
            self.quarantine('下载对象或格式发生变化');self.identity={}
        self.identity={**self.identity,**identity};self.save()
    def save(self):
        if self.path:wxq.atomic_json(self.path,self.identity)
    def response(self,headers,resuming):
        content_range=headers.get('Content-Range')
        match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',content_range or '')
        total=int(match[3]) if match else int(headers.get('Content-Length') or 0)
        validator=headers.get('ETag') or headers.get('Last-Modified')
        if resuming and validator and self.identity.get('validator') not in [None,validator]:
            self.quarantine('远端对象标识发生变化');self.identity={};self.save()
            raise ObjectChanged('网络下载对象标识变化，旧分片已隔离，重新下载')
        if validator:self.identity['validator']=validator
        offset=re.match(r'bytes=(\d+)-',resuming) if isinstance(resuming,str) else None
        if match and offset and int(match[1])!=int(offset[1]):
            self.quarantine('服务端续传起点与请求不符')
            raise ObjectChanged('网络续传起点变化，旧分片已隔离，重新下载')
        if resuming and not match:
            self.quarantine('服务端不接受续传或Content-Range无效')
            if content_range:raise ObjectChanged('网络续传响应损坏，重新下载完整文件')
        elif resuming and total and self.identity.get('total') not in [None,total]:
            self.quarantine('远端对象长度发生变化');self.identity.pop('total',None);self.save()
            raise ObjectChanged('网络下载对象长度变化，旧分片已隔离，重新获取完整文件')
        if total:self.identity['total']=total;self.save()

def guarded_downloader(base,guard):
    class Downloader(base):
        def process_info(self,info):
            guard.begin(info)
            return super().process_info(info)
        def urlopen(self,request):
            response=super().urlopen(request)
            headers=getattr(request,'headers',{})
            # API metadata and signing requests are not media objects.
            ranged=headers.get('Range') or headers.get('range')
            url=getattr(response,'url','')
            if ranged or re.search(r'\.(?:m4s|mp4|m4a|flv)(?:[?]|$)',url):
                try:guard.response(response.headers,ranged)
                except Exception:response.close();raise
            return response
    return Downloader
