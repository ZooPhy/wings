#!/usr/bin/env python3
"""Build the data bundle used by the WINGS Surveillance Explorer.

The explorer deliberately treats supplied phylogenies as visualization inputs.
It displays the first Newick tree in each configured file and does not infer,
reroot, date, or otherwise modify a phylogeny.
"""


import argparse
import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

SEGMENT_ORDER = ("HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS")
MISSING_TEXT = {"", "NA", "N/A", "NONE", "NAN", "NULL", "UNKNOWN"}


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return default if text.upper() in MISSING_TEXT else text


def _number(value: Any) -> float | None:
    text = _clean(value)
    if not text:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _integer(value: Any) -> int | None:
    number = _number(value)
    if number is None:
        return None
    return int(number)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def read_metadata(path: Path) -> list[dict[str, str]]:
    rows = read_tsv(path)
    if not rows:
        raise ValueError(f"Metadata file is empty: {path}")

    fields = set(rows[0])
    sample_field = "sample_id" if "sample_id" in fields else "sample" if "sample" in fields else None
    if sample_field is None:
        raise ValueError("Metadata must contain a sample_id or sample column")

    seen: set[str] = set()
    normalized: list[dict[str, str]] = []
    for row in rows:
        sample_id = _clean(row.get(sample_field))
        if not sample_id:
            raise ValueError("Metadata contains a row with an empty sample identifier")
        if sample_id in seen:
            raise ValueError(f"Metadata contains duplicate sample identifier: {sample_id}")
        seen.add(sample_id)
        normalized.append({**row, "sample_id": sample_id})
    return normalized


def read_sample_summaries(paths: Iterable[Path]) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for path in paths:
        if not path.is_file() or path.stat().st_size == 0:
            continue
        rows = read_tsv(path)
        if not rows:
            continue
        row = rows[0]
        sample_id = _clean(row.get("sample_id") or row.get("sample"))
        if not sample_id:
            # The standard WINGS path embeds the sample ID in the parent directory.
            sample_id = path.parent.parent.name
        result[sample_id] = row
    return result


def normalize_h5_status(row: dict[str, str]) -> str:
    if not row:
        return "NOT_RECORDED"
    status = _clean(row.get("h5_screen") or row.get("h5n1_screen"), "INDETERMINATE").upper()
    if status == "PASS":
        return "DETECTED"
    if status == "FAIL":
        return "INDETERMINATE"
    if status not in {"DETECTED", "NOT_DETECTED", "INDETERMINATE"}:
        return "INDETERMINATE"
    return status


def extract_subtype(value: Any, prefix: str) -> str:
    text = _clean(value)
    if not text:
        return ""
    match = re.search(rf"(?:^|_){re.escape(prefix)}(\d+)(?:_|$)", text, flags=re.IGNORECASE)
    return f"{prefix.upper()}{match.group(1)}" if match else ""


def build_sample_records(
    metadata_rows: list[dict[str, str]],
    summaries: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for meta in metadata_rows:
        sample_id = meta["sample_id"]
        summary = summaries.get(sample_id, {})
        ha_call = _clean(summary.get("ha_call")) or extract_subtype(summary.get("ha_contig"), "H")
        na_call = _clean(summary.get("na_call")) or extract_subtype(summary.get("na_contig"), "N")
        subtype = _clean(summary.get("potential_subtype"))
        if not subtype:
            subtype = f"{ha_call}{na_call}" if ha_call and na_call else ha_call or na_call or "Undetermined"

        latitude = _number(meta.get("latitude"))
        longitude = _number(meta.get("longitude"))
        has_coordinates = latitude is not None and longitude is not None

        samples.append(
            {
                "sample_id": sample_id,
                "host": _clean(meta.get("host") or meta.get("host_common_name") or meta.get("host_species"), "Unknown"),
                "host_common_name": _clean(meta.get("host_common_name")),
                "host_species": _clean(meta.get("host_species")),
                "specimen_type": _clean(meta.get("specimen_type") or meta.get("sample_type"), "Unknown"),
                "collection_date": _clean(meta.get("collection_date"), "Unknown"),
                "state": _clean(meta.get("state"), "Unknown"),
                "country": _clean(meta.get("country"), "Unknown"),
                "flyway": _clean(meta.get("flyway"), "Unknown"),
                "latitude": latitude,
                "longitude": longitude,
                "has_coordinates": has_coordinates,
                "h5_status": normalize_h5_status(summary),
                "ha_call": ha_call or "Unknown",
                "na_call": na_call or "Unknown",
                "potential_subtype": subtype,
                "segments_pass": _integer(summary.get("segments_pass") or summary.get("pass_segments")),
                "review_flags": _clean(summary.get("review_flags"), "NONE"),
                "report_href": f"../{sample_id}/summary/{sample_id}.sample_summary.html",
            }
        )
    return samples


class NewickParser:
    def __init__(self, text: str):
        self.text = text.strip()
        self.i = 0

    def peek(self) -> str:
        return self.text[self.i] if self.i < len(self.text) else ""

    def consume(self, expected: str | None = None) -> str:
        if self.i >= len(self.text):
            raise ValueError("Unexpected end of Newick tree")
        ch = self.text[self.i]
        if expected is not None and ch != expected:
            raise ValueError(f"Expected {expected!r} at position {self.i}, found {ch!r}")
        self.i += 1
        return ch

    def skip_ws(self) -> None:
        while self.peek() and self.peek().isspace():
            self.i += 1

    def parse_label(self) -> str:
        self.skip_ws()
        if self.peek() == "'":
            self.consume("'")
            parts: list[str] = []
            while self.peek():
                if self.peek() == "'":
                    self.consume("'")
                    if self.peek() == "'":
                        self.consume("'")
                        parts.append("'")
                        continue
                    break
                parts.append(self.consume())
            return "".join(parts).strip()

        start = self.i
        while self.peek() and self.peek() not in ":,();":
            self.i += 1
        return self.text[start:self.i].strip()

    def parse_length(self) -> float | None:
        self.skip_ws()
        if self.peek() != ":":
            return None
        self.consume(":")
        self.skip_ws()
        start = self.i
        while self.peek() and self.peek() not in ",();":
            self.i += 1
        token = self.text[start:self.i].strip()
        if not token:
            return None
        try:
            return float(token)
        except ValueError as exc:
            raise ValueError(f"Invalid Newick branch length: {token!r}") from exc

    def parse_node(self) -> dict[str, Any]:
        self.skip_ws()
        children: list[dict[str, Any]] = []
        if self.peek() == "(":
            self.consume("(")
            while True:
                children.append(self.parse_node())
                self.skip_ws()
                if self.peek() == ",":
                    self.consume(",")
                    continue
                if self.peek() == ")":
                    self.consume(")")
                    break
                raise ValueError(f"Malformed Newick near position {self.i}")

        label = self.parse_label()
        length = self.parse_length()
        node: dict[str, Any] = {"length": length if length is not None else 0.0}
        if children:
            node["children"] = children
            if label:
                node["label"] = label
                try:
                    node["support"] = float(label)
                except ValueError:
                    pass
        else:
            if not label:
                raise ValueError("Newick leaf is missing a taxon name")
            node["name"] = label
        return node

    def parse(self) -> dict[str, Any]:
        root = self.parse_node()
        self.skip_ws()
        if self.peek() == ";":
            self.consume(";")
        self.skip_ws()
        if self.i != len(self.text):
            raise ValueError(f"Unexpected text after Newick tree at position {self.i}")
        return root


def first_newick_tree_and_count(path: Path) -> tuple[str, int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    first_end = text.find(";")
    if first_end < 0:
        raise ValueError(f"No complete Newick tree found in {path}")
    first = text[: first_end + 1].strip()
    tree_count = text.count(";")
    return first, tree_count


def map_tip_to_sample(tip: str, sample_ids: set[str]) -> str | None:
    if "__" in tip:
        candidate = tip.split("__", 1)[0]
        if candidate in sample_ids:
            return candidate

    # Backward-compatible fallback for labels such as sample_A_HA_H5.
    matches = [sample_id for sample_id in sample_ids if tip == sample_id or tip.startswith(sample_id + "_")]
    return max(matches, key=len) if matches else None


def annotate_tree_samples(node: dict[str, Any], sample_ids: set[str], unmatched: list[str]) -> int:
    children = node.get("children")
    if children:
        return sum(annotate_tree_samples(child, sample_ids, unmatched) for child in children)
    tip = str(node.get("name", ""))
    sample_id = map_tip_to_sample(tip, sample_ids)
    node["sample_id"] = sample_id
    if sample_id is None:
        unmatched.append(tip)
    return 1


def infer_segment_from_path(path: Path) -> str | None:
    upper = path.name.upper()
    for segment in SEGMENT_ORDER:
        if re.search(rf"(?:^|[^A-Z0-9]){segment}(?:[^A-Z0-9]|$)", upper):
            return segment
    stem = path.stem.upper()
    for segment in SEGMENT_ORDER:
        if stem.startswith(segment):
            return segment
    return None


def build_tree_records(tree_paths: Iterable[Path], sample_ids: set[str]) -> tuple[dict[str, Any], list[str]]:
    trees: dict[str, Any] = {}
    warnings: list[str] = []
    for path in tree_paths:
        segment = infer_segment_from_path(path)
        if segment is None:
            warnings.append(f"Could not infer influenza segment from tree filename: {path.name}")
            continue
        if segment in trees:
            warnings.append(f"Multiple {segment} tree files supplied; using the first and ignoring {path.name}")
            continue

        first_tree, tree_count = first_newick_tree_and_count(path)
        root = NewickParser(first_tree).parse()
        unmatched: list[str] = []
        tip_count = annotate_tree_samples(root, sample_ids, unmatched)
        if unmatched:
            warnings.append(
                f"{segment} tree contains {len(unmatched)} tip(s) that do not match metadata sample IDs"
            )

        trees[segment] = {
            "segment": segment,
            "source_file": path.name,
            "tree_count_in_file": tree_count,
            "displayed_tree_index": 1,
            "tip_count": tip_count,
            "unmatched_tip_count": len(unmatched),
            "root": root,
        }
    return trees, warnings


def build_payload(
    metadata: Path,
    summaries: Iterable[Path],
    trees: Iterable[Path],
) -> dict[str, Any]:
    metadata_rows = read_metadata(metadata)
    summary_rows = read_sample_summaries(summaries)
    samples = build_sample_records(metadata_rows, summary_rows)
    sample_ids = {sample["sample_id"] for sample in samples}
    tree_records, warnings = build_tree_records(trees, sample_ids)

    geolocated = sum(1 for sample in samples if sample["has_coordinates"])
    dates = sorted(
        {sample["collection_date"] for sample in samples if sample["collection_date"] != "Unknown"}
    )
    hosts = sorted({sample["host"] for sample in samples if sample["host"] != "Unknown"})

    return {
        "version": 1,
        "title": "WINGS Surveillance Explorer",
        "samples": samples,
        "trees": tree_records,
        "segment_order": list(SEGMENT_ORDER),
        "summary": {
            "sample_count": len(samples),
            "geolocated_count": geolocated,
            "missing_coordinate_count": len(samples) - geolocated,
            "date_count": len(dates),
            "host_count": len(hosts),
            "tree_segment_count": len(tree_records),
        },
        "dates": dates,
        "hosts": hosts,
        "warnings": warnings,
        "notes": [
            "Collection dates are read from metadata and are not parsed from tree-tip labels.",
            "Phylogenies are displayed as supplied; WINGS does not infer, reroot, or time-calibrate them.",
            "When a tree file contains multiple Newick trees, the first tree is displayed.",
            "Samples without coordinates remain available in the timeline and phylogeny.",
        ],
    }


def _paths_from_snakemake() -> tuple[Path, list[Path], list[Path], Path]:
    metadata = Path(snakemake.input.metadata)
    summaries = [Path(value) for value in snakemake.input.summaries]
    trees = [Path(value) for value in getattr(snakemake.input, "trees", [])]
    output = Path(snakemake.output.json)
    return metadata, summaries, trees, output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--summary", type=Path, action="append", default=[])
    parser.add_argument("--tree", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    if "snakemake" in globals():
        metadata, summaries, trees, output = _paths_from_snakemake()
    else:
        args = parse_args()
        metadata, summaries, trees, output = args.metadata, args.summary, args.tree, args.output

    payload = build_payload(metadata, summaries, trees)
    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Safe when embedded in a script[type=application/json] element.
    text = text.replace("</", "<\\/")
    output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
