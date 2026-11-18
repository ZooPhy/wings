"""Run actual menu handler with simulated actions on macOS; no keys or dialogs."""
from pathlib import Path
import subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
class SettingsMenuTests(unittest.TestCase):
 @unittest.skipUnless(sys.platform=='darwin','Native AppleScript needs macOS')
 def test_settings_success_and_cancel_return_to_menu(self):
  s=(ROOT/'WINGS.applescript').read_text()
  handler='on launcherMenu'+s.split('on launcherMenu',1)[1].split('end launcherMenu',1)[0]+'end launcherMenu\n'
  harness='''
property choices : {"Settings", "Settings", "Settings", "Open WINGS", "Settings", "Quit"}
property visits : 0
on chooseWINGSAction()
 set nextChoice to item 1 of choices
 set choices to rest of choices
 return nextChoice
end chooseWINGSAction
on showWINGSSettings(resourcePath, backend, workspace)
 set visits to visits + 1
 if visits is 2 then error number -128
end showWINGSSettings
on run
 if not my launcherMenu("", "", "") then error "Open action lost"
 if visits is not 3 then error "Settings closed launcher"
 if my launcherMenu("", "", "") then error "Quit action lost"
 if visits is not 4 then error "Settings did not reopen"
 return "PASS"
end run
'''
  r=subprocess.run(['/usr/bin/osascript','-'],input=handler+harness,text=True,capture_output=True,timeout=20)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'PASS')
if __name__=='__main__':unittest.main()
