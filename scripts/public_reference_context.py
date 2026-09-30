#!/usr/bin/env python3
"""Attach reviewed public-record metadata to supplied trees, without changing trees."""
import csv
import hashlib
import json
import re
from datetime import date
from pathlib import Path

SEGMENTS = ("HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS")
FIELDS = ("reference_id", "segment", "tip_label", "accession_version", "isolate", "host",
          "collection_date", "country", "state", "linkage_basis")
ACCESSION_RE = re.compile(r"[A-Z]{1,6}_?\d{5,12}(?:\.\d+)?")


def date_precision(value):
    if not value:
        return "not recorded"
    try:
        if re.fullmatch(r"\d{4}", value):
            date(int(value), 1, 1)
            return "year"
        if re.fullmatch(r"\d{4}-\d{2}", value):
            date.fromisoformat(value + "-01")
            return "month"
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            date.fromisoformat(value)
            return "day"
    except ValueError:
        pass
    raise ValueError(f"Invalid reference collection date: {value!r}; use YYYY, YYYY-MM, YYYY-MM-DD, or blank")


def attach_reference_context(trees, samples, manifest, provenance, warnings):
    if manifest is None:
        return None
    if provenance is None:
        raise ValueError("Public reference metadata requires a provenance JSON")
    raw = Path(manifest).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    meta = json.loads(Path(provenance).read_text(encoding="utf-8"))
    for field in ("manifest_sha256", "retrieved_on", "selection_notes", "citation"):
        if not isinstance(meta.get(field), str) or not meta[field].strip():
            raise ValueError(f"Reference provenance requires {field}")
    if sha != meta["manifest_sha256"]:
        raise ValueError("Public reference manifest checksum does not match provenance")
    if date_precision(meta["retrieved_on"]) != "day":
        raise ValueError("Reference retrieved_on must be a full ISO date")
    import io
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter="\t")
    if not set(FIELDS).issubset(reader.fieldnames or []):
        raise ValueError("Reference TSV requires columns: " + ", ".join(FIELDS))
    groups, by_tip, seen_accessions = {}, {}, set()
    sample_ids = {s["sample_id"] for s in samples}
    for line, source in enumerate(reader, 2):
        row = {key: (source.get(key) or "").strip() for key in FIELDS}
        accession, segment = row["accession_version"], row["segment"].upper()
        if not ACCESSION_RE.fullmatch(accession):
            raise ValueError(
                f"Reference row {line}: valid NCBI nucleotide accession is required "
                "(accession.version is accepted when supplied; versions are not fabricated)"
            )
        if segment not in SEGMENTS or not row["tip_label"]:
            raise ValueError(f"Reference row {line}: valid segment and exact tip_label required")
        if row["tip_label"] in sample_ids:
            raise ValueError(f"Reference row {line}: tip_label collides with a WINGS sample ID")
        row["segment"] = segment
        row["reference_id"] = row["reference_id"] or accession
        row["collection_date_precision"] = date_precision(row["collection_date"])
        row["source_url"] = "https://www.ncbi.nlm.nih.gov/nuccore/" + accession
        key = (segment, row["tip_label"])
        if key in by_tip or accession in seen_accessions:
            raise ValueError(f"Reference row {line}: duplicate segment/tip or accession")
        seen_accessions.add(accession)
        group = groups.setdefault(row["reference_id"], {"reference_id": row["reference_id"], "records": []})
        if any(r["segment"] == segment for r in group["records"]):
            raise ValueError(f"Reference {row['reference_id']}: more than one record for {segment}")
        group["records"].append(row)
        by_tip[key] = row
    if not groups:
        raise ValueError("Public reference manifest is empty")
    for group in groups.values():
        rows = group["records"]
        if len(rows) > 1:
            bases = {r["linkage_basis"] for r in rows}
            if len(bases) != 1 or not next(iter(bases)):
                raise ValueError(f"Reference {group['reference_id']}: linked segments need one explicit linkage_basis")
            for field in ("isolate", "host", "collection_date", "country", "state"):
                if len({r[field].casefold() for r in rows if r[field]}) > 1:
                    raise ValueError(f"Reference {group['reference_id']}: conflicting {field} across linked segments")
        for field in ("isolate", "host", "collection_date", "country", "state", "linkage_basis"):
            group[field] = next((r[field] for r in rows if r[field]), "")
        group["collection_date_precision"] = date_precision(group["collection_date"])
        group["segments"] = {}
        for segment in SEGMENTS:
            row = next((r for r in rows if r["segment"] == segment), None)
            group["segments"][segment] = {
                "status": "NO_TREE" if segment not in trees else "NOT_IN_MANIFEST" if row is None else "ABSENT_FROM_TREE",
                "accession_version": row["accession_version"] if row else None,
                "source_url": row["source_url"] if row else None,
                "tips": [],
            }
    for segment, tree in trees.items():
        matched, unmatched, matched_samples, seen = [], [], [], set()
        def visit(node, parent=None):
            if node.get("children"):
                for child in node["children"]:
                    visit(child, node)
                return
            row = by_tip.get((segment, node.get("name")))
            if row:
                if node.get("sample_id") is not None:
                    raise ValueError(f"Reference tip {node['name']} also maps to a WINGS sample; use distinct labels")
                if node["name"] in seen:
                    raise ValueError(f"Duplicate public tip label in {segment} tree: {node['name']}")
                seen.add(node["name"])
                node["reference_id"] = row["reference_id"]
                node["accession_version"] = row["accession_version"]
                node["tip_kind"] = "public_reference"
                evidence = groups[row["reference_id"]]["segments"][segment]
                evidence["status"] = "PRESENT"
                label = str(parent.get("label", "")) if parent else ""
                support = label if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?(?:/[0-9]+(?:\.[0-9]+)?)*", label) else None
                evidence["tips"].append({"name": node["name"], "parent_support": support})
                matched.append(node["name"])
            elif node.get("sample_id"):
                node["tip_kind"] = "wings_sample"
                matched_samples.append(node["name"])
            else:
                node["tip_kind"] = "unannotated"
                unmatched.append(node.get("name"))
        visit(tree["root"])
        old = f"{segment} tree contains {tree['unmatched_tip_count']} tip(s) that do not match metadata sample IDs"
        if old in warnings:
            warnings.remove(old)
        tree.update(
            public_reference_tip_count=len(matched),
            wings_sample_tip_count=len(matched_samples),
            unmatched_tip_count=len(unmatched),
        )
        if unmatched:
            warnings.append(f"{segment} tree contains {len(unmatched)} unannotated tip(s); no public identity inferred")
    missing = sum(
        e["status"] != "PRESENT"
        for g in groups.values()
        for e in g["segments"].values()
        if e["accession_version"]
    )
    return {
        "schema_version": 1,
        "status": "READY",
        "source_file": Path(manifest).name,
        **{key: meta[key] for key in ("retrieved_on", "selection_notes", "citation")},
        "manifest_sha256": sha,
        "references": list(groups.values()),
        "record_count": len(by_tip),
        "records_without_displayed_tips": missing,
        "note": "Metadata annotate supplied trees. Public accessions are preserved exactly; accession versions are not fabricated when absent.",
    }
