"""Mode commands must never leak into the manual quick-reply queue."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.ai import bridge_commands as bridge, reply_mode as mode
from core.ai.weixin_forward import ForwardOutbox


class ModeCommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        for item in (patch.object(mode, 'PATH', root / 'mode.json'),
                     patch.object(bridge, 'DB', root / 'queue.db')):
            item.start()
            self.addCleanup(item.stop)
        self.hit = {'conv_id': 'friend', 'display': 'Fixture friend'}
        bridge.publish('fixture', [self.hit])

    def queued(self):
        with bridge.connect() as db:
            return db.execute('SELECT count(*) FROM send_commands').fetchone()[0]

    def test_normalized_commands_never_become_chat(self):
        for index, text in enumerate(('切换ai', '切换 ai', '切换Ai', '切换ＡＩ',
                                      '\u200b切换ai', '/切换ai', '切换ai！')):
            with self.subTest(text=text):
                mode.set_mode('manual')
                bridge.mark_forwarded('fixture', 'friend', 'incoming')
                bridge.owner_command(text, 'command-' + str(index))
                self.assertEqual(mode.read_mode()['mode'], 'ai')
                self.assertEqual(self.queued(), 0)

    def test_mistyped_command_is_blocked_but_explicit_payload_is_preserved(self):
        mode.set_mode('manual')
        bridge.mark_forwarded('fixture', 'friend', 'incoming')
        bridge.owner_command('切换ai 测试', 'mistyped')
        self.assertEqual(mode.read_mode()['mode'], 'manual')
        self.assertEqual(self.queued(), 0)
        bridge.owner_command('发送 1 切换ai 测试', 'explicit')
        with bridge.connect() as db:
            self.assertEqual(db.execute('SELECT text FROM send_commands').fetchone()[0], '切换ai 测试')

    def test_repeated_mode_keeps_route_and_replayed_command_cannot_undo_switch(self):
        first = mode.set_mode('manual')
        bridge.mark_forwarded('fixture', 'friend', 'incoming')
        bridge.owner_command('切换人工', 'manual-command')
        self.assertEqual(mode.read_mode(), first)
        bridge.owner_command('reply', 'quick-reply')
        self.assertEqual(self.queued(), 1)
        bridge.owner_command('切换ai', 'ai-command')
        bridge.owner_command('切换人工', 'manual-command')
        self.assertEqual(mode.read_mode()['mode'], 'ai')

    def test_mode_receipt_is_durable_and_deduplicated(self):
        bridge.owner_command('切换ai', 'once')
        bridge.owner_command('切换ai', 'once')
        with bridge.connect() as db:
            rows = db.execute("SELECT payload,state FROM messages WHERE mid='once:mode'").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], 'pending')
        self.assertIn('AI自动回复', json.loads(rows[0][0])['text'])

    def test_invalid_mode_fails_closed(self):
        for value in ('[]', 'null', '1', '{"mode":"ai","revision":""}', 'broken'):
            mode.PATH.write_text(value, encoding='utf-8')
            self.assertEqual(mode.read_mode(), {'mode': 'manual', 'revision': 'invalid'})

    def test_generated_reply_is_deduplicated_chunked_and_does_not_change_route(self):
        current = mode.set_mode('manual')
        bridge.mark_forwarded('fixture', 'friend', 'incoming')
        with bridge.connect() as db:
            route = db.execute('SELECT * FROM latest_reply_route').fetchall()
        outbox = ForwardOutbox(bridge.DB)
        text = 'test reply ' * 250
        for _ in range(2):
            outbox.ai_reply('fixture', self.hit, ['incoming'], current['revision'], text, 'generated')
        with bridge.connect() as db:
            notices = db.execute("SELECT payload FROM messages WHERE conv='ai-reply' ORDER BY mid").fetchall()
            self.assertEqual(route, db.execute('SELECT * FROM latest_reply_route').fetchall())
        self.assertEqual(len(notices), 3)
        chunks = [json.loads(row[0])['text'].split('内容：', 1)[1].rsplit('\n第', 1)[0] for row in notices]
        self.assertEqual(''.join(chunks), text)


if __name__ == '__main__':
    unittest.main()
