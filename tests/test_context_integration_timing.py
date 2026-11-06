"""Check the integration fixture against the clock-skew failure seen on macOS."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from integration_context_setup import write_changed_seed
from prepare_public_genotype_snapshot import prepare


class IntegrationTimingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.seed=self.root/'seed.json';self.output=self.root/'output.json'
        self.data={'schema_version':'wings.genotype-frequencies.v1','unit':'SRA run','has_metadata':True,
                   'audit':{'included_runs':0,'assigned_runs':0},'groups':[],
                   'context_scope':{'reason':'initial synthetic snapshot'}}
        self.seed.write_text(json.dumps(self.data)+'\n')
        prepare(self.seed,self.output,prepared=True)
    def test_changed_input_uses_real_time_and_rebuilt_output_is_not_older(self):
        previous=self.output.read_bytes()
        self.data['context_scope']['reason']='updated synthetic snapshot'
        write_changed_seed(self.seed,self.output,self.data)
        self.assertEqual(self.output.read_bytes(),previous,'Fixture must not rewrite the output contents')
        self.assertNotEqual(self.seed.read_bytes(),previous)
        self.assertGreater(self.seed.stat().st_mtime_ns,self.output.stat().st_mtime_ns)
        self.assertLessEqual(self.seed.stat().st_mtime_ns,time.time_ns())
        prepare(self.seed,self.output,prepared=True)
        self.assertEqual(self.output.read_bytes(),self.seed.read_bytes())
        self.assertGreaterEqual(self.output.stat().st_mtime_ns,self.seed.stat().st_mtime_ns)
    def test_already_old_output_is_not_moved_forward(self):
        old=time.time_ns()-60_000_000_000
        os.utime(self.output,ns=(old,old))
        before=self.output.stat().st_mtime_ns
        self.data['context_scope']['reason']='changed'
        write_changed_seed(self.seed,self.output,self.data)
        self.assertEqual(self.output.stat().st_mtime_ns,before)
        self.assertLessEqual(self.seed.stat().st_mtime_ns,time.time_ns())


if __name__=='__main__':unittest.main()
