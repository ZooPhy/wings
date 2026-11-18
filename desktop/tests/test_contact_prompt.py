"""Exercise the actual prompt guards with saved values and remembered skips."""
import re,shlex,subprocess,tempfile,unittest,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class PromptTests(unittest.TestCase):
 def test_saved_and_skipped_credentials_do_not_prompt_again(self):
  source=(ROOT/'WINGS.applescript').read_text()
  pattern=r'do shell script "([^"\n]+)" & quoted form of \(workspace & "([^"\n]+-prompted)"\) & "([^"\n]+)" & quoted form of \(workspace & "([^"\n]+)"\)'
  checks=re.findall(pattern,source);self.assertEqual(len(checks),2)
  with tempfile.TemporaryDirectory(prefix='WINGS Workspace ') as tmp:
   root=Path(tmp);(root/'.desktop').mkdir()
   for prefix,marker,middle,credential in checks:
    command=prefix+shlex.quote(tmp+marker)+middle+shlex.quote(tmp+credential)
    def status():return subprocess.run(['/bin/sh','-c',command],env={'PATH':'/nonexistent'},capture_output=True).returncode
    self.assertNotEqual(status(),0)
    saved=Path(tmp+credential);saved.write_text('saved-fixture')
    self.assertEqual(status(),0);self.assertEqual(status(),0)
    saved.unlink();Path(tmp+marker).touch()
    self.assertEqual(status(),0);self.assertEqual(status(),0)
 @unittest.skipUnless(sys.platform=='darwin','Native AppleScript requires macOS')
 def test_native_email_normalization(self):
  source=(ROOT/'WINGS.applescript').read_text();handler='on normalizeContactEmail'+source.split('on normalizeContactEmail',1)[1].split('end normalizeContactEmail',1)[0]+'end normalizeContactEmail\n'
  harness='''
on run
 set savedEmail to my normalizeContactEmail(space & "Name+lab@example.org" & return)
 if savedEmail is not "Name+lab@example.org" then error "Email changed"
 repeat with value in {"", "name", "name@", "name@example", "name@example.org" & linefeed & "BAD=value", "name@@example.org"}
  set rejected to false
  try
   my normalizeContactEmail(contents of value)
  on error
   set rejected to true
  end try
  if not rejected then error "Invalid email accepted"
 end repeat
 return "PASS"
end run
'''
  r=subprocess.run(['/usr/bin/osascript','-'],input=handler+harness,text=True,capture_output=True,timeout=20)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'PASS')
if __name__=='__main__':unittest.main()
