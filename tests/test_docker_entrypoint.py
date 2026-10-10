"""Linux entrypoint dispatch with fake executables; no Docker/browser/network required."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class DockerEntrypointTests(unittest.TestCase):
    def test_dispatch(self):
        version = subprocess.check_output(['bash', '--version'], text=True)
        if 'version 3.' in version:
            self.skipTest('Container requires Linux bash >=4; macOS system bash is 3.x')
        source = (Path(__file__).resolve().parents[1] / 'docker/entrypoint.sh').read_text()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, body in [('entrypoint-cron.sh', 'echo cron'),
                               ('entrypoint-fc.sh', 'echo fc'),
                               ('python', 'printf "python"; printf " <%s>" "$@"; printf "\\n"')]:
                target = root / name
                target.write_text('#!/bin/bash\n' + body + '\n')
                target.chmod(0o755)
            script = root / 'entrypoint.sh'
            script.write_text(source.replace('/app/docker/', str(root) + '/'))
            for mode, expected in [('chat', 'python </app/main.py> <chat>\n'),
                                   ('AI', 'python </app/main.py> <chat>\n'),
                                   ('weixin', 'python <-m> <core.ai.weixin_worker>\n'),
                                   ('clawbot', 'python <-m> <core.ai.weixin_worker>\n'),
                                   ('cron', 'cron\n'), ('fc', 'fc\n')]:
                with self.subTest(mode=mode):
                    result = subprocess.run(['bash', str(script)], capture_output=True, text=True,
                                            env={**os.environ, 'LAUNCH_MODE': mode,
                                                 'PATH': str(root) + ':' + os.environ['PATH']})
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, expected)
                    self.assertEqual(result.stderr, '')
