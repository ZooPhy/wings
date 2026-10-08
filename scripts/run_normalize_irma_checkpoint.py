#!/usr/bin/env python3
"""Run IRMA normalization inside the rule-specific Snakemake environment."""

import csv
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


SEGMENT_SEQUENCE = ("HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS")


project_path = Path(str(snakemake.input.project)).resolve()
normalizer_path = Path(str(snakemake.input.normalizer)).resolve()
segments_path = Path(str(snakemake.output.segments)).resolve()
manifest_path = Path(str(snakemake.output.manifest)).resolve()
log_path = Path(str(snakemake.log[0])).resolve()
sample = str(snakemake.params.sample)

segments_path.parent.mkdir(parents=True, exist_ok=True)
manifest_path.parent.mkdir(parents=True, exist_ok=True)
log_path.parent.mkdir(parents=True, exist_ok=True)


def remove_partial_normalized_outputs() -> None:
    if segments_path.exists():
        shutil.rmtree(segments_path, ignore_errors=True)
    if manifest_path.exists():
        manifest_path.unlink()


if segments_path.exists():
    shutil.rmtree(segments_path)

if manifest_path.exists():
    manifest_path.unlink()


normalize_command = [
    sys.executable,
    str(normalizer_path),
    "--project",
    str(project_path),
    "--segments",
    str(segments_path),
    "--manifest",
    str(manifest_path),
    "--sample",
    sample,
]


with log_path.open("w") as log_handle:
    log_handle.write(
        "Normalization command: " + shlex.join(normalize_command) + "\n"
    )
    log_handle.flush()

    try:
        subprocess.run(
            normalize_command,
            check=True,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        log_handle.write(
            "\nESCAPE_STATUS=IRMA_NORMALIZATION_FAILED\n"
            f"NORMALIZER_RETURN_CODE={exc.returncode}\n"
        )
        log_handle.flush()
        remove_partial_normalized_outputs()
        raise RuntimeError(
            f"IRMA output normalization failed for sample {sample}. "
            f"See {log_path}."
        ) from exc


if not manifest_path.is_file() or manifest_path.stat().st_size == 0:
    remove_partial_normalized_outputs()
    with log_path.open("a") as log_handle:
        log_handle.write(
            "\nESCAPE_STATUS=IRMA_NORMALIZATION_FAILED\n"
            "NORMALIZER_ERROR=missing_or_empty_manifest\n"
        )
    raise RuntimeError(
        f"IRMA normalization did not create a non-empty manifest "
        f"for sample {sample}. See {log_path}."
    )


with manifest_path.open(encoding="utf-8", errors="replace") as handle:
    reader = csv.DictReader(handle, delimiter="\t")
    required_columns = {"segment", "status"}

    if (
        reader.fieldnames is None
        or not required_columns.issubset(reader.fieldnames)
    ):
        fieldnames = reader.fieldnames or []
        remove_partial_normalized_outputs()

        with log_path.open("a") as log_handle:
            log_handle.write(
                "\nESCAPE_STATUS=IRMA_NORMALIZATION_FAILED\n"
                "NORMALIZER_ERROR=malformed_manifest\n"
            )

        raise RuntimeError(
            f"IRMA manifest for sample {sample} is malformed; "
            f"required columns are {sorted(required_columns)}, "
            f"found {fieldnames}. See {log_path}."
        )

    manifest_rows = list(reader)


ready_segments = sorted(
    {
        row.get("segment", "")
        for row in manifest_rows
        if row.get("status") == "READY"
        and row.get("segment") in SEGMENT_SEQUENCE
    },
    key=SEGMENT_SEQUENCE.index,
)


with log_path.open("a") as log_handle:
    log_handle.write("\nESCAPE_STATUS=IRMA_NORMALIZATION_COMPLETED\n")
    log_handle.write(
        f"ESCAPE_READY_SEGMENT_COUNT={len(ready_segments)}\n"
    )
    log_handle.write(
        "ESCAPE_READY_SEGMENTS="
        + (",".join(ready_segments) if ready_segments else "NONE")
        + "\n"
    )
