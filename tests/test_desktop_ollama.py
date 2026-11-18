import importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import wings_ollama as ollama
spec=importlib.util.spec_from_file_location('ollama_runner',ROOT/'scripts/wings_local_runner.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class OllamaTests(unittest.TestCase):
 def test_local_addresses_and_container_mapping(self):
  for value in ['http://localhost:11434','http://127.0.0.1:11434/api/chat','http://[::1]:11434/','http://host.docker.internal:11434']:
   self.assertEqual(ollama.endpoint(value,desktop=True),'http://host.docker.internal:11434/api/chat')
  self.assertEqual(ollama.endpoint('http://localhost:12345',desktop=True),'http://host.docker.internal:12345/api/chat')
  for bad in ['https://ollama.com','http://example.com:11434','http://localhost@evil.com:11434','http://localhost:0','http://localhost:65536','http://localhost:11434?x','http://localhost:11434/#x','http://localhost:11434\n','http://localhost:11434/api/pull']:
   with self.subTest(value=bad),self.assertRaises(ValueError):ollama.endpoint(bad,desktop=True)
 def test_default_native_and_desktop_settings(self):
  with patch.dict(os.environ,{},clear=True):self.assertEqual(ollama.settings()['url'],ollama.DEFAULT_URL)
  with tempfile.TemporaryDirectory() as d:
   s=ollama.settings(d);self.assertFalse(s['configured']);self.assertEqual(s['url'],'http://host.docker.internal:11434/api/chat')
 def test_saved_defaults_overrides_and_job_snapshot(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'WINGS_DESKTOP_WORKSPACE':d}):
   p=Path(d)/'.desktop/ollama.conf';p.parent.mkdir();p.write_text('http://localhost:12345\nlab/model:7b\n')
   config=runner.briefing_options({'briefing':True})
   self.assertEqual(config['model'],'lab/model:7b');self.assertEqual(config['url'],'http://host.docker.internal:12345/api/chat')
   self.assertFalse(config['allow_remote'])
   self.assertEqual(runner.briefing_options({'briefing':True,'briefing_model':'override'})['model'],'override')
   p.write_text('http://localhost:23456\nnew:8b\n')
   self.assertEqual(runner.briefing_options({'briefing':True})['model'],'new:8b')
   with patch.object(runner,'check_briefing_model',return_value={'ready':True}) as check:
    runner.require_briefing_model({'public_health_interpretation':config})
   check.assert_called_once_with('lab/model:7b','http://host.docker.internal:12345/api/chat')
 def test_invalid_settings_do_not_block_other_modules(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'WINGS_DESKTOP_WORKSPACE':d}):
   p=Path(d)/'.desktop/ollama.conf';p.parent.mkdir();p.write_text('not valid')
   self.assertIn('error',ollama.public_settings())
   self.assertEqual(runner.briefing_options({'briefing':False}),{'enabled':False})
   with self.assertRaises(ValueError):runner.briefing_options({'briefing':True})
   p.unlink();elsewhere=Path(d)/'other';elsewhere.write_text('http://localhost:11434\nx\n');p.symlink_to(elsewhere)
   with self.assertRaises(ValueError):ollama.settings(d)
 def test_container_check_uses_saved_url_and_only_tags(self):
  with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'WINGS_DESKTOP_WORKSPACE':d}):
   p=Path(d)/'.desktop/ollama.conf';p.parent.mkdir();p.write_text('http://localhost:12345\nlocal\n')
   connection=Mock();connection.getresponse.return_value.status=200;connection.getresponse.return_value.read.return_value=b'{"models":[{"name":"local:latest"},{"name":"<script>"}]}'
   with patch.object(runner,'HTTPConnection',return_value=connection) as factory:
    answer=runner.check_briefing_model('local')
   self.assertTrue(answer['ready']);self.assertEqual(answer['models'],['local:latest'])
   factory.assert_called_once_with('host.docker.internal',12345,timeout=5)
   connection.request.assert_called_once_with('GET','/api/tags')
 def test_local_model_requests_bypass_proxy_without_mutating_environment(self):
  before={'WINGS_DESKTOP_WORKSPACE':'/test','HTTP_PROXY':'http://proxy','NO_PROXY':'example.org'}
  after=ollama.runtime_environment(before)
  self.assertEqual(before['NO_PROXY'],'example.org');self.assertEqual(after['HTTP_PROXY'],before['HTTP_PROXY'])
  self.assertIn('host.docker.internal',after['no_proxy']);self.assertIn('example.org',after['NO_PROXY'])
  self.assertEqual(ollama.runtime_environment({'NO_PROXY':'example.org'}),{'NO_PROXY':'example.org'})
if __name__=='__main__':unittest.main()
