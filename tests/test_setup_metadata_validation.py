import importlib.util
import io
import json
from email.message import Message
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('setup_validation_runner',ROOT/'scripts/wings_local_runner.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class SetupMetadataTests(unittest.TestCase):
    def validate(self, text, samples=None):
        return runner.validate_setup_metadata({'metadata':text,'sample_ids':['A'] if samples is None else samples})

    def test_real_validator_accepts_iso_date_and_blank_optional_fields(self):
        for text in ['sample_id\tcollection_date\nA\t2024-02-29\n','sample_id\nA\n','\ufeffsample_id\tcollection_date\nA\t\n']:
            self.assertTrue(self.validate(text)['ok'])

    def test_invalid_dates_surface_original_line_field_and_value(self):
        for value in ['02/03/2026','2025-02-29','2026-11-25T08:00:00','2026-13-01']:
            result=self.validate('sample_id\tcollection_date\nA\t'+value+'\n')
            self.assertFalse(result['ok'])
            self.assertIn('line 2: collection_date',result['errors'][0])
            self.assertIn(value,result['errors'][0])

    def test_bad_coordinate_and_duplicate_sample_are_blocking(self):
        for text,needle in [('sample_id\tlatitude\nA\t91\n','latitude'),('sample_id\nA\nA\n','duplicate'),('sample_id\nB\n','missing')]:
            result=self.validate(text)
            self.assertFalse(result['ok']);self.assertIn(needle,' '.join(result['errors']))

    def test_warning_does_not_become_error(self):
        result=self.validate('sample_id\tbarcode\nA\tweird\n')
        self.assertTrue(result['ok']);self.assertTrue(result['warnings'])

    def test_missing_header_empty_and_invalid_request(self):
        for text in ['', 'host\nduck\n','sample_id\n']:
            self.assertFalse(self.validate(text,[])['ok'])
        for payload in [None, {'metadata':3}, {'metadata':'sample_id\nA\n','sample_ids':'A'}, {'metadata':'x'*(10*1024*1024+1)}]:
            with self.assertRaises(ValueError):runner.validate_setup_metadata(payload)

    def request(self,payload,origin=None):
        handler=object.__new__(runner.Handler)
        handler.path='/api/metadata/validate';handler.headers=Message()
        raw=json.dumps(payload).encode()
        handler.headers['Content-Length']=str(len(raw));handler.headers['Content-Type']='application/json';handler.headers['Host']='127.0.0.1:8765'
        if origin:handler.headers['Origin']=origin
        handler.rfile=io.BytesIO(raw);replies=[]
        handler.json_response=lambda value,status=200:replies.append((status,value))
        handler.do_POST();return replies[0]

    def test_route_validates_without_starting_jobs_or_creating_run(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(runner,'RUNS_ROOT',Path(tmp)),patch.object(runner.subprocess,'Popen') as process:
            code,result=self.request({'metadata':'sample_id\tcollection_date\nA\tbad\n','sample_ids':['A']},'http://127.0.0.1:8765')
            self.assertEqual(code,200);self.assertFalse(result['ok'])
            self.assertEqual(list(Path(tmp).iterdir()),[]);process.assert_not_called()
            self.assertNotIn('wings-metadata-check',str(result))

    def test_route_rejects_cross_origin(self):
        self.assertEqual(self.request({'metadata':'sample_id\nA\n'},'http://other.example')[0],403)

    def test_launch_config_rechecks_metadata_before_workflow_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            reads=directory/'inputs'/'reads';reads.mkdir(parents=True)
            (reads/'A.fastq.gz').write_bytes(b'fixture')
            (directory/'inputs'/'metadata.tsv').write_text('sample_id\tcollection_date\nA\t2026-02-30\n')
            with patch.object(runner,'run_dir',return_value=directory),patch.object(runner,'read_state',return_value={}),patch.object(runner.subprocess,'Popen') as process:
                with self.assertRaisesRegex(ValueError,'Metadata validation failed'):
                    runner.build_config('fixture')
                process.assert_not_called()
                self.assertFalse((directory/'config.yaml').exists())

    def test_health_exposes_only_credential_presence(self):
        handler=object.__new__(runner.Handler);handler.path='/api/health';replies=[]
        handler.json_response=lambda value,status=200:replies.append(value)
        with patch.object(runner,'runtime_environment',return_value={'NCBI_EMAIL':'private@example.org','EBIRDST_ACCESS_KEY':'SECRET-key'}),patch.object(runner,'storage_settings',return_value={}):
            handler.do_GET()
        self.assertTrue(replies[0]['ebirdst_key_configured'])
        self.assertTrue(replies[0]['phylodynamics_ready'])
        self.assertNotIn('SECRET-key',json.dumps(replies));self.assertNotIn('private@example.org',json.dumps(replies))

if __name__=='__main__':unittest.main()
