"""Durable global reply mode. Invalid configuration fails closed to manual."""
import json,os,uuid,tempfile
from pathlib import Path
PATH=Path(os.getenv('DOUYIN_REPLY_MODE_FILE','/home/ubuntu/douyin-weixin-validation/reply-mode.json'))
def read_mode(path=None):
 p=Path(path or PATH)
 try:
  x=json.loads(p.read_text())
  if x.get('mode') in ('ai','manual') and isinstance(x.get('revision'),str):return x
 except (OSError,ValueError):pass
 return {'mode':'manual','revision':'invalid'}
def set_mode(mode,path=None):
 if mode not in ('ai','manual'):raise ValueError('Unsupported mode')
 p=Path(path or PATH);p.parent.mkdir(exist_ok=True,parents=True,mode=0o700)
 x={'mode':mode,'revision':uuid.uuid4().hex};fd,tmp=tempfile.mkstemp(dir=p.parent,prefix='.mode-')
 try:
  with os.fdopen(fd,'w') as f:json.dump(x,f);f.flush();os.fsync(f.fileno())
  os.replace(tmp,p)
 finally:
  if os.path.exists(tmp):os.unlink(tmp)
 return x

def allows_send(snapshot,path=None):
 current=read_mode(path)
 return snapshot['mode']=='ai' and current==snapshot
