from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = REPO_ROOT / "tests" / "integration10"
WORK = HERE / "work"
RESULTS = WORK / "results"
SAMPLE = "phase10"
SAMPLE_DIR = RESULTS / SAMPLE


def read_one_tsv(path: Path) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8") as handle:
        return next(csv.DictReader(handle, delimiter="\t"))


def test_production_sample_summary_reporting():
    subprocess.run(
        [sys.executable, str(HERE / "prepare_fixtures.py")],
        cwd=REPO_ROOT,
        check=True,
    )

    subprocess.run(
        [
            "snakemake",
            "--snakefile",
            str(HERE / "prepare_assets.smk"),
            "--cores",
            "1",
            "--sdm",
            "conda",
            "--rerun-incomplete",
        ],
        cwd=REPO_ROOT,
        check=True,
    )

    target = (
        f"tests/integration10/work/results/{SAMPLE}/summary/"
        f"{SAMPLE}.sample_summary.html"
    )

    # Production reporting chain. Full IRMA, fastplong, GenoFLU, VADR, and
    # Medaka VCF generation are deliberately outside this test; their direct
    # reporting inputs are deterministic fixtures.
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
            "normalize_irma_outputs",
            "check_coverage",
            "coverage_table",
            "resolve_medaka_model",
            "medaka_inference",
            "medaka_consensus",
            "blastn",
            "summarize_blast",
            "concat_consensus",
            "detect_h5n1",
            "sample_summary",
            "sample_summary_html",
            "--rerun-incomplete",
        ],
        cwd=REPO_ROOT,
        check=True,
    )

    summary_path = (
        SAMPLE_DIR / "summary" / f"{SAMPLE}.sample_summary.tsv"
    )
    html_path = (
        SAMPLE_DIR / "summary" / f"{SAMPLE}.sample_summary.html"
    )

    assert summary_path.stat().st_size > 0
    assert html_path.stat().st_size > 0

    row = read_one_tsv(summary_path)

    # Metadata propagation, including analytical-name collision protection.
    assert row["sample"] == SAMPLE
    assert row["sample_id"] == SAMPLE
    assert row["host_species"] == "Anas platyrhynchos"
    assert row["collection_location"] == "Phoenix, Arizona"
    assert row["flyway"] == "Pacific"
    assert row["project_code"] == "P10-REPORT"
    assert row["metadata_segments_pass"] == "field_value"

    # Analytical values must remain authoritative.
    assert row["reads_before"] == "1000"
    assert row["reads_after"] == "900"
    assert row["segments_detected"] == "8"
    assert row["segments_pass"] == "1"
    assert row["pass_segment_names"] == "HA"
    assert set(row["failed_segment_names"].split(",")) == {
        "NA", "PB2", "PB1", "PA", "NP", "MP", "NS"
    }

    assert row["ha_contig"] == "A_HA_H5_PHASE10"
    assert row["na_contig"] == "A_NA_N1_PHASE10"
    assert row["ha_median_depth"] == "60.00"
    assert row["na_median_depth"] == "20.00"

    # NA is informative at assembly level but fails QC, so the H5N1 screen is
    # indeterminate rather than a biological negative. GenoFLU is disabled by
    # configuration in this reporting-focused integration test.
    assert row["h5_screen"] == "INDETERMINATE"
    assert row["genoflu_status"] == "DISABLED_BY_CONFIG"
    assert row["consensus_segments"] == "1"

    flags = set(row["review_flags"].split(";"))
    assert "fewer_than_8_pass_segments" in flags
    assert "h5_screen_indeterminate" in flags
    assert "coverage_failures" in flags

    assert "PHASE10_H5_REFERENCE" in row["ha_top_blast_hit"]
    assert row["na_top_blast_hit"] == "SKIPPED_QC"

    html = html_path.read_text(encoding="utf-8", errors="replace")
    assert "WINGS" in html
    assert "Wild-bird Influenza Genomics and Surveillance" in html
    assert "Sample phase10" in html
    assert "Anas platyrhynchos" in html
    assert "Phoenix, Arizona" in html
    assert "Pacific" in html
    assert "INDETERMINATE" in html
    assert "PHASE10_H5_REFERENCE" in html
