from __future__ import annotations

import importlib.util
from pathlib import Path


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
