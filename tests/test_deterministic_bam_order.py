import importlib.util
import sys
from pathlib import Path

import pytest

pysam = pytest.importorskip("pysam")

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "normalize_irma_outputs.py"

spec = importlib.util.spec_from_file_location("normalize_irma_outputs", SCRIPT)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def make_record(header, name, start, sequence):
    record = pysam.AlignedSegment(header)
    record.query_name = name
    record.query_sequence = sequence
    record.flag = 0
    record.reference_id = 0
    record.reference_start = start
    record.mapping_quality = 60
    record.cigar = ((0, len(sequence)),)
    record.query_qualities = pysam.qualitystring_to_array("I" * len(sequence))
    return record


def write_bam(path, order):
    header = pysam.AlignmentHeader.from_dict(
        {
            "HD": {"VN": "1.6", "SO": "coordinate"},
            "SQ": [{"SN": "A_NP", "LN": 1000}],
        }
    )

    records = {
        "read_a": make_record(header, "read_a", 100, "ACGT"),
        "read_b": make_record(header, "read_b", 100, "ACGA"),
        "read_c": make_record(header, "read_c", 100, "ACGG"),
        "read_d": make_record(header, "read_d", 200, "TTTT"),
    }

    with pysam.AlignmentFile(path, "wb", header=header) as bam:
        for name in order:
            bam.write(records[name])


def decoded_records(path):
    with pysam.AlignmentFile(path, "rb") as bam:
        return [
            record.to_string()
            for record in bam.fetch(until_eof=True)
        ]


def test_canonicalize_bam_is_independent_of_equal_coordinate_record_order(tmp_path):
    first = tmp_path / "first.bam"
    second = tmp_path / "second.bam"
    first_out = tmp_path / "first.normalized.bam"
    second_out = tmp_path / "second.normalized.bam"

    write_bam(
        first,
        ["read_c", "read_a", "read_b", "read_d"],
    )
    write_bam(
        second,
        ["read_b", "read_c", "read_a", "read_d"],
    )

    module.canonicalize_bam(first, first_out, chunk_size=2)
    module.canonicalize_bam(second, second_out, chunk_size=2)

    assert decoded_records(first_out) == decoded_records(second_out)

    names = [
        line.split("\t", 1)[0]
        for line in decoded_records(first_out)
    ]
    assert names == ["read_a", "read_b", "read_c", "read_d"]

    pysam.index(str(first_out))
    pysam.index(str(second_out))

    assert Path(f"{first_out}.bai").is_file()
    assert Path(f"{second_out}.bai").is_file()
