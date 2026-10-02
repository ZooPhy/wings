#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:
    import yaml
except ImportError as error:  # pragma: no cover
    raise SystemExit("PyYAML is required. Run this inside the WINGS Snakemake environment.") from error

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNS_ROOT = Path(os.environ.get("WINGS_RUNS_DIR", "~/.wings/runs")).expanduser().resolve()
RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
PROCESSES: dict[str, subprocess.Popen[str]] = {}
LOCK = threading.Lock()

STAGE_ORDER = [
    "inputs", "read_qc", "assembly", "polishing", "characterization", "phylogeny", "surveillance", "reporting"
]
RULE_STAGE = {
    "validate_metadata": "inputs",
    "porechop": "read_qc", "fastplong": "read_qc", "nanoplot": "read_qc",
    "irma": "assembly", "normalize_irma_outputs": "assembly", "check_coverage": "assembly", "coverage_table": "assembly", "concat_consensus": "assembly",
    "resolve_medaka_model": "polishing", "medaka_inference": "polishing", "medaka_consensus": "polishing", "medaka_vcf": "polishing",
    "summarize_blast": "characterization", "vadr_annotate": "characterization", "summarize_vadr": "characterization", "genoflu": "characterization", "detect_h5_with_na": "characterization",
    "phylogeny_align": "phylogeny", "phylogeny_segment_input": "phylogeny", "phylogeny_tree": "phylogeny",
    "surveillance_explorer_data": "surveillance", "genomic_ecological_concordance": "surveillance", "attach_genomic_ecological_concordance": "surveillance",
    "sample_summary": "reporting", "sample_summary_html": "reporting", "run_summary_html": "reporting", "archive_interpretation_outputs": "reporting", "archive_replay_inputs": "reporting",
}
RULE_RE = re.compile(r"^(?:rule|checkpoint)\s+([A-Za-z0-9_]+):\s*$", re.MULTILINE)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def run_dir(run_id: str) -> Path:
    if not RUN_ID_RE.fullmatch(run_id):
        raise ValueError("Invalid run ID")
    path = (RUNS_ROOT / run_id).resolve()
    path.relative_to(RUNS_ROOT)
    return path


def state_path(run_id: str) -> Path:
    return run_dir(run_id) / "state.json"


def read_state(run_id: str) -> dict:
    return json.loads(state_path(run_id).read_text(encoding="utf-8"))


def write_state(run_id: str, state: dict) -> None:
    atomic_json(state_path(run_id), state)


def strip_fastq(name: str) -> tuple[str, str]:
    lower = name.lower()
    for suffix in (".fastq.gz", ".fq.gz", ".fastq", ".fq"):
        if lower.endswith(suffix):
            return name[: -len(suffix)], name[-len(suffix):]
    raise ValueError(f"Unsupported FASTQ filename: {name}")


def metadata_ids(path: Path) -> list[str]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames or "sample_id" not in reader.fieldnames:
            raise ValueError("Metadata must contain a sample_id column")
        values = [str(row.get("sample_id", "")).strip() for row in reader]
    values = [value for value in values if value]
    if not values:
        raise ValueError("Metadata contains no sample_id values")
    if len(values) != len(set(values)):
        raise ValueError("Metadata contains duplicate sample_id values")
    return values


def build_config(run_id: str) -> tuple[Path, int]:
    directory = run_dir(run_id)
    state = read_state(run_id)
    reads_dir = directory / "inputs" / "reads"
    metadata = directory / "inputs" / "metadata.tsv"
    reads = sorted(path for path in reads_dir.iterdir() if path.is_file())
    if not reads:
        raise ValueError("No FASTQ files were provided")
    samples_and_ext = [strip_fastq(path.name) for path in reads]
    extensions = {ext.lower() for _, ext in samples_and_ext}
    if len(extensions) != 1:
        raise ValueError("All FASTQ files must use the same extension")
    sample_ids = [sample for sample, _ in samples_and_ext]
    if len(sample_ids) != len(set(sample_ids)):
        raise ValueError("FASTQ filenames produce duplicate sample IDs")
    metadata_sample_ids = metadata_ids(metadata)
    if set(sample_ids) != set(metadata_sample_ids):
        missing_metadata = sorted(set(sample_ids) - set(metadata_sample_ids))
        missing_reads = sorted(set(metadata_sample_ids) - set(sample_ids))
        details = []
        if missing_metadata:
            details.append(f"missing metadata: {', '.join(missing_metadata[:8])}")
        if missing_reads:
            details.append(f"missing reads: {', '.join(missing_reads[:8])}")
        raise ValueError("Sample mismatch (" + "; ".join(details) + ")")

    example = REPO_ROOT / "config" / "config.example.yaml"
    config = yaml.safe_load(example.read_text(encoding="utf-8")) or {}
    results = directory / "results"
    config["reads_dir"] = str(reads_dir)
    config["reads_pattern"] = "{sample}" + next(iter(extensions))
    config["results_dir"] = str(results)
    config["metadata_file"] = str(metadata)
    config["phylogeny_dir"] = str(results / "phylogeny")
    options = state.get("options") or {}
    config["run_genoflu"] = bool(options.get("genoflu", True))
    config["run_vadr"] = bool(options.get("vadr", True))
    config["run_surveillance_explorer"] = bool(options.get("explorer", True))
    phylogeny = dict(config.get("phylogeny") or {})
    phylogeny["enabled"] = bool(options.get("phylogeny", False))
    config["phylogeny"] = phylogeny

    config_path = directory / "execution_config.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return config_path, len(sample_ids)


def infer_stages(state: dict, log_text: str) -> dict[str, str]:
    stages = {stage: "waiting" for stage in STAGE_ORDER}
    stages["inputs"] = "complete"
    seen = []
    for rule in RULE_RE.findall(log_text):
        stage = RULE_STAGE.get(rule)
        if stage and stage not in seen:
            seen.append(stage)
    if state.get("status") == "complete":
        return {stage: "complete" for stage in STAGE_ORDER}
    if state.get("status") in {"failed", "stopped"}:
        if seen:
            current = max(seen, key=STAGE_ORDER.index)
            for stage in STAGE_ORDER:
                if STAGE_ORDER.index(stage) < STAGE_ORDER.index(current):
                    stages[stage] = "complete"
            stages[current] = "failed" if state.get("status") == "failed" else "warning"
        return stages
    if seen:
        current = max(seen, key=STAGE_ORDER.index)
        for stage in STAGE_ORDER:
            if STAGE_ORDER.index(stage) < STAGE_ORDER.index(current):
                stages[stage] = "complete"
        stages[current] = "running"
    return stages


def enriched_state(run_id: str) -> dict:
    state = read_state(run_id)
    log_path = run_dir(run_id) / "snakemake.log"
    log_text = ""
    if log_path.is_file():
        try:
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            pass
    state["log_tail"] = "\n".join(log_text.splitlines()[-120:])
    state["stages"] = infer_stages(state, log_text)
    return state


def wait_for_process(run_id: str, process: subprocess.Popen[str], log_handle) -> None:
    code = process.wait()
    log_handle.close()
    with LOCK:
        PROCESSES.pop(run_id, None)
    state = read_state(run_id)
    if state.get("status") == "stopping":
        state["status"] = "stopped"
    else:
        state["status"] = "complete" if code == 0 else "failed"
    state["exit_code"] = code
    state["finished_at"] = utc_now()
    write_state(run_id, state)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(REPO_ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        print(f"[wings-runner] {self.address_string()} - {fmt % args}")

    def json_response(self, payload: dict | list, status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def error_response(self, message: str, status: int = 400) -> None:
        self.json_response({"error": message}, status)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1024 * 1024:
            raise ValueError("JSON request too large")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8")) if raw else {}

    def parsed(self):
        return urlparse(self.path)

    def do_GET(self) -> None:  # noqa: N802
        parsed = self.parsed()
        try:
            if parsed.path == "/api/health":
                snakemake = shutil.which("snakemake")
                usage = shutil.disk_usage(RUNS_ROOT.parent if RUNS_ROOT.parent.exists() else Path.home())
                self.json_response({
                    "status": "ready",
                    "repo_root": str(REPO_ROOT),
                    "runs_root": str(RUNS_ROOT),
                    "snakemake": snakemake,
                    "snakemake_available": bool(snakemake),
                    "config_yaml_present": (REPO_ROOT / "config.yaml").is_file(),
                    "config_yaml_path": str(REPO_ROOT / "config.yaml"),
                    "free_bytes": usage.free,
                })
                return
            if parsed.path == "/api/runs":
                RUNS_ROOT.mkdir(parents=True, exist_ok=True)
                rows = []
                for path in sorted(RUNS_ROOT.glob("*/state.json"), reverse=True):
                    try:
                        rows.append(json.loads(path.read_text(encoding="utf-8")))
                    except (OSError, json.JSONDecodeError):
                        continue
                self.json_response(rows)
                return
            match = re.fullmatch(r"/api/runs/([^/]+)", parsed.path)
            if match:
                self.json_response(enriched_state(unquote(match.group(1))))
                return
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.error_response(str(error), 400)
            return
        super().do_GET()

    def do_PUT(self) -> None:  # noqa: N802
        parsed = self.parsed()
        match = re.fullmatch(r"/api/runs/([^/]+)/files", parsed.path)
        if not match:
            self.error_response("Unknown endpoint", 404)
            return
        try:
            run_id = unquote(match.group(1))
            directory = run_dir(run_id)
            if not directory.is_dir():
                raise ValueError("Unknown run")
            query = parse_qs(parsed.query)
            kind = (query.get("kind") or [""])[0]
            filename = Path(unquote((query.get("filename") or [""])[0])).name
            if kind not in {"reads", "metadata"}:
                raise ValueError("kind must be reads or metadata")
            if not filename:
                raise ValueError("filename is required")
            length = int(self.headers.get("Content-Length", "-1"))
            if length < 0:
                raise ValueError("Content-Length is required")
            if kind == "metadata" and length > 25 * 1024 * 1024:
                raise ValueError("Metadata file is unexpectedly large")
            destination = directory / "inputs" / ("reads" if kind == "reads" else "") / (filename if kind == "reads" else "metadata.tsv")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp = destination.with_name(f".{destination.name}.upload-{os.getpid()}")
            remaining = length
            with temp.open("wb") as handle:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("Upload ended before Content-Length bytes were received")
                    handle.write(chunk)
                    remaining -= len(chunk)
            temp.replace(destination)
            self.json_response({"stored": str(destination), "size_bytes": destination.stat().st_size})
        except (OSError, ValueError) as error:
            self.error_response(str(error), 400)

    def do_POST(self) -> None:  # noqa: N802
        parsed = self.parsed()
        try:
            if parsed.path == "/api/runs":
                payload = self.read_json()
                name = str(payload.get("name", "")).strip() or "WINGS run"
                cores = max(1, min(64, int(payload.get("cores", 4))))
                run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
                directory = run_dir(run_id)
                (directory / "inputs" / "reads").mkdir(parents=True, exist_ok=False)
                state = {
                    "format": "WINGS_LOCAL_RUN",
                    "schema_version": 1,
                    "run_id": run_id,
                    "name": name,
                    "status": "created",
                    "created_at": utc_now(),
                    "started_at": None,
                    "finished_at": None,
                    "cores": cores,
                    "options": payload.get("options") or {},
                    "sample_count": 0,
                    "results_dir": str(directory / "results"),
                }
                write_state(run_id, state)
                self.json_response({"run_id": run_id}, HTTPStatus.CREATED)
                return

            match = re.fullmatch(r"/api/runs/([^/]+)/(start|stop)", parsed.path)
            if match:
                run_id, action = unquote(match.group(1)), match.group(2)
                state = read_state(run_id)
                if action == "stop":
                    with LOCK:
                        process = PROCESSES.get(run_id)
                    if process and process.poll() is None:
                        state["status"] = "stopping"
                        write_state(run_id, state)
                        process.terminate()
                    self.json_response({"status": "stopping"})
                    return

                if state.get("status") not in {"created", "failed", "stopped"}:
                    raise ValueError(f"Run cannot start from status {state.get('status')}")
                snakemake = shutil.which("snakemake")
                if not snakemake:
                    raise ValueError("snakemake was not found in PATH")
                config_path, sample_count = build_config(run_id)
                directory = run_dir(run_id)
                log_path = directory / "snakemake.log"
                log_handle = log_path.open("w", encoding="utf-8")
                command = [
                    snakemake,
                    "--snakefile", str(REPO_ROOT / "Snakefile"),
                    "--configfile", str(config_path),
                    "--use-conda",
                    "--cores", str(state["cores"]),
                    "--rerun-incomplete",
                    "--printshellcmds",
                ]
                process = subprocess.Popen(
                    command,
                    cwd=REPO_ROOT,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                    start_new_session=True,
                )
                with LOCK:
                    PROCESSES[run_id] = process
                state.update({
                    "status": "running",
                    "started_at": utc_now(),
                    "finished_at": None,
                    "exit_code": None,
                    "pid": process.pid,
                    "sample_count": sample_count,
                    "command": command,
                    "execution_config": str(config_path),
                })
                write_state(run_id, state)
                threading.Thread(target=wait_for_process, args=(run_id, process, log_handle), daemon=True).start()
                self.json_response({"status": "running", "run_id": run_id})
                return
        except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
            self.error_response(str(error), 400)
            return
        self.error_response("Unknown endpoint", 404)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local-first WINGS portal and Snakemake launcher.")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address. Keep 127.0.0.1 for local-only operation.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    if args.host not in {"127.0.0.1", "localhost"}:
        raise SystemExit("For safety, the WINGS local runner only binds to localhost.")

    RUNS_ROOT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://127.0.0.1:{args.port}/run.html"
    print(f"WINGS local runner: {url}")
    print(f"Repository: {REPO_ROOT}")
    print(f"Run storage: {RUNS_ROOT}")
    print("Sequence data remain on this computer; the server is bound to localhost only.")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping WINGS local runner.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
