"""Real macOS launch/signature/DMG regression, with no workflow or GUI actions.

Run: python -m unittest discover -s desktop/tests -p test_macos_distribution.py -v
Requires macOS and Xcode Command Line Tools. No Developer ID is required.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


DESKTOP = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == 'darwin', 'Requires macOS signing and disk-image tools')
class MacOSDistributionTests(unittest.TestCase):
    def test_signature_survives_execution_and_packaging(self):
        root = Path(tempfile.mkdtemp(prefix='WINGS distribution test ')).resolve()
        env = dict(os.environ)
        for name in ('WINGS_SIGN_IDENTITY', 'WINGS_NOTARY_PROFILE',
                     'WINGS_BUILD_APP_ONLY', 'WINGS_APP_RESOURCES'):
            env.pop(name, None)
        # Deliberately contains a wrong inherited value; the launcher must use
        # its own bundle, including when the executable path contains spaces.
        env['WINGS_APP_RESOURCES'] = '/incorrect/inherited/resource/path'

        def run(*args, extra_env=None, timeout=180):
            result = subprocess.run(args, env=env | (extra_env or {}),
                                    capture_output=True, text=True, timeout=timeout)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return result.stdout.strip()

        try:
            preview = root / 'input WINGS.app'
            resources = preview / 'Contents' / 'Resources'
            resources.mkdir(parents=True)
            # No menus, services, downloads, credentials or analyses.
            (resources / 'WINGS.applescript').write_text(
                'on run\nreturn system attribute "WINGS_APP_RESOURCES"\nend run\n')
            icon = DESKTOP / 'WINGS.icns'
            if not icon.is_file():
                icon = Path('/System/Library/CoreServices/CoreTypes.bundle/Contents/Resources/GenericApplicationIcon.icns')
            self.assertTrue(icon.is_file(), 'A fixture icon is required')
            shutil.copyfile(icon, resources / 'WINGS.icns')

            output = root / 'build with spaces'
            run('/bin/bash', str(DESKTOP / 'build-macos.sh'), str(preview), str(output),
                extra_env={'WINGS_BUILD_APP_ONLY': '1'})
            app = output / 'WINGS.app'
            bundled_resources = app / 'Contents' / 'Resources'
            self.assertFalse((bundled_resources / 'Scripts' / 'main.scpt').exists())
            verify = ('/usr/bin/codesign', '--verify', '--deep', '--strict', str(app))
            run(*verify)
            # Repeat execution to catch state written back after the first run.
            for _ in range(2):
                self.assertEqual(run(str(app / 'Contents' / 'MacOS' / 'WINGS')),
                                 str(bundled_resources))
                run(*verify)

            package = root / 'package'
            run('/bin/bash', str(DESKTOP / 'package-wings-dmg.sh'), str(app),
                str(package), timeout=600)
            self.assertTrue((package / 'WINGS-Desktop-Preview.dmg').is_file())
            log = (package / 'packaging.log').read_text()
            self.assertIn('-readonly', log)
            self.assertGreaterEqual(log.count('--verify --deep --strict'), 3)
            run(*verify)
        except BaseException:
            # Never remove a backing image that may still be mounted after a
            # failure. Keep logs and the helper's reported private mount path.
            print(f'Mac distribution test files retained: {root}', file=sys.stderr)
            log = root / 'package' / 'packaging.log'
            if log.is_file():
                print(log.read_text()[-12000:], file=sys.stderr)
            raise
        else:
            shutil.rmtree(root)


if __name__ == '__main__':
    unittest.main()
