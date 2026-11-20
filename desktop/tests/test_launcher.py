"""Exercise the real shell launcher against an isolated, fake Docker CLI.

This validates orchestration and quoting; it does not claim Docker execution.
"""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FAKE = r'''#!/usr/bin/env python3
import json, os, sys, subprocess
from pathlib import Path
a=sys.argv[1:]
log=Path(os.environ['MOCK_STATE'])
s=json.loads(log.read_text()) if log.exists() else {'calls':[]}
s['calls'].append(a)
def save():log.write_text(json.dumps(s))
def out(value=''):save();print(value);sys.exit()
def fail():save();sys.exit(1)
if a[:2]==['--context','desktop-linux']:a=a[2:]
if a[0]=='context':out('unix:///mock/docker.sock')
if a[0]=='info':
 if a[-1]=='{{.Architecture}}':out(os.environ.get('MOCK_ENGINE_ARCH','arm64'))
 out('linux')
if a[:2]==['image','inspect']:
 if not a[-1].startswith('wings-desktop-runtime:'):
  if a[2:4]!=['--platform','linux/amd64']:fail()
  record=s.get('tools',{}).get(a[-1])
  if not record:fail()
  out(record)
 if 'image' not in s:fail()
 out(s['image'])
if a[0]=='pull':
 if a[1:3]!=['--platform','linux/amd64']:fail()
 if os.environ.get('MOCK_PULL_FAIL'):
  print('registry unavailable',file=sys.stderr);fail()
 ref=a[-1]
 if ref=='staphb/vadr:1.7':record='linux/amd64|sha256:fixture-vadr|staphb/vadr@sha256:fixture-vadr-manifest '
 elif ref=='docker.io/cdcgov/irma@sha256:96357063a678fd5887598b093a53373ae286a2eb0155520feae8b72904bcdda8':
  record='linux/amd64|sha256:fixture-irma|'+ref+' '
 else:fail()
 if os.environ.get('MOCK_PULL_ARM64'):record=record.replace('linux/amd64','linux/arm64')
 s.setdefault('tools',{})[ref]=record;out()
if a[0]=='tag':
 if os.environ.get('MOCK_TAG_FAIL'):fail()
 record=next((r for r in s.get('tools',{}).values() if r.split('|')[1]==a[1]),None)
 if not record:fail()
 s['tools'][a[2]]=record;out()
if a[0]=='build':
 if os.environ.get('MOCK_REQUIRE_CREDENTIAL_HELPER'):
  subprocess.run(['docker-credential-desktop','get'],input=b'fixture-registry\n',check=True)
 s['image']=a[a.index('--label')+1].split('=',1)[1];out()
if a[0]=='inspect':
 if 'container' not in s:fail()
 fmt=a[a.index('--format')+1] if '--format' in a else ''
 if 'workspace' in fmt:out(s['container']['workspace'])
 if 'source' in fmt:out(s['container']['source'])
 if 'runtime' in fmt:out(s['container']['runtime'])
 if 'folders' in fmt:out(s['container']['folders'])
 if 'Running' in fmt:out('true' if s['container']['running'] else 'false')
 out('{}')
if a[0]=='run':
 if 'docker-check' in a and os.environ.get('MOCK_CONTROLLER_DOCKER_FAIL'):fail()
 if '-d' in a:
  labels=[a[i+1] for i,v in enumerate(a) if v=='--label']
  s['container']={'running':True}
  for l in labels:
   k,v=l.split('=',1);s['container'][k.rsplit('.',1)[-1]]=v
 out('mock-container')
if a[0]=='exec':
 s['exec_input']=sys.stdin.read();out('Ollama is reachable and the selected model is installed.')
if a[0]=='port':out('127.0.0.1:49123')
if a[0]=='stop':s['container']['running']=False;out()
if a[0]=='rm':s.pop('container',None);out()
fail()
'''


class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.home = self.root / 'home'; self.home.mkdir()
        self.bin = self.home / '.docker/bin'; self.bin.mkdir(parents=True)
        fake = self.bin / 'docker'; fake.write_text(FAKE.replace('#!/usr/bin/env python3', '#!' + sys.executable, 1)); fake.chmod(0o755)
        curl = self.bin / 'curl'; curl.write_text('#!/bin/sh\nexit 0\n'); curl.chmod(0o755)
        self.resources = self.root / 'Application with spaces'; self.resources.mkdir()
        shutil.copy(ROOT / 'desktop.sh', self.resources / 'desktop.sh')
        shutil.copy(ROOT / 'prepare-images.sh', self.resources / 'prepare-images.sh')
        (self.resources / 'runtime').mkdir()
        archive = self.resources / 'source.tar.gz'
        import io, tarfile
        with tarfile.open(archive, 'w:gz') as tar:
            info = tarfile.TarInfo('resources/placeholder'); info.size = 1
            tar.addfile(info, io.BytesIO(b'x'))
        (self.resources / 'source.sha256').write_text(hashlib.sha256(archive.read_bytes()).hexdigest())
        (self.resources / 'runtime.sha256').write_text('a' * 64)
        self.workspace = self.root / "WINGS user's workspace"
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin)+os.pathsep+os.environ['PATH'],
                        MOCK_STATE=str(self.root / 'docker-state.json'), WINGS_DOCKER_BIN=str(fake))
        self.env.pop('DOCKER_HOST', None)

    def tearDown(self):
        self.temp.cleanup()

    def command(self, action='launch', workspace=None, email='test@example.org'):
        return subprocess.run(['bash', str(self.resources / 'desktop.sh'), action,
            str(workspace or self.workspace), email], env=self.env, text=True, capture_output=True)

    def test_start_reopen_and_stop_preserve_data(self):
        import json
        result = self.command()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        token = self.workspace / '.desktop/session'
        self.assertEqual(len(token.read_text().strip()), 64)
        self.assertEqual(token.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.workspace / '.desktop/container.env').exists())
        self.assertEqual(self.command('url').returncode, 0)
        result = self.command()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = json.loads((self.root / 'docker-state.json').read_text())['calls']
        starts = [c for c in calls if 'run' in c and '-d' in c]
        self.assertEqual(len(starts), 1)
        self.assertIn('127.0.0.1::8766', starts[0])
        self.assertIn('type=bind,source='+str(self.workspace)+',target='+str(self.workspace), starts[0])
        self.assertEqual(self.command('stop').returncode, 0)
        self.assertTrue((self.workspace / 'runs').exists())

    def test_remote_daemon_rejected(self):
        self.env['DOCKER_HOST'] = 'tcp://remote.example:2375'
        self.assertNotEqual(self.command().returncode, 0)

    def test_unsafe_mount_delimiter_rejected(self):
        self.assertNotEqual(self.command(workspace=self.root / 'bad,path').returncode, 0)

    def test_corrupt_archive_rejected(self):
        (self.resources / 'source.tar.gz').write_bytes(b'corrupt')
        result = self.command()
        self.assertEqual(result.returncode, 16, result.stderr)

    def test_reference_archive_reused_after_failed_older_setup(self):
        import json
        previous = self.workspace / 'releases/older/app/resources/fluA_reference.fasta.zip'
        previous.parent.mkdir(parents=True)
        previous.write_bytes(b'fixture-reference-archive')
        result = self.command()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        cached = self.workspace / 'cache/fluA_reference.fasta.zip'
        self.assertEqual(cached.read_bytes(), previous.read_bytes())
        calls = json.loads((self.root / 'docker-state.json').read_text())['calls']
        prepare = next(c for c in calls if 'prepare' in c)
        self.assertIn('WINGS_REFERENCE_ARCHIVE=' + str(cached), prepare)

    def check_finder_launch(self, helper_dir):
        helper = helper_dir / 'docker-credential-desktop'
        helper.write_text('#!/bin/sh\nprintf "helper found" > "$MOCK_HELPER_MARKER"\n')
        helper.chmod(0o755)
        config = self.home / '.docker/config.json'
        original = b'{"credsStore":"desktop","auths":{"fixture-registry":{}}}\n'
        config.write_bytes(original)
        marker = self.root / 'helper-called'
        self.env.update(PATH='/usr/bin:/bin:/usr/sbin:/sbin',
                        MOCK_REQUIRE_CREDENTIAL_HELPER='1', MOCK_HELPER_MARKER=str(marker))
        result = self.command()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(marker.read_text(), 'helper found')
        self.assertEqual(config.read_bytes(), original)

    def test_finder_path_finds_helper_next_to_docker(self):
        self.check_finder_launch(self.bin)

    def test_symlinked_cli_finds_helper_in_docker_app(self):
        app_bin = self.root / 'Custom Applications/Docker.app/Contents/Resources/bin'
        app_bin.mkdir(parents=True)
        (self.bin / 'docker').rename(app_bin / 'docker')
        (self.bin / 'docker').symlink_to(app_bin / 'docker')
        self.check_finder_launch(app_bin)


if __name__ == '__main__':
    unittest.main()
