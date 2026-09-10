"""Unit tests for OpenRouter key loading / rotation."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from openmanus_openrouter.keys import KeyRotator, resolve_keys, write_openmanus_config  # noqa: E402


class KeyTests(unittest.TestCase):
    def test_resolve_from_env_list_and_numbered(self):
        env = {
            'OPENROUTER_API_KEYS': 'keyA,keyB',
            'OPENROUTER_API_KEY_1': 'keyC',
            'OPENROUTER_API_KEY_2': 'keyA',  # duplicate
        }
        with patch.dict(os.environ, env, clear=False):
            # clear conflicting vars that may exist in environment
            for name in list(os.environ):
                if name.startswith('OPENROUTER_API_KEY') and name not in env:
                    os.environ.pop(name, None)
            keys = resolve_keys()
        self.assertEqual(keys, ['keyA', 'keyB', 'keyC'])

    def test_keys_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'keys.txt'
            path.write_text('# comment\nkey1\n\nkey2\n', encoding='utf-8')
            with patch.dict(os.environ, {}, clear=False):
                for name in list(os.environ):
                    if name.startswith('OPENROUTER_API_KEY'):
                        os.environ.pop(name, None)
                keys = resolve_keys(str(path))
            self.assertEqual(keys, ['key1', 'key2'])

    def test_rotator(self):
        rotator = KeyRotator(['a', 'b', 'c'])
        self.assertEqual([rotator.next_key() for _ in range(4)], ['a', 'b', 'c', 'a'])

    def test_write_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'config.toml'
            write_openmanus_config(out, model='openrouter/auto', api_key='secret-key')
            text = out.read_text(encoding='utf-8')
            self.assertIn('base_url = "https://openrouter.ai/api/v1"', text)
            self.assertIn('api_key = "secret-key"', text)
            self.assertIn('model = "openrouter/auto"', text)


if __name__ == '__main__':
    unittest.main()
