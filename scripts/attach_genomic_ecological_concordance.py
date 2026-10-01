#!/usr/bin/env python3
"""Attach compact Genomic-Ecological Concordance results to a WINGS Explorer payload."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SCHEMA = "wings.genomic_ecological_concordance.v2"


def compact_concordance(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("schema_version") != SCHEMA:
        raise ValueError(f"Unsupported concordance schema: {data.get('schema_version')!r}")
    models = data.get("models")
    if not isinstance(models, list):
        raise ValueError("Concordance JSON must contain a models list")
    readiness = data.get("readiness")
    if not isinstance(readiness, dict):
        raise ValueError("Concordance JSON must contain readiness metadata")
    keep = {
        "schema_version": data.get("schema_version"),
        "analysis_kind": data.get("analysis_kind"),
        "response": data.get("response"),
        "model_tiers": data.get("model_tiers"),
        "comparisons": data.get("comparisons"),
        "readiness": readiness,
        "weather_summary": data.get("weather_summary"),
        "environmental_distance": {
            "method": (data.get("environmental_distance") or {}).get("method"),
            "standardization_scope": (data.get("environmental_distance") or {}).get("standardization_scope"),
        },
        "seasonal_profile_metric": data.get("seasonal_profile_metric"),
        "permutation_test": data.get("permutation_test"),
        "models": models,
        "caveats": data.get("caveats") or [],
        "detailed_outputs": [
            "results/run_summary/concordance/models.tsv",
            "results/run_summary/concordance/pairs.tsv",
            "results/run_summary/concordance/sample_features.tsv",
            "results/run_summary/concordance/concordance.json",
        ],
    }
    return keep


def attach(explorer: dict[str, Any], concordance: dict[str, Any]) -> dict[str, Any]:
    out = dict(explorer)
    out["genomic_ecological_concordance"] = compact_concordance(concordance)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--explorer", type=Path, required=True)
    parser.add_argument("--concordance", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    explorer = json.loads(args.explorer.read_text(encoding="utf-8"))
    concordance = json.loads(args.concordance.read_text(encoding="utf-8"))
    result = attach(explorer, concordance)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(f"Attached Genomic-Ecological Concordance to {args.output}")


if __name__ == "__main__":
    main()
