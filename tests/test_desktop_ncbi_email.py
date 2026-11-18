import os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from wings_credentials import runtime_environment
from phylodynamics_job_options import validate_options
class EmailTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name);(self.root/'.desktop').mkdir();self.email=self.root/'.desktop/ncbi-email'
  self.base={'WINGS_DESKTOP_WORKSPACE':str(self.root),'NCBI_EMAIL':'stale@example.org'}
 def test_add_later_no_email_and_non_phylodynamics_allowed(self):
  self.assertNotIn('NCBI_EMAIL',runtime_environment(self.base))
  with patch.dict(os.environ,self.base,clear=True):
   validate_options({'phylodynamics':False})
   with self.assertRaisesRegex(ValueError,'Settings'):validate_options({'phylodynamics':True})
 def test_add_and_update_visible_without_process_restart(self):
  with patch.dict(os.environ,self.base,clear=True):
   self.email.write_text('first@example.org');old=runtime_environment();validate_options({'phylodynamics':True})
   self.email.write_text('next@example.org');new=runtime_environment();validate_options({'phylodynamics':True})
   self.assertEqual(old['NCBI_EMAIL'],'first@example.org');self.assertEqual(new['NCBI_EMAIL'],'next@example.org')
   self.assertEqual(os.environ['NCBI_EMAIL'],'stale@example.org')
 def test_bad_email_does_not_echo_private_value(self):
  self.email.write_text('private@example.org\nINJECT=value')
  with self.assertRaises(ValueError) as error:runtime_environment(self.base)
  self.assertNotIn('private',str(error.exception))
 def test_native_environment_preserved(self):
  self.assertEqual(runtime_environment({'NCBI_EMAIL':'native@example.org'}),{'NCBI_EMAIL':'native@example.org'})
 def test_email_and_ebird_key_loaded_independently(self):
  (self.root/'.desktop/ebirdst-access-key').write_text('fixture-key')
  self.assertEqual(runtime_environment(self.base)['EBIRDST_ACCESS_KEY'],'fixture-key')
  self.email.write_text('saved@example.org');env=runtime_environment(self.base)
  self.assertEqual(env['NCBI_EMAIL'],'saved@example.org');self.assertEqual(env['EBIRDST_ACCESS_KEY'],'fixture-key')
 def test_symlink_rejected(self):
  other=self.root/'outside';other.write_text('test@example.org');self.email.symlink_to(other)
  with self.assertRaises(ValueError):runtime_environment(self.base)
if __name__=='__main__':unittest.main()
