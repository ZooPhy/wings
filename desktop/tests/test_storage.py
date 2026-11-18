import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(os.environ.get('WINGS_TEST_SOURCE', str(ROOT.parent / 'source')))
if not (SOURCE / 'scripts/wings_local_runner.py').exists():
    SOURCE = ROOT.parent
spec = importlib.util.spec_from_file_location('wings_desktop_runner_test', SOURCE / 'scripts/wings_local_runner.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class StorageTests(unittest.TestCase):
    def test_outputs_remain_inside_persistent_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / 'workspace'; workspace.mkdir()
            with patch.dict(os.environ, {'WINGS_DESKTOP_WORKSPACE': str(workspace)}):
                self.assertEqual(runner.prepare_storage_directory(str(workspace / 'runs')), workspace / 'runs')
                with self.assertRaises(ValueError):
                    runner.prepare_storage_directory(str(root / 'ephemeral'))
                self.assertFalse((root / 'ephemeral').exists())
                (workspace / 'escape').symlink_to(root, target_is_directory=True)
                with self.assertRaises(ValueError):
                    runner.prepare_storage_directory(str(workspace / 'escape' / 'lost'))
                listing = runner.browse_storage_directories({'path': str(workspace)})
                self.assertEqual(listing['parent'], str(workspace))
                self.assertNotIn('escape', [entry['name'] for entry in listing['directories']])
                with self.assertRaises(ValueError):
                    runner.create_storage_folder({'path': str(root), 'name': 'lost'})

    def test_native_runner_retains_unrestricted_storage(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.dict(os.environ, clear=False):
                os.environ.pop('WINGS_DESKTOP_WORKSPACE', None)
                self.assertEqual(runner.prepare_storage_directory(temp), Path(temp))


if __name__ == '__main__':
    unittest.main()
