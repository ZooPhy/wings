#!/usr/bin/env python3
"""Isolated Snakemake regression test for WINGS missing-segment reporting.

Run in the active WINGS Snakemake environment from the repository root:
    python wings_test_missing_segments.py

Requires Python 3.9+ and Snakemake on PATH. Does not edit the repository,
read real samples, solve Conda environments, or fetch external data.
All generated files and logs are retained in a new system temporary directory.

Production components: segment helpers, the three run-report status inputs,
sample-report status inputs, Medaka status rules, bundle rule and builder.
Fixtures: normalization checkpoint, coverage flags, no-model tables,
HTML rendering, and provenance. BAM placeholders are deliberately not real
alignments; inference is skipped because no model is available. This validates
checkpoint/dependency/status behavior, not biological accuracy or Quarto.
"""

import argparse
import ast
import csv
import hashlib
import html
import inspect
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace


SEGMENTS = ("HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS")
SAMPLE_IDS = ("complete", "partial", "all_missing")
FIELDS = (
    ("medaka_inference_status", "inference.status.tsv"),
    ("medaka_consensus_status", "consensus.status.tsv"),
    ("medaka_variant_status", "variants.status.tsv"),
)
HELPERS = (
    "irma_segments_dir", "irma_manifest_path", "_manifest_rows",
    "segments_for_sample", "run_medaka_status_inputs", "bam_path", "fasta_path",
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def rule_text(source, name):
    match = re.search(r"^rule " + re.escape(name) + r":\s*$", source, re.M)
    require(match is not None, "Cannot find production rule " + name)
    following = re.search(r"^(?:rule|checkpoint) \w+:", source[match.end():], re.M)
    end = match.end() + following.start() if following else len(source)
    return source[match.start():end]


def function_text(source, name):
    match = re.search(r"^def " + re.escape(name) + r"\(.*?(?=^\S|\Z)", source, re.M | re.S)
    require(match is not None, "Missing helper " + name + "; apply the missing-segment update first.")
    ast.parse(match.group())
    return match.group()


def input_entry(rule, name):
    match = re.search(r"^        " + re.escape(name) + r"=.*?(?=^        \w+=|^    \w+:)", rule, re.M | re.S)
    require(match is not None, "Cannot extract report input " + name)
    value = re.sub(r"(?m)^\s*#[^\n]*(?:\n|$)", "", match.group()).rstrip()
    require(value.endswith(","), "Unexpected input layout for " + name)
    # Trailing comments may follow the input. Keep only its expression.
    ast.parse(value.split("=", 1)[1].rstrip().removesuffix(","), mode="eval")
    return value + "\n"


def write_table(path, rows, fields):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def fixture_checkpoint(sample, segments_dir, manifest):
    directory = Path(segments_dir)
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for segment in SEGMENTS:
        missing = sample == "all_missing" or (sample == "partial" and segment == "MP")
        rows.append({"sample": sample, "segment": segment, "status": "MISSING" if missing else "READY"})
        if not missing:
            target = directory / segment
            target.mkdir(exist_ok=True)
            (target / "consensus.fasta").write_text(">fixture_" + segment + "\nACGTACGT\n", encoding="utf-8")
            (target / "alignment.bam").write_bytes(b"SYNTHETIC_DEPENDENCY_PLACEHOLDER_NOT_A_BAM\n")
    write_table(manifest, rows, ("sample", "segment", "status"))


def fixture_flag(sample, segment, output):
    flag = Path(output)
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("FAIL\n" if sample == "partial" and segment == "PB2" else "PASS\n", encoding="utf-8")


def status_value(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        row = next(csv.DictReader(handle, delimiter="\t"))
    return row["status"]


def report_rows(sample):
    base = Path("results") / sample
    rows = []
    with (base / "irma/manifest.tsv").open(newline="", encoding="utf-8") as handle:
        manifest = list(csv.DictReader(handle, delimiter="\t"))
    for record in manifest:
        segment = record["segment"]
        missing = record["status"] == "MISSING"
        row = {"sample": sample, "segment": segment,
               "qc": "MISSING" if missing else (base / "coverage_flags" / (segment + ".flag")).read_text().strip()}
        for name, filename in FIELDS:
            row[name] = "MISSING" if missing else status_value(base / "medaka" / segment / filename)
        rows.append(row)
    return rows


def render_fixture(rows):
    fields = ("sample", "segment", "qc") + tuple(name for name, _ in FIELDS)
    parts = ["<!doctype html><html><head><meta charset='utf-8'><title>WINGS synthetic regression test</title></head><body>",
             "<h1>SYNTHETIC TEST: missing-segment dependencies</h1>",
             "<p>Fixture HTML; not a production Quarto report or biological result.</p><table><thead><tr>"]
    parts.extend("<th>" + html.escape(field) + "</th>" for field in fields)
    parts.append("</tr></thead><tbody>")
    for row in rows:
        parts.append("<tr>" + "".join("<td>" + html.escape(str(row[field])) + "</td>" for field in fields) + "</tr>")
    parts.append("</tbody></table></body></html>")
    return "\n".join(parts)


def write_fixture_sample(sample, output):
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_fixture(report_rows(sample)), encoding="utf-8")


def write_fixture_run(inputs, outputs):
    rows = [row for sample in SAMPLE_IDS for row in report_rows(sample)]
    Path(outputs.html).parent.mkdir(parents=True, exist_ok=True)
    Path(outputs.html).write_text(render_fixture(rows), encoding="utf-8")
    audit = {"rows": rows, "requested_status_inputs": {
        name: [str(path) for path in getattr(inputs, name)] for name, _ in FIELDS}}
    Path(outputs.audit).write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")


def build_harness(source, negative=False):
    run_rule = rule_text(source, "run_summary_html")
    sample_rule = rule_text(source, "sample_summary_html")
    run_inputs = ""
    for name, filename in FIELDS:
        entry = input_entry(run_rule, name)
        require("lambda" in entry and "run_medaka_status_inputs" in entry,
                "Run-report inputs are not patched; run wings_update_missing_segments.py --apply first.")
        if negative:
            entry = (f'        {name}=expand(f"{{RESULTS}}/{{{{sample}}}}/medaka/{{{{segment}}}}/{filename}", '
                     'sample=SAMPLES, segment=SEGMENT_SEQUENCE),\n')
        run_inputs += entry
    sample_inputs = "".join(input_entry(sample_rule, name) for name, _ in FIELDS)
    source_helpers = "\n".join(function_text(source, name) for name in HELPERS)
    fixture_helpers = "\n\n".join(inspect.getsource(function) for function in (
        write_table, fixture_checkpoint, fixture_flag, status_value, report_rows,
        render_fixture, write_fixture_sample, write_fixture_run,
    ))
    header = (
        "import csv, html, json\nfrom pathlib import Path\nfrom types import SimpleNamespace\n"
        "shell.executable('/bin/bash')\nRESULTS = 'results'\n"
        f"SEGMENTS = {SEGMENTS!r}\nSEGMENT_SEQUENCE = SEGMENTS\n"
        f"SAMPLE_IDS = {SAMPLE_IDS!r}\nSAMPLES = list(SAMPLE_IDS)\nFIELDS = {FIELDS!r}\n"
        "MEDAKA_MODEL = ''\nMEDAKA_THREADS = 1\nMEDAKA_FAIL_SOFT = False\n"
    )
    checkpoint = '''
checkpoint normalize_irma_outputs:
    output:
        segments=directory(f"{RESULTS}/{{sample}}/irma/segments"),
        manifest=f"{RESULTS}/{{sample}}/irma/manifest.tsv"
    run:
        fixture_checkpoint(wildcards.sample, output.segments, output.manifest)

rule fixture_coverage:
    input:
        manifest=irma_manifest_path
    output:
        flag=f"{RESULTS}/{{sample}}/coverage_flags/{{segment}}.flag"
    run:
        fixture_flag(wildcards.sample, wildcards.segment, output.flag)

'''
    sample = '''
rule sample_summary_html:
    input:
        manifest=irma_manifest_path,
''' + sample_inputs + '''    output:
        html=f"{RESULTS}/{{sample}}/summary/{{sample}}.sample_summary.html"
    run:
        write_fixture_sample(wildcards.sample, output.html)

'''
    run = '''
rule run_summary_html:
    input:
        manifests=lambda wc: [irma_manifest_path(SimpleNamespace(sample=s)) for s in SAMPLES],
        reports=expand(f"{RESULTS}/{{sample}}/summary/{{sample}}.sample_summary.html", sample=SAMPLES),
''' + run_inputs + '''    output:
        html=f"{RESULTS}/run_summary/run_summary.html",
        audit=f"{RESULTS}/run_summary/dependency_audit.json"
    run:
        write_fixture_run(input, output)

'''
    medaka_rules = "\n".join(rule_text(source, name) for name in ("medaka_inference", "medaka_consensus", "medaka_vcf"))
    return header + fixture_helpers + "\n" + source_helpers + "\n" + checkpoint + medaka_rules + sample + run + rule_text(source, "wings_report_bundle")


def prepare_case(root, repo, source, negative):
    root.mkdir()
    (root / "Snakefile").write_text(build_harness(source, negative), encoding="utf-8")
    (root / "scripts").mkdir()
    shutil.copy2(repo / "scripts/build_report_bundle.py", root / "scripts/build_report_bundle.py")
    (root / "envs").mkdir()
    shutil.copy2(repo / "envs/medaka.yaml", root / "envs/medaka.yaml")
    for sample in SAMPLE_IDS:
        # Empty selectors intentionally take the real SKIPPED_NO_MODEL branch.
        write_table(root / "results" / sample / "medaka/model.tsv",
                    [{"fastq": "synthetic", "basecaller_model": "", "medaka_consensus_selector": ""}],
                    ("fastq", "basecaller_model", "medaka_consensus_selector"))
    provenance = {"synthetic_test": True, "scope": "dependency integration; fixture rendering",
                  "source_snakefile_sha256": hashlib.sha256(source.encode()).hexdigest()}
    run_dir = root / "results/run_summary"
    run_dir.mkdir(parents=True)
    (run_dir / "run_provenance.json").write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    (run_dir / "run_provenance.tsv").write_text("synthetic_test\ttrue\n", encoding="utf-8")
    # Prevent accidental execution of a real Medaka installation. Only the
    # version probe is expected in these no-model/QC-failure test paths.
    bin_dir = root / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "medaka"
    shim.write_text("#!/bin/sh\nif [ \"$#\" -eq 1 ] && [ \"$1\" = \"--version\" ]; then\n"
                    "  echo 'SYNTHETIC TEST VERSION PROBE'\n  exit 0\nfi\n"
                    "echo \"$*\" >> unexpected_medaka_calls.txt\nexit 91\n", encoding="utf-8")
    shim.chmod(0o755)


def run_case(root, executable):
    command = [executable, "--snakefile", "Snakefile", "--cores", "1",
               "--profile", "none", "--workflow-profile", "none",
               "--rerun-incomplete", "results/wings_report_bundle.wings"]
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("SNAKEMAKE_") or key == "WINGS_ATTEMPT_PROVENANCE":
            env.pop(key)
    env["PATH"] = str(root / "bin") + os.pathsep + env.get("PATH", "")
    log = root / "snakemake.log"
    (root / "command.json").write_text(json.dumps(command, indent=2), encoding="utf-8")
    with log.open("w", encoding="utf-8") as handle:
        result = subprocess.run(command, cwd=root, env=env, stdout=handle, stderr=subprocess.STDOUT)
    return result.returncode, log.read_text(encoding="utf-8", errors="replace")


def verify_positive(root):
    require(not (root / "unexpected_medaka_calls.txt").exists(), "Unexpected Medaka computation was requested.")
    audit = json.loads((root / "results/run_summary/dependency_audit.json").read_text())
    require(len(audit["rows"]) == 24, "Expected 24 segment rows across three fixture samples.")
    for name, _ in FIELDS:
        inputs = audit["requested_status_inputs"][name]
        require(len(inputs) == 15 and len(set(inputs)) == 15, "Expected exactly 15 available-segment inputs for " + name)
        require(not any("/all_missing/" in path or "/partial/medaka/MP/" in path for path in inputs), "A missing segment was scheduled.")
    for row in audit["rows"]:
        sample, segment = row["sample"], row["segment"]
        missing = sample == "all_missing" or (sample == "partial" and segment == "MP")
        if missing:
            require(row["qc"] == "MISSING" and all(row[name] == "MISSING" for name, _ in FIELDS), "Missing segment not retained as MISSING.")
            require(not (root / "results" / sample / "medaka" / segment).exists(), "Unexpected output directory for missing segment.")
            require(not (root / "results" / sample / "irma/segments" / segment).exists(), "Missing-segment FASTA/BAM was fabricated.")
        else:
            failed_qc = sample == "partial" and segment == "PB2"
            require(row["medaka_inference_status"] == "SKIPPED_NO_MODEL", "Unexpected inference state.")
            require(row["medaka_consensus_status"] == ("SKIPPED_QC" if failed_qc else "UNPOLISHED"), "Unexpected consensus state.")
            require(row["medaka_variant_status"] == ("SKIPPED_QC" if failed_qc else "SKIPPED_NO_MODEL"), "Unexpected variant state.")
    bundle = json.loads((root / "results/wings_report_bundle.wings").read_text())
    require(bundle["format"] == "WINGS_REPORT_BUNDLE" and bundle["version"] == 1, "Invalid bundle format.")
    require(bundle["sample_count"] == 3 and set(bundle["samples"]) == set(SAMPLE_IDS), "Incorrect bundle samples.")
    require(bundle["provenance"]["data"]["synthetic_test"] is True, "Bundle is not identified as synthetic.")
    require(bundle["run_summary"]["html"] == render_fixture(audit["rows"]), "Embedded run report differs from verified fixture rows.")
    for sample in SAMPLE_IDS:
        expected = [row for row in audit["rows"] if row["sample"] == sample]
        require(bundle["samples"][sample]["html"] == render_fixture(expected), "Embedded sample report differs: " + sample)
    return {"fixture_samples": 3, "segment_rows": 24, "available_segments": 15,
            "missing_segments": 9, "qc_failed_available_segments": 1,
            "bundle": str(root / "results/wings_report_bundle.wings")}


def self_check(repo, source):
    """Check source extraction and fixture helpers without Snakemake."""
    positive = build_harness(source)
    negative = build_harness(source, True)
    require(positive != negative, "Negative control does not differ.")
    for name in ("medaka_inference", "medaka_consensus", "medaka_vcf", "wings_report_bundle"):
        require(rule_text(source, name) in positive, "Production rule changed: " + name)
    with tempfile.TemporaryDirectory(prefix="wings-fixture-selfcheck-") as temp:
        root = Path(temp)
        for sample, expected in (("complete", 8), ("partial", 7), ("all_missing", 0)):
            fixture_checkpoint(sample, root / sample / "segments", root / sample / "manifest.tsv")
            require(len(list((root / sample / "segments").glob("*/alignment.bam"))) == expected, "Wrong fixture segment count.")
    require((repo / "scripts/build_report_bundle.py").is_file(), "Bundle builder not found.")
    print("PASS: source extraction and synthetic fixture checks.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--self-check", action="store_true", help="Check fixtures and extraction only; no workflow execution")
    args = parser.parse_args()
    repo = args.repo.resolve()
    source = (repo / "Snakefile").read_text(encoding="utf-8")
    self_check(repo, source)
    if args.self_check:
        return 0
    executable = shutil.which("snakemake")
    require(executable is not None, "Activate your Snakemake environment first; snakemake was not found on PATH.")
    root = Path(tempfile.mkdtemp(prefix="wings-missing-segment-integration-")).resolve()
    print("Test directory: " + str(root), flush=True)
    print("Running patched dependencies (synthetic fixtures; logs saved in the test directory)...", flush=True)
    positive = root / "patched"
    prepare_case(positive, repo, source, False)
    code, log = run_case(positive, executable)
    if code:
        print(log[-8000:])
        raise RuntimeError("Patched workflow failed. Keep and share " + str(positive / "snakemake.log"))
    summary = verify_positive(positive)
    print("PASS: patched dependencies executed and the production builder created a verified synthetic .wings bundle.", flush=True)
    print("Running old dependencies as a negative control (failure is expected)...", flush=True)
    negative = root / "old_dependencies"
    prepare_case(negative, repo, source, True)
    code, log = run_case(negative, executable)
    expected_error = re.search(r"No normalized (?:BAM|FASTA) found for sample=(?:all_missing|partial)", log)
    require(code != 0 and expected_error is not None, "Negative control did not fail for the expected missing-segment reason. See " + str(negative / "snakemake.log"))
    require(not (negative / "results/wings_report_bundle.wings").exists(), "Negative-control bundle unexpectedly exists.")
    print("PASS: old dependencies reproduced the absent-segment input error.", flush=True)
    summary.update({"passed": True, "negative_control": "expected absent-segment input error",
                    "source_snakefile_sha256": hashlib.sha256(source.encode()).hexdigest(),
                    "scope": "real Snakemake checkpoint/status/bundle integration with synthetic upstream and HTML fixtures"})
    (root / "test_summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print("PASS: missing-segment integration test.\nSummary: " + str(root / "test_summary.json"))
    print("Synthetic bundle: " + summary["bundle"])
    print("No repository configuration, sample data, or analysis results were modified.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError, SyntaxError, KeyError) as error:
        print("FAIL: " + str(error), file=sys.stderr)
        sys.exit(1)
