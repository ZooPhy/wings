#!/usr/bin/env python3
"""Cache ecological context for display. No sequence data or browser-time requests.

BirdCast supports a WINGS CSV or metadata-driven dashboard acquisition.
Weather requests send only coordinates and dates to Open-Meteo when requested.
"""
import argparse
import csv
import hashlib
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit, parse_qs
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
WEATHER_EXTRA_FIELDS = {"temperature_2m_min": "°C", "temperature_2m_max": "°C", "weather_code": "wmo code"}
ALL_WEATHER_FIELDS = {**WEATHER_FIELDS, **WEATHER_EXTRA_FIELDS}
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


def weather_request(meta, days, today=None, *, extended=True):
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
              "daily": ",".join(ALL_WEATHER_FIELDS if extended else WEATHER_FIELDS), "models": "era5", "timezone": "auto", "cell_selection": "nearest",
              "elevation": "nan", "temperature_unit": "celsius", "precipitation_unit": "mm", "wind_speed_unit": "kmh"}
    return WEATHER_URL + "?" + urlencode(params), "READY", ""


def validate_weather_row(row, fields):
    for key in fields:
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f'Invalid weather value: {key}')
        if not key.startswith('temperature_') and value < 0:
            raise ValueError(f'Negative weather value: {key}')
        if key == 'weather_code' and (value != int(value) or not 0 <= value <= 99):
            raise ValueError('Invalid weather condition code')
    temperatures = [row.get(k) for k in ('temperature_2m_min', 'temperature_2m_mean', 'temperature_2m_max')]
    known = [v for v in temperatures if v is not None]
    if known != sorted(known):
        raise ValueError('Weather temperature minimum/mean/maximum are inconsistent')


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
    requested = set(parse_qs(urlsplit(request_url).query).get('daily', [''])[0].split(','))
    fields = {**WEATHER_FIELDS, **{k: v for k, v in WEATHER_EXTRA_FIELDS.items() if k in daily or k in requested}}
    for key, expected in fields.items():
        if units.get(key) != expected or len(daily.get(key, [])) != len(dates):
            raise ValueError(f"Weather field {key}: units or array length mismatch")
    query = parse_qs(urlsplit(request_url).query)
    if query.get('start_date') and query.get('end_date'):
        if any(not query['start_date'][0] <= d <= query['end_date'][0] for d in dates):
            raise ValueError('Weather response has dates outside the requested interval')
    rows = []
    for i, day in enumerate(dates):
        row = {"date": day}
        for key in fields:
            value = daily[key][i]
            if value is not None and (number(value) is None or isinstance(value, bool)):
                raise ValueError(f"Invalid weather value: {key} on {day}")
            row[key] = number(value)
        validate_weather_row(row, fields)
        rows.append(row)
    return {"status": "READY", "dataset": "ERA5", "provider": "Open-Meteo / Copernicus Climate Change Service",
            "resolution": "0.25° grid (approximately 25 km)", "timezone": data["timezone"],
            "grid_latitude": grid_lat, "grid_longitude": grid_lon, "date_basis": "Local calendar day",
            "source_url": "https://open-meteo.com/en/docs/historical-weather-api", "request_url": request_url,
            "retrieved_at": retrieved_at, "raw_sha256": digest(raw), "units": fields,
            "condition_basis": "Most severe condition during the local calendar day; source-derived WMO code",
            "rows": sorted(rows, key=lambda r: r["date"]), "license": "CC BY 4.0; ERA5 attribution applies"}


def read_weather_cache(path, expected_url=None):
    cached = strict_json(path.read_text())
    url, raw = cached['request_url'], cached['raw'].encode('utf-8')
    if (expected_url is not None and url != expected_url) or path.stem != digest(url.encode()) or cached['raw_sha256'] != digest(raw):
        raise ValueError(f'Weather cache checksum/request mismatch: {path}')
    return normalize_weather(raw, url, cached['retrieved_at'])


def fallback_weather(cache_dir, request_url):
    """Reuse one compatible source response, never merge different locations."""
    wanted = parse_qs(urlsplit(request_url).query)
    signature = lambda q: {k: v for k, v in q.items() if k not in ('daily', 'start_date', 'end_date')}
    choices = []
    for path in sorted((Path(cache_dir) / 'weather').glob('*.json')):
        try:
            cached = strict_json(path.read_text())
            url = cached['request_url']
            if urlsplit(url)[:2] != urlsplit(request_url)[:2] or urlsplit(url).path != urlsplit(request_url).path:
                continue
            query = parse_qs(urlsplit(url).query)
            if signature(query) != signature(wanted):
                continue
            if query['end_date'][0] < wanted['start_date'][0] or query['start_date'][0] > wanted['end_date'][0]:
                continue
            context = read_weather_cache(path)
            overlap = sum(wanted['start_date'][0] <= r['date'] <= wanted['end_date'][0] for r in context['rows'])
            if overlap:
                choices.append(((overlap, len(context['units']), context.get('retrieved_at', '')), digest(url.encode()), context))
        except (ValueError, KeyError, TypeError, OSError):
            # Unrelated/invalid cache entries are never borrowed as a fallback.
            continue
    if not choices:
        return None
    _, key, context = max(choices, key=lambda item: item[0])
    return key, context


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
                   birdcast_csv=None, birdcast_provenance=None, opener=urlopen,
                   fetch_birdcast=False, refresh_birdcast=False, birdcast_night_offset=-1,
                   birdcast_cache=False):
    if not 1 <= days <= 365:
        raise ValueError("days must be between 1 and 365")
    if refresh and not fetch_weather:
        raise ValueError("--refresh-weather requires --fetch-weather")
    if refresh_birdcast and not fetch_birdcast:
        raise ValueError('--refresh-birdcast requires --fetch-birdcast')
    if (fetch_birdcast or birdcast_cache) and (birdcast_csv or birdcast_provenance):
        raise ValueError('Choose BirdCast acquisition or CSV import, not both')
    rows = read_metadata(metadata)
    if fetch_birdcast or birdcast_cache:
        import runpy
        acquire = runpy.run_path(str(Path(__file__).with_name('birdcast_data.py')))['acquire']
        birdcast = acquire(rows, cache_dir, helpers=globals(), fetch=fetch_birdcast,
                           refresh=refresh_birdcast, night_offset=birdcast_night_offset, opener=opener)
    else:
        birdcast = birdcast_snapshot(birdcast_csv, birdcast_provenance)
    bindings, weather, resolved = {}, {}, {}
    for row in rows:
        sid, meta = row["sample_id"], sample_metadata(row)
        url, status, reason = weather_request(meta, days)
        binding = {"metadata": meta, "status": status, "reason": reason, "weather_key": None}
        bindings[sid] = binding
        if url is None:
            continue
        key = digest(url.encode())
        target = Path(cache_dir) / "weather" / (key + ".json")
        if key in resolved:
            binding.update(resolved[key])
            continue
        context = read_weather_cache(target, url) if target.exists() and not refresh else None
        failure = ''
        if context is None and fetch_weather:
            try:
                with opener(url, timeout=60) as response:
                    raw = response.read()
                retrieved = stamp()
                context = normalize_weather(raw, url, retrieved)
                cached = {"request_url": url, "retrieved_at": retrieved, "raw_sha256": digest(raw), "raw": raw.decode("utf-8")}
                write_json(target, cached)
            except Exception as exc:
                context = None
                failure = f"Weather retrieval failed ({type(exc).__name__}); rerun the cache command to retry."
                print(f"{sid}: {failure}")
        source_key = key
        if context is None:
            fallback = fallback_weather(cache_dir, url)
            if fallback:
                source_key, context = fallback
                binding['reason'] = 'Using a compatible cached weather response; dates or extended fields may be incomplete.'
        if context is None:
            binding.update(status='FETCH_FAILED' if failure else 'NOT_LOADED',
                           reason=failure or 'Weather snapshot not loaded; build the cache with --fetch-weather.')
        else:
            weather[source_key] = context
            binding['weather_key'] = source_key
        resolved[key] = {k: binding[k] for k in ('status', 'reason', 'weather_key')}
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
        if row.get('timezone') is not None or row.get('status') == 'AVAILABLE':
            timezone_name(row.get("timezone"))
        value = row.get("birds_crossed")
        if row.get("status") == "AVAILABLE":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("Invalid BirdCast estimate in ecological snapshot")
        elif row.get("status") not in {"UNAVAILABLE", "OUT_OF_SEASON"} or value is not None or not row.get("reason"):
            raise ValueError("Invalid BirdCast missing-data status in ecological snapshot")
    if bird["status"] == "READY" and not seen:
        raise ValueError("READY BirdCast snapshot has no records")
    if bird.get('seasons'):
        import runpy
        validate_season = runpy.run_path(str(Path(__file__).with_name('birdcast_data.py')))['validate_season']
        season_keys = set()
        for context in bird['seasons']:
            validate_season(context)
            state = context.get('state_code')
            expected_key = f'US-{state}_{context["start_date"]}_{context["end_date"]}'
            if state not in STATES or state in {'AK', 'HI'} or context.get('key') != expected_key or expected_key in season_keys:
                raise ValueError('Invalid or duplicate BirdCast season in ecological snapshot')
            season_keys.add(expected_key)
    for context in data["weather"].values():
        units = context.get('units', {})
        if context.get("dataset") != "ERA5" or not isinstance(units, dict) or any(units.get(k) != v for k, v in WEATHER_FIELDS.items()) or any(ALL_WEATHER_FIELDS.get(k) != v for k, v in units.items()):
            raise ValueError("Unexpected weather dataset/units in ecological snapshot")
        timezone_name(context.get("timezone"))
        dates = [r.get("date") for r in context.get("rows", [])]
        if any(iso_date(d) is None for d in dates) or len(set(dates)) != len(dates):
            raise ValueError("Invalid or duplicate weather dates in ecological snapshot")
        for row in context["rows"]:
            if any(row.get(k) is not None and k not in units for k in WEATHER_EXTRA_FIELDS):
                raise ValueError('Weather field has no declared units')
            validate_weather_row(row, units)
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
    for sample in samples:
        binding = bird.get('bindings', {}).get(sample['sample_id'])
        if binding and binding.get('metadata') != sample_metadata(sample):
            binding.update(status='STALE_METADATA', reason='Sample date or location changed; rebuild the ecological snapshot.', night=None)
    data["snapshot_sha256"] = digest(raw)
    data["source_file"] = Path(path).name
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("resources/ecology/ecological-context.json"))
    parser.add_argument("--cache-dir", type=Path, default=Path("resources/ecology/cache"))
    parser.add_argument('--base-snapshot', type=Path, help='Retain valid weather bindings from an existing snapshot')
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--fetch-weather", action="store_true")
    parser.add_argument("--refresh-weather", action="store_true")
    parser.add_argument('--fetch-birdcast', action='store_true', help='Fetch one state/night per unique metadata match')
    parser.add_argument('--birdcast-cache', action='store_true', help='Bind metadata to cached BirdCast records without network access')
    parser.add_argument('--refresh-birdcast', action='store_true')
    parser.add_argument('--birdcast-night-offset', type=int, choices=(-1, 0), default=-1,
                        help='-1: preceding night (default); 0: collection-date evening')
    parser.add_argument("--birdcast-csv", type=Path)
    parser.add_argument("--birdcast-provenance", type=Path)
    parser.add_argument("--clear-birdcast", action="store_true", help="Explicitly remove a previously imported BirdCast snapshot")
    args = parser.parse_args()
    if args.clear_birdcast and (args.birdcast_csv or args.birdcast_provenance or args.fetch_birdcast or args.birdcast_cache):
        parser.error("--clear-birdcast cannot be combined with BirdCast input files")
    previous_birdcast = None
    if not args.birdcast_csv and not args.clear_birdcast and not args.fetch_birdcast and not args.birdcast_cache and args.output.exists():
        previous_birdcast = load_snapshot(args.output, read_metadata(args.metadata))["birdcast"]
    snapshot = build_snapshot(args.metadata, args.cache_dir, args.days, args.fetch_weather,
                              args.refresh_weather, args.birdcast_csv, args.birdcast_provenance,
                              fetch_birdcast=args.fetch_birdcast, refresh_birdcast=args.refresh_birdcast,
                              birdcast_night_offset=args.birdcast_night_offset, birdcast_cache=args.birdcast_cache)
    if args.base_snapshot:
        base = load_snapshot(args.base_snapshot, read_metadata(args.metadata))
        for sid, binding in base['bindings'].items():
            if binding.get('status') == 'READY' and snapshot['bindings'][sid].get('status') != 'READY':
                key = binding['weather_key']
                snapshot['bindings'][sid] = binding
                snapshot['weather'][key] = base['weather'][key]
    if previous_birdcast is not None:
        snapshot["birdcast"] = previous_birdcast
    write_json(args.output, snapshot)
    print(f"Saved {args.output}: {len(snapshot['weather'])} weather contexts; BirdCast {snapshot['birdcast']['status']}")


if __name__ == "__main__":
    main()
