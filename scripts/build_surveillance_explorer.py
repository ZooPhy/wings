#!/usr/bin/env python3
"""Build the data bundle used by the WINGS Surveillance Explorer.

The explorer treats WINGS-generated or externally supplied trees as visualization
inputs. It displays the first Newick tree in each configured file and does not
infer, reroot, date, or otherwise modify a phylogeny.
"""


import argparse
import csv
import hashlib
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
    if tip in sample_ids:
        return tip
    matches = [sample_id for sample_id in sample_ids if tip.startswith(sample_id + "__")]
    if matches:
        return max(matches, key=len)

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
            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "tree_count_in_file": tree_count,
            "displayed_tree_index": 1,
            "tip_count": tip_count,
            "unmatched_tip_count": len(unmatched),
            "root": root,
        }
    return trees, warnings


def read_recorded_genotype(path: Path | None, status: str) -> dict[str, Any]:
    """Display the existing GenoFLU result; do not derive a genotype."""
    result = {"status": status or "NOT_RECORDED", "call": None, "reason": "", "source_file": None}
    if status == "DISABLED_BY_CONFIG":
        result["reason"] = "GenoFLU was disabled for this run."
        return result
    if path is None or not path.is_file() or not path.stat().st_size:
        result["reason"] = "No GenoFLU output was supplied to the explorer."
        return result
    result["source_file"] = f"{path.parent.name}/{path.name}"
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) == 2 and lines[0].startswith("sample\tstatus"):
        result["status"] = lines[1].split("\t", 1)[-1]
        result["reason"] = "GenoFLU did not run; the recorded eligibility status is shown."
        return result
    match = re.search(r"consensus\s+Genotype\s+-->\s*([^:\r\n]+):\s*([^\r\n]*)", text, re.I)
    if match:
        value = match.group(1).strip()
        result["reason"] = match.group(2).strip()
        if value.casefold() not in {"not assigned", "unassigned", "not available", "not run", "unknown", "indeterminate"}:
            result["call"] = value
        result["status"] = "RECORDED" if result["call"] else "NOT_ASSIGNED"
    else:
        result["status"] = "NOT_ASSIGNED"
        result["reason"] = "No consensus genotype was recorded in the supplied output."
    return result


def attach_genome_evidence(samples, summaries, coverage_paths, genoflu_paths, trees, warnings):
    """Join existing report evidence by sample ID and segment, preserving missing values."""
    sample_ids = {sample["sample_id"] for sample in samples}
    coverage = {}
    for path in coverage_paths:
        if not path.is_file() or not path.stat().st_size:
            warnings.append(f"Coverage evidence unavailable: {path.name}")
            continue
        for row in read_tsv(path):
            sample_id = _clean(row.get("sample_id") or row.get("sample")) or path.parent.parent.name
            # NA is a segment name here, not a missing-value token.
            segment = str(row.get("segment", "")).strip().upper()
            if sample_id not in sample_ids or segment not in SEGMENT_ORDER:
                warnings.append(f"Unmatched coverage record in {path.name}: {sample_id} / {segment}")
                continue
            key = (sample_id, segment)
            if key in coverage:
                raise ValueError(f"Duplicate coverage evidence for {sample_id} / {segment}")
            coverage[key] = row
    genotypes = {}
    for path in genoflu_paths:
        sample_id = path.parent.parent.name
        if sample_id not in sample_ids:
            warnings.append(f"Unmatched GenoFLU sample directory: {sample_id}")
            continue
        if sample_id in genotypes:
            raise ValueError(f"Duplicate GenoFLU output for {sample_id}")
        genotypes[sample_id] = path

    tip_evidence = {}
    def visit(node, segment, parent=None):
        if node.get("children"):
            for child in node["children"]:
                visit(child, segment, node)
            return
        sample_id = node.get("sample_id")
        if sample_id:
            label = str((parent or {}).get("label", ""))
            # Preserve numeric and compound support labels without assuming a
            # support method, percentage scale, or confidence threshold.
            support = label if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:/[0-9]+(?:\.[0-9]+)?)*", label) else None
            tip_evidence.setdefault((sample_id, segment), []).append({
                "name": node["name"], "parent_support": support,
            })
    for segment, tree in trees.items():
        visit(tree["root"], segment)

    for sample in samples:
        sample_id = sample["sample_id"]
        status = _clean(summaries.get(sample_id, {}).get("genoflu_status"))
        sample["genotype"] = read_recorded_genotype(genotypes.get(sample_id), status)
        sample["segments"] = {}
        for segment in SEGMENT_ORDER:
            row = coverage.get((sample_id, segment))
            source = row or {}
            missing_sequence = any(str(source.get(key, "")).upper() == "MISSING"
                                   for key in ("assembly_status", "selection_status"))
            tips = tip_evidence.get((sample_id, segment), [])
            record = {
                "segment": segment,
                "record_status": "NOT_RECORDED" if row is None else "MISSING_SEQUENCE" if missing_sequence else "AVAILABLE",
                "source_file": "coverage/coverage.tsv" if row is not None else None,
                "tree_status": "NO_TREE" if segment not in trees else "PRESENT" if tips else "ABSENT_FROM_TREE",
                "tree_source": trees.get(segment, {}).get("source_file"),
                "tips": tips,
                "contig": _clean(source.get("contig")),
                "overall_status": _clean(source.get("overall_status") or source.get("coverage_flag"), "NOT_RECORDED"),
                "coverage_status": _clean(source.get("coverage_status"), "NOT_RECORDED"),
                "length_status": _clean(source.get("length_status"), "NOT_RECORDED"),
                "n_content_status": _clean(source.get("n_content_status"), "NOT_RECORDED"),
                "selection_reason": _clean(source.get("selection_reason")),
                "qc_reason": _clean(source.get("qc_reason")),
            }
            for field in ("length", "median_depth", "mean_depth", "breadth_covered", "n_fraction"):
                record[field] = _number(source.get(field))
            sample["segments"][segment] = record


APHIS_SOURCE_URL = "https://www.aphis.usda.gov/livestock-poultry-disease/avian/avian-influenza/hpai-detections/wild-birds"
APHIS_COLUMNS = ("State", "County", "Collection Date", "Date Detected", "HPAI Strain", "Bird Species", "WOAH Classification", "Sampling Method", "Submitting Agency")
US_STATES = dict(item.split(":", 1) for item in (
    "AL:Alabama|AK:Alaska|AZ:Arizona|AR:Arkansas|CA:California|CO:Colorado|CT:Connecticut|DE:Delaware|DC:District of Columbia|FL:Florida|GA:Georgia|HI:Hawaii|ID:Idaho|IL:Illinois|IN:Indiana|IA:Iowa|KS:Kansas|KY:Kentucky|LA:Louisiana|ME:Maine|MD:Maryland|MA:Massachusetts|MI:Michigan|MN:Minnesota|MS:Mississippi|MO:Missouri|MT:Montana|NE:Nebraska|NV:Nevada|NH:New Hampshire|NJ:New Jersey|NM:New Mexico|NY:New York|NC:North Carolina|ND:North Dakota|OH:Ohio|OK:Oklahoma|OR:Oregon|PA:Pennsylvania|RI:Rhode Island|SC:South Carolina|SD:South Dakota|TN:Tennessee|TX:Texas|UT:Utah|VT:Vermont|VA:Virginia|WA:Washington|WV:West Virginia|WI:Wisconsin|WY:Wyoming"
).split("|"))


def us_state_code(value):
    text = str(value or "").strip().casefold()
    if text.startswith("us-"):
        text = text[3:]
    return next((code for code, name in US_STATES.items() if text in {code.casefold(), name.casefold()}), None)


def aphis_date(value):
    from datetime import datetime
    text = str(value or "").strip()
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            pass
    return None


def build_outbreak_context(path, provenance_path=None):
    """Read a pinned APHIS CSV; preserve every source record and both dates."""
    import hashlib
    if path is None:
        return {"status": "NOT_CONFIGURED", "records": [], "source_url": APHIS_SOURCE_URL}
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    provenance = {}
    if provenance_path is not None:
        provenance = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
        if provenance.get("sha256") != digest:
            raise ValueError("APHIS provenance SHA-256 does not match the CSV; update the snapshot and its provenance together")
    records = []
    unknown_states = set()
    invalid_dates = {"collection_date": 0, "detected_date": 0}
    seen = set()
    repeated = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames or []
        if len(headers) != len(set(headers)) or set(APHIS_COLUMNS) - set(headers):
            raise ValueError("APHIS CSV must have unique headers including: " + ", ".join(APHIS_COLUMNS))
        for index, row in enumerate(reader, 1):
            if None in row or any(row.get(key) is None for key in APHIS_COLUMNS):
                raise ValueError(f"Malformed APHIS CSV record {index}")
            values = tuple(row[key].strip() for key in APHIS_COLUMNS)
            repeated += values in seen
            seen.add(values)
            state, county, collection, detected, strain, species, classification, method, agency = values
            code = us_state_code(state)
            if code is None:
                unknown_states.add(state or "(missing)")
            collection_date, detected_date = aphis_date(collection), aphis_date(detected)
            invalid_dates["collection_date"] += collection_date is None
            invalid_dates["detected_date"] += detected_date is None
            records.append({
                "source_row": index, "state": state, "state_code": code, "county": county,
                "collection_date": collection_date, "detected_date": detected_date,
                "collection_date_raw": collection, "detected_date_raw": detected,
                "strain": strain, "species": species, "classification": classification,
                "sampling_method": method, "submitting_agency": agency,
                "geographic_precision": "county" if _clean(county) else "state" if code else "unknown",
            })
    ranges = {}
    for field in invalid_dates:
        dates = sorted(record[field] for record in records if record[field])
        ranges[field] = {"min": dates[0] if dates else None, "max": dates[-1] if dates else None}
    return {
        "status": "READY", "source_name": "USDA APHIS wild-bird HPAI detections",
        "source_url": APHIS_SOURCE_URL, "source_file": path.name, "sha256": digest,
        "snapshot_supplied_date": provenance.get("snapshot_supplied_date"),
        "snapshot_date_basis": provenance.get("snapshot_date_basis", "Not recorded"),
        "record_count": len(records), "records": records, "states": US_STATES,
        "date_ranges": ranges, "undated_counts": invalid_dates,
        "repeated_rows_retained": repeated, "unmapped_states": sorted(unknown_states),
        "geographic_display_precision": "state",
        "record_reference": "SHA-256 of CSV plus 1-based data-record number; not an APHIS case ID",
        "notes": [
            "Counts are source rows, not unique outbreaks, infection prevalence, or estimates of incidence.",
            "Source geography is county/state. Map shading aggregates by state; no exact detection locations are inferred.",
            "Collection dates and confirmatory detection dates are distinct. Missing dates are never substituted.",
            "Date and place overlap provide context only and do not imply epidemiological linkage.",
            "The CSV provides no unique record IDs or record-specific web URLs. Links open the APHIS source table.",
        ],
    }


def build_payload(
    metadata: Path,
    summaries: Iterable[Path],
    trees: Iterable[Path],
    ebird_samples: Path | None = None,
    ebird_terms: Path | None = None,
    ebird_citation: Path | None = None,
    coverage: Iterable[Path] = (),
    genoflu: Iterable[Path] = (),
    aphis_csv: Path | None = None,
    aphis_provenance: Path | None = None,
    ecological_context: Path | None = None,
    ecological_loader: Path | None = None,
    reference_manifest: Path | None = None,
    reference_provenance: Path | None = None,
    reference_loader: Path | None = None,
) -> dict[str, Any]:
    metadata_rows = read_metadata(metadata)
    summary_rows = read_sample_summaries(summaries)
    samples = build_sample_records(metadata_rows, summary_rows)
    sample_ids = {sample["sample_id"] for sample in samples}
    tree_records, warnings = build_tree_records(trees, sample_ids)
    references = None
    if reference_manifest is not None:
        import runpy
        loader = reference_loader or Path(__file__).with_name("public_reference_context.py")
        references = runpy.run_path(str(loader))["attach_reference_context"](
            tree_records, samples, reference_manifest, reference_provenance, warnings)
    attach_genome_evidence(samples, summary_rows, coverage, genoflu, tree_records, warnings)
    ebird_contexts = build_ebird_contexts(samples, ebird_samples, warnings)
    ebird_attribution = None
    if ebird_contexts:
        source_dir = ebird_samples.parent
        terms_path = ebird_terms or source_dir / "terms_of_use.txt"
        citation_path = ebird_citation or source_dir / "recommended_citation.txt"
        if not terms_path.is_file() or not citation_path.is_file():
            raise ValueError(
                "eBird context requires terms_of_use.txt and recommended_citation.txt "
                f"in {source_dir}. Copy both from the eBird release before building the report."
            )
        terms_text = terms_path.read_text(encoding="utf-8-sig").strip()
        citation_text = citation_path.read_text(encoding="utf-8-sig").strip()
        if not terms_text or not citation_text:
            raise ValueError("eBird terms and recommended citation must be nonempty")
        ebird_attribution = {
            "terms": terms_text,
            "citation": citation_text,
            "source_url": "https://ebird.org/data/download",
        }

    ecology = None
    if ecological_context is not None:
        import runpy
        loader = ecological_loader or Path(__file__).with_name("build_ecological_context.py")
        ecology = runpy.run_path(str(loader))["load_snapshot"](ecological_context, samples)

    geolocated = sum(1 for sample in samples if sample["has_coordinates"])
    dates = sorted(
        {sample["collection_date"] for sample in samples if sample["collection_date"] != "Unknown"}
    )
    hosts = sorted({sample["host"] for sample in samples if sample["host"] != "Unknown"})

    return {
        "version": 2,
        "title": "WINGS Surveillance Explorer",
        "samples": samples,
        "trees": tree_records,
        "ebird_contexts": ebird_contexts,
        "ebird_attribution": ebird_attribution,
        "outbreak_context": build_outbreak_context(aphis_csv, aphis_provenance),
        "ecological_context": ecology,
        "public_reference_context": references,
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
            "When the optional phylogeny stage is enabled, WINGS infers segment trees from QC-passing consensus sequences; otherwise, the Explorer displays available external trees. Trees are displayed without rerooting or time calibration.",
            "When a tree file contains multiple Newick trees, the first tree is displayed.",
            "Samples without coordinates remain available in the timeline and phylogeny.",
        ],
    }


def build_ebird_contexts(
    samples: list[dict[str, Any]], path: Path | None, warnings: list[str]
) -> list[dict[str, Any]]:
    """Group identical metadata windows so checklists are displayed only once."""
    if path is None or not path.is_file():
        return []
    by_id = {sample["sample_id"]: sample for sample in samples}
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in read_tsv(path):
        if _clean(row.get("status")) != "READY":
            continue
        sample = by_id.get(_clean(row.get("sample_id")))
        if sample is None:
            continue
        country = _clean(row.get("country")).upper()
        meta_country = sample["country"].upper()
        if meta_country in {"USA", "UNITED STATES", "UNITED STATES OF AMERICA"}:
            meta_country = "US"
        elif meta_country in {"CAN", "CANADA"}:
            meta_country = "CA"
        if (sample["host"] != _clean(row.get("host")) or
            sample["collection_date"] != _clean(row.get("collection_date")) or
            sample["state"].casefold() != _clean(row.get("state")).casefold() or
            meta_country != country):
            warnings.append(f"eBird summary for {sample['sample_id']} does not match current metadata; ignored.")
            continue
        total = _integer(row.get("complete_checklists"))
        reported = _integer(row.get("reporting_checklists"))
        if total is None or total <= 0 or reported is None or not 0 <= reported <= total:
            warnings.append(f"Invalid eBird checklist counts for {sample['sample_id']}; ignored.")
            continue
        radius = _number(row.get("radius_km"))
        if radius is not None and not sample["has_coordinates"]:
            warnings.append(f"eBird radius for {sample['sample_id']} has no matching coordinates; ignored.")
            continue
        key = (sample["host"], country, sample["state"].casefold(),
               _clean(row.get("ebird_species")).casefold(),
               _clean(row.get("date_from")), _clean(row.get("date_to")),
               _clean(row.get("release")), radius,
               sample["latitude"] if radius is not None else None,
               sample["longitude"] if radius is not None else None)
        if (not key[3] or not key[4] or not key[5] or
            not key[4] <= sample["collection_date"] <= key[5]):
            continue
        if key not in grouped:
            grouped[key] = {
                "host": sample["host"], "species": _clean(row.get("ebird_species")),
                "state": sample["state"], "country": country,
                "date_from": key[4], "date_to": key[5], "radius_km": radius,
                "complete_checklists": total, "reporting_checklists": reported,
                "reporting_frequency": reported / total,
                "release": _clean(row.get("release")), "sample_ids": [],
            }
        record = grouped[key]
        if (record["complete_checklists"], record["reporting_checklists"]) != (total, reported):
            warnings.append(f"Conflicting eBird summaries for {sample['sample_id']}; ignored.")
            continue
        if sample["sample_id"] not in record["sample_ids"]:
            record["sample_ids"].append(sample["sample_id"])
    return list(grouped.values())


def _paths_from_snakemake() -> tuple[Path, list[Path], list[Path], Path, Path | None, Path | None, Path | None]:
    metadata = Path(snakemake.input.metadata)
    summaries = [Path(value) for value in snakemake.input.summaries]
    trees = [Path(value) for value in getattr(snakemake.input, "trees", [])]
    output = Path(snakemake.output.json)
    ebird = getattr(snakemake.input, "ebird_samples", [])
    terms = getattr(snakemake.input, "ebird_terms", [])
    citation = getattr(snakemake.input, "ebird_citation", [])
    return (metadata, summaries, trees, output, Path(ebird[0]) if ebird else None,
            Path(terms[0]) if terms else None, Path(citation[0]) if citation else None)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--summary", type=Path, action="append", default=[])
    parser.add_argument("--tree", type=Path, action="append", default=[])
    parser.add_argument("--ebird-samples", type=Path)
    parser.add_argument("--ebird-terms", type=Path)
    parser.add_argument("--ebird-citation", type=Path)
    parser.add_argument("--coverage", type=Path, action="append", default=[],
                        help="Existing per-sample coverage TSV (repeat for each sample).")
    parser.add_argument("--genoflu", type=Path, action="append", default=[],
                        help="Existing <sample>/genoflu/GenoFLU.tsv (repeat for each sample).")
    parser.add_argument("--aphis-csv", type=Path)
    parser.add_argument("--aphis-provenance", type=Path)
    parser.add_argument("--reference-manifest", type=Path)
    parser.add_argument("--reference-provenance", type=Path)
    parser.add_argument("--ecological-context", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    if "snakemake" in globals():
        metadata, summaries, trees, output, ebird, terms, citation = _paths_from_snakemake()
        refs = list(getattr(snakemake.input, "reference_manifest", []))
        ref_prov = list(getattr(snakemake.input, "reference_provenance", []))
        reference_manifest = Path(refs[0]) if refs else None
        reference_provenance = Path(ref_prov[0]) if ref_prov else None
        reference_loader = Path(snakemake.input.reference_loader) if refs else None
        coverage = [Path(value) for value in getattr(snakemake.input, "coverage", [])]
        genoflu = [Path(value) for value in getattr(snakemake.input, "genoflu", [])]
        aphis = list(getattr(snakemake.input, "aphis_csv", []))
        provenance = list(getattr(snakemake.input, "aphis_provenance", []))
        aphis_csv = Path(aphis[0]) if aphis else None
        aphis_provenance = Path(provenance[0]) if provenance else None
        ecology = list(getattr(snakemake.input, "ecological_context", []))
        ecological_context = Path(ecology[0]) if ecology else None
        ecological_loader = Path(snakemake.input.ecological_loader) if ecology else None
    else:
        args = parse_args()
        reference_manifest, reference_provenance, reference_loader = args.reference_manifest, args.reference_provenance, None
        metadata, summaries, trees, output, ebird, terms, citation = (
            args.metadata, args.summary, args.tree, args.output, args.ebird_samples,
            args.ebird_terms, args.ebird_citation,
        )
        coverage, genoflu = args.coverage, args.genoflu
        aphis_csv, aphis_provenance = args.aphis_csv, args.aphis_provenance
        ecological_context, ecological_loader = args.ecological_context, None

    payload = build_payload(metadata, summaries, trees, ebird, terms, citation,
                            coverage=coverage, genoflu=genoflu,
                            aphis_csv=aphis_csv, aphis_provenance=aphis_provenance,
                            ecological_context=ecological_context, ecological_loader=ecological_loader,
                            reference_manifest=reference_manifest, reference_provenance=reference_provenance,
                            reference_loader=reference_loader)
    output.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    # Safe when embedded in a script[type=application/json] element.
    text = text.replace("</", "<\\/")
    output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
