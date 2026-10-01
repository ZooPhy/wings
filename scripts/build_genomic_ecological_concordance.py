#!/usr/bin/env python3
"""Build the WINGS Genomic-Ecological Concordance research module.

The module is metadata-driven. It derives pairwise predictors itself and uses a
fixed, pre-specified model hierarchy for every influenza segment:

  M0 spatiotemporal = temporal separation + geographic distance
  M1 host           = M0 + same-host indicator
  M2 ecology        = M1 + eBird seasonal-profile distance
  M3 environment    = M2 + multivariate ERA5 environmental distance

The response is segment-specific patristic distance among unambiguous WINGS
sample tips. Pairwise observations share samples, so ordinary OLS p-values are
not reported. Incremental model tests use a Freedman-Lane-style sample-label
permutation of the reduced-model residual matrix, followed by Benjamini-
Hochberg FDR correction within each comparison family across segments.

This is an exploratory association analysis. Concordance is not evidence of
direct transmission, infection source, reassortment, or causality.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

SEGMENTS = ("HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS")
BASELINE = ("temporal_days", "geographic_km")
HOST = BASELINE + ("same_host",)
ECOLOGY = HOST + ("seasonal_profile_distance",)
ENVIRONMENT = ECOLOGY + ("environmental_distance",)
COMPARISONS = (
    ("host_vs_baseline", BASELINE, HOST),
    ("ecology_vs_host", HOST, ECOLOGY),
    ("environment_vs_ecology", ECOLOGY, ENVIRONMENT),
)
WEATHER_FEATURES = (
    "temperature_7d_mean_c",
    "precipitation_7d_total_mm",
    "wind_7d_mean_max_kmh",
)
MISSING = {"", "NA", "N/A", "NONE", "NAN", "NULL", "UNKNOWN"}


def clean(value: Any) -> str:
    text = str(value or "").strip()
    return "" if text.upper() in MISSING else text


def number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def iso_date(value: Any) -> date | None:
    text = clean(value)
    if not text:
        return None
    try:
        parsed = date.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.isoformat() == text else None


def haversine_km(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    lat1, lon1 = number(a.get("latitude")), number(a.get("longitude"))
    lat2, lon2 = number(b.get("latitude")), number(b.get("longitude"))
    if None in (lat1, lon1, lat2, lon2):
        return None
    if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90 and -180 <= lon1 <= 180 and -180 <= lon2 <= 180):
        return None
    r = 6371.0088
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def temporal_days(a: dict[str, Any], b: dict[str, Any]) -> int | None:
    da, db = iso_date(a.get("collection_date")), iso_date(b.get("collection_date"))
    return abs((da - db).days) if da and db else None


def same_host(a: dict[str, Any], b: dict[str, Any]) -> int | None:
    ha, hb = clean(a.get("host")), clean(b.get("host"))
    if not ha or not hb:
        return None
    return int(ha.casefold() == hb.casefold())


def _tree_tip_paths(root: dict[str, Any]) -> dict[str, list[tuple[int, float]]]:
    """Return sample -> one root-to-tip path; duplicated sample tips are omitted."""
    paths: dict[str, list[list[tuple[int, float]]]] = {}
    counter = 0

    def visit(node: dict[str, Any], parent_path: list[tuple[int, float]], distance: float) -> None:
        nonlocal counter
        node_id = counter
        counter += 1
        edge = number(node.get("length"))
        if edge is None or edge < 0:
            edge = 0.0
        here = distance + edge
        path = parent_path + [(node_id, here)]
        children = node.get("children") or []
        if children:
            for child in children:
                visit(child, path, here)
            return
        sid = clean(node.get("sample_id"))
        if sid:
            paths.setdefault(sid, []).append(path)

    root_copy = dict(root)
    root_copy["length"] = 0.0  # Root branch length is irrelevant to pairwise distance.
    visit(root_copy, [], 0.0)
    return {sid: values[0] for sid, values in paths.items() if len(values) == 1}


def patristic_distance(path_a: list[tuple[int, float]], path_b: list[tuple[int, float]]) -> float:
    db = dict(path_b)
    lca_distance = 0.0
    for node_id, distance in path_a:
        if node_id in db:
            lca_distance = distance
        else:
            break
    return path_a[-1][1] + path_b[-1][1] - 2 * lca_distance


def profile_values(profile: dict[str, Any]) -> list[float | None]:
    return [number(item.get("value")) for item in profile.get("bins", [])]


def seasonal_profile_distance(a: dict[str, Any] | None, b: dict[str, Any] | None) -> float | None:
    """1 - Pearson correlation of annual eBird profile shape."""
    if not a or not b:
        return None
    va, vb = profile_values(a), profile_values(b)
    if len(va) != len(vb) or len(va) < 26:
        return None
    paired = [(x, y) for x, y in zip(va, vb) if x is not None and y is not None]
    if len(paired) < 26:
        return None
    xa = np.asarray([x for x, _ in paired], dtype=float)
    xb = np.asarray([y for _, y in paired], dtype=float)
    if np.std(xa) == 0 or np.std(xb) == 0:
        return None
    corr = float(np.corrcoef(xa, xb)[0, 1])
    if not math.isfinite(corr):
        return None
    return max(0.0, min(2.0, 1.0 - corr))


def weather_summary(explorer: dict[str, Any], sample: dict[str, Any], radius_days: int = 3) -> dict[str, float | None]:
    out = {name: None for name in WEATHER_FEATURES}
    context = explorer.get("ecological_context") or {}
    binding = (context.get("bindings") or {}).get(sample.get("sample_id")) or {}
    key = binding.get("weather_key")
    if binding.get("status") != "READY" or not key:
        return out
    weather = (context.get("weather") or {}).get(key) or {}
    center = iso_date(sample.get("collection_date"))
    if center is None:
        return out
    start, end = center - timedelta(days=radius_days), center + timedelta(days=radius_days)
    rows = []
    for row in weather.get("rows", []):
        day = iso_date(row.get("date"))
        if day and start <= day <= end:
            rows.append(row)
    if not rows:
        return out
    temps = [number(r.get("temperature_2m_mean")) for r in rows]
    precips = [number(r.get("precipitation_sum")) for r in rows]
    winds = [number(r.get("wind_speed_10m_max")) for r in rows]
    temps = [x for x in temps if x is not None]
    precips = [x for x in precips if x is not None]
    winds = [x for x in winds if x is not None]
    if temps:
        out["temperature_7d_mean_c"] = float(np.mean(temps))
    if precips:
        out["precipitation_7d_total_mm"] = float(np.sum(precips))
    if winds:
        out["wind_7d_mean_max_kmh"] = float(np.mean(winds))
    return out


def _compatible_profile(profile: dict[str, Any], sample: dict[str, Any]) -> bool:
    if clean(profile.get("sample_id")) != clean(sample.get("sample_id")):
        return False
    pdate = clean((profile.get("collection") or {}).get("date"))
    sdate = clean(sample.get("collection_date"))
    return not pdate or not sdate or pdate == sdate


def _same_optional_number(a: Any, b: Any, tolerance: float = 1e-7) -> bool:
    xa, xb = number(a), number(b)
    if xa is None or xb is None:
        return xa is None and xb is None
    return abs(xa - xb) <= tolerance


def _validated_external_ecological_context(
    context: dict[str, Any], samples: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    """Reject stale date/location bindings before an external snapshot is used."""
    out = {**context, "bindings": {}}
    source_bindings = context.get("bindings") or {}
    weather = context.get("weather") or {}
    for sid, sample in samples.items():
        binding = source_bindings.get(sid)
        if binding is None:
            out["bindings"][sid] = {
                "status": "NOT_LOADED",
                "reason": "Sample not included in this ecological snapshot.",
                "weather_key": None,
            }
            continue
        binding = dict(binding)
        meta = binding.get("metadata") or {}
        stale = False
        if meta:
            if clean(meta.get("collection_date")) != clean(sample.get("collection_date")):
                stale = True
            if not _same_optional_number(meta.get("latitude"), sample.get("latitude")):
                stale = True
            if not _same_optional_number(meta.get("longitude"), sample.get("longitude")):
                stale = True
        if stale:
            binding = {
                "status": "STALE_METADATA",
                "reason": "Sample date or coordinates changed; rebuild the ecological snapshot.",
                "weather_key": None,
            }
        elif binding.get("status") == "READY" and binding.get("weather_key") not in weather:
            binding = {
                "status": "INVALID_SNAPSHOT",
                "reason": "Weather binding references a missing weather context.",
                "weather_key": None,
            }
        out["bindings"][sid] = binding
    return out


def overlay_external_context(
    explorer: dict[str, Any],
    ecological_context: dict[str, Any] | None = None,
    phenology: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Overlay run-specific context not already embedded in the Explorer payload."""
    out = dict(explorer)
    samples = {s.get("sample_id"): s for s in out.get("samples", [])}
    if ecological_context is not None:
        out["ecological_context"] = _validated_external_ecological_context(ecological_context, samples)
    if phenology is not None:
        profiles = [
            p for p in phenology.get("profiles", [])
            if p.get("sample_id") in samples and _compatible_profile(p, samples[p.get("sample_id")])
        ]
        out["ecological_clock"] = {**phenology, "profiles": profiles}
    return out


def sample_features(explorer: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Create sample-level weather summaries and standardized environmental vectors."""
    samples = {s["sample_id"]: s for s in explorer.get("samples", []) if clean(s.get("sample_id"))}
    profiles = {
        p.get("sample_id"): p
        for p in ((explorer.get("ecological_clock") or {}).get("profiles") or [])
        if clean(p.get("sample_id"))
    }
    features: dict[str, dict[str, Any]] = {}
    for sid, sample in samples.items():
        w = weather_summary(explorer, sample)
        features[sid] = {
            "sample_id": sid,
            "host": clean(sample.get("host")),
            "collection_date": clean(sample.get("collection_date")),
            "latitude": number(sample.get("latitude")),
            "longitude": number(sample.get("longitude")),
            "phenology_available": sid in profiles,
            **w,
            "environment_vector_available": False,
            "temperature_z": None,
            "precipitation_z": None,
            "wind_z": None,
        }

    complete = [
        row for row in features.values()
        if all(number(row.get(field)) is not None for field in WEATHER_FEATURES)
    ]
    scaling: dict[str, Any] = {
        "complete_samples": len(complete),
        "features": {},
        "constant_features": [],
    }
    if len(complete) >= 2:
        matrix = np.asarray([[float(row[field]) for field in WEATHER_FEATURES] for row in complete], dtype=float)
        means = matrix.mean(axis=0)
        scales = matrix.std(axis=0)
        for idx, field in enumerate(WEATHER_FEATURES):
            scaling["features"][field] = {"mean": float(means[idx]), "sd": float(scales[idx])}
            if scales[idx] == 0:
                scaling["constant_features"].append(field)
        for row, values in zip(complete, matrix):
            z = np.zeros(len(WEATHER_FEATURES), dtype=float)
            for idx in range(len(WEATHER_FEATURES)):
                z[idx] = 0.0 if scales[idx] == 0 else (values[idx] - means[idx]) / scales[idx]
            row["temperature_z"] = float(z[0])
            row["precipitation_z"] = float(z[1])
            row["wind_z"] = float(z[2])
            row["environment_vector_available"] = True
    return features, scaling


def environmental_distance(a: dict[str, Any], b: dict[str, Any]) -> float | None:
    if not a.get("environment_vector_available") or not b.get("environment_vector_available"):
        return None
    va = np.asarray([a["temperature_z"], a["precipitation_z"], a["wind_z"]], dtype=float)
    vb = np.asarray([b["temperature_z"], b["precipitation_z"], b["wind_z"]], dtype=float)
    return float(np.linalg.norm(va - vb))


def build_pairs(explorer: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    samples = {s["sample_id"]: s for s in explorer.get("samples", []) if clean(s.get("sample_id"))}
    profiles = {
        p.get("sample_id"): p
        for p in ((explorer.get("ecological_clock") or {}).get("profiles") or [])
        if clean(p.get("sample_id"))
    }
    feature_map, scaling = sample_features(explorer)
    output: list[dict[str, Any]] = []

    for segment in SEGMENTS:
        record = (explorer.get("trees") or {}).get(segment)
        if not record or not record.get("root"):
            continue
        paths = _tree_tip_paths(record["root"])
        ids = sorted(set(paths) & set(samples))
        for i, a_id in enumerate(ids):
            for b_id in ids[i + 1:]:
                a, b = samples[a_id], samples[b_id]
                fa, fb = feature_map[a_id], feature_map[b_id]
                temp = None if fa["temperature_7d_mean_c"] is None or fb["temperature_7d_mean_c"] is None else abs(fa["temperature_7d_mean_c"] - fb["temperature_7d_mean_c"])
                precip = None if fa["precipitation_7d_total_mm"] is None or fb["precipitation_7d_total_mm"] is None else abs(fa["precipitation_7d_total_mm"] - fb["precipitation_7d_total_mm"])
                wind = None if fa["wind_7d_mean_max_kmh"] is None or fb["wind_7d_mean_max_kmh"] is None else abs(fa["wind_7d_mean_max_kmh"] - fb["wind_7d_mean_max_kmh"])
                output.append({
                    "segment": segment,
                    "sample_a": a_id,
                    "sample_b": b_id,
                    "patristic_distance": patristic_distance(paths[a_id], paths[b_id]),
                    "temporal_days": temporal_days(a, b),
                    "geographic_km": haversine_km(a, b),
                    "same_host": same_host(a, b),
                    "seasonal_profile_distance": seasonal_profile_distance(profiles.get(a_id), profiles.get(b_id)),
                    "temperature_difference_c": temp,
                    "precipitation_difference_mm": precip,
                    "wind_difference_kmh": wind,
                    "environmental_distance": environmental_distance(fa, fb),
                })
    return output, list(feature_map.values()), scaling


def _complete(rows: list[dict[str, Any]], predictors: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        r for r in rows
        if number(r.get("patristic_distance")) is not None
        and all(number(r.get(p)) is not None for p in predictors)
    ]


def _unique_samples(rows: list[dict[str, Any]]) -> int:
    return len({sid for row in rows for sid in (row["sample_a"], row["sample_b"])})


def _fit(
    rows: list[dict[str, Any]],
    predictors: tuple[str, ...],
    response_values: list[float] | np.ndarray | None = None,
    min_unique_samples: int = 8,
) -> dict[str, Any]:
    n = len(rows)
    p = len(predictors)
    n_samples = _unique_samples(rows)
    if n_samples < min_unique_samples:
        return {"status": "INSUFFICIENT_SAMPLES", "n_pairs": n, "n_samples": n_samples, "predictor_count": p}
    if n < max(10, p + 3):
        return {"status": "INSUFFICIENT_PAIRS", "n_pairs": n, "n_samples": n_samples, "predictor_count": p}
    X = np.asarray([[float(r[pred]) for pred in predictors] for r in rows], dtype=float)
    y = np.asarray(response_values if response_values is not None else [float(r["patristic_distance"]) for r in rows], dtype=float)
    means = X.mean(axis=0)
    scales = X.std(axis=0)
    if np.any(scales == 0):
        constants = [predictors[i] for i, scale in enumerate(scales) if scale == 0]
        return {
            "status": "CONSTANT_PREDICTOR", "n_pairs": n, "n_samples": n_samples,
            "constant_predictors": constants, "predictor_count": p,
        }
    Xz = (X - means) / scales
    design = np.column_stack([np.ones(n), Xz])
    rank = int(np.linalg.matrix_rank(design))
    if rank < design.shape[1]:
        return {
            "status": "RANK_DEFICIENT", "n_pairs": n, "n_samples": n_samples,
            "rank": rank, "columns": int(design.shape[1]), "predictor_count": p,
        }
    coef, *_ = np.linalg.lstsq(design, y, rcond=None)
    fitted = design @ coef
    residuals = y - fitted
    ss_res = float(np.sum(residuals ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    if ss_tot <= 0:
        return {"status": "CONSTANT_RESPONSE", "n_pairs": n, "n_samples": n_samples, "predictor_count": p}
    r2 = 1.0 - ss_res / ss_tot
    adj = 1.0 - (1.0 - r2) * (n - 1) / (n - p - 1)
    return {
        "status": "READY",
        "n_pairs": n,
        "n_samples": n_samples,
        "predictor_count": p,
        "r2": r2,
        "adjusted_r2": adj,
        "_fitted": fitted,
        "_residuals": residuals,
    }


def _permutation_p(
    rows: list[dict[str, Any]],
    reduced: tuple[str, ...],
    full: tuple[str, ...],
    observed_delta: float,
    permutations: int,
    rng: np.random.Generator,
    min_unique_samples: int,
) -> tuple[float | None, int]:
    """Freedman-Lane-style node-label permutation for dyadic residuals."""
    if permutations <= 0:
        return None, 0
    reduced_fit = _fit(rows, reduced, min_unique_samples=min_unique_samples)
    if reduced_fit.get("status") != "READY":
        return None, 0
    residual_lookup = {
        tuple(sorted((r["sample_a"], r["sample_b"]))): float(resid)
        for r, resid in zip(rows, reduced_fit["_residuals"])
    }
    fitted = np.asarray(reduced_fit["_fitted"], dtype=float)
    ids = sorted({x for r in rows for x in (r["sample_a"], r["sample_b"])})
    if len(ids) < min_unique_samples:
        return None, 0

    extreme = 0
    valid = 0
    for _ in range(permutations):
        shuffled = list(rng.permutation(ids))
        mapping = dict(zip(ids, shuffled))
        permuted_residuals = []
        ok = True
        for r in rows:
            key = tuple(sorted((mapping[r["sample_a"]], mapping[r["sample_b"]])))
            value = residual_lookup.get(key)
            if value is None:
                ok = False
                break
            permuted_residuals.append(value)
        if not ok:
            continue
        yperm = fitted + np.asarray(permuted_residuals, dtype=float)
        rfit = _fit(rows, reduced, yperm, min_unique_samples=min_unique_samples)
        ffit = _fit(rows, full, yperm, min_unique_samples=min_unique_samples)
        if rfit.get("status") != "READY" or ffit.get("status") != "READY":
            continue
        delta = ffit["r2"] - rfit["r2"]
        valid += 1
        if delta >= observed_delta - 1e-12:
            extreme += 1
    return ((extreme + 1) / (valid + 1) if valid else None), valid


def _bh_adjust(records: list[dict[str, Any]]) -> None:
    """Benjamini-Hochberg FDR within each pre-specified comparison family."""
    for comparison, _, _ in COMPARISONS:
        indexed = [
            (idx, float(row["permutation_p"]))
            for idx, row in enumerate(records)
            if row["comparison"] == comparison and row.get("permutation_p") is not None
        ]
        if not indexed:
            continue
        ranked = sorted(indexed, key=lambda item: item[1])
        m = len(ranked)
        qvals = [1.0] * m
        running = 1.0
        for pos in range(m - 1, -1, -1):
            _, p = ranked[pos]
            rank = pos + 1
            running = min(running, p * m / rank)
            qvals[pos] = min(1.0, running)
        for (idx, _), q in zip(ranked, qvals):
            records[idx]["fdr_q"] = q



def _display_status(reduced_fit: dict[str, Any], full_fit: dict[str, Any], min_unique_samples: int) -> tuple[str, str]:
    """Map machine fit states to a stable report-facing status and diagnostic."""
    rstatus = reduced_fit.get("status")
    fstatus = full_fit.get("status")
    n_samples = min(int(reduced_fit.get("n_samples") or 0), int(full_fit.get("n_samples") or 0))
    if rstatus == fstatus == "READY":
        return "READY", "Model comparison estimable."
    if n_samples < min_unique_samples or "INSUFFICIENT_SAMPLES" in {rstatus, fstatus}:
        return (
            "INSUFFICIENT_UNIQUE_SAMPLES",
            f"{n_samples} unique samples are available; at least {min_unique_samples} are required.",
        )
    if rstatus == "READY" and fstatus == "RANK_DEFICIENT":
        rank = full_fit.get("rank")
        columns = full_fit.get("columns")
        detail = f" (design rank {rank} of {columns})" if rank is not None and columns is not None else ""
        return (
            "INSUFFICIENT_INDEPENDENT_VARIATION",
            "The added predictor is not independently estimable after the reduced-model predictors" + detail + ".",
        )
    if fstatus == "CONSTANT_PREDICTOR" or rstatus == "CONSTANT_PREDICTOR":
        constants = full_fit.get("constant_predictors") or reduced_fit.get("constant_predictors") or []
        suffix = f": {', '.join(constants)}" if constants else ""
        return "INSUFFICIENT_PREDICTOR_VARIATION", "One or more required predictors are constant" + suffix + "."
    if fstatus == "INSUFFICIENT_PAIRS" or rstatus == "INSUFFICIENT_PAIRS":
        return "INSUFFICIENT_COMPLETE_PAIRS", "Too few complete sample pairs are available for this model comparison."
    if fstatus == "CONSTANT_RESPONSE" or rstatus == "CONSTANT_RESPONSE":
        return "CONSTANT_GENETIC_DISTANCE", "The complete-case genetic-distance response has no variation."
    return "NOT_ESTIMABLE", f"Reduced model: {rstatus}; full model: {fstatus}."

def compare_models(
    pairs: list[dict[str, Any]],
    permutations: int = 999,
    seed: int = 20261001,
    min_unique_samples: int = 8,
) -> list[dict[str, Any]]:
    rng = np.random.default_rng(seed)
    out: list[dict[str, Any]] = []
    for segment in SEGMENTS:
        segment_rows = [r for r in pairs if r["segment"] == segment]
        for label, reduced, full in COMPARISONS:
            rows = _complete(segment_rows, full)
            reduced_fit = _fit(rows, reduced, min_unique_samples=min_unique_samples)
            full_fit = _fit(rows, full, min_unique_samples=min_unique_samples)
            status = (
                "READY" if reduced_fit.get("status") == full_fit.get("status") == "READY"
                else f"REDUCED_{reduced_fit.get('status')}__FULL_{full_fit.get('status')}"
            )
            display_status, diagnostic = _display_status(reduced_fit, full_fit, min_unique_samples)
            record: dict[str, Any] = {
                "segment": segment,
                "comparison": label,
                "status": status,
                "display_status": display_status,
                "diagnostic": diagnostic,
                "reduced_status": reduced_fit.get("status"),
                "full_status": full_fit.get("status"),
                "n_samples": _unique_samples(rows),
                "n_pairs": len(rows),
                "reduced_predictors": ",".join(reduced),
                "full_predictors": ",".join(full),
                "reduced_r2": reduced_fit.get("r2"),
                "full_r2": full_fit.get("r2"),
                "delta_r2": None,
                "reduced_adjusted_r2": reduced_fit.get("adjusted_r2"),
                "full_adjusted_r2": full_fit.get("adjusted_r2"),
                "delta_adjusted_r2": None,
                "permutation_p": None,
                "fdr_q": None,
                "permutations_requested": permutations,
                "permutations_valid": 0,
            }
            if status == "READY":
                record["delta_r2"] = full_fit["r2"] - reduced_fit["r2"]
                record["delta_adjusted_r2"] = full_fit["adjusted_r2"] - reduced_fit["adjusted_r2"]
                pvalue, valid = _permutation_p(
                    rows, reduced, full, record["delta_r2"], permutations, rng, min_unique_samples
                )
                record["permutation_p"] = pvalue
                record["permutations_valid"] = valid
            out.append(record)
    _bh_adjust(out)
    return out


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: "" if row.get(k) is None else row.get(k) for k in fields})


def build(
    explorer: dict[str, Any],
    permutations: int = 999,
    seed: int = 20261001,
    min_unique_samples: int = 8,
) -> dict[str, Any]:
    pairs, samples, environment_scaling = build_pairs(explorer)
    models = compare_models(
        pairs, permutations=permutations, seed=seed, min_unique_samples=min_unique_samples
    )
    ready_by_comparison = {
        label: sum(1 for row in models if row["comparison"] == label and row["status"] == "READY")
        for label, _, _ in COMPARISONS
    }
    environment_vectors = {
        tuple(round(float(row[name]), 12) for name in ("temperature_z", "precipitation_z", "wind_z"))
        for row in samples
        if row.get("environment_vector_available")
    }
    bindings = ((explorer.get("ecological_context") or {}).get("bindings") or {})
    weather_keys = {
        binding.get("weather_key")
        for binding in bindings.values()
        if binding.get("status") == "READY" and binding.get("weather_key")
    }
    return {
        "schema_version": "wings.genomic_ecological_concordance.v2",
        "analysis_kind": "exploratory_dyadic_model_comparison",
        "response": "segment-specific patristic distance among unambiguous WINGS sample tips",
        "model_tiers": {
            "M0_spatiotemporal": list(BASELINE),
            "M1_host": list(HOST),
            "M2_ecology": list(ECOLOGY),
            "M3_environment": list(ENVIRONMENT),
        },
        "comparisons": [label for label, _, _ in COMPARISONS],
        "readiness": {
            "minimum_unique_samples": min_unique_samples,
            "ready_comparisons_by_family": ready_by_comparison,
            "total_pair_rows": len(pairs),
            "samples_with_complete_environment_vector": sum(1 for row in samples if row["environment_vector_available"]),
            "distinct_environment_profiles": len(environment_vectors),
            "distinct_weather_contexts": len(weather_keys),
            "samples_with_phenology": sum(1 for row in samples if row["phenology_available"]),
            "total_samples": len(samples),
        },
        "weather_summary": "7-day window centered on collection date (collection date +/- 3 calendar days): mean temperature, total precipitation, mean daily maximum wind speed",
        "environmental_distance": {
            "method": "Euclidean distance among sample-level z scores for the three ERA5 7-day summaries",
            "standardization_scope": "all WINGS samples with complete values for temperature, precipitation, and wind",
            "scaling": environment_scaling,
        },
        "seasonal_profile_metric": "1 - Pearson correlation across jointly available eBird Status & Trends weekly relative-abundance values; lower values indicate more similar annual shape",
        "permutation_test": {
            "permutations": permutations,
            "seed": seed,
            "method": "Freedman-Lane-style sample-label permutation of the reduced-model dyadic residual matrix; fitted reduced-model values are retained",
            "multiple_testing": "Benjamini-Hochberg FDR within each comparison family across influenza segments",
        },
        "sample_features": samples,
        "pairs": pairs,
        "models": models,
        "caveats": [
            "Ecological or environmental concordance is not evidence of direct transmission, infection source, reassortment, or causality.",
            "Patristic distances are segment-specific and inherit uncertainty and sampling limitations of the supplied phylogenies.",
            "Pairs share samples and are not independent biological observations; readiness is therefore gated by unique sample count as well as pair count.",
            "Missing coordinates, phenology profiles, or weather remain missing and are not replaced with centroids or zeros.",
            "Model comparisons use the same complete-case pair set within each nested comparison.",
            "The environmental tier uses one pre-specified multivariate distance rather than selecting weather variables opportunistically for each dataset.",
        ],
    }


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--explorer", type=Path, required=True, help="WINGS surveillance_explorer.json")
    parser.add_argument("--ecological-context", type=Path, help="Optional run-specific ecological-context.json override")
    parser.add_argument("--phenology", type=Path, help="Optional run-specific wings_phenology.json override")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--permutations", type=int, default=999)
    parser.add_argument("--seed", type=int, default=20261001)
    parser.add_argument("--min-unique-samples", type=int, default=8)
    args = parser.parse_args()
    if args.permutations < 0:
        parser.error("--permutations must be >= 0")
    if args.min_unique_samples < 4:
        parser.error("--min-unique-samples must be >= 4")

    explorer = json.loads(args.explorer.read_text(encoding="utf-8"))
    explorer = overlay_external_context(
        explorer,
        ecological_context=_load_json(args.ecological_context),
        phenology=_load_json(args.phenology),
    )
    result = build(
        explorer,
        permutations=args.permutations,
        seed=args.seed,
        min_unique_samples=args.min_unique_samples,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pair_fields = [
        "segment", "sample_a", "sample_b", "patristic_distance", "temporal_days", "geographic_km",
        "same_host", "seasonal_profile_distance", "temperature_difference_c",
        "precipitation_difference_mm", "wind_difference_kmh", "environmental_distance",
    ]
    sample_fields = [
        "sample_id", "host", "collection_date", "latitude", "longitude", "phenology_available",
        "temperature_7d_mean_c", "precipitation_7d_total_mm", "wind_7d_mean_max_kmh",
        "environment_vector_available", "temperature_z", "precipitation_z", "wind_z",
    ]
    model_fields = [
        "segment", "comparison", "status", "display_status", "diagnostic", "reduced_status", "full_status",
        "n_samples", "n_pairs", "reduced_predictors", "full_predictors",
        "reduced_r2", "full_r2", "delta_r2", "reduced_adjusted_r2", "full_adjusted_r2",
        "delta_adjusted_r2", "permutation_p", "fdr_q", "permutations_requested", "permutations_valid",
    ]
    write_tsv(args.output_dir / "sample_features.tsv", result["sample_features"], sample_fields)
    write_tsv(args.output_dir / "pairs.tsv", result["pairs"], pair_fields)
    write_tsv(args.output_dir / "models.tsv", result["models"], model_fields)
    (args.output_dir / "concordance.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    ready = sum(1 for row in result["models"] if row["status"] == "READY")
    print(
        "Genomic-ecological concordance: "
        f"{len(result['pairs'])} segment pairs; {ready}/{len(result['models'])} comparisons ready; "
        f"environment {result['readiness']['samples_with_complete_environment_vector']}/{result['readiness']['total_samples']} samples; "
        f"phenology {result['readiness']['samples_with_phenology']}/{result['readiness']['total_samples']} samples"
    )


if __name__ == "__main__":
    main()
