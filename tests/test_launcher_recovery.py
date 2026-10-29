import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock

PATH = Path(__file__).resolve().parents[1]/'scripts/wings_local_runner.py'

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        spec=importlib.util.spec_from_file_location('runner', PATH)
        self.r=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.r)
        self.tmp=tempfile.TemporaryDirectory()
        self.r.RUNS_ROOT=Path(self.tmp.name).resolve()
        self.directory=self.r.run_dir('run1')
        self.directory.mkdir()
        (self.directory/'attempts/a').mkdir(parents=True)
        self.log=self.directory/'attempts/a/snakemake.log'
        self.s=dict(status='running',pid=123,execution_config='/run1/execution_config.yaml',active_attempt='a',launcher_log='attempts/a/snakemake.log',attempts=[dict(attempt_id='a',status='running',log_path='attempts/a/snakemake.log')])
        self.r.write_state('run1', self.s)
        self.complete='[Wed Oct 28 18:53:42 2026]\nFinished jobid: 0 (Rule: all)\n954 of 954 steps (100%) done\n'
    def tearDown(self): self.tmp.cleanup()
    def recover(self, text, alive=False):
        self.log.write_text(text)
        with patch.object(self.r,'recorded_process_alive',return_value=alive):
            return self.r.reconcile_state('run1')
    def test_completed_orphan_updates_run_and_attempt_without_inventing_exit(self):
        s=self.recover(self.complete)
        self.assertEqual(s['status'],'complete')
        self.assertEqual(s['attempts'][0]['status'],'complete')
        self.assertIsNone(s['exit_code'])
        self.assertEqual(len(list(self.directory.glob('state.before-recovery*'))),1)
        self.r.reconcile_state('run1')
        self.assertEqual(len(list(self.directory.glob('state.before-recovery*'))),1)
    def test_active_process_is_untouched_even_with_completion_log(self):
        self.assertEqual(self.recover(self.complete,True),self.s)
    def test_uncertain_process_is_untouched(self):
        self.assertEqual(self.recover(self.complete,None),self.s)
    def test_failure(self):
        self.assertEqual(self.recover('WorkflowError:\nJob failed')['status'],'failed')
    def test_incomplete_log_is_interrupted(self):
        self.assertEqual(self.recover('10 of 100 steps (10%) done')['status'],'interrupted')
    def test_generic_100_percent_is_not_completion(self):
        self.assertEqual(self.recover('100 of 100 steps (100%) done')['status'],'interrupted')
    def test_previous_attempt_not_used(self):
        (self.directory/'snakemake.log').write_text(self.complete)
        self.assertEqual(self.recover('still working')['status'],'interrupted')
    def test_owned_exit_code_is_authoritative(self):
        process=Mock();process.poll.return_value=0
        self.r.PROCESSES['run1']=process
        s=self.r.reconcile_state('run1')
        self.assertEqual(s['status'],'complete');self.assertEqual(s['exit_code'],0)
    def test_reused_pid(self):
        with patch.object(self.r.subprocess,'run',return_value=Mock(returncode=0,stdout='S /usr/bin/other')):
            self.assertFalse(self.r.recorded_process_alive(self.s))
    def test_live_matching_command(self):
        with patch.object(self.r.subprocess,'run',return_value=Mock(returncode=0,stdout='S python snakemake --configfile /run1/execution_config.yaml')):
            self.assertTrue(self.r.recorded_process_alive(self.s))
    def test_missing_pid_is_not_automatically_declared_dead(self):
        self.assertIsNone(self.r.recorded_process_alive({}))
    def test_permission_or_ps_failure_is_unknown(self):
        with patch.object(self.r.subprocess,'run',return_value=Mock(returncode=2,stdout='')):
            self.assertIsNone(self.r.recorded_process_alive(self.s))

if __name__=='__main__':unittest.main()
