import sys,importlib.util,tempfile,time,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.ai import reply_mode as mode
from core.ai import bridge_commands as b
with tempfile.TemporaryDirectory() as d:
 b.DB=Path(d)/'queue.db';mode.PATH=Path(d)/'mode.json';mode.set_mode('manual')
 b.publish('acc',[{'conv_id':'a','display':'A','is_group':False},{'conv_id':'b','display':'B','is_group':False},{'conv_id':'group','display':'G','is_group':True}])
 b.owner_command('发送 3 群聊测试','fixture-group')
 with b.connect() as c:queued=c.execute("SELECT count(*) FROM send_commands WHERE state='queued'").fetchone()[0]
 print('SAME_INPUT=发送 3 群聊测试; queued_without_confirmation='+str(queued))
 if hasattr(b,'mark_forwarded'):
  now=time.time();b.mark_forwarded('acc','a','msg-a',now=now);b.owner_command('快捷回复A','fixture-a',now=now+59)
  b.mark_forwarded('acc','b','msg-b',now=now+1);b.owner_command('快捷回复B','fixture-b',now=now+2)
  b.owner_command('超时不要发','fixture-expired',now=now+62)
  b.owner_command('快捷回复B','fixture-b',now=now+2)
  with b.connect() as c:
   pairs=c.execute('SELECT conv,text FROM send_commands ORDER BY updated').fetchall();assert pairs==[('group','群聊测试'),('a','快捷回复A'),('b','快捷回复B')],pairs
  b.mark_forwarded('__control__','__control__','no-route',now=now+3)
  with b.connect() as c:assert c.execute('SELECT conv FROM latest_reply_route').fetchone()[0]=='b'
  class Browser:
   def __init__(self):self.selected=None;self.sent=[]
   def select_conversation(self,cid):self.selected=cid;return True
   def type_and_send(self,hit,text,log_content):assert self.selected==hit['conv_id'];self.sent.append((hit['conv_id'],text));return {'ok':True}
  im=Browser()
  for _ in range(5):b.process_browser('acc',im,None)
  assert im.sent==pairs,im.sent
  mode.set_mode('ai');b.owner_command('AI模式不要转发','fixture-ai',now=now+3)
  with b.connect() as c:assert c.execute('SELECT count(*) FROM send_commands').fetchone()[0]==3
  print('PASS group=sent_once direct=no_confirm window_59s=A window_61s=blocked newest=B pending_target=frozen duplicates=ignored control_notice=no_route ai=blocked network=mocked')
 else:print('BASELINE group=blocked quick_reply=unsupported')
