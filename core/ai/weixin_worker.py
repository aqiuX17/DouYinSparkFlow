"""Outbound-only iLink worker; accepts only the QR-bound user's context."""
from core.ai.bridge_commands import owner_command, mark_forwarded
from core.ai.weixin_forward import ClosingConnection
import hashlib
import json,os,time,secrets,base64,threading,urllib.request,urllib.parse,sqlite3
from pathlib import Path
os.umask(0o077)
ROOT=Path(os.getenv('DOUYIN_WEIXIN_STATE_DIR','/home/ubuntu/douyin-weixin-validation'));DB=Path(os.getenv('DOUYIN_WEIXIN_DB',str(ROOT/'forward.sqlite3')));LOCK=threading.Lock()
BIND=json.loads((ROOT/'binding.json').read_text());OWNER=BIND['ilink_user_id'];BASE=BIND.get('baseurl') or 'https://ilinkai.weixin.qq.com'
u=urllib.parse.urlparse(BASE)
if u.scheme!='https' or not (u.hostname=='ilinkai.weixin.qq.com' or (u.hostname or '').endswith('.weixin.qq.com')):raise RuntimeError('Untrusted backend host')
def record(event,**kw):
    print(json.dumps({'event':event,**kw},ensure_ascii=False),flush=True)
def api(endpoint,body):
    body['base_info']={'channel_version':'2.4.9','bot_agent':'DouyinWeixinBridge/0.1'}
    h={'Content-Type':'application/json','AuthorizationType':'ilink_bot_token','Authorization':'Bearer '+BIND['bot_token'],'X-WECHAT-UIN':base64.b64encode(str(secrets.randbits(32)).encode()).decode(),'iLink-App-Id':'bot','iLink-App-ClientVersion':str((2<<16)|(4<<8)|9)}
    req=urllib.request.Request(BASE.rstrip('/')+'/'+endpoint,data=json.dumps(body).encode(),headers=h)
    x=json.load(urllib.request.urlopen(req,timeout=45))
    if x.get('ret',0)!=0 or x.get('errcode',0)!=0:raise ValueError('business:'+str(x.get('ret'))+':'+str(x.get('errcode')))
    return x

def accept_context(message):
    return message.get('from_user_id')==OWNER and bool(message.get('context_token'))
def monitor():
    cursorfile=ROOT/'forward-cursor.json';cursor=json.loads(cursorfile.read_text()).get('cursor','') if cursorfile.exists() else ''
    while True:
        try:
            x=api('ilink/bot/getupdates',{'get_updates_buf':cursor})
            for m in x.get('msgs') or []:
                if accept_context(m):
                    with LOCK:(ROOT/'context.json').write_text(json.dumps({'context_token':m['context_token'],'to_user_id':OWNER,'received_at':time.time()}))
                    record('owner_context_updated')
                    text=''.join(i.get('text_item',{}).get('text','') for i in m.get('item_list',[]) if i.get('type')==1).strip()
                    message_key='weixin:'+str(m.get('message_id') or hashlib.sha256(json.dumps(m,sort_keys=True).encode()).hexdigest())
                    owner_command(text,message_key)

            if x.get('get_updates_buf'):
                cursor=x['get_updates_buf'];cursorfile.write_text(json.dumps({'cursor':cursor}))
        except Exception as e:
            record('poll_failed',error_type=type(e).__name__);time.sleep(20)
def connection():
    db=sqlite3.connect(str(DB),timeout=5,factory=ClosingConnection);db.execute('PRAGMA busy_timeout=5000');return db

def work_once():
    if not DB.exists():return
    with LOCK:
        try:c=json.loads((ROOT/'context.json').read_text())
        except (OSError,ValueError):return
    if c.get('to_user_id')!=OWNER or not c.get('context_token'):return
    with connection() as db:
        row=db.execute("SELECT account,conv,mid,payload FROM messages WHERE state='pending' OR (state='blocked_context' AND updated<?) ORDER BY created LIMIT 1",(c.get('received_at',0),)).fetchone()
        if not row:return
        key=row[:3];db.execute("UPDATE messages SET state='sending',attempts=attempts+1,updated=? WHERE account=? AND conv=? AND mid=?",(time.time(),*key))
    try:
        text=json.loads(row[3])['text']
        if key[0]!='__control__':text+='\n人工模式下，60秒内直接回复将发到本会话；新的抖音通知会切换目标。'
        x=api('ilink/bot/sendmessage',{'msg':{'from_user_id':'','to_user_id':OWNER,'client_id':'douyin-forward-'+secrets.token_hex(12),'message_type':2,'message_state':2,'context_token':c['context_token'],'item_list':[{'type':1,'text_item':{'text':text}}]}})
        state='api_accepted' if x.get('message_id') else 'uncertain';error=''
        if state=='api_accepted' and key[0]!='__control__':mark_forwarded(*key)
    except ValueError as e:
        state='blocked_context';error=str(e) if str(e).startswith('business:') else 'invalid_response'
    except Exception as e:
        state='uncertain';error=type(e).__name__
    with connection() as db:db.execute('UPDATE messages SET state=?,updated=?,error=? WHERE account=? AND conv=? AND mid=?',(state,time.time(),error,*key))
    record('forward_result',state=state,error=error)

if __name__=='__main__':
    if DB.exists():
        with connection() as db:db.execute("UPDATE messages SET state='uncertain',error='worker_restart_during_send' WHERE state='sending'")
    threading.Thread(target=monitor,daemon=True).start();record('worker_started',outbound_only=True)
    while True:
        try:work_once()
        except Exception as e:record('worker_error',error_type=type(e).__name__)
        time.sleep(2)
