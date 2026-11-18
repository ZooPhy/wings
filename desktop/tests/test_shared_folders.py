import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_launcher import LauncherTests
class SharedFolders(LauncherTests):
 def test_home_readonly_workspace_writable_and_extra_restart(self):
  r=self.command();self.assertEqual(r.returncode,0,r.stderr)
  state=json.loads((self.root/'docker-state.json').read_text())
  start=next(a for a in state['calls'] if 'run' in a and '-d' in a)
  mounts=[a for i,a in enumerate(start) if i and start[i-1]=='--mount']
  self.assertIn(f'type=bind,source={self.home},target={self.home},readonly',mounts)
  self.assertIn(f'type=bind,source={self.workspace},target={self.workspace}',mounts)
  extra=self.root/'Extra reference files';extra.mkdir()
  (self.workspace/'.desktop/shared-folders').write_text(str(extra)+'\n')
  blocked=self.command();self.assertEqual(blocked.returncode,17);self.assertIn('Shared folders changed',blocked.stderr)
  self.assertEqual(self.command('stop').returncode,0)
  self.assertEqual(self.command().returncode,0)
  state=json.loads((self.root/'docker-state.json').read_text())
  starts=[a for a in state['calls'] if 'run' in a and '-d' in a]
  self.assertIn(f'type=bind,source={extra},target={extra},readonly',starts[-1])
 def test_missing_shared_directory_does_not_launch(self):
  (self.workspace/'.desktop').mkdir(parents=True)
  (self.workspace/'.desktop/shared-folders').write_text(str(self.root/'missing drive')+'\n')
  r=self.command();self.assertNotEqual(r.returncode,0);self.assertIn('shared folder is unavailable',r.stderr)
 def test_symlink_to_filesystem_root_rejected(self):
  (self.workspace/'.desktop').mkdir(parents=True);alias=self.root/'alias';alias.symlink_to('/')
  (self.workspace/'.desktop/shared-folders').write_text(str(alias)+'\n')
  r=self.command();self.assertNotEqual(r.returncode,0);self.assertIn('resolved shared-folder',r.stderr)
if __name__=='__main__':unittest.main()
