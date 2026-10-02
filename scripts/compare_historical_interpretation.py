#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from archive_interpretation_outputs import discover_artifacts


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def read_vcf_variants(path: Path) -> set[tuple[str, int, str, str]]:
    variants: set[tuple[str, int, str, str]] = set()

    if not path.is_file() or path.stat().st_size == 0:
        return variants

    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue

            fields = line.rstrip("\n").split("\t")
            if len(fields) < 5:
                continue

            try:
                pos = int(fields[1])
            except ValueError:
                continue

            chrom = fields[0]
            ref = fields[3]

            for alt in fields[4].split(","):
                if alt and alt != ".":
                    variants.add((chrom, pos, ref, alt))

    return variants


def sample_segment_from_vcf(relative_path: str) -> tuple[str, str]:
    parts = Path(relative_path).parts

    # Expected:
    # SAMPLE/medaka/SEGMENT/variants.vcf
    if len(parts) >= 4 and parts[-1] == "variants.vcf":
        return parts[-4], parts[-2]

    return "", ""


def variant_text(variant: tuple[str, int, str, str]) -> str:
    chrom, pos, ref, alt = variant
    return f"{chrom}:{pos}:{ref}>{alt}"


PRIMARY_GENOMIC_CATEGORIES = {
    "sample_summary",
    "blast",
    "coverage",
    "consensus",
    "genoflu",
    "variant_status",
}

CONTEXT_CATEGORIES = {
    "contextual_tree",
    "surveillance_explorer",
}

INTEGRATED_CATEGORIES = {
    "concordance",
}


REPLAY_INPUT_GROUPS = {
    "metadata": "sample_metadata",
    "validated_metadata": "sample_metadata",
    "public_reference_manifest": "public_references",
    "public_reference_provenance": "public_references",
    "ecological_context": "ecological_context",
    "phenology": "phenology",
    "surveillance_effort": "surveillance_effort",
    "aphis_snapshot": "outbreak_context",
    "aphis_provenance": "outbreak_context",
    "ebird_context": "ebird_context",
    "ebird_terms": "ebird_context",
    "ebird_citation": "ebird_context",
}


def replay_input_group(label: str) -> str:
    if label.startswith("public_reference_tree_"):
        return "public_references"
    return REPLAY_INPUT_GROUPS.get(label, "other")


def compare_replay_inputs(
    historical_snapshot: dict,
    current_provenance: dict,
) -> dict[str, object]:
    historical_inputs = historical_snapshot.get("inputs", {})
    current_inputs = current_provenance.get("replay_inputs", {})

    if not isinstance(historical_inputs, dict):
        raise ValueError(
            "Historical replay snapshot has no inputs mapping."
        )
    if not isinstance(current_inputs, dict):
        raise ValueError(
            "Current provenance has no replay_inputs mapping."
        )

    rows = []

    for label in sorted(
        set(historical_inputs) | set(current_inputs)
    ):
        historical = historical_inputs.get(label)
        current = current_inputs.get(label)

        historical_sha = (
            str(historical.get("sha256", ""))
            if isinstance(historical, dict)
            else ""
        )
        current_sha = (
            str(current.get("sha256", ""))
            if isinstance(current, dict)
            else ""
        )

        if historical is None:
            status = "NEW"
        elif current is None or current_sha.upper() == "MISSING":
            status = "MISSING_CURRENT"
        elif historical_sha == current_sha:
            status = "MATCH"
        else:
            status = "CHANGED"

        rows.append(
            {
                "label": label,
                "group": replay_input_group(label),
                "status": status,
                "historical_sha256": historical_sha or None,
                "current_sha256": current_sha or None,
                "historical_path": (
                    historical.get("original_path")
                    if isinstance(historical, dict)
                    else None
                ),
                "current_path": (
                    current.get("path")
                    if isinstance(current, dict)
                    else None
                ),
            }
        )

    counts = Counter(row["status"] for row in rows)

    changed = [
        row
        for row in rows
        if row["status"] != "MATCH"
    ]

    return {
        "counts": dict(sorted(counts.items())),
        "changed_count": len(changed),
        "changed_labels": [
            row["label"] for row in changed
        ],
        "inputs": rows,
    }


LAYER_REPLAY_GROUPS = {
    "surveillance_context": {
        "sample_metadata",
        "public_references",
        "ecological_context",
        "phenology",
        "surveillance_effort",
        "outbreak_context",
        "ebird_context",
    },
    "integrated_concordance": {
        "sample_metadata",
        "ecological_context",
        "phenology",
        "ebird_context",
    },
}


def build_layer_attribution(
    layers: dict[str, dict[str, object]],
    replay_attribution: dict[str, object],
) -> dict[str, dict[str, object]]:
    changed_inputs = [
        row
        for row in replay_attribution.get("inputs", [])
        if row.get("status") != "MATCH"
    ]

    result: dict[str, dict[str, object]] = {}

    for layer_name, relevant_groups in LAYER_REPLAY_GROUPS.items():
        layer_status = str(
            layers.get(layer_name, {}).get(
                "status",
                "NOT_AVAILABLE",
            )
        )

        relevant = [
            row
            for row in changed_inputs
            if row.get("group") in relevant_groups
        ]

        changed_labels = sorted(
            str(row.get("label", ""))
            for row in relevant
        )
        changed_groups = sorted(
            {
                str(row.get("group", ""))
                for row in relevant
            }
        )

        if layer_status == "CHANGED" and relevant:
            relationship = "COINCIDENT_INPUT_CHANGE"
        elif layer_status == "CHANGED":
            relationship = (
                "LAYER_CHANGED_WITHOUT_RECORDED_INPUT_CHANGE"
            )
        elif layer_status == "STABLE" and relevant:
            relationship = "INPUT_CHANGED_LAYER_STABLE"
        elif layer_status == "STABLE":
            relationship = "NO_CHANGE"
        else:
            relationship = "NOT_ASSESSABLE"

        result[layer_name] = {
            "layer_status": layer_status,
            "changed_replay_inputs": changed_labels,
            "changed_replay_groups": changed_groups,
            "relationship": relationship,
        }

    return result


REPLAY_INPUT_DISPLAY = {
    "metadata": "sample metadata",
    "validated_metadata": "validated sample metadata",
    "public_reference_manifest": "public-reference manifest",
    "public_reference_provenance": "public-reference provenance",
    "ecological_context": "ecological context",
    "phenology": "phenology context",
    "surveillance_effort": "surveillance-effort data",
    "aphis_snapshot": "APHIS outbreak snapshot",
    "aphis_provenance": "APHIS outbreak provenance",
    "ebird_context": "eBird context",
}


def build_attribution_summary(
    attribution: dict[str, object],
) -> str:
    changed = [
        row
        for row in attribution.get("inputs", [])
        if row.get("status") != "MATCH"
    ]

    if not changed:
        return "No replay-sensitive inputs changed."

    names = [
        REPLAY_INPUT_DISPLAY.get(
            str(row.get("label", "")),
            str(row.get("label", "")),
        )
        for row in changed
    ]

    if len(names) == 1:
        return f"Changed replay input: {names[0]}."

    return (
        "Changed replay inputs: "
        + ", ".join(names[:-1])
        + f", and {names[-1]}."
    )


def build_layer_attribution_summary(
    layer_attribution: dict[str, dict[str, object]],
) -> str:
    context = layer_attribution.get(
        "surveillance_context",
        {},
    )
    integrated = layer_attribution.get(
        "integrated_concordance",
        {},
    )

    statements = []

    if (
        context.get("relationship")
        == "COINCIDENT_INPUT_CHANGE"
    ):
        groups = ", ".join(
            str(group).replace("_", " ")
            for group in context.get(
                "changed_replay_groups",
                [],
            )
        )
        statements.append(
            "The surveillance/context change occurred alongside "
            f"updated {groups} input."
        )
    elif (
        context.get("relationship")
        == "LAYER_CHANGED_WITHOUT_RECORDED_INPUT_CHANGE"
    ):
        statements.append(
            "The surveillance/context layer changed without a "
            "recorded change in its replay-sensitive inputs."
        )
    elif (
        context.get("relationship")
        == "INPUT_CHANGED_LAYER_STABLE"
    ):
        statements.append(
            "Replay-sensitive surveillance/context inputs changed, "
            "but the archived surveillance/context interpretation "
            "remained stable."
        )

    if (
        integrated.get("relationship")
        == "COINCIDENT_INPUT_CHANGE"
    ):
        statements.append(
            "The genomic-ecological interpretation changed "
            "alongside one or more relevant replay-input changes."
        )
    elif (
        integrated.get("relationship")
        == "LAYER_CHANGED_WITHOUT_RECORDED_INPUT_CHANGE"
    ):
        statements.append(
            "The genomic-ecological interpretation changed without "
            "a recorded change in its mapped replay-sensitive inputs."
        )
    elif (
        integrated.get("relationship")
        == "INPUT_CHANGED_LAYER_STABLE"
    ):
        statements.append(
            "Relevant ecological/context inputs changed, but the "
            "genomic-ecological interpretation remained stable."
        )

    return " ".join(statements)


def summarize_artifact_layer(
    artifact_results: dict[str, dict[str, object]],
    categories: set[str],
) -> dict[str, object]:
    selected = [
        record
        for record in artifact_results.values()
        if record.get("category") in categories
    ]

    counts = Counter(
        str(record.get("status", ""))
        for record in selected
    )

    if not selected:
        status = "NOT_AVAILABLE"
    elif counts.get("MISSING", 0):
        status = "INCOMPLETE"
    elif counts.get("CHANGED", 0) or counts.get("NEW", 0):
        status = "CHANGED"
    else:
        status = "STABLE"

    return {
        "status": status,
        "artifact_count": len(selected),
        "counts": dict(sorted(counts.items())),
    }


def summarize_variant_layer(
    artifact_results: dict[str, dict[str, object]],
    variant_rows: list[dict[str, object]],
) -> dict[str, object]:
    vcfs = [
        record
        for record in artifact_results.values()
        if record.get("category") == "variant_vcf"
    ]

    row_counts = Counter(
        str(row.get("status", ""))
        for row in variant_rows
    )

    new_vcfs = sum(
        record.get("status") == "NEW"
        for record in vcfs
    )
    missing_vcfs = sum(
        record.get("status") == "MISSING"
        for record in vcfs
    )

    if not vcfs:
        status = "NOT_AVAILABLE"
    elif missing_vcfs or row_counts.get("MISSING_CURRENT", 0):
        status = "INCOMPLETE"
    elif new_vcfs or row_counts.get("CHANGED", 0):
        status = "CHANGED"
    else:
        status = "STABLE"

    return {
        "status": status,
        "segment_vcf_count": len(vcfs),
        "counts": dict(sorted(row_counts.items())),
        "new_vcf_count": new_vcfs,
        "missing_vcf_count": missing_vcfs,
    }


def combine_genomic_status(
    primary_status: str,
    variant_status: str,
) -> str:
    statuses = {primary_status, variant_status}

    if "INCOMPLETE" in statuses:
        return "INCOMPLETE"
    if "CHANGED" in statuses:
        return "CHANGED"
    if statuses <= {"STABLE", "NOT_AVAILABLE"} and "STABLE" in statuses:
        return "STABLE"
    return "NOT_AVAILABLE"


def build_interpretation(layers: dict[str, dict[str, object]]) -> str:
    genomic = str(layers["genomic_overall"]["status"])
    context = str(layers["surveillance_context"]["status"])
    integrated = str(layers["integrated_concordance"]["status"])

    if genomic == "INCOMPLETE":
        return (
            "The genomic comparison is incomplete because one or more "
            "historical or current genomic outputs are unavailable."
        )

    if genomic == "CHANGED":
        return (
            "The primary genomic interpretation changed. Downstream "
            "surveillance/context or concordance changes should therefore "
            "be interpreted in light of the changed genomic result."
        )

    if genomic == "STABLE" and integrated == "CHANGED":
        return (
            "The underlying genomic result is stable, but the integrated "
            "genomic-ecological interpretation changed."
        )

    if genomic == "STABLE" and context == "CHANGED":
        return (
            "The underlying genomic result is stable, while "
            "surveillance/context outputs changed. The change is downstream "
            "of the genomic calls; replay-input provenance can distinguish "
            "updated context from other workflow changes."
        )

    if genomic == "STABLE":
        return (
            "The underlying genomic result is stable, with no detected "
            "change in the archived surveillance/context or integrated "
            "interpretation."
        )

    return (
        "Historical comparison is available, but there are not enough "
        "archived genomic outputs to classify genomic stability."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare an archived WINGS interpretation with current "
            "analytical outputs."
        )
    )
    parser.add_argument(
        "--interpretation",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--archive-root",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--results-root",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--current-provenance",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--output-json",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--variant-tsv",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--summary-tsv",
        type=Path,
        help="Optional one-row summary for report rendering.",
    )
    args = parser.parse_args()

    archive_root = args.archive_root.resolve()
    results_root = args.results_root.resolve()

    try:
        historical = read_json(args.interpretation.resolve())
        current_provenance = read_json(
            args.current_provenance.resolve()
        )

        replay_snapshot_rel = str(
            historical.get("replay_snapshot", "")
        ).strip()

        if not replay_snapshot_rel:
            raise ValueError(
                "Historical interpretation does not reference "
                "a replay snapshot."
            )

        historical_replay_snapshot = read_json(
            archive_root / replay_snapshot_rel
        )

        replay_attribution = compare_replay_inputs(
            historical_replay_snapshot,
            current_provenance,
        )

        historical_artifacts = historical.get("artifacts")
        if not isinstance(historical_artifacts, dict):
            raise ValueError(
                "Interpretation manifest has no artifacts mapping."
            )

        current_discovered = {
            path.relative_to(results_root).as_posix(): category
            for path, category in discover_artifacts(results_root).items()
        }

        artifact_results: dict[str, dict[str, object]] = {}
        variant_rows: list[dict[str, object]] = []

        all_paths = sorted(
            set(historical_artifacts) | set(current_discovered)
        )

        for relative in all_paths:
            historical_record = historical_artifacts.get(relative)
            current_path = results_root / relative

            if historical_record is None:
                artifact_results[relative] = {
                    "category": current_discovered[relative],
                    "status": "NEW",
                    "historical_sha256": None,
                    "current_sha256": (
                        sha256_file(current_path)
                        if current_path.is_file()
                        else None
                    ),
                }
                continue

            category = str(historical_record.get("category", ""))
            historical_sha = str(
                historical_record.get("sha256", "")
            )
            object_rel = str(
                historical_record.get("object_path", "")
            )

            historical_object = archive_root / object_rel

            if not historical_object.is_file():
                raise FileNotFoundError(
                    f"Historical archive object missing: "
                    f"{historical_object}"
                )

            if sha256_file(historical_object) != historical_sha:
                raise ValueError(
                    f"Historical archive object failed verification: "
                    f"{relative}"
                )

            if not current_path.is_file():
                artifact_status = "MISSING"
                current_sha = None
            else:
                current_sha = sha256_file(current_path)
                artifact_status = (
                    "MATCH"
                    if current_sha == historical_sha
                    else "CHANGED"
                )

            artifact_results[relative] = {
                "category": category,
                "status": artifact_status,
                "historical_sha256": historical_sha,
                "current_sha256": current_sha,
            }

            if category != "variant_vcf":
                continue

            sample, segment = sample_segment_from_vcf(relative)

            historical_variants = read_vcf_variants(
                historical_object
            )
            current_variants = (
                read_vcf_variants(current_path)
                if current_path.is_file()
                else set()
            )

            added = sorted(
                current_variants - historical_variants
            )
            removed = sorted(
                historical_variants - current_variants
            )

            if not current_path.is_file():
                variant_status = "MISSING_CURRENT"
            elif not added and not removed:
                variant_status = "STABLE"
            else:
                variant_status = "CHANGED"

            variant_rows.append(
                {
                    "sample": sample,
                    "segment": segment,
                    "status": variant_status,
                    "historical_variant_count": len(
                        historical_variants
                    ),
                    "current_variant_count": len(
                        current_variants
                    ),
                    "added_count": len(added),
                    "removed_count": len(removed),
                    "added_variants": ";".join(
                        variant_text(v) for v in added
                    ),
                    "removed_variants": ";".join(
                        variant_text(v) for v in removed
                    ),
                    "artifact_path": relative,
                }
            )

        counts = Counter(
            record["status"]
            for record in artifact_results.values()
        )

        variant_counts = Counter(
            row["status"]
            for row in variant_rows
        )

        primary_layer = summarize_artifact_layer(
            artifact_results,
            PRIMARY_GENOMIC_CATEGORIES,
        )
        variant_layer = summarize_variant_layer(
            artifact_results,
            variant_rows,
        )
        context_layer = summarize_artifact_layer(
            artifact_results,
            CONTEXT_CATEGORIES,
        )
        integrated_layer = summarize_artifact_layer(
            artifact_results,
            INTEGRATED_CATEGORIES,
        )

        layers = {
            "primary_genomic": primary_layer,
            "variant_calls": variant_layer,
            "surveillance_context": context_layer,
            "integrated_concordance": integrated_layer,
            "genomic_overall": {
                "status": combine_genomic_status(
                    str(primary_layer["status"]),
                    str(variant_layer["status"]),
                )
            },
        }

        layer_attribution = build_layer_attribution(
            layers,
            replay_attribution,
        )
        layer_attribution_summary = (
            build_layer_attribution_summary(
                layer_attribution
            )
        )

        report = {
            "format": "WINGS_INTERPRETATION_COMPARISON",
            "schema_version": 3,
            "historical_snapshot_id": historical.get(
                "snapshot_id"
            ),
            "layers": layers,
            "interpretation": build_interpretation(layers),
            "replay_input_attribution": replay_attribution,
            "attribution_summary": build_attribution_summary(
                replay_attribution
            ),
            "layer_attribution": layer_attribution,
            "layer_attribution_summary": (
                layer_attribution_summary
            ),
            "artifact_counts": dict(sorted(counts.items())),
            "variant_counts": dict(
                sorted(variant_counts.items())
            ),
            "artifacts": artifact_results,
            "variants": variant_rows,
        }

        args.output_json.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        with args.output_json.open(
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                report,
                handle,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")

        args.variant_tsv.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        fieldnames = [
            "sample",
            "segment",
            "status",
            "historical_variant_count",
            "current_variant_count",
            "added_count",
            "removed_count",
            "added_variants",
            "removed_variants",
            "artifact_path",
        ]

        with args.variant_tsv.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=fieldnames,
                delimiter="\t",
                lineterminator="\n",
            )
            writer.writeheader()
            writer.writerows(variant_rows)

        if args.summary_tsv:
            summary_row = {
                "historical_snapshot_id": historical.get(
                    "snapshot_id", ""
                ),
                "genomic_overall": layers[
                    "genomic_overall"
                ]["status"],
                "primary_genomic": layers[
                    "primary_genomic"
                ]["status"],
                "variant_calls": layers[
                    "variant_calls"
                ]["status"],
                "surveillance_context": layers[
                    "surveillance_context"
                ]["status"],
                "integrated_concordance": layers[
                    "integrated_concordance"
                ]["status"],
                "stable_variant_vcfs": variant_counts.get(
                    "STABLE", 0
                ),
                "changed_variant_vcfs": variant_counts.get(
                    "CHANGED", 0
                ),
                "missing_variant_vcfs": variant_counts.get(
                    "MISSING_CURRENT", 0
                ),
                "interpretation": report["interpretation"],
            }

            args.summary_tsv.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            with args.summary_tsv.open(
                "w",
                newline="",
                encoding="utf-8",
            ) as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=list(summary_row),
                    delimiter="\t",
                    lineterminator="\n",
                )
                writer.writeheader()
                writer.writerow(summary_row)

    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(
        "Artifact comparison: "
        + ", ".join(
            f"{status}={count}"
            for status, count in sorted(counts.items())
        )
    )
    print(
        "Variant comparison: "
        + ", ".join(
            f"{status}={count}"
            for status, count in sorted(
                variant_counts.items()
            )
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
