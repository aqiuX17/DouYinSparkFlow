"""Bound-owner commands, direct text sends and 60-second latest-notification routing."""
import json,os,sqlite3,time,secrets
from pathlib import Path
from core.ai.weixin_forward import ClosingConnection
try:
 from .reply_mode import read_mode, set_mode, mode_command, describe_mode
except ImportError:
 from reply_mode import read_mode, set_mode, mode_command, describe_mode
DB=Path(os.getenv('DOUYIN_WEIXIN_DB','/home/ubuntu/douyin-weixin-validation/forward.sqlite3'))
RESERVED={'切换人工','人工模式','切换AI','切换ai','AI模式','查看模式'}
def connect():
 DB.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
 c=sqlite3.connect(str(DB),timeout=5,factory=ClosingConnection);c.execute('PRAGMA busy_timeout=5000')
 c.executescript('''CREATE TABLE IF NOT EXISTS catalog(n INTEGER PRIMARY KEY AUTOINCREMENT,account TEXT,conv TEXT,hit TEXT,active INTEGER,updated REAL,UNIQUE(account,conv));
 CREATE TABLE IF NOT EXISTS inbound_commands(id TEXT PRIMARY KEY);
 CREATE TABLE IF NOT EXISTS send_commands(code TEXT PRIMARY KEY,account TEXT,conv TEXT,text TEXT,state TEXT,expires REAL,revision TEXT,updated REAL);
 CREATE TABLE IF NOT EXISTS latest_reply_route(singleton INTEGER PRIMARY KEY CHECK(singleton=1),account TEXT,conv TEXT,mid TEXT,expires REAL,revision TEXT);
 CREATE TABLE IF NOT EXISTS messages(account TEXT,conv TEXT,mid TEXT,payload TEXT,state TEXT,attempts INTEGER DEFAULT 0,created REAL,updated REAL,error TEXT,PRIMARY KEY(account,conv,mid));''')
 os.chmod(DB,0o600);return c

def publish(account,hits):
 with connect() as c:
  c.execute('UPDATE catalog SET active=0 WHERE account=?',(str(account),))
  for h in hits:
   if h.get('conv_id'):
    c.execute('INSERT INTO catalog(account,conv,hit,active,updated) VALUES(?,?,?,?,?) ON CONFLICT(account,conv) DO UPDATE SET hit=excluded.hit,active=1,updated=excluded.updated',(str(account),str(h['conv_id']),json.dumps(h,ensure_ascii=False),1,time.time()))

def notify(c,key,text):
 c.execute('INSERT OR IGNORE INTO messages(account,conv,mid,payload,state,created,updated) VALUES(?,?,?,?,?,?,?)',('__control__','__control__',key,json.dumps({'text':text},ensure_ascii=False),'pending',time.time(),time.time()))

def mark_forwarded(account,conv,mid,now=None):
 if str(account)=='__control__':return
 now=time.time() if now is None else now
 mode=read_mode()
 with connect() as c:
  if c.execute('SELECT 1 FROM catalog WHERE account=? AND conv=? AND active=1',(str(account),str(conv))).fetchone():
   c.execute('INSERT OR REPLACE INTO latest_reply_route VALUES(1,?,?,?,?,?)',(str(account),str(conv),str(mid),now+60,mode['revision']))

def enqueue(c,row,text,key,mode):
 code=secrets.token_hex(8);h=json.loads(row[2])
 c.execute('INSERT INTO send_commands VALUES(?,?,?,?,?,?,?,?)',(code,row[0],row[1],text,'queued',time.time()+300,mode['revision'],time.time()))
 label='群聊' if h.get('is_group') else '好友'
 notify(c,key+':reply','已安排直接发送。'+label+'：'+str(h.get('display') or h.get('title'))+'\n内容：'+text+'\n等待抖音发送回执，无需再次确认。')

def owner_command(text,message_key,now=None):
 # Only the caller's QR-bound-owner gate authorizes invocation.
 now=time.time() if now is None else now
 with connect() as c:
  c.execute('BEGIN IMMEDIATE')
  if c.execute('SELECT 1 FROM inbound_commands WHERE id=?',(message_key,)).fetchone():return
  c.execute('INSERT INTO inbound_commands VALUES(?)',(message_key,));response=None
  command=mode_command(text)
  if command=='invalid':
   notify(c,message_key+':mode','未识别的模式指令，未作为聊天消息发送。请发送：切换AI / 切换人工 / 查看模式。若要发送这段原文，请使用“发送 编号 内容”。');return
  if command is not None:
   before=read_mode()
   current=before if command=='status' else set_mode(command)
   prefix='模式未改变。' if command!='status' and current==before else '模式已更新。' if command!='status' else ''
   notify(c,message_key+':mode',prefix+describe_mode(current));return
  if text in ('获取聊天列表','聊天列表','获取好友列表'):
   rows=c.execute('SELECT n,hit FROM catalog WHERE active=1 ORDER BY n').fetchall();lines=['聊天列表（编号固定；启动扫描时更新；好友和群聊均可发送）']
   for n,h in rows:
    h=json.loads(h);lines.append(str(n)+' '+str(h.get('display') or h.get('title') or '未命名')+(' [群聊]' if h.get('is_group') else ' [好友]'))
   if not rows:lines.append('尚未完成扫描，请稍后再试。')
   pages=[];page=''
   for line in lines:
    if len(page)+len(line)>1400:pages.append(page);page=''
    page+=line+'\n'
   if page:pages.append(page)
   for i,page in enumerate(pages):notify(c,message_key+':list:'+str(i),page.rstrip())
   return
  if text in ('帮助','发送帮助'):
   response='获取聊天列表\n切换人工\n发送 会话编号 内容（好友/群聊直接发送，无二次确认）\n抖音新消息通知转发后60秒内，普通文字直接回复最新通知对应会话。新通知会切换目标；超时请用编号指定。\n查看模式\n切换AI'
  elif text=='查看回复目标':
   route=c.execute('SELECT account,conv,expires,revision FROM latest_reply_route WHERE singleton=1').fetchone();mode=read_mode()
   if route and route[2]>=now and mode['mode']=='manual' and route[3]==mode['revision']:
    row=c.execute('SELECT n,hit FROM catalog WHERE account=? AND conv=? AND active=1',route[:2]).fetchone()
    response='当前快捷回复目标：'+str(json.loads(row[1]).get('display') or json.loads(row[1]).get('title'))+'（编号'+str(row[0])+'），剩余约'+str(max(0,int(route[2]-now)))+'秒。' if row else '当前目标已不可用。'
   else:response='当前没有有效快捷回复目标，请用“发送 编号 内容”。'
  elif text.startswith('确认发送 '):response='已取消二次确认。请使用“发送 编号 内容”，或在60秒窗口内直接回复。旧确认码不会发送。'
  elif text.startswith('发送 '):
   parts=text.split(maxsplit=2);mode=read_mode()
   if len(parts)!=3 or not parts[1].isdigit():response='格式：发送 会话编号 内容。'
   elif len(parts[2])>1500:response='内容超过1500字，请缩短。'
   elif mode['mode']!='manual':response='请先发送“切换人工”，再发送消息。'
   else:
    row=c.execute('SELECT account,conv,hit FROM catalog WHERE n=? AND active=1',(int(parts[1]),)).fetchone()
    if row:enqueue(c,row,parts[2],message_key,mode);return
    response='编号不存在或已失效，请获取聊天列表。'
  elif not text:return
  elif len(text)>1500:response='内容超过1500字，请缩短。'
  else:
   mode=read_mode();route=c.execute('SELECT account,conv,expires,revision FROM latest_reply_route WHERE singleton=1').fetchone()
   if mode['mode']!='manual':response='当前为AI模式，未转发这条文字。请先切换人工。'
   elif not route or route[2]<now or route[3]!=mode['revision']:response='60秒快捷回复窗口已结束或没有目标，未发送。请用“发送 编号 内容”。'
   else:
    row=c.execute('SELECT account,conv,hit FROM catalog WHERE account=? AND conv=? AND active=1',route[:2]).fetchone()
    if row:enqueue(c,row,text,message_key,mode);return
    response='对应会话已不可用，未发送。'
  if response:notify(c,message_key+':reply',response)

def process_browser(account,im,engine):
 with connect() as c:
  c.execute('BEGIN IMMEDIATE')
  row=c.execute("SELECT code,conv,text,expires,revision,updated FROM send_commands WHERE account=? AND state='queued' ORDER BY updated LIMIT 1",(str(account),)).fetchone()
  if not row:return False
  code,cid,text,expires,revision,queued_at=row;mode=read_mode()
  if expires<time.time() or mode['mode']!='manual' or mode['revision']!=revision:
   c.execute("UPDATE send_commands SET state='cancelled',updated=? WHERE code=?",(time.time(),code));notify(c,code+':result','未发送：排队已过期或模式改变。');return True
  hitrow=c.execute('SELECT hit FROM catalog WHERE account=? AND conv=? AND active=1',(str(account),cid)).fetchone()
  if not hitrow:
   c.execute("UPDATE send_commands SET state='cancelled',updated=? WHERE code=?",(time.time(),code));notify(c,code+':result','未发送：会话不可用。');return True
  hit=json.loads(hitrow[0]);c.execute("UPDATE send_commands SET state='sending',updated=? WHERE code=?",(time.time(),code))
 state='uncertain';response='未确认发送成功，请先在抖音核对；不会自动重发。'
 queue_ms=max(0,round((time.time()-queued_at)*1000));select_ms=send_ms=None
 try:
  started=time.perf_counter();selected=im.select_conversation(cid);select_ms=round((time.perf_counter()-started)*1000)
  if not selected:state='failed';response='未发送：无法选择对应会话。'
  elif read_mode()!=mode:state='cancelled';response='未发送：模式已改变。'
  else:
   started=time.perf_counter()
   try:result=im.type_and_send(hit,text,log_content=False)
   finally:send_ms=round((time.perf_counter()-started)*1000)
   if result.get('ok'):state='sent';response='抖音发送回执已确认。'+('群聊：' if hit.get('is_group') else '好友：')+str(hit.get('display') or hit.get('title'))+'\n内容：'+text+'\n这不等于对方已读。'
 except Exception:pass
 with connect() as c:
  c.execute('UPDATE send_commands SET state=?,updated=? WHERE code=?',(state,time.time(),code));notify(c,code+':result',response)
 # No message, account, conversation or credentials in timing diagnostics.
 import logging
 logging.getLogger('app').info('manual_send_timing queue_ms=%s select_ms=%s send_ms=%s state=%s',queue_ms,select_ms,send_ms,state)
 return True

def recover(account):
 with connect() as c:
  rows=c.execute("SELECT code FROM send_commands WHERE account=? AND state='sending'",(str(account),)).fetchall()
  for (code,) in rows:
   c.execute("UPDATE send_commands SET state='uncertain',updated=? WHERE code=?",(time.time(),code));notify(c,code+':result','服务重启时发送未确认，请在抖音核对；不会自动重发。')
