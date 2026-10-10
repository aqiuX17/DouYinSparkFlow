"""Durable global mode; invalid state disables automatic replies."""
import json, os, uuid, tempfile
from pathlib import Path
PATH = Path(os.getenv('DOUYIN_REPLY_MODE_FILE', '/home/ubuntu/douyin-weixin-validation/reply-mode.json'))
COMMANDS = {'切换人工':'manual', '人工模式':'manual', '切换AI':'ai', '切换ai':'ai', 'AI模式':'ai', '查看模式':'status'}

def mode_command(text):
    """Recognize control text before ordinary chat routing; never edit payloads."""
    import unicodedata
    value = unicodedata.normalize('NFKC', text)
    value = ''.join(c for c in value if not c.isspace() and c not in '\u200b\ufeff\u200c\u200d')
    value = value.casefold().lstrip('/').rstrip('。.!！?？')
    aliases = {key.casefold(): command for key, command in COMMANDS.items()}
    if value in aliases:
        return aliases[value]
    # A mistyped control instruction must never become a quick reply.
    if value.startswith(('切换', '人工模式', 'ai模式', '查看模式')):
        return 'invalid'
    return None

def read_mode(path=None):
    try:
        value = json.loads(Path(path or PATH).read_text(encoding='utf-8'))
        if (isinstance(value, dict) and value.get('mode') in ('ai', 'manual')
                and isinstance(value.get('revision'), str) and value['revision']):
            return value
    except (OSError, ValueError):
        pass
    return {'mode':'manual', 'revision':'invalid'}

def set_mode(mode, path=None):
    if mode not in ('ai', 'manual'):
        raise ValueError('Unsupported mode')
    p = Path(path or PATH)
    current = read_mode(p)
    if current['mode'] == mode and current['revision'] != 'invalid':
        return current
    p.parent.mkdir(exist_ok=True, parents=True, mode=0o700)
    value = {'mode':mode, 'revision':uuid.uuid4().hex}
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix='.mode-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream); stream.flush(); os.fsync(stream.fileno())
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return value

def allows_send(snapshot, path=None):
    return snapshot.get('mode') == 'ai' and read_mode(path) == snapshot

def describe_mode(current):
    if current['mode'] == 'ai':
        detail = 'AI自动回复：已监听会话的新消息由AI回复；微信普通文字不会发到抖音。'
    else:
        detail = '人工回复：不再启动AI生成，模式切换前仍在生成的回复将丢弃。发送 编号 内容，或在新消息通知后60秒内回复对应会话。'
    return ('当前模式：' + detail + '\n作用范围：全部账号的已监听会话。切换不撤回已发消息；已经进入发送动作的消息请核对回执。'
            + '\n抖音新消息仍转发；AI生成内容及发送结果也会通知。切回AI不补发人工期间已处理的消息。'
            + '\n命令：切换AI / 切换人工 / 查看模式 / 获取聊天列表')
