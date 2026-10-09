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


def test_stage_inference_marks_latest_stage_running():
    runner = load_runner()
    state = {"status": "running"}
    log = "rule porechop:\nrule irma:\nrule medaka_inference:\n"
    stages = runner.infer_stages(state, log)
    assert stages["read_qc"] == "complete"
    assert stages["assembly"] == "complete"
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

    assert stages["read_qc"] == "complete"
    assert stages["assembly"] == "running"
    assert stages["polishing"] == "waiting"


def test_setup_rules_do_not_advance_pipeline_stage():
    runner = load_runner()
    state = {"status": "running"}
    log = (
        "rule validate_metadata:\n"
        "rule resolve_medaka_model:\n"
        "rule archive_replay_inputs:\n"
    )

    stages = runner.infer_stages(state, log)

    assert stages["inputs"] == "running"
    assert stages["read_qc"] == "waiting"
    assert stages["polishing"] == "waiting"
    assert stages["reporting"] == "waiting"


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
