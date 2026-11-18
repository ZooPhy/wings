"""Run actual menu handler with simulated actions on macOS; no keys or dialogs."""
from pathlib import Path
import subprocess,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
class SettingsMenuTests(unittest.TestCase):
 @unittest.skipUnless(sys.platform=='darwin','Native AppleScript needs macOS')
 def test_grouped_settings_keep_actions_and_recover_from_cancel_and_error(self):
  source=(ROOT/'WINGS.applescript').read_text()
  def handler(name):
   return 'on '+name+source.split('on '+name,1)[1].split('end '+name,1)[0]+'end '+name+'\n'
  harness='''
property categories : {"NCBI & eBird access", "Ollama", "Folders and storage", "Setup and diagnostics", "Stop WINGS service", "Stop WINGS service"}
property pendingActions : {}
property visited : {}
property reportedErrors : {}
property stopCount : 0
on chooseSettingsCategory()
 if categories is {} then error "Settings failed to return after stopping"
 set category to item 1 of categories
 set categories to rest of categories
 set pendingActions to my settingsActions(category)
 return category
end chooseSettingsCategory
on chooseSettingsAction(category)
 if pendingActions is {} then return false
 set action to item 1 of pendingActions
 set pendingActions to rest of pendingActions
 return action
end chooseSettingsAction
on runSettingsAction(action, resourcePath, backend, workspace)
 set end of visited to action
 if action is "Add or update NCBI email" then error number -128
 if action is "Configure Ollama" then error "Simulated save error" number 77
 if action is "Stop WINGS service" then
  set stopCount to stopCount + 1
  if stopCount is 1 then error number -128
 end if
end runSettingsAction
on settingsError(messageText)
 set end of reportedErrors to messageText
end settingsError
on run
 my showWINGSSettings("", "", "")
 set expected to {"Add or update NCBI email", "Add or update eBird access key", "Get an eBird access key", "Remove eBird access key", "Configure Ollama", "Check Ollama connection", "Share a folder with WINGS", "Open workspace", "View setup progress", "Export installation diagnostics", "Stop WINGS service", "Stop WINGS service"}
 if visited is not expected then error "Actions lost or menu closed early"
 if (count of reportedErrors) is not 1 then error "Cancellation shown as an error"
 if categories is not {} then error "Stop cancellation closed settings"
 return "PASS"
end run
'''
  r=subprocess.run(['/usr/bin/osascript','-'],input=handler('settingsActions')+handler('showWINGSSettings')+harness,text=True,capture_output=True,timeout=20)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'PASS')

 @unittest.skipUnless(sys.platform=='darwin','Native AppleScript needs macOS')
 def test_done_returns_without_running_an_action(self):
  source=(ROOT/'WINGS.applescript').read_text()
  handler='on showWINGSSettings'+source.split('on showWINGSSettings',1)[1].split('end showWINGSSettings',1)[0]+'end showWINGSSettings\n'
  harness='''
on chooseSettingsCategory()
 return false
end chooseSettingsCategory
on chooseSettingsAction(category)
 error "Done opened a submenu"
end chooseSettingsAction
on runSettingsAction(action, resourcePath, backend, workspace)
 error "Done performed an action"
end runSettingsAction
on run
 my showWINGSSettings("", "", "")
 return "PASS"
end run
'''
  r=subprocess.run(['/usr/bin/osascript','-'],input=handler+harness,text=True,capture_output=True,timeout=20)
  self.assertEqual(r.returncode,0,r.stderr);self.assertEqual(r.stdout.strip(),'PASS')

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
