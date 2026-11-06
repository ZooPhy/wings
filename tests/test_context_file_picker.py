"""Filesystem chooser boundaries and local runner integration; no native dialogs."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import context_file_picker as p
import context_setup as context
import test_context_runner as runner_tests

class PickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve();self.base=self.root/'browse';self.base.mkdir()
        self.choices=[{'id':'test-root','label':'Test location','path':str(self.base)}]
        self.patch=patch.object(p,'roots',return_value=self.choices);self.patch.start();self.addCleanup(self.patch.stop)
        self.api={};self.payload={'kind':'ebird_download','root_id':'test-root','relative':''}
    def test_list_folders_only_and_csv_mode(self):
        (self.base/'B folder').mkdir();(self.base/'A folder').mkdir();(self.base/'.hidden').mkdir()
        (self.base/'bird.CSV').write_text('do not read');(self.base/'secret.txt').write_text('no content')
        result=p.browse(self.api,self.payload)
        self.assertEqual([r['name'] for r in result['entries']],['A folder','B folder'])
        result=p.browse(self.api,{**self.payload,'kind':'aphis_csv'})
        self.assertEqual([r['name'] for r in result['entries']],['A folder','B folder','bird.CSV'])
        self.assertNotIn('do not read',str(result));self.assertIsNone(result['parent'])
    def test_select_unicode_and_spaces_and_return_to_parent(self):
        folder=self.base/'birds 🐦 with spaces';folder.mkdir()
        result=p.browse(self.api,{**self.payload,'relative':folder.name})
        self.assertEqual(result['parent'],'');self.assertEqual(result['path'],str(folder))
        self.assertEqual(p.select(self.api,{**self.payload,'relative':folder.name})['path'],str(folder))
    def test_escape_hidden_paths_and_symlinks_rejected(self):
        outside=self.root/'outside';outside.mkdir();(self.base/'escape').symlink_to(outside,target_is_directory=True)
        (self.base/'.hidden').mkdir();(self.base/'hidden-link').symlink_to(self.base/'.hidden',target_is_directory=True)
        for relative in ['../outside',str(outside),'.hidden','escape','hidden-link']:
            with self.subTest(relative=relative),self.assertRaises(ValueError):p.browse(self.api,{**self.payload,'relative':relative})
        self.assertEqual(p.browse(self.api,self.payload)['entries'],[])
    def test_csv_selection_rejects_other_files_and_folders(self):
        (self.base/'ok.csv').write_text('a,b');(self.base/'bad.txt').write_text('a,b')
        self.assertEqual(p.select(self.api,{**self.payload,'kind':'aphis_csv','relative':'ok.csv'})['status'],'SELECTED')
        for name in ['bad.txt','']:
            with self.assertRaises(ValueError):p.select(self.api,{**self.payload,'kind':'aphis_csv','relative':name})
        with self.assertRaises(ValueError):p.select(self.api,{**self.payload,'relative':'ok.csv'})
    def test_pagination_and_invalid_payloads(self):
        for n in range(103):(self.base/f'folder-{n:03}').mkdir()
        first=p.browse(self.api,self.payload);self.assertEqual(len(first['entries']),100);self.assertEqual(first['next_offset'],100)
        second=p.browse(self.api,{**self.payload,'offset':100});self.assertEqual(len(second['entries']),3);self.assertIsNone(second['next_offset'])
        for override in [{'kind':[]},{'kind':'bad'},{'root_id':'missing'},{'relative':None},{'offset':True},{'offset':-1}]:
            with self.subTest(override=override),self.assertRaises(ValueError):p.browse(self.api,{**self.payload,**override})
    def test_same_origin_required_before_reading_folders(self):
        valid={'Origin':'http://localhost:8765','Host':'localhost:8765','Content-Type':'application/json'}
        p.browser_origin(SimpleNamespace(headers=valid))
        for override in [{'Origin':''},{'Origin':'http://evil.example:8765'},{'Origin':'http://localhost:8766'},{'Host':'evil.example:8765'},{'Origin':'http://user@localhost:8765'},{'Content-Type':'text/plain'}]:
            with self.subTest(override=override),self.assertRaises(ValueError):p.browser_origin(SimpleNamespace(headers={**valid,**override}))
    def test_linux_or_remote_mac_falls_back_to_runner_browser(self):
        with patch.object(p,'native_available',return_value=False),patch.object(p.subprocess,'run') as run:
            self.assertEqual(p.native(self.api,self.payload)['status'],'BROWSE');run.assert_not_called()
        with patch.object(p.sys,'platform','darwin'),patch.dict(os.environ,{'SSH_CONNECTION':'remote'}):self.assertFalse(p.native_available())
    def test_native_selection_cancellation_fallback_and_fixed_script(self):
        folder=self.root/'native selected folder';folder.mkdir()
        with patch.object(p,'native_available',return_value=True),patch.object(p.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=str(folder)+'\n',stderr='')) as run:
            result=p.native(self.api,{**self.payload,'path':'$(not used)'})
            self.assertEqual(result['path'],str(folder));self.assertEqual(run.call_args.args[0],['/usr/bin/osascript','-e',p.SCRIPTS['ebird_download']]);self.assertNotIn('shell',run.call_args.kwargs)
        for err,expected in [('User canceled. (-128)','CANCELLED'),('No graphical session','BROWSE')]:
            with patch.object(p,'native_available',return_value=True),patch.object(p.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='',stderr=err)):
                self.assertEqual(p.native(self.api,self.payload)['status'],expected)
        with patch.object(p,'native_available',return_value=True),patch.object(p.subprocess,'run',side_effect=subprocess.TimeoutExpired('osascript',180)):
            self.assertEqual(p.native(self.api,self.payload)['status'],'BROWSE')
        self.assertFalse(p.NATIVE_LOCK.locked())
    def test_native_concurrency_guard(self):
        p.NATIVE_LOCK.acquire()
        try:
            with patch.object(p,'native_available',return_value=True),self.assertRaisesRegex(ValueError,'already open'):p.native(self.api,self.payload)
        finally:p.NATIVE_LOCK.release()
    def test_choosing_explicit_download_overrides_automatic_cache_reuse(self):
        opts=context.options({'ebird_source':str(self.base)})
        with patch.object(context,'load',side_effect=AssertionError('Must not inspect cached package first')):
            self.assertEqual(context.find_ebird(self.base/'metadata.tsv',opts)['status'],'NEEDS_IMPORT')

class PickerRouteTests(unittest.TestCase):
    setUp=runner_tests.RunnerContextTests.setUp
    request=runner_tests.RunnerContextTests.request
    def test_actual_runner_dispatch_and_origin_guard(self):
        with patch.object(p,'roots',return_value=[{'id':'test','label':'Test','path':str(self.root)}]):
            code,data=self.request('POST','/api/context/files/roots',{},origin='http://127.0.0.1:8765')
            self.assertEqual(code,200);self.assertEqual(data['roots'][0]['id'],'test')
            for origin in [None,'https://evil.example']:
                code,_=self.request('POST','/api/context/files/roots',{},origin=origin);self.assertEqual(code,400)
            with patch.object(p,'native_available',return_value=False):
                code,data=self.request('POST','/api/context/files/native',{'kind':'ebird_download'},origin='http://127.0.0.1:8765')
                self.assertEqual(code,200);self.assertEqual(data['status'],'BROWSE')

if __name__=='__main__':unittest.main()
