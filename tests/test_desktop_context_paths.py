import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import context_file_picker as p
class DesktopPaths(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='Mac paths ');self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name).resolve();self.home=self.root/'Mac Home';self.home.mkdir()
  for name in ['Downloads','Documents','Desktop']:(self.home/name).mkdir()
  self.workspace=self.home/'WINGS Workspace';self.workspace.mkdir();self.extra=self.root/'External data';self.extra.mkdir()
  self.api={'REPO_ROOT':self.workspace,'RUNS_ROOT':self.workspace/'runs'}
  env={'WINGS_DESKTOP_WORKSPACE':str(self.workspace),'WINGS_HOST_HOME':str(self.home),'WINGS_BROWSE_ROOTS':str(self.home)+os.pathsep+str(self.extra)}
  self.env=patch.dict(os.environ,env);self.env.start();self.addCleanup(self.env.stop)
 def test_host_shortcuts_replace_container_shortcuts(self):
  roots=p.roots(self.api);labels=[r['label'] for r in roots]
  for label in ['Downloads','Documents','Desktop','Home','WINGS Workspace','External data']:self.assertIn(label,labels)
  self.assertNotIn('Mounted data',labels);self.assertNotIn('Removable media',labels)
 def test_pasted_home_and_shared_folder_paths(self):
  folder=self.home/'Downloads'/'Bird data';folder.mkdir()
  for value in ['~/Downloads/Bird data',str(folder),str(self.extra)]:
   r=p.resolve_path(self.api,{'kind':'ebird_download','path':value});self.assertEqual(r['status'],'BROWSE')
  self.assertEqual(p.resolve_path(self.api,{'kind':'ebird_download','path':'~'})['path'],str(self.home))
 def test_csv_and_unavailable_folder(self):
  csv=self.extra/'birds.csv';csv.write_text('a,b')
  self.assertEqual(p.resolve_path(self.api,{'kind':'aphis_csv','path':str(csv)})['path'],str(csv))
  outside=self.root/'not shared';outside.mkdir()
  with self.assertRaisesRegex(ValueError,'Share this folder'):p.resolve_path(self.api,{'kind':'ebird_download','path':str(outside)})
 def test_hidden_escape_symlink_and_relative_path_rejected(self):
  outside=self.root/'private';outside.mkdir();(self.home/'link').symlink_to(outside)
  (self.home/'.private').mkdir()
  for value in ['../private',str(self.home/'.private'),str(self.home/'link'),'bad\x00path']:
   with self.subTest(value=value),self.assertRaises(ValueError):p.resolve_path(self.api,{'kind':'ebird_download','path':value})
if __name__=='__main__':unittest.main()
