from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_attempt_snapshot_freezes_command_config_diff_and_packages(tmp_path):
    runner = load("attempt_runner", ROOT / "scripts" / "wings_local_runner.py")
    config = tmp_path / "execution_config.yaml"
    config.write_text("results_dir: results\n")
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    outputs = {
        ("git", "rev-parse", "HEAD"): "a" * 40 + "\n",
        ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main\n",
        ("git", "describe", "--tags", "--always", "--dirty"): "v1.0-dirty\n",
        ("git", "status", "--porcelain", "--untracked-files=all"): " M Snakefile\n?? notes.txt\n",
        ("git", "diff", "--binary", "HEAD", "--"): "diff --git a/Snakefile b/Snakefile\n",
        ("conda", "list", "--json"): '[{"name":"python","version":"3.12"}]\n',
        ("conda", "list", "--explicit"): "@EXPLICIT\nhttps://example.invalid/python.tar.bz2\n",
    }

    def fake_run(args, **kwargs):
        class Result:
            returncode = 0
            stdout = outputs[tuple(args)]
        return Result()

    with patch.object(runner.subprocess, "run", side_effect=fake_run), \
         patch.object(runner.shutil, "which", return_value="conda"):
        path = runner.capture_attempt_provenance(
            attempt, ["snakemake", "--cores", "1"], config,
            "2026-10-16T00:00:00Z", True,
        )
    record = json.loads(path.read_text())
    assert record["command"] == ["snakemake", "--cores", "1"]
    assert record["resumed"] is True
    assert record["git"]["commit"] == "a" * 40
    assert record["git"]["dirty"] is True
    assert record["git"]["tracked_diff"]["content"].startswith("diff --git")
    assert record["effective_config"]["sha256"] == runner.sha256_file(config)
    assert record["effective_config"]["content"] == "results_dir: results\n"
    assert "python" in record["launcher_environment"]["conda-list.json"]["content"]


def test_run_provenance_loads_attempt_snapshot_from_environment(tmp_path, monkeypatch):
    writer = load("provenance_writer", ROOT / "scripts" / "write_run_provenance.py")
    path = tmp_path / "attempt-provenance.json"
    path.write_text('{"schema_version":1,"command":["snakemake"]}\n')
    monkeypatch.setenv("WINGS_ATTEMPT_PROVENANCE", str(path))
    record = writer.load_attempt_provenance()
    assert record["command"] == ["snakemake"]
    assert record["record_sha256"] == writer.sha256_file(path)


def test_run_provenance_allows_terminal_execution_without_launcher(monkeypatch):
    writer = load("provenance_writer_terminal", ROOT / "scripts" / "write_run_provenance.py")
    monkeypatch.delenv("WINGS_ATTEMPT_PROVENANCE", raising=False)
    assert writer.load_attempt_provenance() is None


def test_verifier_detects_tampering(tmp_path):
    verifier = load("attempt_verifier", ROOT / "scripts" / "verify_run_provenance.py")
    config = tmp_path / "config.json"
    config.write_text("{}\n")
    diff = "diff --git a/a b/a\n"
    packages = "[]\n"
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps({"launcher_attempt": {
        "effective_config": {"path": str(config), "sha256": verifier.sha256_file(config), "content": config.read_text()},
        "git": {"commit": "a" * 40, "dirty": True,
                "tracked_diff": {"content": diff,
                                 "sha256": verifier.sha256_bytes(diff.encode())}},
        "launcher_environment": {"conda-list.json": {"captured": True,
            "content": packages, "sha256": verifier.sha256_bytes(packages.encode())}},
    }}))
    class Result:
        returncode = 0
    with patch.object(verifier.subprocess, "run", return_value=Result()):
        assert verifier.verify(provenance, tmp_path)["status"] == "PASS"
        data = json.loads(provenance.read_text())
        data["launcher_attempt"]["git"]["tracked_diff"]["content"] += "changed"
        provenance.write_text(json.dumps(data))
        result = verifier.verify(provenance, tmp_path)
    assert result["status"] == "FAIL"
    assert "Tracked source diff SHA-256 mismatch" in result["errors"]


def test_publication_verification_rejects_dirty_launch(tmp_path):
    verifier = load("attempt_verifier_clean", ROOT / "scripts" / "verify_run_provenance.py")
    config = "synthetic: true\n"
    diff = ""
    provenance = tmp_path / "provenance.json"
    provenance.write_text(json.dumps({"launcher_attempt": {
        "effective_config": {"path": "missing.yaml",
                             "sha256": verifier.sha256_bytes(config.encode()),
                             "content": config},
        "git": {"commit": "a" * 40, "dirty": True,
                "tracked_diff": {"content": diff,
                                 "sha256": verifier.sha256_bytes(diff.encode())}},
        "launcher_environment": {},
    }}))
    class Result:
        returncode = 0
    with patch.object(verifier.subprocess, "run", return_value=Result()):
        assert verifier.verify(provenance, tmp_path)["status"] == "PASS"
        result = verifier.verify(provenance, tmp_path, require_clean=True)
    assert result["status"] == "FAIL"
    assert "Publication verification requires a clean Git worktree at launch" in result["errors"]


def test_capture_definition_precedes_script_entrypoint():
    source = (ROOT / "scripts" / "wings_local_runner.py").read_text()
    assert source.index("def capture_attempt_provenance") < source.index('if __name__ == "__main__"')
