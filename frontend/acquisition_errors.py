"""Stable diagnostics across worker/HTTP process boundaries."""
import re

def describe_error(error,phase=None,log=None):
 text=str(error);code=getattr(error,'code',None)
 cause=error
 for _ in range(6):
  if cause is None:break
  code=code or getattr(cause,'status',None)
  cause=getattr(cause,'cause',None) or getattr(cause,'__cause__',None)
 if not isinstance(code,int):
  match=re.search(r'(?:HTTP(?: Error)?[ :]+|B站请求失败[（(])(-?\d+)',text,re.I)
  code=int(match[1]) if match else (412 if re.search(r'\b412\b',text) else None)
 category=getattr(error,'category',None)
 if not category:
  if code in [-352,-401,403,412,429] or re.search(r'-352|-401|风控',text):category='risk'
  elif code in [-101,-111] or re.search(r'login|sign in|登录',text,re.I):category='login'
  elif code in [-404,404,410] or re.search(r'video.*(?:removed|deleted)|视频.*(?:删除|不存在)',text,re.I):category='unavailable'
  elif re.search(r'No video formats|requested format.*not available',text,re.I):category='formats'
  elif re.search(r'WinError (?:5|32|33)|PermissionError|拒绝访问',text):category='storage'
  elif re.search(r'HTTP|connection|timed? ?out|网络|Downloaded.*bytes.*expected|ConnectionReset|RemoteDisconnected|WinError (?:10053|10054|10060)\b|TransportError|远程主机.*关闭',text,re.I):category='network'
  else:category='processing'
 return {'category':category,'code':code,'phase':getattr(error,'phase',None) or phase or 'unknown','reason':text,'recoverable':category not in ['login','unavailable'],'log':log,'hint':'更新登录信息后重试' if category=='login' else '保留材料，可恢复处理'}

class AcquisitionFailure(RuntimeError):
 def __init__(self,rows):
  detail=rows[0].get('error_info') or {}
  self.category=detail.get('category');self.code=detail.get('code');self.phase=detail.get('phase')
  self.parts=[{'id':r['id'],'error_info':r.get('error_info')} for r in rows]
  super().__init__('; '.join(r.get('error','') for r in rows))
