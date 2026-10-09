from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = REPO_ROOT / "tests" / "integration11"
WORK = HERE / "work"
RESULTS = WORK / "results"
RUN_DIR = RESULTS / "run_summary"


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def test_production_run_summary_integration():
    subprocess.run(
        [sys.executable, str(HERE / "prepare_fixtures.py")],
        cwd=REPO_ROOT,
        check=True,
    )

    target = "tests/integration11/work/results/run_summary/run_summary.html"

    # Only the real production run-level report rule executes. Its complete set
    # of per-sample inputs is deterministic fixture data representing outputs
    # already validated in earlier integration phases.
    subprocess.run(
        [
            "snakemake",
            "--snakefile",
            "Snakefile",
            target,
            "--configfile",
            str(HERE / "config.yaml"),
            "--cores",
            "1",
            "--sdm",
            "conda",
            "--allowed-rules",
            "run_summary_html",
            "--rerun-incomplete",
        ],
        cwd=REPO_ROOT,
        check=True,
    )

    html_path = RUN_DIR / "run_summary.html"
    tsv_path = RUN_DIR / "run_summary.tsv"
    review_path = RUN_DIR / "samples_requiring_review.tsv"

    assert html_path.stat().st_size > 0
    assert tsv_path.stat().st_size > 0
    assert review_path.stat().st_size > 0

    rows = read_tsv(tsv_path)
    by_sample = {row["sample_id"]: row for row in rows}

    assert set(by_sample) == {"complete", "near_complete", "partial", "failed"}

    assert by_sample["complete"]["genome_status"] == "Complete"
    assert by_sample["near_complete"]["genome_status"] == "Near-complete"
    assert by_sample["partial"]["genome_status"] == "Partial"
    assert by_sample["failed"]["genome_status"] == "Failed"

    assert by_sample["complete"]["review_required"].lower() == "false"
    assert by_sample["near_complete"]["review_required"].lower() == "true"
    assert by_sample["partial"]["review_required"].lower() == "true"
    assert by_sample["failed"]["review_required"].lower() == "true"

    # Subtypes are derived by the production run-summary logic from HA/NA
    # contig names when explicit ha_call/na_call fields are absent.
    assert by_sample["complete"]["ha_call"] == "H3"
    assert by_sample["complete"]["na_call"] == "N2"
    assert by_sample["complete"]["potential_subtype"] == "H3N2"

    assert by_sample["near_complete"]["ha_call"] == "H5"
    assert by_sample["near_complete"]["na_call"] == "N1"
    assert by_sample["near_complete"]["potential_subtype"] == "H5N1"

    assert by_sample["failed"]["ha_call"] == "Unknown"
    assert by_sample["failed"]["na_call"] == "Unknown"

    # Explicit Medaka status aggregation.
    assert by_sample["complete"]["medaka_polished_segments"] == "8"
    assert by_sample["complete"]["medaka_skipped_qc_segments"] == "0"
    assert by_sample["near_complete"]["medaka_polished_segments"] == "7"
    assert by_sample["near_complete"]["medaka_skipped_qc_segments"] == "1"
    assert by_sample["partial"]["medaka_polished_segments"] == "3"
    assert by_sample["partial"]["medaka_skipped_qc_segments"] == "5"
    assert by_sample["failed"]["medaka_polished_segments"] == "0"
    assert by_sample["failed"]["medaka_skipped_qc_segments"] == "8"

    # Arbitrary metadata from sample summaries remains available in run_summary.tsv.
    assert by_sample["complete"]["project_code"] == "RUN11-A"
    assert by_sample["failed"]["project_code"] == "RUN11-D"

    review_rows = read_tsv(review_path)
    review_samples = {row["sample_id"] for row in review_rows}
    assert review_samples == {"near_complete", "partial", "failed"}

    html = html_path.read_text(encoding="utf-8", errors="replace")
    assert "WINGS" in html
    assert "Wild-bird Influenza Genomics and Surveillance" in html
    assert "Run Summary" in html
    assert "Complete" in html
    assert "Near-complete" in html
    assert "Partial" in html
    assert "Failed" in html
    assert "H5N1" in html
    assert "Mallard" in html
    assert "Northern Pintail" in html
    assert "Green-winged Teal" in html
    assert '<div class="alert alert-secondary" role="note">' in html
    assert "No historical comparison is available yet." in html
    assert '&lt;div class="alert alert-secondary"' not in html
