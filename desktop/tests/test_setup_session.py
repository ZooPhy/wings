"""Setup progress remains independent of the browser; no host runtime required."""
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin
import json, os, shlex, shutil, subprocess, sys, tempfile, time, unittest
ROOT=Path(__file__).resolve().parents[1]

class Links(HTMLParser):
 def __init__(self):super().__init__();self.log=None
 def handle_starttag(self,tag,attrs):
  attrs=dict(attrs)
  if tag=='a' and attrs.get('id')=='log':self.log=attrs.get('href')

class SetupSessionTests(unittest.TestCase):
 def scenario(self,status=0,open_failure=False,reopen=False):
  with tempfile.TemporaryDirectory(prefix='wings setup & spaces ') as tmp:
   root=Path(tmp);resources=root/'App Resources';resources.mkdir();workspace=root/'WINGS Workspace';(workspace/'.desktop').mkdir(parents=True);(workspace/'logs').mkdir()
   for name in ['setup-progress.sh','setup-progress.html','setup-progress.js','wings_logo.jpg']:
    shutil.copy2(ROOT/name,resources/name)
   backend=resources/'desktop.sh';backend.write_text('''#!/bin/bash
if [[ "$1" == launch ]]; then
 echo 'Checking Docker Desktop…'; sleep 0.1
 echo 'Preparing BLAST references, VADR models, and assembly tools…'
 echo 'Building BLAST database version 4 with local makeblastdb...'
 echo 'private-secret <script> bad token=must-not-leak'
 sleep 1.2
 if [[ "$TEST_EXIT" == 0 ]]; then
  echo 'Downloading VADR influenza models 1.7...'; sleep 1.1
  echo 'Starting WINGS…'; echo 'WINGS is ready.'
 else echo 'No space left on device'; fi
 exit "$TEST_EXIT"
fi
if [[ "$1" == url ]]; then printf '%s\\n' 'http://127.0.0.1:12345/desktop/session?token=test-token'; exit 0; fi
exit 99
''')
   fake_open=root/'open';fake_open.write_text('#!'+sys.executable+'''\nimport json,os,sys,time
with open(os.environ['OPEN_RECORD'],'a') as f:f.write(json.dumps({'arg':sys.argv[1],'time':time.monotonic()})+'\\n')
if os.environ.get('OPEN_FAILURE')=='1' and sys.argv[1].startswith('http:'):sys.exit(1)
''');fake_open.chmod(0o755)
   script=(ROOT/'setup-session.sh').read_text().replace('/usr/bin/open',shlex.quote(str(fake_open)))
   worker=root/'worker.sh';worker.write_text(script);log=workspace/'logs/setup-test.log';done=workspace/'.desktop/one.done';opened=root/'opened.jsonl'
   env=dict(os.environ,TEST_EXIT=str(status),OPEN_RECORD=str(opened),OPEN_FAILURE='1' if open_failure else '0')
   started=time.monotonic();p=subprocess.Popen(['bash',str(worker),str(resources),str(workspace),'',str(done),str(log)],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
   snapshots=[]
   reopened=False
   state=Path(str(log)+'.status/state.js')
   while p.poll() is None and time.monotonic()-started<10:
    if state.exists():
     snapshots.append(state.read_text())
     if reopen and not reopened and '"phase":4' in snapshots[-1]:
      second_log=workspace/'logs/setup-second.log'
      second=subprocess.run(['bash',str(worker),str(resources),str(workspace),'',str(workspace/'.desktop/two.done'),str(second_log)],env=env,capture_output=True,text=True,timeout=2)
      self.assertEqual(second.returncode,0,second.stderr)
      self.assertIn('already running',second_log.read_text())
      self.assertFalse(Path(str(second_log)+'.status').exists())
      reopened=True
    time.sleep(.1)
   out,err=p.communicate(timeout=2)
   self.assertEqual(p.returncode,status,err);self.assertEqual(done.read_text().strip(),str(status))
   if reopen:self.assertTrue(reopened)
   records=[json.loads(x) for x in opened.read_text().splitlines()]
   self.assertTrue(records[0]['arg'].endswith('/index.html'))
   self.assertLess(records[0]['time']-started,1.5)
   self.assertTrue(any('"phase":4' in s for s in snapshots),snapshots)
   data=json.loads(state.read_text().removeprefix('window.WINGSSetup.update(').removesuffix(');\n'))
   for s in snapshots+[state.read_text()]:
    self.assertNotIn('private-secret',s);self.assertNotIn('test-token',s);self.assertNotIn('<script>',s)
   urls=[v for v in records if v['arg'].startswith('http:')]
   self.assertNotIn('test-token',log.read_text())
   self.assertFalse((workspace/'.desktop/setup-session.lock').exists())
   self.assertEqual((workspace/'.desktop/setup-page').read_text().strip(),str(log)+'.status/index.html')
   page=Path(str(log)+'.status/index.html')
   links=Links();links.feed(page.read_text())
   # No JavaScript is needed to navigate to the actual log, including in a
   # file:// page under a workspace whose URL contains encoded spaces.
   self.assertEqual(urljoin(page.as_uri(),links.log),log.as_uri())
   self.assertNotIn('@@WINGS_SETUP_LOG@@',page.read_text())
   if status==0:
    self.assertEqual(len(urls),1);self.assertEqual(data['status'],'ready')
    self.assertEqual(data['phase'],6);self.assertEqual(data['browserOpened'],not open_failure)
   else:
    self.assertEqual(urls,[]);self.assertEqual(data['status'],'failed');self.assertEqual(data['error'],'disk')
 def test_live_steps_and_completion(self):self.scenario()
 def test_reopen_attaches_to_existing_setup(self):self.scenario(reopen=True)
 def test_failure_stops_at_current_step_without_browser_launch(self):self.scenario(7)
 def test_browser_failure_does_not_undo_setup(self):self.scenario(open_failure=True)
 def test_untrusted_log_name_cannot_enter_generated_html(self):
  with tempfile.TemporaryDirectory() as tmp:
   log=Path(tmp)/'setup-<script>.log'
   command='. "$1"; progress_init'
   result=subprocess.run(['bash','-c',command,'bash',str(ROOT/'setup-progress.sh')],
     env=dict(os.environ,resources=str(ROOT),log_path=str(log)),capture_output=True,text=True)
   self.assertNotEqual(result.returncode,0)
   self.assertFalse(Path(str(log)+'.status').exists())

if __name__=='__main__':unittest.main()
