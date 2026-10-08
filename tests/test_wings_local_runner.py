from __future__ import annotations

import importlib.util
import json
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
