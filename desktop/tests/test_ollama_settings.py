from pathlib import Path
import importlib.util,json,os,subprocess,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]

class OllamaSettingsTests(unittest.TestCase):
 def test_save_validation_permissions_and_preservation(self):
  with tempfile.TemporaryDirectory(prefix='WINGS settings with spaces ') as d:
   def save(url,model):return subprocess.run(['bash',str(ROOT/'ollama-settings.sh'),d,url,model],capture_output=True,text=True)
   self.assertEqual(save('http://localhost:12345','lab/model:7b').returncode,0)
   p=Path(d)/'.desktop/ollama.conf';expected=p.read_bytes()
   self.assertEqual(expected,b'http://localhost:12345\nlab/model:7b\n');self.assertEqual(p.stat().st_mode&0o777,0o600)
   for url,model in [('http://localhost:0','ok'),('http://elsewhere:11434','ok'),('http://localhost:11434','x; touch BAD'),('http://localhost:11434','a\nb'),('http://localhost:65536','ok')]:
    self.assertNotEqual(save(url,model).returncode,0);self.assertEqual(p.read_bytes(),expected)
   self.assertEqual(list(p.parent.glob('.ollama.*')),[])
   p.unlink();target=Path(d)/'outside';target.write_text('unchanged');p.symlink_to(target)
   self.assertNotEqual(save('http://localhost:11434','ok').returncode,0);self.assertEqual(target.read_text(),'unchanged')

from test_launcher import LauncherTests
class ContainerCheckTests(unittest.TestCase):
 setUp=LauncherTests.setUp
 tearDown=LauncherTests.tearDown
 command=LauncherTests.command
 def test_check_requires_matching_running_service_and_uses_exec(self):
  self.assertNotEqual(self.command('ollama-check').returncode,0)
  self.assertEqual(self.command().returncode,0)
  helper=self.resources/'wings_ollama.py';helper.write_text('canonical-helper-fixture')
  checked=self.command('ollama-check')
  self.assertEqual(checked.returncode,0,checked.stderr)
  state=json.loads((self.root/'docker-state.json').read_text())
  self.assertEqual(state['exec_input'],'canonical-helper-fixture')
  calls=[c for c in state['calls'] if 'exec' in c]
  self.assertEqual(len(calls),1)
  self.assertIn('/opt/conda/bin/python',calls[0]);self.assertEqual(calls[0][-2:],['--workspace',str(self.workspace)])
  (self.resources/'source.sha256').write_text('b'*64)
  self.assertIn('earlier WINGS service',self.command('ollama-check').stderr)
  self.command('stop');self.assertNotEqual(self.command('ollama-check').returncode,0)

if __name__=='__main__':unittest.main()

