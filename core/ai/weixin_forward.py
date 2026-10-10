"""Private durable outbox; no network or browser operations here."""
import json,os,sqlite3,time
from pathlib import Path

class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()

class ForwardOutbox:
    def __init__(self, path=None):
        self.path=Path(path or os.getenv('DOUYIN_WEIXIN_DB','/home/ubuntu/douyin-weixin-validation/forward.sqlite3'))
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS sessions(account TEXT,conv TEXT,baseline INTEGER,started REAL,PRIMARY KEY(account,conv));
CREATE TABLE IF NOT EXISTS messages(account TEXT,conv TEXT,mid TEXT,payload TEXT,state TEXT,attempts INTEGER DEFAULT 0,created REAL,updated REAL,error TEXT,PRIMARY KEY(account,conv,mid));''')
        os.chmod(self.path,0o600)
    def connect(self):
        db=sqlite3.connect(str(self.path),timeout=5,factory=ClosingConnection);db.execute('PRAGMA busy_timeout=5000');return db
    @staticmethod
    def order(row):
        x=str(row.get('order',''));return int(x) if x.isdigit() else None
    def seed(self,account,hit,rows):
        cid=str(hit['conv_id']);account=str(account)
        with self.connect() as db:
            old=db.execute('SELECT 1 FROM sessions WHERE account=? AND conv=?',(account,cid)).fetchone()
            if not old:
                orders=[self.order(r) for r in rows if self.order(r) is not None]
                db.execute('INSERT INTO sessions VALUES(?,?,?,?)',(account,cid,max(orders,default=0),time.time()))
                for row in rows:
                    if row.get('id'):db.execute('INSERT OR IGNORE INTO messages(account,conv,mid,payload,state,created,updated) VALUES(?,?,?,?,?,?,?)',(account,cid,str(row['id']),'','ignored',time.time(),time.time()))
        if old:self.capture(account,hit,rows)
    def capture(self,account,hit,rows):
        cid=str(hit['conv_id']);account=str(account);added=0
        with self.connect() as db:
            base=db.execute('SELECT baseline,started FROM sessions WHERE account=? AND conv=?',(account,cid)).fetchone()
            if not base:return 0
            for row in rows:
                if not row.get('id') or row.get('from_me') or not isinstance(row.get('text'),str) or not row['text'].strip():continue
                order=self.order(row)
                if order is not None:
                    if order<=base[0]:continue
                else:
                    try:
                        if float(row.get('created_at') or 0)<base[1]:continue
                    except (TypeError,ValueError):continue
                text='抖音新消息\n会话：'+str(hit.get('display') or hit.get('title') or cid)+'\n'+row['text']
                payload=json.dumps({'text':text[:1800],'is_group':bool(hit.get('is_group'))},ensure_ascii=False)
                cur=db.execute('INSERT OR IGNORE INTO messages(account,conv,mid,payload,state,created,updated) VALUES(?,?,?,?,?,?,?)',(account,cid,str(row['id']),payload,'pending',time.time(),time.time()));added+=cur.rowcount
        return added

    def ai_reply(self, account, hit, ids, revision, reply, state):
        """Control notifications never change the manual quick-reply destination."""
        import hashlib
        labels = {'generated':'已生成（尚未发送）', 'sent':'抖音发送回执已确认（不代表已读）',
                  'cancelled':'未发送：模式改变或消息已过时',
                  'uncertain':'发送未确认，请核对抖音；不会自动重发'}
        if state not in labels: raise ValueError('Unsupported AI reply state')
        key = hashlib.sha256(json.dumps([str(account), str(hit['conv_id']), list(ids), revision, state]).encode()).hexdigest()
        header = ('AI回复 · ' + labels[state] + '\n账号：' + str(account)
                  + '\n会话：' + str(hit.get('display') or hit.get('title') or hit['conv_id']) + '\n内容：')
        # Split rather than silently truncating generated content.
        chunks = [reply[i:i+1200] for i in range(0, len(reply), 1200)] or ['']
        with self.connect() as db:
            for i, chunk in enumerate(chunks):
                text = header + chunk + (f'\n第{i+1}/{len(chunks)}段' if len(chunks)>1 else '')
                db.execute('INSERT OR IGNORE INTO messages(account,conv,mid,payload,state,created,updated) VALUES(?,?,?,?,?,?,?)',
                           ('__control__', 'ai-reply', key+':'+str(i), json.dumps({'text':text},ensure_ascii=False), 'pending', time.time(),time.time()))
