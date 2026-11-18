"""Run actual wrapper and child processes with deliberately awkward paths."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/run_porechop_abi.py'
TOOL = '''
import sys,shutil,os
from pathlib import Path
from types import SimpleNamespace
from . import abinitio
def main():
    a=sys.argv
    args=SimpleNamespace(input=a[a.index('-i')+1], threads=int(a[a.index('--threads')+1]))
    scratch=Path(a[a.index('-tmp')+1])
    assert not any(c.isspace() for c in str(scratch))
    conf=Path(__file__).parent/'config with spaces.config'
    assert conf.read_text()=='fixture config'
    abinitio.execApproxCounter(args, str(scratch/'counts'), str(conf), int(os.environ.get('FIXTURE_RUNS','10')), 1)
    if os.environ.get('FIXTURE_NO_OUTPUT'): return
    shutil.copyfile(args.input,a[a.index('-o')+1])
'''
ABI = '''
import subprocess
from pathlib import Path
def execApproxCounter(args,out_file,conf_file,mr,v,print_dest=None):
    command=str(Path(__file__).parent/'approx_counter')+' '+args.input
    subprocess.check_call(command.split())
'''
COUNTER = '''#!/usr/bin/env python3
import os,sys,time
from pathlib import Path
a=sys.argv[1:]
assert Path(a[0]).read_bytes().startswith(b'@fixture')
assert Path(a[a.index('--config')+1]).read_text()=='fixture config'
if os.environ.get('FIXTURE_FAIL'): sys.exit(7)
with Path(a[a.index('-o')+1]).open('x') as f: f.write('counts')
time.sleep(0.05)
'''


class PathTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='WINGS Workspace ')
        self.root=Path(self.temp.name)
        self.package=self.root/'site packages'/'porechop_abi'
        self.package.mkdir(parents=True)
        for name,content in [('__init__.py',''),('version.py',"__version__='0.5.1'"),
                             ('porechop_abi.py',TOOL),('abinitio.py',ABI),
                             ('approx_counter',COUNTER),('config with spaces.config','fixture config')]:
            (self.package/name).write_text(content)
        (self.package/'approx_counter').chmod(0o755)
        self.source=self.root/"reads 'with' spaces ; literal.fastq"
        self.source.write_bytes(b'@fixture\nACGT\n+\nIIII\n')
        self.dest=self.root/'results with spaces'/'trimmed.fastq'
        self.env=os.environ.copy()
        self.env['PYTHONPATH']=str(self.package.parent)

    def tearDown(self):
        for record in self.root.rglob('*.porechop-provenance.json'):
            scratch=Path(json.loads(record.read_text())['temporary_directory'])
            if scratch.is_dir():shutil.rmtree(scratch)
        self.temp.cleanup()

    def run_wrapper(self,dest=None,**env):
        return subprocess.run([sys.executable,str(SCRIPT),'--threads','1','--input',str(self.source),
            '--output',str(dest or self.dest)],env={**self.env,**env},capture_output=True,text=True,timeout=15)

    def record(self,dest=None):
        dest=dest or self.dest
        return json.loads(dest.with_name(dest.name+'.porechop-provenance.json').read_text())

    def test_spaces_quotes_and_semicolons_reach_counter_unchanged(self):
        before=(self.package/'abinitio.py').read_bytes()
        result=self.run_wrapper()
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(self.dest.read_bytes(),self.source.read_bytes())
        record=self.record(); command=record['counter_commands'][0]
        self.assertEqual(command[0],str(self.package/'approx_counter'))
        self.assertEqual(command[1],str(self.source))
        self.assertEqual(command[command.index('--config')+1],str(self.package/'config with spaces.config'))
        self.assertEqual(command[-2:],['-mr','10'])
        self.assertEqual(record['status'],'complete')
        self.assertFalse(Path(record['temporary_directory']).exists())
        self.assertEqual((self.package/'abinitio.py').read_bytes(),before)

    def test_unwrapped_fixture_reproduces_space_split_failure(self):
        code = "from porechop_abi import abinitio; from types import SimpleNamespace; import sys; abinitio.execApproxCounter(SimpleNamespace(input=sys.argv[1]),'', '',10,1)"
        result = subprocess.run([sys.executable,'-c',code,str(self.source)],env=self.env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('FileNotFoundError',result.stderr)
        self.assertIn("'/tmp/WINGS'",result.stderr)

    def test_single_batch_does_not_add_multirun_argument(self):
        result=self.run_wrapper(FIXTURE_RUNS='1')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertNotIn('-mr',self.record()['counter_commands'][0])

    def test_concurrent_samples_use_different_scratch(self):
        outputs=[self.root/f'output {i}'/'trimmed.fastq' for i in range(2)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(self.run_wrapper,outputs))
        for result in results:self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertNotEqual(self.record(outputs[0])['temporary_directory'],self.record(outputs[1])['temporary_directory'])

    def test_counter_failure_is_not_reported_as_success(self):
        result=self.run_wrapper(FIXTURE_FAIL='1')
        self.assertNotEqual(result.returncode,0)
        self.assertFalse(self.dest.exists())
        self.assertEqual(self.record()['status'],'failed')
        self.assertTrue(Path(self.record()['temporary_directory']).exists())

    def test_missing_output_is_a_failure(self):
        self.assertNotEqual(self.run_wrapper(FIXTURE_NO_OUTPUT='1').returncode,0)
        self.assertEqual(self.record()['status'],'failed')

    def test_existing_output_preserved(self):
        self.dest.parent.mkdir();self.dest.write_text('keep')
        self.assertNotEqual(self.run_wrapper().returncode,0)
        self.assertEqual(self.dest.read_text(),'keep')

    def test_unknown_version_and_missing_counter_rejected(self):
        (self.package/'version.py').write_text("__version__='9.9.9'")
        self.assertNotEqual(self.run_wrapper().returncode,0)
        (self.package/'version.py').write_text("__version__='0.5.1'")
        (self.package/'approx_counter').unlink()
        self.assertNotEqual(self.run_wrapper().returncode,0)


if __name__=='__main__':unittest.main()
