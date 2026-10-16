"""Status/attempt regressions using synthetic logs and mocked subprocesses."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch


class RunnerStatusTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "runner_status_test", Path(__file__).resolve().parents[1] / "scripts/wings_local_runner.py")
        self.runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.runner)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runner.RUNS_ROOT = Path(self.temp.name).resolve()

    def test_incomplete_completion_record_is_not_counted(self):
        log = Path(self.temp.name) / "scheduler.log"
        log.write_text("localrule sample_summary:\n    jobid: 1\nShell command: None\n"
                       "Finished jobid: 1 (Rule: sample_summary)")
        records, _ = self.runner.launcher_status_log(log)
        self.assertEqual(self.runner.stage_progress({"status": "running"}, records)["reporting"]["completed"], 0)
        with log.open("a") as handle:
            handle.write("\n")
        records, _ = self.runner.launcher_status_log(log)
        self.assertEqual(self.runner.stage_progress({"status": "running"}, records)["reporting"]["completed"], 1)

    def test_successful_retry_clears_current_job_failure(self):
        log = ("localrule sample_summary:\n    jobid: 1\nShell command: None\n"
               "Error in rule sample_summary:\n    jobid: 1\n"
               "localrule sample_summary:\n    jobid: 1\nShell command: None\n"
               "Finished jobid: 1 (Rule: sample_summary)\n")
        detail = self.runner.stage_progress({"status": "running"}, log)["reporting"]
        self.assertEqual(detail["failed_rules"], [])
        self.assertEqual(detail["completed"], 1)
        self.assertEqual(len(self.runner.failure_details(Path(self.temp.name), log)), 1)

    def test_retry_does_not_clear_another_job_failure(self):
        log = ("Error in rule sample_summary:\n    jobid: 2\n"
               "localrule sample_summary:\n    jobid: 1\nShell command: None\n"
               "Finished jobid: 1 (Rule: sample_summary)\n")
        self.assertEqual(self.runner.stage_progress({"status": "running"}, log)["reporting"]["status"], "failed")

    def prepare_failed_run(self):
        directory = self.runner.run_dir("test-run")
        directory.mkdir()
        self.runner.write_state("test-run", {"status": "failed", "sample_count": 3})
        return directory

    def test_resume_requires_saved_configuration(self):
        self.prepare_failed_run()
        with patch.object(self.runner.shutil, "which", return_value="synthetic-scheduler"), patch.object(self.runner.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(ValueError, "Saved execution_config"):
                self.runner.launch_attempt("test-run", resume=True)
            spawn.assert_not_called()

    def test_resume_preserves_configuration_and_prior_log(self):
        directory = self.prepare_failed_run()
        config = directory / "execution_config.yaml"
        config.write_text("synthetic: true\n")
        old_log = directory / "snakemake.log"
        old_log.write_text("prior attempt\n")
        process = Mock(pid=123)
        process.poll.return_value = None
        with patch.object(self.runner.shutil, "which", return_value="synthetic-scheduler"), patch.object(self.runner, "workflow_command", return_value=["synthetic-scheduler"]), patch.object(self.runner, "build_config") as build, patch.object(self.runner, "capture_attempt_provenance", side_effect=lambda attempt_dir, *_: attempt_dir / "attempt-provenance.json"), patch.object(self.runner.subprocess, "Popen", return_value=process) as spawn, patch.object(self.runner.threading, "Thread"):
            result = self.runner.launch_attempt("test-run", resume=True)
            try:
                build.assert_not_called()
                self.assertEqual(config.read_text(), "synthetic: true\n")
                self.assertEqual(old_log.read_text(), "prior attempt\n")
                state = self.runner.read_state("test-run")
                self.assertEqual(len(state["attempts"]), 2)
                self.assertEqual(state["attempts"][0]["attempt_id"], "legacy")
                self.assertEqual(state["active_attempt"], result["attempt_id"])
                with self.assertRaisesRegex(ValueError, "active launcher"):
                    self.runner.launch_attempt("test-run", resume=True)
                self.assertEqual(spawn.call_count, 1)
            finally:
                spawn.call_args.kwargs["stdout"].close()


if __name__ == "__main__":
    unittest.main()
