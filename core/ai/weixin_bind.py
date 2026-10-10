import json,os,base64,secrets,urllib.request,urllib.parse,time
from pathlib import Path
os.umask(0o077)
root=Path(os.getenv('DOUYIN_WEIXIN_STATE_DIR','/home/ubuntu/douyin-weixin-validation'));root.mkdir(parents=True,exist_ok=True,mode=0o700)
headers={'iLink-App-Id':'bot','iLink-App-ClientVersion':str((2<<16)|(4<<8)|9)}
def request(base,ep,body=None):
 h=dict(headers)
 if body is not None:h.update({'Content-Type':'application/json','AuthorizationType':'ilink_bot_token','X-WECHAT-UIN':base64.b64encode(str(secrets.randbits(32)).encode()).decode()})
 req=urllib.request.Request(base.rstrip('/')+'/'+ep,data=None if body is None else json.dumps(body).encode(),headers=h)
 return json.load(urllib.request.urlopen(req,timeout=40))
base='https://ilinkai.weixin.qq.com'
x=request(base,'ilink/bot/get_bot_qrcode?bot_type=3',{'local_token_list':[]})
if not x.get('qrcode') or not x.get('qrcode_img_content'):raise RuntimeError('QR response missing required fields')
(root/'qr.json').write_text(json.dumps(x))
(root/'status.json').write_text(json.dumps({'status':'waiting_scan'}))
print('QR_READY',flush=True)
for _ in range(100):
 try:s=request(base,'ilink/bot/get_qrcode_status?qrcode='+urllib.parse.quote(x['qrcode'],safe=''))
 except Exception as e:
  print('POLL_ERROR',type(e).__name__,flush=True);time.sleep(3);continue
 status=s.get('status','unknown');(root/'status.json').write_text(json.dumps({'status':status}))
 print('STATUS',status,flush=True)
 if status=='confirmed':
  if not s.get('bot_token') or not s.get('ilink_user_id'):raise RuntimeError('Missing binding identity')
  (root/'binding.json').write_text(json.dumps(s));print('BINDING_SAVED_PRIVATE',flush=True);break
 if status in ('expired','need_verifycode','verify_code_blocked','binded_redirect'):break
 if status=='scaned_but_redirect':
  host=s.get('redirect_host','');u=urllib.parse.urlparse('https://'+host if not host.startswith('https://') else host)
  if u.scheme!='https' or not (u.hostname or '').endswith('.weixin.qq.com'):raise RuntimeError('Untrusted redirect host')
  base=urllib.parse.urlunparse((u.scheme,u.netloc,'','','',''))
 time.sleep(1)
