#!/usr/bin/env python3
"""Replace integration7 placeholder BAMs with tiny valid BAM fixtures."""

from pathlib import Path

import pysam


project = Path(str(snakemake.params.project)).resolve()
alignments = project / "alignments"


def write_bam(path: Path, read_count: int) -> None:
    reference_name = path.stem.replace("\\", "")

    header = pysam.AlignmentHeader.from_dict(
        {
            "HD": {"VN": "1.6", "SO": "coordinate"},
            "SQ": [{"SN": reference_name, "LN": 2500}],
        }
    )

    with pysam.AlignmentFile(str(path), "wb", header=header) as bam:
        for i in range(read_count):
            record = pysam.AlignedSegment(header)
            record.query_name = f"{reference_name}_read_{i:03d}"
            record.query_sequence = "ACGT" * 25
            record.flag = 0
            record.reference_id = 0
            record.reference_start = 100 + (i * 10)
            record.mapping_quality = 60
            record.cigar = ((0, 100),)
            record.query_qualities = pysam.qualitystring_to_array("I" * 100)
            bam.write(record)

    pysam.index(str(path))


for bam_path in sorted(alignments.glob("*.bam")):
    if "HIGH" in bam_path.name:
        read_count = 3
    elif "LOW" in bam_path.name:
        read_count = 2
    else:
        read_count = 1

    write_bam(bam_path, read_count)


stamp = Path(str(snakemake.output.stamp)).resolve()
stamp.parent.mkdir(parents=True, exist_ok=True)
stamp.touch()
