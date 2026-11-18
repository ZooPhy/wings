"""Browser state model; no native GUI or runtime needed by end users."""
from pathlib import Path
import shutil, subprocess, unittest
ROOT=Path(__file__).resolve().parents[1]
class SetupStatusTests(unittest.TestCase):
 @unittest.skipUnless(shutil.which('node'),'Node needed for developer-only tests')
 def test_live_status_model(self):
  subprocess.run(['node','--test',str(ROOT/'tests/test_setup_progress.cjs')],check=True)
if __name__=='__main__':unittest.main()
