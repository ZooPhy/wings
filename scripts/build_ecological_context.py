#!/usr/bin/env python3
"""Cache ecological context for display. No sequence data or browser-time requests.

BirdCast pilot input is a documented WINGS CSV, not an official BirdCast export.
Weather requests send only coordinates and dates to Open-Meteo when requested.
"""
import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

STATES = dict(pair.split(":", 1) for pair in (
    "AL:Alabama|AK:Alaska|AZ:Arizona|AR:Arkansas|CA:California|CO:Colorado|CT:Connecticut|"
    "DE:Delaware|DC:District of Columbia|FL:Florida|GA:Georgia|HI:Hawaii|ID:Idaho|IL:Illinois|"
    "IN:Indiana|IA:Iowa|KS:Kansas|KY:Kentucky|LA:Louisiana|ME:Maine|MD:Maryland|MA:Massachusetts|"
    "MI:Michigan|MN:Minnesota|MS:Mississippi|MO:Missouri|MT:Montana|NE:Nebraska|NV:Nevada|"
    "NH:New Hampshire|NJ:New Jersey|NM:New Mexico|NY:New York|NC:North Carolina|ND:North Dakota|"
    "OH:Ohio|OK:Oklahoma|OR:Oregon|PA:Pennsylvania|RI:Rhode Island|SC:South Carolina|"
    "SD:South Dakota|TN:Tennessee|TX:Texas|UT:Utah|VT:Vermont|VA:Virginia|WA:Washington|"
    "WV:West Virginia|WI:Wisconsin|WY:Wyoming").split("|"))
WEATHER_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_FIELDS = {"temperature_2m_mean": "°C", "precipitation_sum": "mm", "wind_speed_10m_max": "km/h"}
BIRDCAST_URL = "https://dashboard.birdcast.org/"


def iso_date(value):
    try:
        parsed = date.fromisoformat(str(value))
        return parsed if parsed.isoformat() == value else None
    except (ValueError, TypeError):
        return None


def number(value):
    if value is None or str(value).strip().upper() in {"", "NA", "N/A", "UNKNOWN", "NONE"}:
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def state_code(value):
    v = str(value or "").strip().upper().removeprefix("US-")
    return next((k for k, name in STATES.items() if v in (k, name.upper())), None)


def sample_metadata(row):
    def text(value):
        value = str(value or "").strip()
        return "Unknown" if value.upper() in {"", "NA", "N/A", "NONE", "NAN", "NULL", "UNKNOWN"} else value
    country = text(row.get("country")).upper()
    if country in {"USA", "UNITED STATES", "UNITED STATES OF AMERICA"}:
        country = "US"
    return {"collection_date": text(row.get("collection_date")),
            "country": country, "state": state_code(row.get("state")) or text(row.get("state")),
            "latitude": number(row.get("latitude")), "longitude": number(row.get("longitude"))}


def strict_json(raw):
    def invalid(value):
        raise ValueError(f"Non-finite JSON constant: {value}")
    return json.loads(raw, parse_constant=invalid)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    # Single-file atomic replacement; an interrupted update leaves the old snapshot.
    import os
    import tempfile
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


def timezone_name(value):
    try:
        ZoneInfo(value)
    except (ValueError, ZoneInfoNotFoundError, TypeError) as exc:
        raise ValueError(f"An IANA timezone is required: {value!r}") from exc
    return value


def birdcast_snapshot(csv_path=None, provenance_path=None):
    if csv_path is None:
        if provenance_path is not None:
            raise ValueError("BirdCast provenance requires --birdcast-csv")
        return {"status": "NOT_LOADED", "records": [], "source_url": BIRDCAST_URL,
                "reason": "No BirdCast pilot snapshot imported. Open the source dashboard for regional context."}
    if provenance_path is None:
        raise ValueError("--birdcast-provenance is required with --birdcast-csv")
    raw = Path(csv_path).read_bytes()
    provenance = strict_json(Path(provenance_path).read_text())
    for field in ("source_url", "retrieved_on", "citation", "reuse_basis", "sha256"):
        if not isinstance(provenance.get(field), str) or not provenance[field].strip():
            raise ValueError(f"BirdCast provenance requires {field}")
    url = urlsplit(provenance["source_url"])
    if url.scheme != "https" or not url.hostname:
        raise ValueError("BirdCast source_url must be an HTTPS URL")
    if not iso_date(provenance["retrieved_on"]):
        raise ValueError("BirdCast retrieved_on must be YYYY-MM-DD")
    if provenance["sha256"] != digest(raw):
        raise ValueError("BirdCast CSV checksum does not match provenance")
    import io
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    required = {"state", "night", "timezone", "birds_crossed", "status", "reason"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("BirdCast CSV requires: " + ", ".join(sorted(required)))
    records, seen = [], set()
    for source_row, row in enumerate(reader, 1):
        state = state_code(row["state"])
        night = iso_date(row["night"])
        if state is None or state in {"AK", "HI"} or night is None:
            raise ValueError(f"BirdCast row {source_row}: valid contiguous-U.S. state and ISO night required")
        timezone_name(row["timezone"])
        if (state, row["night"]) in seen:
            raise ValueError(f"Duplicate BirdCast state/night at row {source_row}")
        seen.add((state, row["night"]))
        status = row["status"].strip().upper()
        n = number(row["birds_crossed"])
        if status == "AVAILABLE":
            if n is None or n < 0:
                raise ValueError(f"BirdCast row {source_row}: AVAILABLE requires a finite nonnegative estimate")
        elif status in {"UNAVAILABLE", "OUT_OF_SEASON"}:
            if row["birds_crossed"].strip() or not row["reason"].strip():
                raise ValueError(f"BirdCast row {source_row}: missing data require a blank value and reason")
        else:
            raise ValueError(f"BirdCast row {source_row}: unknown status {status}")
        records.append({"state_code": state, "state": STATES[state], "date": night.isoformat(),
                        "timezone": row["timezone"], "birds_crossed": n, "status": status,
                        "reason": row["reason"].strip(), "source_row": source_row})
    if not records:
        raise ValueError("BirdCast CSV is empty; do not import a blank template")
    return {"status": "READY", "records": sorted(records, key=lambda r: (r["state_code"], r["date"])),
            "metric": "Estimated birds crossing the state during the night", "units": "birds/night",
            "date_basis": "Local evening date; sunset to following sunrise", "geographic_scale": "state",
            "source_file": Path(csv_path).name, **provenance}


def weather_request(meta, days, today=None):
    lat, lon = meta["latitude"], meta["longitude"]
    when = iso_date(meta["collection_date"])
    if lat is None or lon is None or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None, "MISSING_COORDINATES", "Valid sample coordinates are required; no state-centroid weather is substituted."
    if when is None:
        return None, "MISSING_DATE", "Sample collection date is missing or invalid."
    start = max(date(1940, 1, 1), when - timedelta(days=days))
    end = min((today or datetime.now(timezone.utc).date()) - timedelta(days=5), when + timedelta(days=days))
    if end < start:
        return None, "OUT_OF_RANGE", "The requested dates are outside the available historical ERA5 window (approximately five-day lag)."
    params = {"latitude": lat, "longitude": lon, "start_date": start.isoformat(), "end_date": end.isoformat(),
              "daily": ",".join(WEATHER_FIELDS), "models": "era5", "timezone": "auto", "cell_selection": "nearest",
              "elevation": "nan", "temperature_unit": "celsius", "precipitation_unit": "mm", "wind_speed_unit": "kmh"}
    return WEATHER_URL + "?" + urlencode(params), "READY", ""


def normalize_weather(raw, request_url, retrieved_at):
    data = strict_json(raw)
    if data.get("error"):
        raise ValueError("Weather service returned an error: " + str(data.get("reason")))
    timezone_name(data.get("timezone"))
    grid_lat, grid_lon = number(data.get("latitude")), number(data.get("longitude"))
    if grid_lat is None or grid_lon is None or not -90 <= grid_lat <= 90 or not -180 <= grid_lon <= 180:
        raise ValueError("Weather response lacks valid grid coordinates")
    daily = data.get("daily", {})
    dates = daily.get("time", [])
    if not dates or len(set(dates)) != len(dates) or any(iso_date(d) is None for d in dates):
        raise ValueError("Weather daily dates are empty, invalid, or repeated")
    units = data.get("daily_units", {})
    for key, expected in WEATHER_FIELDS.items():
        if units.get(key) != expected or len(daily.get(key, [])) != len(dates):
            raise ValueError(f"Weather field {key}: units or array length mismatch")
    rows = []
    for i, day in enumerate(dates):
        row = {"date": day}
        for key in WEATHER_FIELDS:
            value = daily[key][i]
            if value is not None and (number(value) is None or isinstance(value, bool)):
                raise ValueError(f"Invalid weather value: {key} on {day}")
            row[key] = number(value)
            if key != "temperature_2m_mean" and row[key] is not None and row[key] < 0:
                raise ValueError(f"Negative weather value: {key}")
        rows.append(row)
    return {"status": "READY", "dataset": "ERA5", "provider": "Open-Meteo / Copernicus Climate Change Service",
            "resolution": "0.25° grid (approximately 25 km)", "timezone": data["timezone"],
            "grid_latitude": grid_lat, "grid_longitude": grid_lon, "date_basis": "Local calendar day",
            "source_url": "https://open-meteo.com/en/docs/historical-weather-api", "request_url": request_url,
            "retrieved_at": retrieved_at, "raw_sha256": digest(raw), "units": WEATHER_FIELDS,
            "rows": sorted(rows, key=lambda r: r["date"]), "license": "CC BY 4.0; ERA5 attribution applies"}


def read_metadata(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    seen = set()
    for row in rows:
        sid = str(row.get("sample_id") or row.get("sample") or "").strip()
        if not sid or sid in seen:
            raise ValueError("Metadata must have nonempty, unique sample_id (or sample) values")
        row["sample_id"] = sid
        seen.add(sid)
    if not rows:
        raise ValueError("Metadata is empty")
    return rows


def build_snapshot(metadata, cache_dir, days=30, fetch_weather=False, refresh=False,
                   birdcast_csv=None, birdcast_provenance=None, opener=urlopen):
    if not 1 <= days <= 365:
        raise ValueError("days must be between 1 and 365")
    if refresh and not fetch_weather:
        raise ValueError("--refresh-weather requires --fetch-weather")
    birdcast = birdcast_snapshot(birdcast_csv, birdcast_provenance)
    bindings, weather = {}, {}
    for row in read_metadata(metadata):
        sid, meta = row["sample_id"], sample_metadata(row)
        url, status, reason = weather_request(meta, days)
        binding = {"metadata": meta, "status": status, "reason": reason, "weather_key": None}
        bindings[sid] = binding
        if url is None:
            continue
        key = digest(url.encode())
        target = Path(cache_dir) / "weather" / (key + ".json")
        if key in weather:
            binding["weather_key"] = key
            continue
        cached = strict_json(target.read_text()) if target.exists() and not refresh else None
        if cached is None and fetch_weather:
            try:
                with opener(url, timeout=60) as response:
                    raw = response.read()
                retrieved = stamp()
                context = normalize_weather(raw, url, retrieved)
                cached = {"request_url": url, "retrieved_at": retrieved, "raw_sha256": digest(raw), "raw": raw.decode("utf-8")}
                write_json(target, cached)
            except Exception as exc:
                binding.update(status="FETCH_FAILED", reason=f"Weather retrieval failed ({type(exc).__name__}); rerun the cache command to retry.")
                print(f"{sid}: {binding['reason']}")
                continue
        if cached is None:
            binding.update(status="NOT_LOADED", reason="Weather snapshot not loaded; build the cache with --fetch-weather.")
            continue
        raw = cached["raw"].encode("utf-8")
        if cached["request_url"] != url or cached["raw_sha256"] != digest(raw):
            raise ValueError(f"Weather cache checksum/request mismatch: {target}")
        context = normalize_weather(raw, url, cached["retrieved_at"])
        weather[key] = context
        binding["weather_key"] = key
    return {"schema_version": 1, "created_at": stamp(), "window_days": days, "states": STATES,
            "metadata_sha256": digest(Path(metadata).read_bytes()), "bindings": bindings,
            "weather": weather, "birdcast": birdcast}


def load_snapshot(path, samples):
    """Validate a cache and reject stale sample bindings before report embedding."""
    raw = Path(path).read_bytes()
    data = strict_json(raw)
    if data.get("schema_version") != 1 or not isinstance(data.get("bindings"), dict) or not isinstance(data.get("weather"), dict):
        raise ValueError("Unsupported ecological snapshot; rebuild with build_ecological_context.py")
    if data.get("birdcast", {}).get("status") not in {"READY", "NOT_LOADED"}:
        raise ValueError("Invalid BirdCast snapshot status")
    bird = data["birdcast"]
    seen = set()
    for row in bird.get("records", []):
        key = (row.get("state_code"), row.get("date"))
        if key[0] not in STATES or key[0] in {"AK", "HI"} or iso_date(key[1]) is None or key in seen:
            raise ValueError("Invalid or duplicate BirdCast state/night in ecological snapshot")
        seen.add(key)
        timezone_name(row.get("timezone"))
        value = row.get("birds_crossed")
        if row.get("status") == "AVAILABLE":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Invalid BirdCast estimate in ecological snapshot")
        elif row.get("status") not in {"UNAVAILABLE", "OUT_OF_SEASON"} or value is not None or not row.get("reason"):
            raise ValueError("Invalid BirdCast missing-data status in ecological snapshot")
    if bird["status"] == "READY" and not seen:
        raise ValueError("READY BirdCast snapshot has no records")
    for context in data["weather"].values():
        if context.get("dataset") != "ERA5" or context.get("units") != WEATHER_FIELDS:
            raise ValueError("Unexpected weather dataset/units in ecological snapshot")
        timezone_name(context.get("timezone"))
        dates = [r.get("date") for r in context.get("rows", [])]
        if any(iso_date(d) is None for d in dates) or len(set(dates)) != len(dates):
            raise ValueError("Invalid or duplicate weather dates in ecological snapshot")
        for row in context["rows"]:
            for field in WEATHER_FIELDS:
                value = row.get(field)
                if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)):
                    raise ValueError("Invalid weather value in ecological snapshot")
                if field != "temperature_2m_mean" and value is not None and value < 0:
                    raise ValueError("Negative precipitation or wind in ecological snapshot")
    bindings = {}
    for sample in samples:
        sid = sample["sample_id"]
        binding = data["bindings"].get(sid)
        if binding is None:
            bindings[sid] = {"status": "NOT_LOADED", "reason": "Sample not included in this ecological snapshot.", "weather_key": None}
        elif binding.get("metadata") != sample_metadata(sample):
            bindings[sid] = {"status": "STALE_METADATA", "reason": "Sample date or location changed; rebuild the ecological snapshot.", "weather_key": None}
        else:
            if binding.get("status") == "READY" and binding.get("weather_key") not in data["weather"]:
                raise ValueError("Ecological snapshot references a missing weather context")
            bindings[sid] = binding
    data["bindings"] = bindings
    data["snapshot_sha256"] = digest(raw)
    data["source_file"] = Path(path).name
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("resources/ecology/ecological-context.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path("resources/ecology/cache"))
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--fetch-weather", action="store_true")
    parser.add_argument("--refresh-weather", action="store_true")
    parser.add_argument("--birdcast-csv", type=Path)
    parser.add_argument("--birdcast-provenance", type=Path)
    parser.add_argument("--clear-birdcast", action="store_true", help="Explicitly remove a previously imported BirdCast snapshot")
    args = parser.parse_args()
    if args.clear_birdcast and (args.birdcast_csv or args.birdcast_provenance):
        parser.error("--clear-birdcast cannot be combined with BirdCast input files")
    previous_birdcast = None
    if not args.birdcast_csv and not args.clear_birdcast and args.output.exists():
        previous_birdcast = load_snapshot(args.output, read_metadata(args.metadata))["birdcast"]
    snapshot = build_snapshot(args.metadata, args.cache_dir, args.days, args.fetch_weather,
                              args.refresh_weather, args.birdcast_csv, args.birdcast_provenance)
    if previous_birdcast is not None:
        snapshot["birdcast"] = previous_birdcast
    write_json(args.output, snapshot)
    print(f"Saved {args.output}: {len(snapshot['weather'])} weather contexts; BirdCast {snapshot['birdcast']['status']}")


if __name__ == "__main__":
    main()
