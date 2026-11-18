"""Offline setup regression; run the real tiny-database check when BLAST exists."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FAKE = '''import hashlib, json, os, sys
from pathlib import Path
args=sys.argv[1:]
if args==['-version']:
 print('makeblastdb: fixture');sys.exit()
source=args[args.index('-in')+1];out=args[args.index('-out')+1]
if ' ' in str(Path(out).resolve()):
 print('BLAST Database error: Database memory map file error',file=sys.stderr);sys.exit(1)
if any(c.isspace() for c in str(Path(source).resolve())):
 print('BLAST options error: File '+source.split()[0]+' does not exist',file=sys.stderr);sys.exit(1)
assert Path(source).is_file()
assert args[args.index('-blastdb_version')+1]==os.environ['BLAST_DB_VERSION']
for suffix in ('.nin','.nhr','.nsq'):Path(out+suffix).write_text('fixture')
Path(os.environ['BLAST_CALL']).write_text(json.dumps({'args':args,'cwd':os.getcwd(),'input_sha256':hashlib.sha256(Path(source).read_bytes()).hexdigest()}))
'''


class BlastSetupTests(unittest.TestCase):
    def fixture(self, root, fake=True, script=None):
        app=root/'WINGS Workspace'/'application';(app/'scripts').mkdir(parents=True)
        shutil.copyfile(script or ROOT/'scripts/build_blast_db.sh',app/'scripts/build_blast_db.sh')
        archive=root/'shared cache'/'fluA_reference.fasta.zip';archive.parent.mkdir()
        with zipfile.ZipFile(archive,'w') as z:z.writestr('tiny.fasta','>fixture\n'+'ACGT'*100+'\n')
        env=dict(os.environ,WINGS_REFERENCE_ARCHIVE=str(archive),BLAST_DB_VERSION='4',
                 EXPECTED_ARCHIVE_SHA256=hashlib.sha256(archive.read_bytes()).hexdigest(),BLAST_CALL=str(root/'call.json'))
        if fake:
            binpath=root/'bin';binpath.mkdir()
            tool=binpath/'makeblastdb';tool.write_text('#!'+sys.executable+'\n'+FAKE);tool.chmod(0o755)
            checker=binpath/'blastdbcmd'
            checker.write_text('#!'+sys.executable+'''\nimport os, sys
from pathlib import Path
a=sys.argv[1:]; prefix=a[a.index('-db')+1]
assert ' ' not in str(Path(prefix).resolve())
assert all(Path(prefix+s).is_file() for s in ('.nin','.nhr','.nsq'))
sys.exit(int(os.environ.get('BLAST_CHECK_FAIL','0')))
''');checker.chmod(0o755)
            env['PATH']=str(binpath)+os.pathsep+env['PATH']
        result=subprocess.run(['bash',str(app/'scripts/build_blast_db.sh')],env=env,text=True,capture_output=True)
        return result,app

    def test_setup_in_space_containing_workspace_with_shared_archive(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);result,app=self.fixture(root)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            call=json.loads((root/'call.json').read_text())
            prefix=Path(call['args'][call['args'].index('-out')+1])
            self.assertNotIn(' ',str(prefix))
            self.assertEqual(prefix.name,'fluA_db')
            staged_input=Path(call['args'][call['args'].index('-in')+1])
            self.assertFalse(any(c.isspace() for c in str(staged_input)))
            self.assertEqual(staged_input.parent,prefix.parent)
            self.assertEqual(call['input_sha256'],hashlib.sha256((app/'resources/flu_db/fluA_reference.fasta').read_bytes()).hexdigest())
            self.assertFalse(staged_input.exists(), 'temporary input cleaned after success')
            self.assertFalse(prefix.parent.exists(), 'temporary build cleaned after success')
            self.assertTrue((app/'resources/flu_db/fluA_db.nin').is_file())
            with (app/'resources/flu_db/database_manifest.tsv').open() as f:
                row=next(csv.DictReader(f,delimiter='\t'))
            self.assertEqual(row['blast_db_version'],'4')

    def test_failed_verification_does_not_publish_database_or_manifest(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {'BLAST_CHECK_FAIL':'3'}):
            root=Path(temp); result,app=self.fixture(root)
            self.assertEqual(result.returncode,3,result.stdout+result.stderr)
            db=app/'resources/flu_db'
            self.assertFalse((db/'database_manifest.tsv').exists())
            self.assertFalse(list(db.glob('fluA_db.*')))
            call=json.loads((root/'call.json').read_text())
            prefix=Path(call['args'][call['args'].index('-out')+1])
            self.assertFalse(prefix.parent.exists(), 'temporary build cleaned after failure')
            self.assertTrue((root/'shared cache/fluA_reference.fasta.zip').exists())

    @unittest.skipUnless(shutil.which('makeblastdb') and shutil.which('blastn') and shutil.which('blastdbcmd'),'BLAST binaries unavailable here; exercised in container CI')
    def test_real_blast_build_and_query_under_space_containing_path(self):
        with tempfile.TemporaryDirectory() as temp:
            result,app=self.fixture(Path(temp),fake=False)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            db=app/'resources/flu_db'
            result=subprocess.run(['blastn','-query','fluA_reference.fasta','-db','fluA_db',
                '-outfmt','6','-dust','no'],cwd=db,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertTrue(result.stdout.strip())

    def test_workflow_blast_rule_resolves_query_before_changing_directory(self):
        class Q(str):
            def __format__(self,spec): return shlex.quote(self) if spec=='q' else str(self)
        with tempfile.TemporaryDirectory(prefix='wings query ') as temp:
            root=Path(temp);db=root/'reference cache';db.mkdir()
            (db/'fluA_db.nin').write_text('fixture')
            (root/'query.fa').write_text('>query\nACGT\n');(root/'flag').write_text('PASS\n')
            binpath=root/'bin';binpath.mkdir()
            tool=binpath/'blastn'
            tool.write_text('#!'+sys.executable+'''\nimport sys
from pathlib import Path
a=sys.argv[1:]
assert Path(a[a.index('-query')+1]).is_file()
assert Path(a[a.index('-db')+1]+'.nin').is_file()
assert ' ' not in a[a.index('-db')+1]
print('query\\tfixture\\ttitle\\t100\\t4\\t4\\t1\\t4\\t1\\t4\\t0\\t100')
''');tool.chmod(0o755)
            rule=(ROOT/'Snakefile').read_text().split('rule blastn:',1)[1].split('rule summarize_blast:',1)[0]
            shell=rule.split('r"""',1)[1].split('"""',1)[0]
            shell=shell.format(input=SimpleNamespace(fasta=Q('query.fa'),flag=Q('flag')),
                params=SimpleNamespace(database_prefix=Q(str(db/'fluA_db')),max_target_seqs=10,max_hsps=1),
                output=SimpleNamespace(txt=Q('result.tsv')),log=Q('blast.log'),threads=1)
            result=subprocess.run(['bash','-c',shell],cwd=root,env=dict(os.environ,PATH=str(binpath)+os.pathsep+os.environ['PATH']),capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr+(root/'blast.log').read_text())
            self.assertTrue((root/'result.tsv').read_text().startswith('query\tfixture'))


if __name__=='__main__': unittest.main()
