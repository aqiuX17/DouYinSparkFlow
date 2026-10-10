"""Manual send dispatch regression: mock browser, real queue, no network."""
import json, os, subprocess, sys, unittest
from pathlib import Path

class ManualDispatchTests(unittest.TestCase):
    def check_scenario(self, scenario, expected_wait):
        child = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--probe', scenario],
                               capture_output=True, text=True, encoding='utf-8', timeout=30,
                               env=dict(os.environ, PYTHONUTF8='1', PYTHONIOENCODING='utf-8'))
        self.assertEqual(child.returncode, 0, child.stderr)
        result = json.loads(child.stdout)
        self.assertEqual(result['queue_wait_virtual_ms'], expected_wait)
        self.assertEqual(result['send_calls'], 1)
        self.assertEqual(result['final_state'], 'sent')
        self.assertFalse(result['actual_network'])

    def test_dispatch_between_conversation_scans(self):
        self.check_scenario('scan', 500)

    def test_dispatch_during_idle_poll(self):
        self.check_scenario('idle', 100)

if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == '--probe':
    """Real queue/runner, six mock conversations, virtual browser clock; no network."""
    import sys,os,json,tempfile,threading
    from pathlib import Path
    from unittest.mock import MagicMock,patch
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    scenario=sys.argv[2]
    with tempfile.TemporaryDirectory() as d:
     os.environ.update(DOUYIN_WEIXIN_DB=d+'/queue.db',DOUYIN_REPLY_MODE_FILE=d+'/mode.json',DOUYIN_SESSION_DIR=d+'/sessions')
     from core.ai import reply_mode as mode,bridge_commands as bridge
     from core.ai.runner import run_account
     from app.config.models import Account,Config
     from core.ai.config import AIConfig,ProviderConfig
     mode.set_mode('manual');stop=threading.Event()
     clock={'ms':0,'ready':False,'queued':False,'sent':None,'arrived':100 if scenario=='scan' else 3650}
     hits=[{'conv_id':str(i),'title':'fixture-'+str(i),'display':'fixture-'+str(i),'is_group':False} for i in range(6)]
     cfg=Config(ai_chat=AIConfig(providers=[ProviderConfig(api_key='synthetic')],poll_interval=2,cooldown=3))
     account=Account(unique_id='fixture',username='Fixture',cookies='[]',ai_targets=[h['title'] for h in hits])
     browser=MagicMock();page=browser.new_context.return_value.new_page.return_value
     page.evaluate.return_value={'hasChatRoot':True,'loginVisible':False}
     im=MagicMock(ready=True,last_scan={'scanned_all':True})
     im.wait_ready.return_value={'status':'READY'};im.iter_conversations.return_value=hits
     im.read_chat_messages.return_value=[]
     def emit(kind,text):
      if '已监听 6 个会话' in text:clock.update(ms=0,ready=True)
     def wait(ms):
      if not clock['ready']:return
      clock['ms']+=ms
      if not clock['queued'] and clock['ms']>=clock['arrived']:
       clock['queued']=True;bridge.owner_command('发送 1 你好','command')
      if clock['ms']>15000:stop.set()
     def send(hit,text,**kw):
      assert hit['conv_id']=='0' and text=='你好'
      clock['sent']=clock['ms'];stop.set();return {'ok':True}
     page.wait_for_timeout.side_effect=wait;im.type_and_send.side_effect=send
     with patch('cloakbrowser.launch',return_value=browser),patch('core.ai.runner.DouyinIM',return_value=im),patch('core.ai.runner.create_provider',return_value=MagicMock()):
      run_account(account,cfg.ai_chat,cfg,stop,emit)
     assert clock['sent'] is not None and im.type_and_send.call_count==1
     with bridge.connect() as db:state=db.execute('SELECT state FROM send_commands').fetchone()[0]
     print(json.dumps({'scenario':scenario,'input':'发送 1 你好','targets':6,'poll_interval_ms':2000,'arrival_at_virtual_ms':clock['arrived'],'browser_send_at_virtual_ms':clock['sent'],'queue_wait_virtual_ms':clock['sent']-clock['arrived'],'send_calls':im.type_and_send.call_count,'final_state':state,'actual_network':False},ensure_ascii=False))
     db.close()
     import gc
     gc.collect()
elif __name__ == '__main__':
    unittest.main()
