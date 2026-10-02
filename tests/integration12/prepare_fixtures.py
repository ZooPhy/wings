#!/usr/bin/env python3
from __future__ import annotations

import gzip
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / "tests" / "integration12"
WORK = HERE / "work"
DATA = WORK / "data"
RESULTS = WORK / "results"

SAMPLES = ("bundle_alpha", "bundle_beta")


def main() -> None:
    if WORK.exists():
        shutil.rmtree(WORK)

    DATA.mkdir(parents=True)

    # The production Snakefile discovers samples from FASTQ filenames.
    for sample in SAMPLES:
        with gzip.open(DATA / f"{sample}.fastq.gz", "wt", encoding="utf-8") as handle:
            handle.write("@fixture\nACGT\n+\nIIII\n")

    metadata_text = (
        "sample_id\thost_common_name\tstate\tcountry\n"
        "bundle_alpha\tMallard\tArizona\tUSA\n"
        "bundle_beta\tNorthern Pintail\tNevada\tUSA\n"
    )
    (WORK / "metadata.tsv").write_text(
        metadata_text,
        encoding="utf-8",
    )

    metadata_dir = RESULTS / "metadata"
    metadata_dir.mkdir(parents=True)
    (metadata_dir / "validated_metadata.tsv").write_text(
        metadata_text,
        encoding="utf-8",
    )

    run_dir = RESULTS / "run_summary"
    run_dir.mkdir(parents=True)
    (run_dir / "run_summary.html").write_text(
        """<!doctype html>
<html>
<head><meta charset="utf-8"><title>WINGS Phase 12 Run Summary</title></head>
<body>
<h1>WINGS — Wild-bird Influenza Genomics and Surveillance</h1>
<h2>Run Summary Report</h2>
<p id="fixture-marker">PHASE12_RUN_SUMMARY</p>
<p>Samples: bundle_alpha, bundle_beta</p>
</body>
</html>
""",
        encoding="utf-8",
    )

    for sample in SAMPLES:
        summary_dir = RESULTS / sample / "summary"
        summary_dir.mkdir(parents=True)
        (summary_dir / f"{sample}.sample_summary.html").write_text(
            f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>WINGS {sample}</title></head>
<body>
<h1>WINGS — Wild-bird Influenza Genomics and Surveillance</h1>
<h2>Sample {sample}</h2>
<p id="fixture-marker">PHASE12_{sample.upper()}</p>
</body>
</html>
""",
            encoding="utf-8",
        )

    print(
        "Prepared Phase 12 bundle fixtures for: "
        + ", ".join(SAMPLES)
    )


if __name__ == "__main__":
    main()
