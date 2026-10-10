"""Private durable outbox; no network or browser operations here."""
import json,os,sqlite3,time
from pathlib import Path

class ForwardOutbox:
    def __init__(self, path=None):
        self.path=Path(path or os.getenv('DOUYIN_WEIXIN_DB','/home/ubuntu/douyin-weixin-validation/forward.sqlite3'))
        self.path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS sessions(account TEXT,conv TEXT,baseline INTEGER,started REAL,PRIMARY KEY(account,conv));
CREATE TABLE IF NOT EXISTS messages(account TEXT,conv TEXT,mid TEXT,payload TEXT,state TEXT,attempts INTEGER DEFAULT 0,created REAL,updated REAL,error TEXT,PRIMARY KEY(account,conv,mid));''')
        os.chmod(self.path,0o600)
    def connect(self):
        db=sqlite3.connect(str(self.path),timeout=5);db.execute('PRAGMA busy_timeout=5000');return db
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
