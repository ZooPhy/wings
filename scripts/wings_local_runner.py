#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
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
    "medaka_inference": "polishing", "medaka_consensus": "polishing", "medaka_vcf": "polishing",
    "summarize_blast": "characterization", "vadr_annotate": "characterization", "summarize_vadr": "characterization", "genoflu": "characterization", "detect_h5_with_na": "characterization",
    "phylogeny_align": "phylogeny", "phylogeny_segment_input": "phylogeny", "phylogeny_tree": "phylogeny",
    "surveillance_explorer_data": "surveillance", "genomic_ecological_concordance": "surveillance", "attach_genomic_ecological_concordance": "surveillance",
    "sample_summary": "reporting", "sample_summary_html": "reporting", "run_summary_html": "reporting", "archive_interpretation_outputs": "reporting",
    "effective_run_config": "inputs", "sample_metadata": "inputs",
    "seqtk_rename": "read_qc", "resolve_medaka_model": "read_qc",
    "prepare_vadr_input": "characterization",
    "contextual_phylogeny_inputs": "phylogeny", "contextual_phylogeny_align": "phylogeny",
    "contextual_phylogeny_tree": "phylogeny", "phylogeny_complete": "phylogeny",
    "phylogeny_ready_segments": "phylogeny", "select_contextual_references": "phylogeny",
    "finalize_contextual_references": "phylogeny",
    "ebirdst_phenology": "surveillance", "metadata_ecological_context": "surveillance",
    "run_provenance": "reporting", "archive_replay_inputs": "reporting",
    "select_historical_baseline": "reporting", "historical_stability": "reporting",
    "wings_report_bundle": "reporting",
}
RULE_RE = re.compile(
    r"^(?:\[[^\n]+\]\s*)?\s*(?:(?:local)?rule|(?:local)?checkpoint)\s+([A-Za-z0-9_]+):\s*$",
    re.MULTILINE,
)
MILESTONE_RE = re.compile(r"^\[(\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}:\d{2})\]\s+(.+)$")
PROGRESS_LOG_BYTES = 128 * 1024
PROGRESS_MILESTONES = 20
STATUS_LOG_CACHE = {}
STATUS_LOG_LOCK = threading.Lock()


def log_milestones(text: str) -> list[dict]:
    """Read recorded milestones; gaps are wall time, not per-task CPU time."""
    milestones = []
    previous = None
    for line in text.splitlines():
        match = MILESTONE_RE.fullmatch(line.strip())
        if not match:
            continue
        stamp, message = match.groups()
        try:
            # IRMA uses space-padded hours before 10:00. Normalize whitespace
            # before parsing, including nonbreaking spaces in copied logs.
            current = datetime.strptime(" ".join(stamp.split()), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        gap = (current - previous).total_seconds() if previous is not None else None
        milestones.append({
            "timestamp": current.strftime("%Y-%m-%d %H:%M:%S"),
            "message": message,
            "seconds_since_previous": gap if gap is not None and gap >= 0 else None,
        })
        previous = current
    return milestones


def irma_log_progress(directory: Path) -> list[dict]:
    """Report bounded log tails without invoking tools or modifying run outputs."""
    progress = []
    root = directory.resolve()
    for path in sorted((directory / "results").glob("*/irma/irma.log")):
        sample_id = path.parent.parent.name
        try:
            # A result-directory symlink must not expose files outside this run.
            path = path.resolve()
            path.relative_to(root)
            with path.open("rb") as handle:
                stat = os.fstat(handle.fileno())
                offset = max(0, stat.st_size - PROGRESS_LOG_BYTES)
                handle.seek(offset)
                raw = handle.read(PROGRESS_LOG_BYTES)
            if offset:
                raw = raw.partition(b"\n")[2]
            # A writer may still be emitting the last line.
            if raw and not raw.endswith(b"\n"):
                raw = raw.rpartition(b"\n")[0]
            milestones = log_milestones(raw.decode("utf-8", errors="replace"))
            progress.append({
                "sample_id": sample_id,
                "last_modified": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "log_size_bytes": stat.st_size,
                "recent_milestones": milestones[-PROGRESS_MILESTONES:],
                "earlier_milestones_omitted": bool(offset) or len(milestones) > PROGRESS_MILESTONES,
            })
        except (OSError, ValueError):
            continue
    return progress


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


def bundle_path(run_id: str) -> Path:
    directory = run_dir(run_id)
    path = (directory / "results" / "wings_report_bundle.wings").resolve()
    path.relative_to(directory)
    return path


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
    # Share the opt-in Porechop backend with terminal runs without copying other settings.
    local_config_path = REPO_ROOT / "config.yaml"
    if local_config_path.is_file():
        local_config = yaml.safe_load(local_config_path.read_text(encoding="utf-8")) or {}
        if not isinstance(local_config, dict):
            raise ValueError("Local config.yaml must contain a YAML mapping")
        for key in ("porechop_counter_build", "porechop_threads", "porechop_adapter_search_threads"):
            if key in local_config:
                config[key] = local_config[key]
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


def execution_limits(payload: dict) -> tuple[int, int]:
    """Keep CPU capacity separate from the number of simultaneous tasks."""
    cores = max(1, min(64, int(payload.get("cores", 1))))
    jobs = max(1, min(64, int(payload.get("max_parallel_jobs", 1))))
    return cores, jobs


def workflow_command(executable: str, config_path: Path, state: dict) -> list[str]:
    cores, jobs = execution_limits(state)
    return [
        executable,
        "--snakefile", str(REPO_ROOT / "Snakefile"),
        "--configfile", str(config_path),
        "--use-conda",
        "--cores", str(cores),
        "--resources", f"wings_task_slots={jobs}",
        "--default-resources", "wings_task_slots=1",
        "--set-resource-scopes", "wings_task_slots=global",
        "--rerun-incomplete",
        "--printshellcmds",
    ]


def stage_progress(state: dict, log_text: str) -> dict[str, dict]:
    """Count recorded jobs, without assuming that samples advance together.

    Checkpoints can introduce or remove downstream jobs. Their stage totals
    remain unknown until the workflow finishes; observed counts are exact.
    Counts describe this launcher attempt, not cached work from an earlier one.
    """
    expected = {}
    table = re.search(r"^Job stats:\s*\n(.*?)(?:\n\s*\n|\Z)", log_text, re.MULTILINE | re.DOTALL)
    if table:
        for rule, count in re.findall(r"^\s*([A-Za-z0-9_]+)\s+(\d+)\s*$", table[1], re.MULTILINE):
            if rule != "total":
                expected[rule] = int(count)

    jobs = {}
    anonymous = set()
    errors = set()
    events = []
    for match in RULE_RE.finditer(log_text):
        # A rule's metadata ends before its shell command or the next rule.
        following = log_text[match.end():match.end() + 16384]
        following = following.split("Shell command:", 1)[0]
        next_rule = RULE_RE.search(following)
        if next_rule:
            following = following[:next_rule.start()]
        job = re.search(r"^\s*jobid:\s*(\d+)\s*$", following, re.MULTILINE)
        events.append((match.start(), "start", job[1] if job else None, match[1]))
    for match in re.finditer(r"^Finished jobid:\s*(\d+)\s*\(Rule:\s*([A-Za-z0-9_]+)\)", log_text, re.MULTILINE):
        events.append((match.start(), "complete", match[1], match[2]))
    for match in re.finditer(r"^Error in (?:rule|checkpoint)\s+([A-Za-z0-9_]+):", log_text, re.MULTILINE):
        following = log_text[match.end():match.end() + 16384]
        boundary = re.search(r"^(?:\s*(?:local)?(?:rule|checkpoint) |Finished jobid:|Error in )", following, re.MULTILINE)
        if boundary:
            following = following[:boundary.start()]
        job = re.search(r"^\s*jobid:\s*(\d+)\s*$", following, re.MULTILINE)
        events.append((match.start(), "error", job[1] if job else None, match[1]))
    for _, event, job_id, rule in sorted(events):
        if event == "error" and job_id is None:
            errors.add(rule)
        elif job_id is None:
            anonymous.add(rule)
        else:
            jobs[job_id] = (rule, event)

    dynamic = "normalize_irma_outputs" in expected or bool(re.search(r"^\s*(?:local)?checkpoint\s", log_text, re.MULTILINE))
    provisional_stages = set(STAGE_ORDER[2:]) if dynamic else set()
    finished = state.get("status") == "complete"
    terminal = state.get("status") in {"failed", "stopped"}
    details = {}
    for stage in STAGE_ORDER:
        rules = {rule for rule in expected if RULE_STAGE.get(rule) == stage}
        rules.update(rule for rule, _ in jobs.values() if RULE_STAGE.get(rule) == stage)
        rules.update(rule for rule in anonymous | errors if RULE_STAGE.get(rule) == stage)
        completed = sum(event == "complete" for rule, event in jobs.values() if RULE_STAGE.get(rule) == stage)
        active = sum(event == "start" for rule, event in jobs.values() if RULE_STAGE.get(rule) == stage)
        active += sum(RULE_STAGE.get(rule) == stage for rule in anonymous)
        failed_rules = sorted(
            {rule for rule in errors if RULE_STAGE.get(rule) == stage}
            | {rule for rule, event in jobs.values() if event == "error" and RULE_STAGE.get(rule) == stage}
        )
        counts_known = bool(table) and all(rule in expected for rule in rules) and stage not in provisional_stages
        total = sum(expected.get(rule, 0) for rule in rules) if counts_known else None
        if finished:
            options = state.get("options") or {}
            disabled = (stage == "phylogeny" and options.get("phylogeny") is False) or (
                stage == "surveillance" and options.get("explorer") is False
            )
            status = "skipped" if disabled and not rules else "complete"
        elif failed_rules:
            status = "failed"
        elif terminal and active:
            status = "interrupted"
        elif active:
            status = "running"
        elif total is not None and total > 0 and completed == total:
            status = "complete"
        elif completed:
            status = "partial"
        else:
            status = "waiting"
        if stage == "inputs" and not rules and state.get("sample_count", 0) > 0:
            status = "complete"  # Input validation performed before launch.
        detail = {"status": status, "completed": completed, "expected": total,
                  "active": 0 if terminal or finished else active,
                  "totals_provisional": stage in provisional_stages,
                  "failed_rules": failed_rules}
        if finished:
            # Scheduling may omit cached jobs; a successful attempt verifies
            # the workflow but does not give a fresh count for those jobs.
            detail["cached_work_possible"] = True
        if stage == "assembly":
            detail["irma_completed"] = sum(rule == "irma" and event == "complete" for rule, event in jobs.values())
            detail["irma_expected"] = expected.get("irma")
        details[stage] = detail
    return details


def infer_stages(state: dict, log_text: str) -> dict[str, str]:
    return {stage: detail["status"] for stage, detail in stage_progress(state, log_text).items()}


def failure_details(directory: Path, log_text: str) -> list[dict]:
    """Describe recorded failures without reading sequence inputs or changing outputs."""
    failures = []
    root = directory.resolve()
    blocks = list(re.finditer(
        r"^Error in (?:rule|checkpoint)\s+([A-Za-z0-9_]+):", log_text, re.MULTILINE
    ))
    for index, match in enumerate(blocks):
        end = blocks[index + 1].start() if index + 1 < len(blocks) else len(log_text)
        block = log_text[match.end():end].split("Shell command:", 1)[0]
        block = block[:16384]
        rule = match[1]
        job = re.search(r"^\s*jobid:\s*(\d+)\s*$", block, re.MULTILINE)
        sample = re.search(r"^\s*wildcards:.*?\bsample=([^,\s]+)", block, re.MULTILINE)
        detail = {"rule": rule, "stage": RULE_STAGE.get(rule),
                  "job_id": job[1] if job else None,
                  "sample_id": sample[1] if sample else None,
                  "message": f"Task {rule} failed.", "logs": []}
        log_line = re.search(r"^\s*log:\s*(.+)$", block, re.MULTILINE)
        if log_line:
            for name in log_line[1].split(","):
                # Snakemake may append '(check log file(s) for error details)'.
                name = name.strip().split(" (check log", 1)[0]
                try:
                    path = Path(name)
                    path = (path if path.is_absolute() else directory / path).resolve()
                    relative = path.relative_to(root)
                    if not path.is_file():
                        continue
                    with path.open("rb") as handle:
                        handle.seek(max(0, path.stat().st_size - PROGRESS_LOG_BYTES))
                        tail = handle.read(PROGRESS_LOG_BYTES).decode("utf-8", errors="replace")
                    invalid = re.search(r"^\s*Line\s+(\d+):\s*illegal character\s+(\S+)", tail, re.MULTILINE)
                    if invalid:
                        detail["category"] = "input_validation"
                        detail["message"] = (
                            f"Task {rule}: input validation failed on line {invalid[1]} "
                            f"(illegal character {invalid[2][:32]!r})."
                        )
                    detail["logs"].append(relative.as_posix())
                except (OSError, ValueError):
                    continue
        failures.append(detail)
    # Snakemake can repeat the same failed-job block during shutdown.
    # Keep its latest details without merging different jobs or sample logs.
    unique = {}
    for detail in failures:
        key = (detail["rule"], detail["job_id"], detail["sample_id"], tuple(detail["logs"]))
        unique[key] = detail
    return list(unique.values())


def launcher_status_log(log_path: Path) -> tuple[str, str]:
    """Read scheduler records and a bounded tail; skip verbose shell output.

    Cache only an unchanged, fully read log. A bounded readline also prevents
    a very long shell-output line from becoming an enormous temporary string.
    """
    try:
        with STATUS_LOG_LOCK:
            stat = log_path.stat()
            signature = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
            cached = STATUS_LOG_CACHE.get(log_path)
            if cached and cached[0] == signature:
                return cached[1], cached[2]
            records = []
            table = False
            metadata = False
            with log_path.open("rb") as handle:
                while True:
                    raw = handle.readline(16384)
                    if not raw:
                        break
                    long_line = not raw.endswith(b"\n") and len(raw) == 16384
                    if long_line:
                        while raw and not raw.endswith(b"\n"):
                            raw = handle.readline(16384)
                        continue
                    if not raw.endswith(b"\n"):
                        # A writer may still be appending this scheduler record.
                        break
                    line = raw.decode("utf-8", errors="replace")
                    stripped = line.strip()
                    if stripped == "Job stats:":
                        table = True
                        metadata = False
                        records.append(line)
                    elif table:
                        records.append(line)
                        if not stripped:
                            table = False
                    elif RULE_RE.fullmatch(line.rstrip("\r\n")) or re.match(
                        r"^Error in (?:rule|checkpoint)\s+[A-Za-z0-9_]+:", line
                    ):
                        metadata = True
                        records.append(line)
                    elif line.startswith("Finished jobid:"):
                        metadata = False
                        records.append(line)
                    elif metadata and stripped.startswith("Shell command:"):
                        records.append("Shell command:\n")
                        metadata = False
                    elif metadata and re.match(r"^\s*(?:jobid|wildcards|log):", line):
                        records.append(line)
                handle.seek(max(0, stat.st_size - PROGRESS_LOG_BYTES))
                raw_tail = handle.read(PROGRESS_LOG_BYTES)
            if stat.st_size > PROGRESS_LOG_BYTES:
                raw_tail = raw_tail.partition(b"\n")[2]
            progress = "".join(records)
            tail = "\n".join(raw_tail.decode("utf-8", errors="replace").splitlines()[-120:])
            after = log_path.stat()
            after_signature = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            if after_signature == signature:
                # Keep memory bounded when users open many saved runs.
                if len(STATUS_LOG_CACHE) >= 16:
                    STATUS_LOG_CACHE.pop(next(iter(STATUS_LOG_CACHE)))
                STATUS_LOG_CACHE[log_path] = (signature, progress, tail)
            return progress, tail
    except OSError:
        return "", ""


def enriched_state(run_id: str) -> dict:
    state = read_state(run_id)
    directory = run_dir(run_id)
    log_path = (directory / state.get("launcher_log", "snakemake.log")).resolve()
    log_path.relative_to(directory)
    log_text, state["log_tail"] = launcher_status_log(log_path)
    state["stage_progress"] = stage_progress(state, log_text)
    state["stages"] = {stage: detail["status"] for stage, detail in state["stage_progress"].items()}
    state["status_scope"] = "launcher_attempt"
    state["failures"] = failure_details(run_dir(run_id), log_text)
    for index, failure in enumerate(state["failures"]):
        failure["log_urls"] = [
            f"/api/runs/{run_id}/failure-log?failure={index}&log={log_index}"
            for log_index in range(len(failure["logs"]))
        ]
    state["irma_progress"] = irma_log_progress(run_dir(run_id))
    state["can_resume"] = state.get("status") in {"failed", "stopped"} and (
        directory / "execution_config.yaml"
    ).is_file()
    for attempt in state.get("attempts", []):
        attempt["log_url"] = f"/api/runs/{run_id}/attempt-log?attempt={attempt['attempt_id']}"
    return state


def wait_for_process(run_id: str, process: subprocess.Popen[str], log_handle) -> None:
    code = process.wait()
    log_handle.close()
    with LOCK:
        if PROCESSES.get(run_id) is not process:
            return
        PROCESSES.pop(run_id, None)
        state = read_state(run_id)
        if state.get("status") == "stopping":
            state["status"] = "stopped"
        else:
            state["status"] = "complete" if code == 0 else "failed"
        state["exit_code"] = code
        state["finished_at"] = utc_now()
        for attempt in state.get("attempts", []):
            if attempt["attempt_id"] == state.get("active_attempt"):
                attempt.update({"status": state["status"], "finished_at": state["finished_at"], "exit_code": code})
        write_state(run_id, state)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_attempt_provenance(attempt_dir: Path, command: list[str], config_path: Path,
                               started_at: str, resumed: bool) -> Path:
    """Freeze launcher state before starting Snakemake without modifying the repository."""
    def run(args: list[str]) -> tuple[int, str]:
        try:
            result = subprocess.run(args, cwd=REPO_ROOT, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, timeout=30)
            return result.returncode, result.stdout
        except (OSError, subprocess.SubprocessError) as error:
            return 127, f"NOT_CAPTURED: {error}"

    git = {}
    for key, args in {
        "commit": ["git", "rev-parse", "HEAD"],
        "branch": ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        "describe": ["git", "describe", "--tags", "--always", "--dirty"],
        "status_porcelain": ["git", "status", "--porcelain", "--untracked-files=all"],
    }.items():
        code, output = run(args)
        git[key] = output.strip() if code == 0 else "NOT_CAPTURED"

    diff_path = attempt_dir / "tracked-source.diff"
    code, diff = run(["git", "diff", "--binary", "HEAD", "--"])
    diff_path.write_text(diff if code == 0 else "", encoding="utf-8")

    packages = {}
    conda = shutil.which("conda")
    if conda:
        for filename, args in {
            "conda-list.json": [conda, "list", "--json"],
            "conda-explicit.txt": [conda, "list", "--explicit"],
        }.items():
            result_code, output = run(args)
            path = attempt_dir / filename
            path.write_text(output if result_code == 0 else "", encoding="utf-8")
            packages[filename] = {"sha256": sha256_file(path), "captured": result_code == 0,
                                  "content": output if result_code == 0 else None}
    else:
        packages["status"] = "conda not found on PATH"

    record = {
        "schema_version": 1,
        "captured_at_utc": started_at,
        "resumed": resumed,
        "command": command,
        "working_directory": str(REPO_ROOT),
        "effective_config": {
            "path": str(config_path),
            "sha256": sha256_file(config_path),
            "content": config_path.read_text(encoding="utf-8"),
        },
        "git": {
            **git,
            "dirty": git.get("status_porcelain") not in {"", "NOT_CAPTURED"},
            "tracked_diff": {"path": diff_path.name, "sha256": sha256_file(diff_path),
                             "size_bytes": diff_path.stat().st_size,
                             "content": diff if code == 0 else None},
        },
        "launcher_environment": packages,
    }
    path = attempt_dir / "attempt-provenance.json"
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def launch_attempt(run_id: str, resume: bool = False) -> dict:
    """Launch one browser-owned attempt, preserving existing configuration and logs."""
    with LOCK:
        state = read_state(run_id)
        process = PROCESSES.get(run_id)
        if process and process.poll() is None:
            raise ValueError("This run already has an active launcher process")
        if state.get("status") not in {"created", "failed", "stopped"}:
            raise ValueError(f"Run cannot start from status {state.get('status')}")
        if resume and state.get("status") not in {"failed", "stopped"}:
            raise ValueError("Resume requires a failed or stopped run")
        resume = resume or state.get("status") in {"failed", "stopped"}
        executable = shutil.which("snakemake")
        if not executable:
            raise ValueError("snakemake was not found in PATH")
        directory = run_dir(run_id)
        if resume:
            config_path = (directory / "execution_config.yaml").resolve()
            config_path.relative_to(directory)
            if not config_path.is_file():
                raise ValueError("Saved execution_config.yaml is missing; this run cannot resume")
            sample_count = state.get("sample_count", 0)
        else:
            config_path, sample_count = build_config(run_id)
        attempts = list(state.get("attempts") or [])
        if resume and not attempts:
            attempts.append({
                "attempt_id": "legacy", "status": state["status"],
                "started_at": state.get("started_at"), "finished_at": state.get("finished_at"),
                "exit_code": state.get("exit_code"),
                "log_path": state.get("launcher_log", "snakemake.log"),
            })
        attempt_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        attempt_dir = directory / "attempts" / attempt_id
        attempt_dir.mkdir(parents=True, exist_ok=False)
        log_path = attempt_dir / "snakemake.log"
        command = workflow_command(executable, config_path, state)
        started = utc_now()
        attempt_provenance = capture_attempt_provenance(
            attempt_dir, command, config_path, started, resume
        )
        environment = os.environ.copy()
        environment["WINGS_ATTEMPT_PROVENANCE"] = str(attempt_provenance)
        log_handle = log_path.open("x", encoding="utf-8")
        try:
            process = subprocess.Popen(command, cwd=REPO_ROOT, stdout=log_handle,
                                       stderr=subprocess.STDOUT, text=True, start_new_session=True,
                                       env=environment)
        except BaseException:
            log_handle.close()
            raise
        relative_log = log_path.relative_to(directory).as_posix()
        relative_provenance = attempt_provenance.relative_to(directory).as_posix()
        attempts.append({"attempt_id": attempt_id, "status": "running", "started_at": started,
                         "finished_at": None, "exit_code": None, "log_path": relative_log,
                         "provenance_path": relative_provenance, "resumed": resume})
        state.update({"status": "running", "started_at": started, "finished_at": None,
                      "exit_code": None, "pid": process.pid, "sample_count": sample_count,
                      "command": command, "execution_config": str(config_path),
                      "launcher_log": relative_log, "active_attempt": attempt_id, "attempts": attempts})
        try:
            write_state(run_id, state)
        except BaseException:
            process.terminate()
            process.wait()
            log_handle.close()
            raise
        PROCESSES[run_id] = process
    threading.Thread(target=wait_for_process, args=(run_id, process, log_handle), daemon=True).start()
    return {"status": "running", "run_id": run_id, "attempt_id": attempt_id}


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
            match = re.fullmatch(r"/api/runs/([^/]+)/bundle", parsed.path)
            if match:
                run_id = unquote(match.group(1))
                directory = run_dir(run_id)
                if not directory.is_dir():
                    self.error_response("Unknown run", HTTPStatus.NOT_FOUND)
                    return

                state = read_state(run_id)
                if state.get("status") != "complete":
                    self.error_response(
                        "Run results are not available until the run is complete",
                        HTTPStatus.CONFLICT,
                    )
                    return

                bundle = bundle_path(run_id)
                if not bundle.is_file():
                    self.error_response(
                        "WINGS report bundle is not available",
                        HTTPStatus.NOT_FOUND,
                    )
                    return

                body = bundle.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
                return

            match = re.fullmatch(r"/api/runs/([^/]+)/(failure-log|attempt-log)", parsed.path)
            if match:
                run_id = unquote(match.group(1))
                query = parse_qs(parsed.query)
                directory = run_dir(run_id)
                if match.group(2) == "attempt-log":
                    attempt_id = query.get("attempt", [""])[0]
                    attempt = next((a for a in read_state(run_id).get("attempts", [])
                                    if a["attempt_id"] == attempt_id), None)
                    if not attempt:
                        raise ValueError("Unknown attempt")
                    relative = attempt["log_path"]
                else:
                    failure_index = int(query.get("failure", ["0"])[0])
                    log_index = int(query.get("log", ["0"])[0])
                    failures = enriched_state(run_id)["failures"]
                    if not 0 <= failure_index < len(failures):
                        raise ValueError("Unknown failure")
                    logs = failures[failure_index]["logs"]
                    if not 0 <= log_index < len(logs):
                        raise ValueError("Unknown failure log")
                    relative = logs[log_index]
                path = (directory / relative).resolve()
                path.relative_to(directory)
                with path.open("rb") as handle:
                    handle.seek(max(0, path.stat().st_size - PROGRESS_LOG_BYTES))
                    body = handle.read(PROGRESS_LOG_BYTES)
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(body)
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
                cores, max_parallel_jobs = execution_limits(payload)
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
                    "max_parallel_jobs": max_parallel_jobs,
                    "options": payload.get("options") or {},
                    "sample_count": 0,
                    "results_dir": str(directory / "results"),
                }
                write_state(run_id, state)
                self.json_response({"run_id": run_id}, HTTPStatus.CREATED)
                return

            match = re.fullmatch(r"/api/runs/([^/]+)/(start|stop|resume)", parsed.path)
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

                self.json_response(launch_attempt(run_id, resume=action == "resume"))
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
