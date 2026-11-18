import hashlib
import importlib.util
import json
from pathlib import Path
import plistlib
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime'))
from controller import verify
spec = importlib.util.spec_from_file_location('desktop_package', ROOT / 'package.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class PackageTests(unittest.TestCase):
    def test_bundle_manifest_archive_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'; source.mkdir()
            for name in ['Snakefile', 'rules/phylodynamics.smk', 'scripts/phylodynamic_selection.py',
                         'scripts/phylodynamic_bayesian.py', 'config/phylodynamics.example.yaml', 'config/config.example.yaml',
                         'scripts/phylodynamics_job_options.py', 'scripts/phylodynamics_submission.py', 'scripts/wings_ollama.py']:
                p = source / name; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('fixture\n')
            app = package.bundle(source, root / 'dist')
            resources = app / 'Contents/Resources'
            self.assertEqual((resources/'setup-session.sh').read_bytes(), (ROOT/'setup-session.sh').read_bytes())
            for name in ['setup-progress.sh', 'setup-progress.js', 'setup-progress.html', 'ollama-settings.sh']:
                self.assertEqual((resources/name).read_bytes(), (ROOT/name).read_bytes())
            self.assertEqual((resources/'wings_ollama.py').read_bytes(), (source/'scripts/wings_ollama.py').read_bytes())
            self.assertEqual(plistlib.loads((app / 'Contents/Info.plist').read_bytes())['CFBundleExecutable'], 'WINGS')
            self.assertTrue((app / 'Contents/MacOS/WINGS').stat().st_mode & 0o111)
            self.assertEqual(hashlib.sha256((resources / 'source.tar.gz').read_bytes()).hexdigest(),
                             (resources / 'source.sha256').read_text().strip())
            unpacked = root / 'unpacked'; unpacked.mkdir()
            with tarfile.open(resources / 'source.tar.gz') as archive:
                archive.extractall(unpacked, filter='data')
            verify(unpacked)
            (unpacked / 'rules/phylodynamics.smk').unlink()
            with self.assertRaisesRegex(RuntimeError, 'Missing'):
                verify(unpacked)

    def test_private_data_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'source/results').mkdir(parents=True)
            (root / 'source/results/sample.fasta').write_text('private')
            with self.assertRaises(ValueError):
                package.bundle(root / 'source', root / 'out')

    def test_source_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / 'source').mkdir()
            (root / 'outside').write_text('private')
            (root / 'source/escape').symlink_to(root / 'outside')
            with self.assertRaises(ValueError):
                package.bundle(root / 'source', root / 'out')


if __name__ == '__main__':
    unittest.main()
