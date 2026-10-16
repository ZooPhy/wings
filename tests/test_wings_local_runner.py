from __future__ import annotations

import importlib.util
import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "wings_local_runner.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("wings_local_runner", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_strip_fastq_supported_extensions():
    runner = load_runner()
    assert runner.strip_fastq("sample.fastq.gz") == ("sample", ".fastq.gz")
    assert runner.strip_fastq("sample.fq") == ("sample", ".fq")


def test_stage_inference_does_not_complete_earlier_stages_on_later_activity():
    runner = load_runner()
    state = {"status": "running"}
    log = "rule porechop:\nrule irma:\nrule medaka_inference:\n"
    stages = runner.infer_stages(state, log)
    assert stages["read_qc"] == "running"
    assert stages["assembly"] == "running"
    assert stages["polishing"] == "running"
    assert stages["reporting"] == "waiting"


def test_stage_inference_accepts_indented_and_timestamped_rules():
    runner = load_runner()
    state = {"status": "running"}
    log = (
        "[Fri Oct  2 15:08:32 2026]\n"
        "    rule porechop:\n"
        "[Fri Oct  2 15:09:10 2026] rule irma:\n"
    )

    stages = runner.infer_stages(state, log)

    assert stages["read_qc"] == "running"
    assert stages["assembly"] == "running"
    assert stages["polishing"] == "waiting"


def test_setup_and_archival_rules_are_assigned_to_their_own_stages():
    runner = load_runner()
    state = {"status": "running"}
    log = (
        "rule validate_metadata:\n"
        "rule resolve_medaka_model:\n"
        "rule archive_replay_inputs:\n"
    )

    stages = runner.infer_stages(state, log)

    assert stages["inputs"] == "running"
    assert stages["read_qc"] == "running"
    assert stages["polishing"] == "waiting"
    assert stages["reporting"] == "running"


def job_log(rule, job_id, complete=False, checkpoint=False):
    kind = "localcheckpoint" if checkpoint else "localrule"
    text = f"{kind} {rule}:\n    input: synthetic\n    jobid: {job_id}\nShell command: None\n"
    if complete:
        text += f"Finished jobid: {job_id} (Rule: {rule})\n"
    return text


def test_twelve_sample_progress_counts_irma_and_overlapping_stages():
    runner = load_runner()
    log = "Job stats:\njob count\n--- ---\nirma 12\nmedaka_inference 12\ntotal 24\n\n"
    log += "".join(job_log("irma", i, complete=True) for i in range(3))
    log += job_log("irma", 3) + job_log("medaka_inference", 20, complete=True)
    progress = runner.stage_progress({"status": "running", "sample_count": 12}, log)
    assert progress["assembly"]["status"] == "running"
    assert progress["assembly"]["irma_completed"] == 3
    assert progress["assembly"]["irma_expected"] == 12
    assert progress["assembly"]["active"] == 1
    assert progress["polishing"]["status"] == "partial"
    assert progress["polishing"]["completed"] == 1


def test_counts_are_deduplicated_and_retries_remain_active():
    runner = load_runner()
    log = "Job stats:\nporechop 1\ntotal 1\n\n" + job_log("porechop", 1, complete=True)
    log += "Finished jobid: 1 (Rule: porechop)\n"
    assert runner.stage_progress({"status": "running"}, log)["read_qc"]["completed"] == 1
    log += job_log("porechop", 1)
    detail = runner.stage_progress({"status": "running"}, log)["read_qc"]
    assert detail["completed"] == 0
    assert detail["active"] == 1
    assert detail["status"] == "running"


def test_checkpoint_totals_remain_provisional_until_success():
    runner = load_runner()
    log = "Job stats:\nnormalize_irma_outputs 1\nmedaka_inference 1\ntotal 2\n\n"
    log += job_log("normalize_irma_outputs", 1, complete=True, checkpoint=True)
    log += job_log("medaka_inference", 2, complete=True)
    progress = runner.stage_progress({"status": "running"}, log)
    assert progress["assembly"]["completed"] == 1
    assert progress["assembly"]["expected"] is None
    assert progress["polishing"]["status"] == "partial"
    assert progress["polishing"]["totals_provisional"] is True
    assert runner.infer_stages({"status": "complete"}, log)["polishing"] == "complete"


def test_failure_is_attributed_to_the_failed_rule_not_the_furthest_stage():
    runner = load_runner()
    log = job_log("sample_summary", 1, complete=True)
    log += job_log("ebirdst_phenology", 2) + "Error in rule ebirdst_phenology:\n"
    detail = runner.stage_progress({"status": "failed"}, log)
    assert detail["surveillance"]["status"] == "failed"
    assert detail["surveillance"]["failed_rules"] == ["ebirdst_phenology"]
    assert detail["reporting"]["status"] == "partial"
    assert detail["surveillance"]["active"] == 0


def test_stopped_jobs_are_interrupted_without_inventing_a_failed_stage():
    runner = load_runner()
    detail = runner.stage_progress({"status": "stopped"}, job_log("irma", 1))
    assert detail["assembly"]["status"] == "interrupted"
    assert detail["polishing"]["status"] == "waiting"


def test_missing_counts_never_prove_stage_completion_and_optional_stages_are_skipped():
    runner = load_runner()
    log = job_log("irma", 1, complete=True)
    detail = runner.stage_progress({"status": "running"}, log)["assembly"]
    assert detail["expected"] is None
    assert detail["status"] == "partial"
    assert runner.infer_stages({"status": "complete", "options": {"phylogeny": False}}, log)["phylogeny"] == "skipped"
    assert runner.infer_stages({"status": "complete"}, "Nothing to be done.\n")["assembly"] == "complete"


def test_resumed_attempt_counts_do_not_claim_all_samples_completed():
    runner = load_runner()
    log = "Job stats:\nirma 3\ntotal 3\n\n" + job_log("irma", 1, complete=True)
    detail = runner.stage_progress({"status": "running", "sample_count": 12}, log)["assembly"]
    assert detail["irma_expected"] == 3
    assert detail["irma_completed"] == 1


def test_enriched_state_exposes_attempt_scope_without_modifying_state(tmp_path, monkeypatch):
    runner = load_runner()
    monkeypatch.setattr(runner, "RUNS_ROOT", tmp_path)
    make_run(runner, "synthetic-run", "failed")
    original = runner.state_path("synthetic-run").read_bytes()
    (runner.run_dir("synthetic-run") / "snakemake.log").write_text(job_log("irma", 1, complete=True))
    # A separately written continuation must not silently replace launcher state.
    (runner.run_dir("synthetic-run") / "snakemake-resume-test.log").write_text(job_log("irma", 2))
    data = runner.enriched_state("synthetic-run")
    assert data["status"] == "failed"
    assert data["status_scope"] == "launcher_attempt"
    assert data["stage_progress"]["assembly"]["irma_completed"] == 1
    assert runner.state_path("synthetic-run").read_bytes() == original


def test_log_milestones_measure_gaps_without_assuming_timezone():
    runner = load_runner()
    events = runner.log_milestones(
        "Command: synthetic test\n"
        "[2026-10-09 10:00:00]\tTEST started\n"
        "[2026-10-09 10:01:15]\tTEST input complete\n"
        "[2026-10-09 10:05:59]\tTEST step complete\n"
    )
    assert [event["seconds_since_previous"] for event in events] == [None, 75, 284]
    assert events[-1]["message"] == "TEST step complete"
    assert events[-1]["timestamp"] == "2026-10-09 10:05:59"


def test_log_milestones_invalid_dates_and_clock_reversal():
    runner = load_runner()
    events = runner.log_milestones(
        "[2026-10-09 10:05:00] first\n"
        "[2026-99-99 10:06:00] invalid\n"
        "[2026-10-09 10:04:00] clock changed\n"
        "[2026-10-09 10:04:10] last\n"
    )
    assert [event["seconds_since_previous"] for event in events] == [None, None, 10]


def test_log_milestones_space_padded_hours_across_midnight():
    runner = load_runner()
    events = runner.log_milestones(
        "[2026-10-08 23:59:50]\tTEST before midnight\n"
        "[2026-10-09  0:00:10]\tTEST after midnight\n"
        "[2026-10-09  1:02:03]\tTEST next milestone\n"
    )
    assert [event["seconds_since_previous"] for event in events] == [None, 20, 3713]
    assert events[1]["timestamp"] == "2026-10-09 00:00:10"
    assert events[2]["timestamp"] == "2026-10-09 01:02:03"


def test_log_milestones_copied_whitespace_and_completion():
    runner = load_runner()
    events = runner.log_milestones(
        "[2026-10-09\u00a0 1:55:47]\tTEST started\n"
        "[2026-10-09\t9:00:00]\tTEST finished!\n"
        "ESCAPE_STATUS=IRMA_COMPLETED\n"
    )
    assert len(events) == 2
    assert events[-1]["message"] == "TEST finished!"
    assert events[-1]["timestamp"] == "2026-10-09 09:00:00"


def test_progress_is_read_only_and_ignores_partial_lines(tmp_path, monkeypatch):
    runner = load_runner()
    monkeypatch.setattr(runner, "RUNS_ROOT", tmp_path)
    make_run(runner, "synthetic-run", "running")
    directory = runner.run_dir("synthetic-run")
    path = directory / "results" / "sample-one" / "irma" / "irma.log"
    path.parent.mkdir(parents=True)
    content = b"[2026-10-09 10:00:00] TEST started\n[2026-10-09 10:01:00] still being written"
    path.write_bytes(content)
    os.utime(path, (1000, 1000))
    original_state = runner.state_path("synthetic-run").read_bytes()
    row = runner.enriched_state("synthetic-run")["irma_progress"][0]
    assert row["sample_id"] == "sample-one"
    assert row["last_modified"] == "1970-01-01T00:16:40+00:00"
    assert row["log_size_bytes"] == len(content)
    assert len(row["recent_milestones"]) == 1
    assert path.read_bytes() == content
    assert runner.state_path("synthetic-run").read_bytes() == original_state
    path.write_bytes(content + b"\n")
    row = runner.enriched_state("synthetic-run")["irma_progress"][0]
    assert row["recent_milestones"][-1]["seconds_since_previous"] == 60


def test_progress_handles_missing_empty_and_truncated_logs(tmp_path, monkeypatch):
    runner = load_runner()
    assert runner.irma_log_progress(tmp_path) == []
    path = tmp_path / "results" / "sample-one" / "irma" / "irma.log"
    path.parent.mkdir(parents=True)
    path.write_text("")
    assert runner.irma_log_progress(tmp_path)[0]["recent_milestones"] == []
    path.write_text("x" * 300 + "\n" + "".join(
        f"[2026-10-09 10:00:{i:02d}] event {i}\n" for i in range(30)
    ))
    row = runner.irma_log_progress(tmp_path)[0]
    assert len(row["recent_milestones"]) == 20
    assert row["recent_milestones"][0]["seconds_since_previous"] == 1
    assert row["earlier_milestones_omitted"] is True
    monkeypatch.setattr(runner, "PROGRESS_LOG_BYTES", 200)
    row = runner.irma_log_progress(tmp_path)[0]
    assert row["recent_milestones"][-1]["message"] == "event 29"
    assert row["recent_milestones"][0]["seconds_since_previous"] is None
    assert row["earlier_milestones_omitted"] is True


def test_progress_does_not_follow_logs_outside_run(tmp_path):
    runner = load_runner()
    directory = tmp_path / "run"
    path = directory / "results" / "sample-one" / "irma" / "irma.log"
    path.parent.mkdir(parents=True)
    outside = tmp_path / "outside.log"
    outside.write_text("[2026-10-09 10:00:00] external data\n")
    path.symlink_to(outside)
    assert runner.irma_log_progress(directory) == []



@contextmanager
def running_server(runner):
    server = runner.ThreadingHTTPServer(("127.0.0.1", 0), runner.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def fetch(url):
    try:
        with urlopen(url, timeout=5) as response:
            return response.status, response.headers, response.read()
    except HTTPError as error:
        return error.code, error.headers, error.read()


def make_run(runner, run_id, status, bundle=None):
    directory = runner.run_dir(run_id)
    (directory / "results").mkdir(parents=True)

    runner.write_state(
        run_id,
        {
            "format": "WINGS_LOCAL_RUN",
            "schema_version": 1,
            "run_id": run_id,
            "name": "Test WINGS run",
            "status": status,
        },
    )

    if bundle is not None:
        runner.bundle_path(run_id).write_text(
            json.dumps(bundle),
            encoding="utf-8",
        )


def test_bundle_endpoint_serves_only_completed_run_bundle(tmp_path, monkeypatch):
    runner = load_runner()
    monkeypatch.setattr(runner, "RUNS_ROOT", (tmp_path / "runs").resolve())
    runner.RUNS_ROOT.mkdir(parents=True)

    bundle = {
        "format": "WINGS_REPORT_BUNDLE",
        "version": 1,
        "run_summary": {"html": "<h1>Run summary</h1>"},
        "samples": {},
    }

    make_run(runner, "complete-run", "complete", bundle)
    make_run(runner, "running-run", "running", bundle)
    make_run(runner, "missing-bundle-run", "complete")

    with running_server(runner) as base_url:
        status, headers, body = fetch(
            f"{base_url}/api/runs/complete-run/bundle"
        )
        assert status == 200
        assert headers["Content-Type"] == "application/json; charset=utf-8"
        assert headers["Cache-Control"] == "no-store"
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert json.loads(body) == bundle

        status, _, body = fetch(
            f"{base_url}/api/runs/running-run/bundle"
        )
        assert status == 409
        assert json.loads(body)["error"] == (
            "Run results are not available until the run is complete"
        )

        status, _, body = fetch(
            f"{base_url}/api/runs/missing-bundle-run/bundle"
        )
        assert status == 404
        assert json.loads(body)["error"] == (
            "WINGS report bundle is not available"
        )

        status, _, body = fetch(
            f"{base_url}/api/runs/unknown-run/bundle"
        )
        assert status == 404
        assert json.loads(body)["error"] == "Unknown run"


def test_bundle_endpoint_rejects_path_traversal(tmp_path, monkeypatch):
    runner = load_runner()
    monkeypatch.setattr(runner, "RUNS_ROOT", (tmp_path / "runs").resolve())
    runner.RUNS_ROOT.mkdir(parents=True)

    with running_server(runner) as base_url:
        status, _, body = fetch(
            f"{base_url}/api/runs/%2E%2E%2Foutside/bundle"
        )

    assert status == 400
    assert json.loads(body)["error"] == "Invalid run ID"


def test_execution_limits_default_to_serial_and_keep_core_capacity_separate():
    runner = load_runner()
    assert runner.execution_limits({}) == (1, 1)
    assert runner.execution_limits({"cores": 8}) == (8, 1)
    assert runner.execution_limits({"cores": 8, "max_parallel_jobs": 2}) == (8, 2)
    assert runner.execution_limits({"cores": 0, "max_parallel_jobs": 999}) == (1, 64)


def test_workflow_command_keeps_legacy_runs_serial_without_dropping_resume_flags():
    runner = load_runner()
    config_path = Path("/tmp/run config.yaml")
    command = runner.workflow_command("/tools/snakemake", config_path, {"cores": 8})
    assert command[command.index("--cores") + 1] == "8"
    assert command[command.index("--resources") + 1] == "wings_task_slots=1"
    assert command[command.index("--default-resources") + 1] == "wings_task_slots=1"
    assert command[command.index("--set-resource-scopes") + 1] == "wings_task_slots=global"
    assert command[command.index("--configfile") + 1] == str(config_path)
    assert "--rerun-incomplete" in command
    assert "--use-conda" in command
    parallel = runner.workflow_command("snakemake", config_path, {"cores": 8, "max_parallel_jobs": 3})
    assert parallel[parallel.index("--resources") + 1] == "wings_task_slots=3"


def test_created_run_persists_separate_cpu_and_task_limits(tmp_path, monkeypatch):
    from urllib.request import Request

    runner = load_runner()
    monkeypatch.setattr(runner, "RUNS_ROOT", (tmp_path / "runs").resolve())
    with running_server(runner) as base_url:
        for payload, expected in [({}, (1, 1)), ({"cores": 8}, (8, 1)),
                                  ({"cores": 8, "max_parallel_jobs": 2}, (8, 2))]:
            request = Request(base_url + "/api/runs", data=json.dumps(payload).encode(),
                              headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=5) as response:
                assert response.status == 201
                created = json.loads(response.read())
            state = runner.read_state(created["run_id"])
            assert (state["cores"], state["max_parallel_jobs"]) == expected


def test_start_uses_persisted_task_limit_for_the_subprocess(tmp_path, monkeypatch):
    from urllib.request import Request

    runner = load_runner()
    monkeypatch.setattr(runner, "RUNS_ROOT", (tmp_path / "runs").resolve())
    make_run(runner, "serial-run", "created")
    state = runner.read_state("serial-run")
    state.update(cores=8, max_parallel_jobs=1)
    runner.write_state("serial-run", state)
    config_path = tmp_path / "execution_config.yaml"
    config_path.write_text("synthetic: true\n")
    captured = []

    class Process:
        pid = 123

    def popen(command, **kwargs):
        captured.append(command)
        return Process()

    def wait(run_id, process, handle):
        handle.close()

    monkeypatch.setattr(runner.shutil, "which", lambda _: "/tools/snakemake")
    monkeypatch.setattr(runner, "build_config", lambda _: (config_path, 5))
    monkeypatch.setattr(runner.subprocess, "Popen", popen)
    monkeypatch.setattr(
        runner, "capture_attempt_provenance",
        lambda attempt_dir, *_: attempt_dir / "attempt-provenance.json",
    )
    monkeypatch.setattr(runner, "wait_for_process", wait)
    with running_server(runner) as base_url:
        with urlopen(Request(base_url + "/api/runs/serial-run/start", data=b"", method="POST"), timeout=5) as response:
            assert response.status == 200
    assert len(captured) == 1
    assert captured[0][captured[0].index("--cores") + 1] == "8"
    assert captured[0][captured[0].index("--resources") + 1] == "wings_task_slots=1"
    saved = runner.read_state("serial-run")
    assert saved["sample_count"] == 5
    assert saved["command"] == captured[0]


def test_serial_task_resource_prevents_overlapping_single_core_jobs(tmp_path, monkeypatch):
    import shutil
    import subprocess
    from unittest import SkipTest

    executable = shutil.which("snakemake")
    if executable is None:
        raise SkipTest("Snakemake is required for the scheduling integration check")
    runner = load_runner()
    monkeypatch.setattr(runner, "REPO_ROOT", tmp_path)
    config_path = tmp_path / "execution_config.yaml"
    config_path.write_text("{}\n")
    (tmp_path / "Snakefile").write_text('''
import os
import time
from pathlib import Path

rule all:
    input: "a.done", "b.done", "c.done"

rule work:
    output: "{item}.done"
    threads: 1
    run:
        descriptor = os.open("active-task.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        try:
            time.sleep(0.5)
            Path(output[0]).touch()
        finally:
            os.close(descriptor)
            Path("active-task.lock").unlink()
''')
    command = runner.workflow_command(executable, config_path, {"cores": 4, "max_parallel_jobs": 1})
    result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    assert all((tmp_path / f"{name}.done").is_file() for name in "abc")
    assert not (tmp_path / "active-task.lock").exists()
