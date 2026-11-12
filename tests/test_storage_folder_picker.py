"""Exercise the runner folder listing and its HTTP origin guard without launching jobs."""
import ast
import email.message
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TREE = ast.parse((ROOT / 'scripts/wings_local_runner.py').read_text())


class StorageFolderPickerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.scope = dict(Path=Path, os=os, RUNS_ROOT=self.root, REPO_ROOT=ROOT,
                          json=json, subprocess=subprocess,
                          context_runner=types.SimpleNamespace(handle_post=lambda *_: False))
        function = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == 'browse_storage_directories')
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<folder listing>', 'exec'), self.scope)
        self.browse = self.scope['browse_storage_directories']

    def test_only_folders_are_listed_and_hidden_is_opt_in(self):
        for name in ['beta', 'Alpha', '.cache', '<folder>']:
            (self.root / name).mkdir()
        (self.root / 'private.txt').write_text('not returned')
        result = self.browse({'path': str(self.root)})
        self.assertEqual([d['name'] for d in result['directories']], ['<folder>', 'Alpha', 'beta'])
        self.assertNotIn('not returned', json.dumps(result))
        self.assertIn('.cache', [d['name'] for d in self.browse({'path': str(self.root), 'show_hidden': True})['directories']])

    def test_parent_root_home_and_missing_path(self):
        result = self.browse({'path': str(self.root / 'new' / 'runs')})
        self.assertEqual(result['path'], str(self.root.resolve()))
        self.assertTrue(result['notice'])
        self.assertFalse((self.root / 'new').exists())
        with patch.object(Path, 'home', return_value=self.root):
            self.assertEqual(self.browse({})['path'], str(self.root.resolve()))
            self.assertEqual(self.browse({'path': '~'})['path'], str(Path('~').expanduser().resolve()))
        result = self.browse({'path': self.root.anchor})
        self.assertEqual(result['path'], result['parent'])

    def test_search_pagination_and_no_storage_changes(self):
        for i in range(205):
            (self.root / f'folder_{i:03}').mkdir()
        result = self.browse({'path': str(self.root)})
        self.assertEqual((len(result['directories']), result['total']), (200, 205))
        tail = self.browse({'path': str(self.root), 'offset': 200})
        self.assertEqual(len(tail['directories']), 5)
        self.assertEqual(self.browse({'path': str(self.root), 'query': 'FOLDER_204'})['total'], 1)
        self.assertEqual(self.scope['RUNS_ROOT'], self.root)

    def test_invalid_arguments(self):
        for payload in [[], {'path': 42}, {'path': 'relative'}, {'path': '/bad\x00path'},
                        {'query': []}, {'offset': -1}, {'offset': True}, {'show_hidden': 'yes'}]:
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.browse(payload)

    def test_permission_error_is_reported(self):
        with patch.object(os, 'scandir', side_effect=PermissionError('Access denied')):
            with self.assertRaises(PermissionError):
                self.browse({'path': str(self.root)})

    def request(self, origin, content_type='application/json'):
        handler = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'Handler')
        method = next(n for n in handler.body if isinstance(n, ast.FunctionDef) and n.name == 'do_POST')
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<POST handler>', 'exec'), self.scope)
        headers = email.message.Message()
        headers['Host'] = '127.0.0.1:8765'
        headers['Content-Type'] = content_type
        if origin is not None:
            headers['Origin'] = origin
        result = {}
        fake = types.SimpleNamespace(headers=headers, parsed=lambda: types.SimpleNamespace(path='/api/storage/directories'),
            read_json=lambda: {'path': str(self.root)},
            json_response=lambda body, status=200: result.update(body=body, status=status),
            error_response=lambda error, status=400: result.update(error=error, status=status))
        self.scope['do_POST'](fake)
        return result

    def test_local_portal_request_succeeds(self):
        result = self.request('http://127.0.0.1:8765')
        self.assertEqual(result['status'], 200)
        self.assertEqual(result['body']['path'], str(self.root.resolve()))

    def test_cross_origin_and_simple_requests_are_rejected(self):
        self.assertEqual(self.request('https://unrelated.example')['status'], 403)
        self.assertEqual(self.request(None, 'text/plain')['status'], 403)


if __name__ == '__main__':
    unittest.main()
