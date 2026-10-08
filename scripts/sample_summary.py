#!/usr/bin/env python3

import csv
import json
from pathlib import Path


def read_fastplong_json(path: Path) -> dict:
    with path.open() as handle:
        data = json.load(handle)

    summary = data.get("summary", {})
    before = summary.get("before_filtering", {})
    after = summary.get("after_filtering", {})
    filtering = data.get("filtering_result", {})
    adapter_cutting = data.get("adapter_cutting", {})

    return {
        "reads_before": before.get("total_reads", "NA"),
        "bases_before": before.get("total_bases", "NA"),
        "q20_rate_before": before.get("q20_rate", "NA"),
        "q30_rate_before": before.get("q30_rate", "NA"),
        "reads_after": after.get("total_reads", "NA"),
        "bases_after": after.get("total_bases", "NA"),
        "q20_rate_after": after.get("q20_rate", "NA"),
        "q30_rate_after": after.get("q30_rate", "NA"),
        "reads_passed": filtering.get("passed_filter_reads", "NA"),
        "reads_low_quality": filtering.get("low_quality_reads", "NA"),
        "reads_too_short": filtering.get("too_short_reads", "NA"),
        "reads_with_adapters": adapter_cutting.get("adapter_trimmed_reads", "NA"),
    }


def read_coverage(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_metadata(path: Path) -> dict[str, str]:
    if not path.is_file() or path.stat().st_size == 0:
        return {}

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        row = next(reader, None)

    if not row:
        return {}

    return {
        str(key).strip(): ("" if value is None else str(value).strip())
        for key, value in row.items()
        if key is not None and str(key).strip()
    }


def read_blast(path: Path) -> dict[str, str]:
    hits = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            hits[row["segment"]] = row["top_hit"]
    return hits


def read_h5_flag(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    status = path.read_text().strip().upper() or "MISSING"
    # Backward compatibility for reports generated from older WINGS outputs.
    if status == "PASS":
        return "DETECTED"
    if status == "FAIL":
        return "INDETERMINATE"
    return status


def read_genoflu(path: Path | None) -> str:
    if path is None:
        return "DISABLED_BY_CONFIG"

    if not path.exists() or path.stat().st_size == 0:
        return "MISSING"

    lines = [
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip()
    ]
    if not lines:
        return "MISSING"

    if len(lines) == 2 and lines[0].startswith("sample	status"):
        return lines[1].split("	", 1)[-1]

    return "COMPLETED"


def count_fasta_records(path: Path) -> int:
    if not path.exists():
        return 0

    count = 0
    with path.open() as handle:
        for line in handle:
            if line.startswith(">"):
                count += 1
    return count


def write_summary(
    output_path: Path,
    sample: str,
    fastplong: dict,
    coverage_rows: list[dict],
    blast_hits: dict[str, str],
    h5_status: str,
    genoflu_status: str,
    consensus_segments: int,
    metadata: dict[str, str] | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pass_segments = [
        row["segment"]
        for row in coverage_rows
        if row.get("coverage_flag") == "PASS"
    ]

    failed_segments = [
        row["segment"]
        for row in coverage_rows
        if row.get("coverage_flag") == "FAIL"
    ]

    missing_segments = [
        row["segment"]
        for row in coverage_rows
        if row.get("coverage_flag") == "MISSING"
    ]
    ha_rows = [row for row in coverage_rows if row.get("segment") == "HA"]
    na_rows = [row for row in coverage_rows if row.get("segment") == "NA"]

    ha_contig = ha_rows[0].get("contig", "NA") if ha_rows else "NA"
    na_contig = na_rows[0].get("contig", "NA") if na_rows else "NA"
    ha_median_depth = ha_rows[0].get("median_depth", "NA") if ha_rows else "NA"
    na_median_depth = na_rows[0].get("median_depth", "NA") if na_rows else "NA"


    multiple_candidate_rows = []
    for row in coverage_rows:
        try:
            candidate_count = int(row.get("candidate_count") or 0)
        except (TypeError, ValueError):
            candidate_count = 0
        if candidate_count > 1:
            multiple_candidate_rows.append((row.get("segment", "NA"), candidate_count))

    multiple_candidate_segments = [segment for segment, _ in multiple_candidate_rows]
    max_irma_candidate_count = max((count for _, count in multiple_candidate_rows), default=1)

    review_flags = []

    if len(pass_segments) < 8:
        review_flags.append("fewer_than_8_pass_segments")

    # A valid NOT_DETECTED H5 eligibility result is not itself a QC problem.
    # DETECTED warrants attention as an H5 surveillance finding. INDETERMINATE
    # warrants review because QC-passing HA plus a resolved QC-passing NA are
    # required before GenoFLU is eligible to run.
    if h5_status == "DETECTED":
        review_flags.append("h5_screen_detected")
    elif h5_status != "NOT_DETECTED":
        review_flags.append("h5_screen_indeterminate")

    if failed_segments:
        review_flags.append("coverage_failures")

    if consensus_segments == 0:
        review_flags.append("no_consensus_segments")

    if multiple_candidate_segments:
        review_flags.append("multiple_irma_candidates")

    analytical_fields = [
        "reads_before",
        "reads_after",
        "bases_before",
        "bases_after",
        "q20_rate_before",
        "q20_rate_after",
        "q30_rate_before",
        "q30_rate_after",
        "reads_passed",
        "reads_low_quality",
        "reads_too_short",
        "reads_with_adapters",
        "segments_detected",
        "segments_pass",
        "pass_segment_names",
        "failed_segment_names",
        "segments_missing",
        "missing_segment_names",
        "ha_contig",
        "na_contig",
        "ha_median_depth",
        "na_median_depth",
        "h5_screen",
        "genoflu_status",
        "consensus_segments",
        "multiple_irma_candidate_segments",
        "multiple_irma_candidate_count",
        "max_irma_candidate_count",
        "review_flags",
        "ha_top_blast_hit",
        "na_top_blast_hit",
    ]

    metadata = dict(metadata or {})
    normalized_metadata = {}
    reserved_fields = {"sample", *analytical_fields}

    for key, value in metadata.items():
        output_key = key if key not in reserved_fields else f"metadata_{key}"
        normalized_metadata[output_key] = value

    metadata_fields = list(normalized_metadata)
    fieldnames = ["sample", *metadata_fields, *analytical_fields]
    detected_segments = [
        row["segment"]
        for row in coverage_rows
        if row.get("coverage_flag") != "MISSING"
    ]
    row = {
    "sample": sample,
    **normalized_metadata,
    **fastplong,
    "segments_detected": len(detected_segments),
    "segments_pass": len(pass_segments),
    "pass_segment_names": ",".join(pass_segments) or "NONE",
    "failed_segment_names": ",".join(failed_segments) or "NONE",
    "segments_missing": len(missing_segments),
    "missing_segment_names": ",".join(missing_segments) or "NONE",
    "ha_contig": ha_contig,
    "na_contig": na_contig,
    "ha_median_depth": ha_median_depth,
    "na_median_depth": na_median_depth,
    "h5_screen": h5_status,
    "genoflu_status": genoflu_status,
    "consensus_segments": consensus_segments,
    "multiple_irma_candidate_segments": ",".join(multiple_candidate_segments) or "NONE",
    "multiple_irma_candidate_count": len(multiple_candidate_segments),
    "max_irma_candidate_count": max_irma_candidate_count,
    "review_flags": ";".join(review_flags) or "NONE",
    "ha_top_blast_hit": blast_hits.get("HA", "NO_HIT"),
    "na_top_blast_hit": blast_hits.get("NA", "NO_HIT"),}

    with output_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerow(row)


def main() -> None:
    sample = snakemake.wildcards.sample

    metadata = read_metadata(Path(snakemake.input.metadata))
    fastplong = read_fastplong_json(Path(snakemake.input.fastplong))
    coverage_rows = read_coverage(Path(snakemake.input.coverage))
    blast_hits = read_blast(Path(snakemake.input.blast))
    h5_input = getattr(snakemake.input, "h5", None)
    if h5_input is None:
        # Temporary compatibility with Snakefiles that still name this input "h5n1".
        h5_input = getattr(snakemake.input, "h5n1")
    h5_status = read_h5_flag(Path(h5_input))
    genoflu_file = str(
        getattr(snakemake.params, "genoflu_file", "") or ""
    ).strip()
    genoflu_status = read_genoflu(
        Path(genoflu_file) if genoflu_file else None
    )
    consensus_segments = count_fasta_records(Path(snakemake.input.consensus))

    write_summary(
        output_path=Path(snakemake.output.tsv),
        sample=sample,
        fastplong=fastplong,
        coverage_rows=coverage_rows,
        blast_hits=blast_hits,
        h5_status=h5_status,
        genoflu_status=genoflu_status,
        consensus_segments=consensus_segments,
        metadata=metadata,
    )


if __name__ == "__main__":
    main()
