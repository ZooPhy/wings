#!/usr/bin/env python3
"""Build WINGS Ecological Clock profiles from eBird Status & Trends.

The builder is metadata-driven. It resolves bird identity from the user's WINGS
metadata and the bundled WINGS host map, then resolves exact common/scientific
names against the official version-matched ebirdst modeled-species reference. Only weekly median abundance
rasters needed by geolocated samples are downloaded. Large source rasters remain
in an external cache; the WINGS report receives only compact derived profiles.

Access key: set EBIRDST_ACCESS_KEY in the environment. Never place the key in
config.yaml, Git, or a report bundle.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import sys
import tempfile
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

VERSION = "0.2.3"
VERSION_YEAR_DEFAULT = 2023
RESOLUTION_DEFAULT = "27km"
API_LIST = "https://st-download.ebird.org/v1/list-obj/{version_year}/{species_code}"
API_FETCH = "https://st-download.ebird.org/v1/fetch"
EBIRDST_REFERENCE_URLS = {
    # Pinned official ebirdst package data. This table contains only species with
    # Status & Trends products and records species_code/common/scientific names.
    2023: (
        "https://raw.githubusercontent.com/ebird/ebirdst/"
        "024957b30d6143f597e5f775a40e643be105ad59/data/ebirdst_runs.rda"
    ),
}

CENSUS_BOUNDARY_YEAR = 2024
CENSUS_STATE_BOUNDARY_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_state_20m.zip"
)
US_STATE_CODES = dict(pair.split(":", 1) for pair in (
    "AL:Alabama|AK:Alaska|AZ:Arizona|AR:Arkansas|CA:California|CO:Colorado|CT:Connecticut|"
    "DE:Delaware|DC:District of Columbia|FL:Florida|GA:Georgia|HI:Hawaii|ID:Idaho|IL:Illinois|"
    "IN:Indiana|IA:Iowa|KS:Kansas|KY:Kentucky|LA:Louisiana|ME:Maine|MD:Maryland|MA:Massachusetts|"
    "MI:Michigan|MN:Minnesota|MS:Mississippi|MO:Missouri|MT:Montana|NE:Nebraska|NV:Nevada|"
    "NH:New Hampshire|NJ:New Jersey|NM:New Mexico|NY:New York|NC:North Carolina|ND:North Dakota|"
    "OH:Ohio|OK:Oklahoma|OR:Oregon|PA:Pennsylvania|RI:Rhode Island|SC:South Carolina|"
    "SD:South Dakota|TN:Tennessee|TX:Texas|UT:Utah|VT:Vermont|VA:Virginia|WA:Washington|"
    "WV:West Virginia|WI:Wisconsin|WY:Wyoming|PR:Puerto Rico"
).split("|"))

CITATIONS = {
    2023: (
        "Fink, D. et al. 2024. eBird Status and Trends, Data Version: 2023; "
        "Released: 2025. Cornell Lab of Ornithology. https://doi.org/10.2173/WZTW8903"
    )
}
MISSING = {"", "NA", "N/A", "NONE", "NAN", "NULL", "UNKNOWN"}
COUNTRY_ALIASES = {
    "USA": "US", "UNITED STATES": "US", "UNITED STATES OF AMERICA": "US",
    "CAN": "CA", "CANADA": "CA", "MEX": "MX", "MEXICO": "MX",
}


def clean(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.upper() in MISSING else text


def key(value: object) -> str:
    return " ".join(clean(value).casefold().split())


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


def request_bytes(url: str, timeout: int = 180) -> bytes:
    req = Request(url, headers={"User-Agent": f"WINGS-ebirdst-phenology/{VERSION}"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"request failed for {url.split('?')[0]}: {exc}") from exc


def api_get_json(url: str, access_key: str) -> object:
    sep = "&" if "?" in url else "?"
    raw = request_bytes(url + sep + urlencode({"key": access_key}), timeout=60)
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("eBird Status & Trends list endpoint did not return JSON") from exc


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh, delimiter="\t")]


def read_metadata(path: Path) -> list[dict[str, str]]:
    rows = read_tsv(path)
    if not rows:
        raise ValueError("metadata.tsv is empty")
    seen: set[str] = set()
    for row in rows:
        sid = clean(row.get("sample_id") or row.get("sample"))
        if not sid or sid in seen:
            raise ValueError("metadata must contain nonempty unique sample_id values")
        row["sample_id"] = sid
        seen.add(sid)
    return rows


def load_host_map(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    rows = read_tsv(path)
    if rows and not {"host", "ebird_species"}.issubset(rows[0]):
        raise ValueError("host map requires host and ebird_species columns")
    out: dict[str, str] = {}
    for row in rows:
        host, species = clean(row.get("host")), clean(row.get("ebird_species"))
        if not host or not species:
            continue
        k = key(host)
        if k in out and out[k] != species:
            raise ValueError(f"conflicting host map entries for {host}")
        out[k] = species
    return out


def taxonomy_cache_path(cache_dir: Path, version_year: int) -> Path:
    # Keep the historical function name for compatibility with existing WINGS
    # provenance fields. The cached CSV is generated from the official ebirdst
    # model-species reference, not scraped from the Clements download site.
    return cache_dir / "taxonomy" / f"ebirdst_status_species_v{version_year}.csv"


def _frame_to_taxonomy_csv(frame: object, version_year: int) -> bytes:
    """Convert ebirdst::ebirdst_runs to the compact species reference WINGS needs."""
    try:
        records = frame.to_dict(orient="records")
    except Exception as exc:
        raise ValueError("Could not interpret ebirdst_runs data frame") from exc
    required = {"species_code", "scientific_name", "common_name", "status_version_year"}
    if records and not required.issubset(records[0]):
        raise ValueError("ebirdst_runs lacks required species identity/version fields")
    rows = []
    seen = set()
    for row in records:
        try:
            status_year = int(row.get("status_version_year"))
        except (TypeError, ValueError):
            continue
        if status_year != version_year:
            continue
        code = clean(row.get("species_code")).lower()
        common = clean(row.get("common_name"))
        scientific = clean(row.get("scientific_name"))
        if not code or code.endswith("-example") or not common or not scientific:
            continue
        key_ = (code, common, scientific)
        if key_ in seen:
            continue
        seen.add(key_)
        rows.append(key_)
    if not rows:
        raise ValueError(f"ebirdst_runs contains no Status species for version {version_year}")
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["CATEGORY", "SPECIES_CODE", "PRIMARY_COM_NAME", "SCI_NAME", "STATUS_VERSION_YEAR"])
    for code, common, scientific in sorted(rows):
        writer.writerow(["species", code, common, scientific, version_year])
    return out.getvalue().encode("utf-8")


def _reference_csv_from_rda(raw: bytes, version_year: int) -> bytes:
    try:
        import rdata
    except ImportError as exc:
        raise RuntimeError("rdata is required to read the official ebirdst species reference; use envs/phenology.yaml") from exc
    fd, name = tempfile.mkstemp(suffix=".rda")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
        objects = rdata.read_rda(name)
    finally:
        Path(name).unlink(missing_ok=True)
    frame = objects.get("ebirdst_runs")
    if frame is None:
        frames = list(objects.values())
        frame = frames[0] if len(frames) == 1 else None
    if frame is None:
        raise ValueError("Official ebirdst reference did not contain ebirdst_runs")
    return _frame_to_taxonomy_csv(frame, version_year)


def ensure_taxonomy(cache_dir: Path, version_year: int, taxonomy_file: Path | None = None) -> tuple[Path, dict]:
    """Return the exact modeled-species reference used for Status & Trends.

    A user-supplied eBird taxonomy CSV remains supported for offline runs. By
    default WINGS derives a compact CSV from the official, pinned
    ebirdst::ebirdst_runs dataset. This avoids brittle Clements-site downloads
    and resolves only taxa that actually have Status products.
    """
    if taxonomy_file is not None:
        path = taxonomy_file.expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(path)
        return path, {
            "source_url": None, "retrieved_on": None, "sha256": sha256_file(path),
            "supplied": True, "reference_kind": "user_supplied_ebird_taxonomy",
        }

    target = taxonomy_cache_path(cache_dir, version_year)
    if target.is_file() and target.stat().st_size:
        meta = target.with_suffix(".provenance.json")
        prov = json.loads(meta.read_text()) if meta.is_file() else {}
        return target, {
            "source_url": prov.get("source_url"),
            "retrieved_on": prov.get("retrieved_on"),
            "sha256": sha256_file(target),
            "supplied": False,
            "reference_kind": prov.get("reference_kind", "ebirdst_runs"),
            "source_rda_sha256": prov.get("source_rda_sha256"),
        }

    url = EBIRDST_REFERENCE_URLS.get(version_year)
    if not url:
        raise ValueError(
            f"No official ebirdst modeled-species reference is configured for Status version {version_year}; "
            "supply --taxonomy-file explicitly."
        )
    raw_rda = request_bytes(url)
    raw_csv = _reference_csv_from_rda(raw_rda, version_year)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw_csv)
    retrieved = datetime.now(timezone.utc).date().isoformat()
    provenance = {
        "source_url": url,
        "retrieved_on": retrieved,
        "source_rda_sha256": sha256_bytes(raw_rda),
        "sha256": sha256_bytes(raw_csv),
        "supplied": False,
        "reference_kind": "ebirdst_runs",
        "status_version_year": version_year,
    }
    atomic_write(target.with_suffix(".provenance.json"), json.dumps(provenance, indent=2) + "\n")
    return target, provenance


def _header_map(headers: list[str]) -> dict[str, str]:
    return {h.strip().upper(): h for h in headers if h is not None}


def load_taxonomy(path: Path) -> dict[str, dict]:
    """Index species-only eBird taxonomy by code, common name, and scientific name."""
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        headers = _header_map(reader.fieldnames or [])
        required = {"CATEGORY", "SPECIES_CODE", "PRIMARY_COM_NAME", "SCI_NAME"}
        if not required.issubset(headers):
            raise ValueError(
                "eBird taxonomy CSV requires CATEGORY, SPECIES_CODE, PRIMARY_COM_NAME, and SCI_NAME"
            )
        rows = []
        for source_row, row in enumerate(reader, 2):
            if key(row.get(headers["CATEGORY"])) != "species":
                continue
            code = clean(row.get(headers["SPECIES_CODE"])).lower()
            common = clean(row.get(headers["PRIMARY_COM_NAME"]))
            scientific = clean(row.get(headers["SCI_NAME"]))
            if not code or not common or not scientific:
                continue
            rows.append({
                "species_code": code,
                "common_name": common,
                "scientific_name": scientific,
                "source_row": source_row,
            })
    if not rows:
        raise ValueError("eBird taxonomy contains no species rows")

    indexes: dict[str, dict] = {"code": {}, "common": {}, "scientific": {}}
    for row in rows:
        for field, value in (
            ("code", row["species_code"]),
            ("common", row["common_name"]),
            ("scientific", row["scientific_name"]),
        ):
            k = key(value)
            if k in indexes[field]:
                existing = indexes[field][k]
                if existing is None or existing["species_code"] != row["species_code"]:
                    # Exact duplicates are marked ambiguous rather than guessed.
                    indexes[field][k] = None
            else:
                indexes[field][k] = row
    indexes["rows"] = rows
    return indexes


def valid_lat_lon(row: dict[str, str]) -> tuple[float, float] | None:
    try:
        lat, lon = float(clean(row.get("latitude"))), float(clean(row.get("longitude")))
    except ValueError:
        return None
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def normalized_country(value: object) -> str:
    raw = clean(value).upper()
    return COUNTRY_ALIASES.get(raw, raw)


def resolve_taxon(row: dict[str, str], host_map: dict[str, str], taxonomy: dict[str, dict]) -> tuple[dict | None, dict]:
    """Resolve without fuzzy matching; return taxon and transparent resolution provenance."""
    host = clean(row.get("host"))
    candidates: list[tuple[str, str, str]] = []

    explicit = clean(row.get("ebird_species"))
    if explicit:
        candidates.append(("metadata.ebird_species", explicit, "common"))
    explicit_code = clean(row.get("ebird_species_code") or row.get("species_code"))
    if explicit_code:
        candidates.append(("metadata.ebird_species_code", explicit_code, "code"))
    for field in ("scientific_name", "host_scientific_name", "host_species"):
        value = clean(row.get(field))
        if value:
            candidates.append((f"metadata.{field}", value, "scientific"))
    mapped = host_map.get(key(host))
    if mapped:
        candidates.append(("WINGS host map", mapped, "common"))
    if host:
        # Permit metadata that already use eBird common/scientific/code values.
        candidates.extend([
            ("metadata.host", host, "code"),
            ("metadata.host", host, "common"),
            ("metadata.host", host, "scientific"),
        ])

    tried = []
    for source, value, field in candidates:
        k = key(value)
        tried.append({"source": source, "value": value, "match_field": field})
        hit = taxonomy[field].get(k)
        if hit:
            return dict(hit), {"status": "RESOLVED", "source": source, "input": value, "match_field": field}
    return None, {"status": "UNRESOLVED", "tried": tried}


def us_state_code(value: object) -> str | None:
    raw = clean(value).strip()
    folded = raw.casefold()
    if folded.startswith("us-"):
        folded = folded[3:]
    for code, name in US_STATE_CODES.items():
        if folded in {code.casefold(), name.casefold()}:
            return code
    return None


def census_boundary_cache_dir(cache_dir: Path) -> Path:
    return cache_dir / "boundaries" / f"census_cb_{CENSUS_BOUNDARY_YEAR}_us_state_20m"


def ensure_us_state_boundaries(cache_dir: Path) -> tuple[Path, dict]:
    """Download/cache the official U.S. Census 1:20m state cartographic boundary shapefile."""
    dest = census_boundary_cache_dir(cache_dir)
    shp = dest / f"cb_{CENSUS_BOUNDARY_YEAR}_us_state_20m.shp"
    prov_path = dest / "provenance.json"
    if shp.is_file():
        prov = json.loads(prov_path.read_text()) if prov_path.is_file() else {}
        return shp, {
            "source_url": prov.get("source_url", CENSUS_STATE_BOUNDARY_URL),
            "retrieved_on": prov.get("retrieved_on"),
            "zip_sha256": prov.get("zip_sha256"),
            "boundary_year": CENSUS_BOUNDARY_YEAR,
        }
    raw = request_bytes(CENSUS_STATE_BOUNDARY_URL)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        members = [n for n in archive.namelist() if Path(n).name.startswith(f"cb_{CENSUS_BOUNDARY_YEAR}_us_state_20m.")]
        if not members:
            raise ValueError("Census boundary archive does not contain the expected state shapefile")
        for member in members:
            target = dest / Path(member).name
            target.write_bytes(archive.read(member))
    if not shp.is_file():
        raise ValueError("Census state shapefile was not extracted correctly")
    prov = {
        "source_url": CENSUS_STATE_BOUNDARY_URL,
        "retrieved_on": datetime.now(timezone.utc).date().isoformat(),
        "zip_sha256": sha256_bytes(raw),
        "boundary_year": CENSUS_BOUNDARY_YEAR,
        "resolution": "1:20,000,000 cartographic boundary",
        "provider": "U.S. Census Bureau",
    }
    atomic_write(prov_path, json.dumps(prov, indent=2) + "\n")
    return shp, prov


def load_us_state_geometry(shapefile_path: Path, state_code: str) -> tuple[dict, str]:
    try:
        import shapefile
    except ImportError as exc:
        raise RuntimeError("pyshp is required for the U.S. state regional fallback; use envs/phenology.yaml") from exc
    with shapefile.Reader(str(shapefile_path)) as reader:
        fields = [f[0] for f in reader.fields[1:]]
        for shape_record in reader.iterShapeRecords():
            record = dict(zip(fields, shape_record.record))
            if clean(record.get("STUSPS")).upper() == state_code:
                return shape_record.shape.__geo_interface__, clean(record.get("NAME")) or US_STATE_CODES[state_code]
    raise LookupError(f"State {state_code} was not found in the Census boundary file")


def regional_raster_mean(raster_path: Path, geometry_wgs84: dict) -> tuple[list[float | None], list[int]]:
    """Weekly arithmetic mean across raster-cell centers inside the supplied region."""
    try:
        import numpy as np
        import rasterio
        from rasterio.features import geometry_mask, geometry_window
        from rasterio.warp import transform_geom
    except ImportError as exc:
        raise RuntimeError("numpy/rasterio are required for regional phenology; use envs/phenology.yaml") from exc
    with rasterio.open(raster_path) as src:
        if src.crs is None:
            raise ValueError(f"{raster_path.name}: GeoTIFF has no CRS")
        if src.count != 52:
            raise ValueError(f"{raster_path.name}: weekly GeoTIFF must have 52 bands; found {src.count}")
        geom = geometry_wgs84
        if str(src.crs).upper() not in {"EPSG:4326", "EPSG:CRS84", "OGC:CRS84"}:
            geom = transform_geom("EPSG:4326", src.crs, geometry_wgs84, precision=12)
        window = geometry_window(src, [geom])
        shape = (int(window.height), int(window.width))
        inside = geometry_mask([geom], out_shape=shape, transform=src.window_transform(window), invert=True, all_touched=False)
        values, counts = [], []
        for band in range(1, 53):
            arr = src.read(band, window=window, masked=True)
            data = np.asarray(arr.data, dtype="float64")
            mask = np.asarray(arr.mask) if np.ndim(arr.mask) else np.full(data.shape, bool(arr.mask))
            valid = inside & ~mask & np.isfinite(data) & (data >= 0)
            count = int(valid.sum())
            counts.append(count)
            values.append(float(data[valid].mean()) if count else None)
        return values, counts

def resolve_samples(metadata: list[dict[str, str]], host_map: dict[str, str], taxonomy: dict[str, dict], regional_fallback: str = "state") -> list[dict]:
    out = []
    for row in metadata:
        taxon, resolution = resolve_taxon(row, host_map, taxonomy)
        base = {
            "sample_id": row["sample_id"],
            "host": clean(row.get("host")),
            "country": normalized_country(row.get("country")),
            "state": clean(row.get("state")),
            "collection_date": clean(row.get("collection_date")),
            "taxon_resolution": resolution,
        }
        if taxon is None:
            base.update(status="UNMAPPED_HOST", reason="Host could not be exactly resolved against the version-matched eBird taxonomy.")
            out.append(base)
            continue
        base.update(
            ebird_species=taxon["common_name"],
            scientific_name=taxon["scientific_name"],
            ebird_species_code=taxon["species_code"],
        )
        try:
            d = date.fromisoformat(base["collection_date"])
        except ValueError:
            base.update(status="MISSING_COLLECTION_DATE", reason="A valid ISO collection date is required for Ecological Clock alignment.")
            out.append(base)
            continue
        base["collection_date"] = d.isoformat()
        coords = valid_lat_lon(row)
        if coords is not None:
            base.update(status="PENDING", latitude=coords[0], longitude=coords[1], spatial_method="POINT")
            out.append(base)
            continue
        state_code = us_state_code(base["state"]) if base["country"] == "US" else None
        if regional_fallback == "state" and state_code:
            base.update(
                status="PENDING_REGIONAL", state_code=state_code, state_name=US_STATE_CODES[state_code],
                spatial_method="REGIONAL_STATE_MEAN",
                reason="Coordinates missing; WINGS will use a clearly labeled U.S. state-level mean seasonal profile.",
            )
        else:
            base.update(status="MISSING_COORDINATES", reason="Sample coordinates are unavailable and no supported regional fallback can be applied.")
        out.append(base)
    return out

def extract_file_keys(obj: object) -> list[str]:
    keys: list[str] = []
    if isinstance(obj, dict):
        for field in ("keys", "objects", "files"):
            items = obj.get(field)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str) and clean(item):
                        keys.append(clean(item))
                    elif isinstance(item, dict):
                        for k in ("key", "Key", "name", "path", "objKey"):
                            if clean(item.get(k)):
                                keys.append(clean(item[k])); break
        for field in ("Key", "key", "name", "path", "objKey"):
            if clean(obj.get(field)):
                keys.append(clean(obj[field]))
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, str) and clean(item):
                keys.append(clean(item))
            elif isinstance(item, dict):
                for k in ("key", "Key", "name", "path", "objKey"):
                    if clean(item.get(k)):
                        keys.append(clean(item[k])); break
    return sorted(set(keys))


def choose_key(keys: list[str], resolution: str) -> str:
    token = f"abundance_median_{resolution}"
    matches = [k for k in keys if token in Path(k).name.lower() and k.lower().endswith((".tif", ".tiff"))]
    weekly = [k for k in matches if "/weekly/" in k.lower() or "weekly" in Path(k).name.lower()]
    candidates = weekly or matches
    if not candidates:
        raise LookupError(f"No weekly median abundance {resolution} GeoTIFF is available for this species")
    # Deterministic and reject truly ambiguous candidates rather than silently picking a different statistic.
    candidates = sorted(candidates)
    if len(candidates) > 1:
        exact = [k for k in candidates if re.search(rf"_abundance_median_{re.escape(resolution)}_\d{{4}}\.tiff?$", k, re.I)]
        if len(exact) == 1:
            return exact[0]
    return candidates[0]


def cached_raster(cache_dir: Path, version_year: int, species_code: str, resolution: str) -> Path | None:
    folder = cache_dir / str(version_year) / species_code
    if not folder.is_dir():
        return None
    token = f"abundance_median_{resolution}"
    matches = sorted(p for p in folder.iterdir() if p.is_file() and token in p.name.lower() and p.suffix.lower() in {".tif", ".tiff"})
    return matches[0] if len(matches) == 1 else None


def download_raster(key_name: str, access_key: str, target: Path) -> dict:
    url = API_FETCH + "?" + urlencode({"objKey": key_name, "key": access_key})
    raw = request_bytes(url)
    if len(raw) < 4 or raw[:2] not in {b"II", b"MM"}:
        raise RuntimeError(f"Status & Trends object {key_name!r} did not return a GeoTIFF")
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".partial")
    tmp.write_bytes(raw)
    tmp.replace(target)
    return {
        "object_key": key_name,
        "retrieved_on": datetime.now(timezone.utc).date().isoformat(),
        "sha256": sha256_bytes(raw),
        "bytes": len(raw),
    }


def prepare_rasters(samples: list[dict], cache_dir: Path, version_year: int, resolution: str, access_key: str, dry_run: bool) -> tuple[dict[str, Path], list[dict]]:
    needed: dict[str, str] = {}
    for sample in samples:
        if sample["status"] in {"PENDING", "PENDING_REGIONAL"}:
            needed[sample["ebird_species_code"]] = sample["ebird_species"]

    rasters: dict[str, Path] = {}
    manifests: list[dict] = []
    for code, common in sorted(needed.items()):
        cached = cached_raster(cache_dir, version_year, code, resolution)
        if cached:
            rasters[code] = cached
            sidecar = cached.with_suffix(cached.suffix + ".provenance.json")
            provenance = json.loads(sidecar.read_text()) if sidecar.is_file() else {}
            retrieved_on = clean(provenance.get("retrieved_on"))
            basis = "recorded_sidecar"
            if not retrieved_on:
                retrieved_on = datetime.fromtimestamp(cached.stat().st_mtime, timezone.utc).date().isoformat()
                basis = "cache_file_mtime"
            manifests.append({
                "species_code": code, "common_name": common, "status": "CACHED",
                "file": str(cached), "sha256": sha256_file(cached),
                "object_key": provenance.get("object_key"),
                "retrieved_on": retrieved_on, "retrieved_on_basis": basis,
            })
            continue
        if dry_run:
            manifests.append({"species_code": code, "common_name": common, "status": "WOULD_DOWNLOAD"})
            continue
        if not access_key:
            raise RuntimeError(
                "At least one required Status & Trends raster is not cached and EBIRDST_ACCESS_KEY is not set."
            )
        list_url = API_LIST.format(version_year=version_year, species_code=code)
        try:
            listing = api_get_json(list_url, access_key)
            object_key = choose_key(extract_file_keys(listing), resolution)
        except LookupError as exc:
            for sample in samples:
                if sample.get("ebird_species_code") == code and sample["status"] == "PENDING":
                    sample.update(status="NO_STATUS_PRODUCT", reason=str(exc))
            manifests.append({"species_code": code, "common_name": common, "status": "NO_STATUS_PRODUCT", "reason": str(exc)})
            continue
        target = cache_dir / str(version_year) / code / Path(object_key).name
        meta = download_raster(object_key, access_key, target)
        sidecar = target.with_suffix(target.suffix + ".provenance.json")
        atomic_write(sidecar, json.dumps({
            "provider": "Cornell Lab of Ornithology eBird Status and Trends",
            "version_year": version_year,
            "species_code": code,
            "common_name": common,
            **meta,
        }, indent=2) + "\n")
        rasters[code] = target
        manifests.append({
            "species_code": code, "common_name": common, "status": "DOWNLOADED",
            "file": str(target), **meta,
        })
    return rasters, manifests


def load_raster_values(raster_path: Path, points: list[tuple[float, float]]) -> list[list[float | None]]:
    try:
        import rasterio
    except ImportError as exc:
        raise RuntimeError("rasterio is required; use envs/phenology.yaml") from exc
    with rasterio.open(raster_path) as src:
        if src.crs is None:
            raise ValueError(f"{raster_path.name}: GeoTIFF has no CRS")
        if src.count != 52:
            raise ValueError(f"{raster_path.name}: weekly GeoTIFF must have 52 bands; found {src.count}")
        coords = points
        if str(src.crs).upper() not in {"EPSG:4326", "EPSG:CRS84", "OGC:CRS84"}:
            from rasterio.warp import transform
            xs, ys = zip(*points)
            tx, ty = transform("EPSG:4326", src.crs, list(xs), list(ys))
            coords = list(zip(tx, ty))
        indexes = list(range(1, 53))
        result: list[list[float | None]] = []
        for xy in coords:
            sampled = next(src.sample([xy], indexes=indexes, masked=True))
            row: list[float | None] = []
            for raw in sampled:
                if bool(getattr(raw, "mask", False)):
                    row.append(None); continue
                try:
                    value = float(raw)
                except (TypeError, ValueError):
                    row.append(None); continue
                row.append(value if math.isfinite(value) and value >= 0 else None)
            result.append(row)
        return result


def collection_status_week(value: str) -> int | None:
    """Match ebirdst::date_to_st_week() for the 2022+ Status week scheme."""
    try:
        d = date.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return min(((d.timetuple().tm_yday - 1) // 7) + 1, 52)


def projected_bins(year: int, values: list[float | None]) -> list[dict]:
    if len(values) != 52:
        raise ValueError("weekly profile must contain 52 values")
    jan1 = date(year, 1, 1)
    dec31 = date(year, 12, 31)
    bins = []
    for i, value in enumerate(values):
        start = jan1 + timedelta(days=7 * i)
        end = dec31 if i == 51 else min(start + timedelta(days=6), dec31)
        bins.append({
            "week_number": i + 1,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "midpoint": (date(year, 1, 4) + timedelta(days=7 * i)).isoformat(),
            "value": value,
        })
    return bins


def contiguous_peak(values: list[float | None], threshold_fraction: float = 0.90) -> dict | None:
    valid = [(i, value) for i, value in enumerate(values) if value is not None and math.isfinite(value)]
    if not valid:
        return None
    peak_index, maximum = max(valid, key=lambda item: item[1])
    if maximum <= 0:
        return None
    qualifying = [v is not None and math.isfinite(v) and v >= maximum * threshold_fraction for v in values]
    n = len(values)
    if all(qualifying):
        return None  # flat/all-year high profile: do not fabricate a narrow seasonal anchor
    seen = {peak_index}
    left = peak_index
    while qualifying[(left - 1) % n] and ((left - 1) % n) not in seen:
        left = (left - 1) % n; seen.add(left)
    right = peak_index
    while qualifying[(right + 1) % n] and ((right + 1) % n) not in seen:
        right = (right + 1) % n; seen.add(right)
    return {
        "peak_index": peak_index,
        "left": left,
        "right": right,
        "wraps_year": left > right,
        "maximum": maximum,
        "threshold_fraction": threshold_fraction,
    }


def profile_from_sample(
    sample: dict, values: list[float | None], raster: Path, version_year: int, resolution: str,
    retrieved_on: str, spatial: dict | None = None, spatial_method_text: str | None = None,
) -> dict | None:
    if not any(v is not None for v in values):
        sample.update(status="NO_MODEL_ESTIMATE", reason="The Status & Trends raster has no modeled estimates for this spatial scope.")
        return None
    year = date.fromisoformat(sample["collection_date"]).year
    bins = projected_bins(year, values)
    peak = contiguous_peak(values)
    anchor = None
    if peak is not None:
        if peak["wraps_year"]:
            idx0 = peak["peak_index"]
            earliest, latest = bins[idx0]["start"], bins[idx0]["end"]
            basis = (
                "WINGS-derived maximum week. The >=90%-of-maximum plateau crosses the calendar boundary, "
                "so the maximum Status week is used as the display anchor to preserve a valid annual interval."
            )
        else:
            earliest, latest = bins[peak["left"]]["start"], bins[peak["right"]]["end"]
            basis = (
                "WINGS-derived contiguous annual-cycle interval around the maximum with relative abundance "
                ">=90% of the maximum. This is a descriptive temporal interval, not a confidence interval "
                "or an eBird-defined migration peak."
            )
        anchor = {
            "earliest": earliest, "latest": latest,
            "label": "Expected relative-abundance peak interval", "basis": basis,
        }

    st_week = collection_status_week(sample["collection_date"])
    spatial = spatial or {
        "method": "POINT",
        "sample_latitude": sample["latitude"],
        "sample_longitude": sample["longitude"],
        "raster_resolution": resolution,
        "description": "Status & Trends raster cell containing the supplied WINGS sample coordinate; no centroid substitution.",
    }
    method = spatial_method_text or (
        f"Median weekly relative-abundance {resolution} raster cell containing the supplied sample coordinate."
    )
    sample.update(
        status="READY", reason="", collection_status_week=st_week,
        collection_week_value=values[st_week - 1] if st_week else None,
        available_week_count=sum(v is not None for v in values),
        missing_week_count=sum(v is None for v in values),
        spatial_method=spatial["method"],
    )
    profile = {
        "profile_id": f"ebirdst-{version_year}-{sample['ebird_species_code']}-{sample['sample_id']}",
        "sample_id": sample["sample_id"],
        "scope": {"host": sample["host"], "country": sample["country"], "state": sample["state"]},
        "species": {
            "common_name": sample["ebird_species"],
            "scientific_name": sample["scientific_name"],
            "species_code": sample["ebird_species_code"],
        },
        "status_version_year": version_year,
        "baseline_kind": "reference_season",
        "measure": "eBird Status & Trends median weekly relative abundance",
        "unit": "expected individuals per standardized 1-hour, 2-km traveling checklist",
        "season_start": date(year, 1, 1).isoformat(),
        "season_end": date(year, 12, 31).isoformat(),
        "bins": bins,
        "spatial": spatial,
        "collection": {
            "date": sample["collection_date"],
            "status_week": st_week,
            "relative_abundance": values[st_week - 1] if st_week else None,
        },
        "source_raster": {"file": raster.name, "sha256": sha256_file(raster)},
        "provenance": {
            "source": f"eBird Status and Trends Data Version {version_year}",
            "citation": CITATIONS.get(version_year, f"eBird Status and Trends Data Version {version_year}"),
            "retrieved_on": retrieved_on,
            "method": (
                method + " "
                f"The 52-week reference profile is projected onto calendar year {year} only to align the annual cycle "
                "with the WINGS collection date; it is not a year-specific observation."
            ),
        },
    }
    if anchor is not None:
        profile["anchor"] = anchor
    return profile


def derive_profiles(samples: list[dict], rasters: dict[str, Path], version_year: int, resolution: str, manifest: list[dict], cache_dir: Path) -> tuple[list[dict], dict | None]:
    profiles: list[dict] = []
    point_by_species: dict[str, list[dict]] = {}
    regional_by_species_state: dict[tuple[str, str], list[dict]] = {}
    for sample in samples:
        if sample.get("ebird_species_code") not in rasters:
            continue
        if sample["status"] == "PENDING":
            point_by_species.setdefault(sample["ebird_species_code"], []).append(sample)
        elif sample["status"] == "PENDING_REGIONAL":
            regional_by_species_state.setdefault((sample["ebird_species_code"], sample["state_code"]), []).append(sample)
    retrieved_lookup = {
        item["species_code"]: clean(item.get("retrieved_on")) or datetime.now(timezone.utc).date().isoformat()
        for item in manifest
    }
    for code, group in sorted(point_by_species.items()):
        raster = rasters[code]
        values = load_raster_values(raster, [(s["longitude"], s["latitude"]) for s in group])
        for sample, weekly in zip(group, values):
            profile = profile_from_sample(
                sample, weekly, raster, version_year, resolution,
                retrieved_lookup.get(code, datetime.now(timezone.utc).date().isoformat()),
            )
            if profile is not None:
                profiles.append(profile)

    boundary_provenance = None
    if regional_by_species_state:
        try:
            shp, boundary_provenance = ensure_us_state_boundaries(cache_dir)
            geometry_cache: dict[str, tuple[dict, str]] = {}
            regional_cache: dict[tuple[str, str], tuple[list[float | None], list[int]]] = {}
            for (code, state_code), group in sorted(regional_by_species_state.items()):
                if state_code not in geometry_cache:
                    geometry_cache[state_code] = load_us_state_geometry(shp, state_code)
                geometry, state_name = geometry_cache[state_code]
                cache_key = (code, state_code)
                if cache_key not in regional_cache:
                    regional_cache[cache_key] = regional_raster_mean(rasters[code], geometry)
                weekly, cell_counts = regional_cache[cache_key]
                positive_counts = [n for n in cell_counts if n > 0]
                for sample in group:
                    spatial = {
                        "method": "REGIONAL_STATE_MEAN",
                        "country": "US",
                        "state_code": state_code,
                        "state_name": state_name,
                        "raster_resolution": resolution,
                        "summary_statistic": "arithmetic mean",
                        "cell_inclusion": "raster-cell center inside state cartographic boundary",
                        "valid_cell_count_min": min(positive_counts) if positive_counts else 0,
                        "valid_cell_count_max": max(positive_counts) if positive_counts else 0,
                        "boundary_provider": "U.S. Census Bureau",
                        "boundary_year": CENSUS_BOUNDARY_YEAR,
                        "boundary_source_url": CENSUS_STATE_BOUNDARY_URL,
                        "description": (
                            f"State-level mean of Status & Trends raster cells within {state_name}; used because the WINGS sample has no coordinates. "
                            "This is a regional fallback, not a point estimate and not a state-centroid substitution."
                        ),
                    }
                    profile = profile_from_sample(
                        sample, weekly, rasters[code], version_year, resolution,
                        retrieved_lookup.get(code, datetime.now(timezone.utc).date().isoformat()),
                        spatial=spatial,
                        spatial_method_text=(
                            f"Arithmetic mean of median weekly relative-abundance {resolution} raster values for cells whose centers fall within "
                            f"the {CENSUS_BOUNDARY_YEAR} U.S. Census cartographic boundary for {state_name}."
                        ),
                    )
                    if profile is not None:
                        profiles.append(profile)
        except Exception as exc:
            for group in regional_by_species_state.values():
                for sample in group:
                    sample.update(status="REGIONAL_BOUNDARY_UNAVAILABLE", reason=f"Regional fallback could not be built ({type(exc).__name__}): {exc}")

    for sample in samples:
        if sample["status"] in {"PENDING", "PENDING_REGIONAL"}:
            sample.update(status="NO_STATUS_PRODUCT", reason="No usable Status & Trends raster was available for this resolved species.")
    return profiles, boundary_provenance

def summarize(samples: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for sample in samples:
        counts[sample["status"]] = counts.get(sample["status"], 0) + 1
    return dict(sorted(counts.items()))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--host-map", type=Path, default=Path("resources/ebird_host_codes_2025.tsv"))
    parser.add_argument("--taxonomy-file", type=Path, help="Optional version-matched eBird taxonomy CSV for offline runs")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, default=Path.home() / ".cache" / "wings" / "ebirdst")
    parser.add_argument("--version-year", type=int, default=VERSION_YEAR_DEFAULT)
    parser.add_argument("--resolution", choices=["3km", "9km", "27km"], default=RESOLUTION_DEFAULT)
    parser.add_argument("--access-key-env", default="EBIRDST_ACCESS_KEY")
    parser.add_argument("--regional-fallback", choices=["none", "state"], default="state", help="Use U.S. state-level mean phenology when coordinates are absent")
    parser.add_argument("--dry-run", action="store_true", help="Resolve metadata/taxonomy and report cache needs; do not download rasters or write output")
    args = parser.parse_args()

    metadata = read_metadata(args.metadata)
    host_map = load_host_map(args.host_map)
    args.cache_dir = args.cache_dir.expanduser().resolve()
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    taxonomy_path, taxonomy_provenance = ensure_taxonomy(args.cache_dir, args.version_year, args.taxonomy_file)
    taxonomy = load_taxonomy(taxonomy_path)
    samples = resolve_samples(metadata, host_map, taxonomy, regional_fallback=args.regional_fallback)

    resolved_species = sorted({
        (s["ebird_species_code"], s["ebird_species"])
        for s in samples if s.get("ebird_species_code")
    })
    point_species = sorted({
        (s["ebird_species_code"], s["ebird_species"])
        for s in samples if s["status"] in {"PENDING", "PENDING_REGIONAL"}
    })
    print(f"WINGS samples: {len(samples)}")
    print(f"Resolved eBird taxa: {len(resolved_species)}")
    for code, name in resolved_species:
        print(f"  {code}: {name}")
    print(f"Species requiring phenology rasters: {len(point_species)}")

    access_key = os.environ.get(args.access_key_env, "").strip()
    rasters, manifest = prepare_rasters(samples, args.cache_dir, args.version_year, args.resolution, access_key, args.dry_run)
    if args.dry_run:
        for item in manifest:
            print(f"  {item['species_code']}: {item['status']}")
        print("Dry run: the modeled-species reference may be cached, but no Status & Trends rasters were downloaded and no output was written.")
        return 0

    profiles, boundary_provenance = derive_profiles(samples, rasters, args.version_year, args.resolution, manifest, args.cache_dir)
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    output = {
        "schema_version": "wings.phenology.v1",
        "generator_version": VERSION,
        "synthetic": False,
        "created_at_utc": created,
        "source": {
            "provider": "Cornell Lab of Ornithology eBird Status and Trends",
            "status_version_year": args.version_year,
            "product": "weekly median relative abundance",
            "resolution": args.resolution,
            "citation": CITATIONS.get(args.version_year, f"eBird Status and Trends Data Version {args.version_year}"),
            "api_list": API_LIST,
            "api_fetch": API_FETCH,
            "taxonomy_version": args.version_year,
            "species_reference": "official ebirdst::ebirdst_runs",
            "notes": [
                "Relative abundance is a modeled standardized expectation, not an observed bird count at the WINGS sample location.",
                "Point profiles use the raster cell containing the supplied sample coordinate.",
                "For U.S. samples without coordinates, the default state fallback is the arithmetic mean across 27-km raster-cell centers within the official 2024 U.S. Census state cartographic boundary; it is explicitly labeled regional and is not a centroid substitution.",
                "The reference annual cycle is projected onto the sample collection year only for calendar alignment and is not year-specific realized migration timing.",
                "Raster nodata/model-NA values are retained as null rather than interpreted as zero.",
                "The peak interval is WINGS-derived and descriptive; it is not an eBird-defined migration peak or statistical confidence interval.",
            ],
        },
        "inputs": {
            "metadata": str(args.metadata.resolve()),
            "metadata_sha256": sha256_file(args.metadata),
            "host_map": str(args.host_map.resolve()) if args.host_map and args.host_map.is_file() else None,
            "host_map_sha256": sha256_file(args.host_map) if args.host_map and args.host_map.is_file() else None,
            "taxonomy_file": str(taxonomy_path),
            "taxonomy_sha256": sha256_file(taxonomy_path),
            "taxonomy_source_url": taxonomy_provenance.get("source_url"),
            "taxonomy_reference_kind": taxonomy_provenance.get("reference_kind"),
            "regional_fallback": args.regional_fallback,
            "regional_boundary": boundary_provenance,
        },
        "summary": {
            "sample_count": len(samples),
            "ready_profile_count": len(profiles),
            "status_counts": summarize(samples),
            "resolved_species_count": len(resolved_species),
        },
        "download_manifest": manifest,
        "sample_status": samples,
        "profiles": profiles,
    }
    atomic_write(args.output, json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(f"Wrote {args.output}: {len(profiles)} ready profiles")
    print("Status: " + ", ".join(f"{k}={v}" for k, v in summarize(samples).items()))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
