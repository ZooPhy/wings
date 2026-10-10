"""Read BirdCast's embedded dashboard data without executing remote JavaScript.

This is an undocumented page format, not a supported public API. Only the
literal subset emitted by Nuxt/devalue is accepted; changes fail closed.
"""
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo


class BirdCastUnavailable(ValueError):
    pass


class LiteralReader:
    def __init__(self, text, names=None):
        self.text, self.pos, self.names = text, 0, names or {}

    def space(self):
        while self.pos < len(self.text) and self.text[self.pos].isspace():
            self.pos += 1

    def take(self, token):
        self.space()
        if not self.text.startswith(token, self.pos):
            raise ValueError("Unsupported BirdCast page serialization")
        self.pos += len(token)

    def value(self, depth=0):
        if depth > 100:
            raise ValueError("BirdCast data nesting exceeds limit")
        self.space()
        c = self.text[self.pos:self.pos + 1]
        if c == '"':
            value, size = json.JSONDecoder().raw_decode(self.text[self.pos:])
            self.pos += size
            return value
        if c in ('{', '['):
            self.pos += 1
            result = {} if c == '{' else []
            close = '}' if c == '{' else ']'
            self.space()
            while not self.text.startswith(close, self.pos):
                if c == '{':
                    self.space()
                    if self.text[self.pos:self.pos + 1] == '"':
                        key = self.value(depth + 1)
                    else:
                        match = re.match(r'[A-Za-z_$][\w$]*', self.text[self.pos:])
                        if not match:
                            raise ValueError("Unsupported BirdCast object key")
                        key = match.group()
                        self.pos += len(key)
                    self.take(':')
                    if key in result:
                        raise ValueError("Duplicate BirdCast data key")
                    result[key] = self.value(depth + 1)
                else:
                    result.append(self.value(depth + 1))
                self.space()
                if self.text.startswith(close, self.pos):
                    break
                self.take(',')
            self.take(close)
            return result
        if self.text.startswith('new Date(', self.pos):
            self.take('new Date(')
            value = self.value(depth + 1)
            self.take(')')
            return value  # UI chart timestamps; no code execution.
        if self.text.startswith('void 0', self.pos):
            self.take('void 0')
            return None
        match = re.match(r'-?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', self.text[self.pos:])
        if match:
            token = match.group()
            self.pos += len(token)
            value = float(token) if any(c in token for c in '.eE') else int(token)
            if not math.isfinite(value):
                raise ValueError("Nonfinite BirdCast number")
            return value
        match = re.match(r'[A-Za-z_$][\w$]*', self.text[self.pos:])
        if match:
            token = match.group()
            self.pos += len(token)
            literals = {'true': True, 'false': False, 'null': None, 'undefined': None}
            if token in literals:
                return literals[token]
            if token in self.names:
                return self.names[token]
        raise ValueError("Unsupported BirdCast expression")

    def complete(self):
        value = self.value()
        self.space()
        if self.pos != len(self.text):
            raise ValueError("Unexpected trailing BirdCast expression")
        return value


def page_data(raw):
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("BirdCast page exceeds size limit")
    text = raw.decode('utf-8')
    script = re.search(r'window\.__NUXT__\s*=\s*(.*?)</script\s*>', text, re.S)
    if not script:
        raise ValueError("BirdCast page has no embedded Nuxt data")
    match = re.fullmatch(r'\(function\(([^)]*)\)\{(.*?)return (.*)\}\((.*)\)\);?\s*', script[1], re.S)
    if not match:
        raise ValueError("BirdCast page format changed")
    names = match[1].split(',')
    if len(names) != len(set(names)) or any(not re.fullmatch(r'[A-Za-z_$][\w$]*', n) for n in names):
        raise ValueError("Invalid BirdCast literal aliases")
    args = LiteralReader('[' + match[4] + ']').complete()
    if len(args) != len(names):
        raise ValueError("BirdCast literal alias count mismatch")
    aliases = dict(zip(names, args))
    # devalue fills shared object literals with simple property assignments.
    prelude = LiteralReader(match[2], aliases)
    while prelude.pos < len(prelude.text):
        prelude.space()
        assignment = re.match(r'([A-Za-z_$][\w$]*)\.([A-Za-z_$][\w$]*)=', prelude.text[prelude.pos:])
        if not assignment or not isinstance(aliases.get(assignment[1]), dict):
            raise ValueError('Unsupported BirdCast alias assignment')
        prelude.pos += len(assignment[0])
        value = prelude.value()
        if isinstance(value, (dict, list)):
            raise ValueError('Nonliteral BirdCast alias assignment')
        aliases[assignment[1]][assignment[2]] = value
        prelude.take(';')
    data = LiteralReader(match[3], aliases).complete()
    candidates = [v for v in data.get('fetch', {}).values()
                  if isinstance(v, dict) and 'migrationLiveDataFromApi' in v]
    if len(candidates) != 1:
        raise ValueError("BirdCast migration data missing or ambiguous")
    return candidates[0]


def normalize_page(raw, state, night, *, data=None):
    data = page_data(raw) if data is None else data
    live = data.get('migrationLiveDataFromApi') or {}
    region = 'US-' + state
    if data.get('night') != night or data.get('region', {}).get('code') != region:
        raise ValueError("BirdCast page region/night does not match request")
    if live.get('regionCode') != region:
        raise ValueError("BirdCast migration region does not match request")
    if data.get('hasNightlyData') is False or not live.get('nightSeries'):
        raise BirdCastUnavailable('BirdCast reports no nightly observations for this region/date; no estimate is available.')
    zone = live.get('timezoneName')
    ZoneInfo(zone)
    total = live.get('cumulativeBirds')
    series = live.get('nightSeries') or []
    if data.get('live') is True:
        raise ValueError("BirdCast night is still in progress")
    if not series or data.get('hasNightlyData') is False:
        raise ValueError("BirdCast has no nightly observations")
    if isinstance(total, bool) or not isinstance(total, (int, float)) or not math.isfinite(total) or total < 0:
        raise ValueError("BirdCast estimate is missing or invalid")
    # Keep only verified count/timestamp fields. Speed/height units are not assumed.
    observations = []
    for row in series:
        local = datetime.fromisoformat(row['localTime'])
        if local.date() not in (date.fromisoformat(night), date.fromisoformat(night) + timedelta(days=1)):
            raise ValueError("BirdCast observation is outside requested night")
        count = row.get('numAloft')
        if count is not None and (isinstance(count, bool) or not isinstance(count, (int, float)) or not math.isfinite(count) or count < 0):
            raise ValueError("BirdCast birds-aloft value is invalid")
        observations.append({'local_time': row['localTime'], 'birds_aloft': count})
    return {'state_code': state, 'date': night, 'timezone': zone,
            'birds_crossed': total, 'status': 'AVAILABLE', 'reason': '',
            'night_series': observations}


def validate_season(context):
    """Validate the small, canonical seasonal payload used by saved reports."""
    start, end = (date.fromisoformat(context[k]) for k in ('start_date', 'end_date'))
    if end < start or (end - start).days > 200:
        raise ValueError('Invalid BirdCast season bounds')
    if context.get('metric') != 'cumulative_birds_crossed' or context.get('schema_version') != 1:
        raise ValueError('Unknown BirdCast seasonal metric/schema')
    rows = context['rows']
    if not rows or len(rows) > (end - start).days + 1:
        raise ValueError('Invalid BirdCast seasonal series length')
    previous, previous_count = None, None
    for row in rows:
        day = date.fromisoformat(row['date'])
        if not start <= day <= end or (previous is not None and day <= previous):
            raise ValueError('Invalid BirdCast seasonal date order')
        for field in ('cumulative_birds', 'mean_birds_aloft'):
            value = row.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                raise ValueError('Invalid BirdCast seasonal count')
        count = row.get('cumulative_birds')
        if count is not None:
            if previous_count is not None and count < previous_count:
                raise ValueError('BirdCast cumulative crossings decreased')
            previous_count = count
        previous = day
    if previous_count is None:
        raise ValueError('BirdCast season has no crossing estimates')
    return context


def normalize_season(data, state, night, nightly_total):
    """totalBirds is seasonal cumulative passage; numAloft is nightly mean aloft.

    Calendar labels are kept verbatim, never shifted using UTC or host time.
    Only adjacent cumulative values can yield a nightly crossing increment.
    """
    hist = data.get('migrationHistDataFromApi') or {}
    live = data.get('migrationLiveDataFromApi') or {}
    bounds = live.get('season') or {}
    if hist.get('regionCode') != 'US-' + state or bounds.get('code') not in ('SP', 'FA'):
        raise ValueError('BirdCast seasonal region/bounds unavailable')
    start, end = (datetime.strptime(bounds[k], '%Y%m%d').date() for k in ('startDate', 'endDate'))
    if not start <= date.fromisoformat(night) <= end:
        raise ValueError('Matched night is outside BirdCast season')
    rows = []
    for item in (hist.get('season') or {}).get('currentSeasonSeries', []):
        label = item.get('dateTime', '')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T00:00:00', label):
            raise ValueError('Unrecognized BirdCast seasonal calendar label')
        rows.append({'date': label[:10], 'cumulative_birds': item.get('totalBirds'),
                     'mean_birds_aloft': item.get('numAloft')})
    context = validate_season({
        'schema_version': 1, 'state_code': state, 'season_code': bounds['code'],
        'key': f'US-{state}_{start.isoformat()}_{end.isoformat()}',
        'label': f'{"Spring" if bounds["code"] == "SP" else "Fall"} {start.year}',
        'start_date': start.isoformat(), 'end_date': end.isoformat(),
        'metric': 'cumulative_birds_crossed', 'rows': rows,
        'source_generated_at': hist.get('generatedDt'),
    })
    # A complete local night must have elapsed. Do not turn live/future values
    # into apparently completed seasonal passage.
    local_today = datetime.now(ZoneInfo(live['timezoneName'])).date()
    if any(r['cumulative_birds'] is not None and date.fromisoformat(r['date']) >= local_today for r in rows):
        raise ValueError('BirdCast seasonal series includes an unfinished night')
    indexed = {r['date']: r['cumulative_birds'] for r in rows}
    current = indexed.get(night)
    previous = 0 if night == start.isoformat() else indexed.get((date.fromisoformat(night) - timedelta(days=1)).isoformat())
    if current is not None and previous is not None:
        # The source rounds the independent nightly figure to whole birds.
        if abs(current - previous - nightly_total) > max(2, nightly_total * 1e-6):
            raise ValueError('Seasonal increment disagrees with matched nightly estimate')
    return context


def collect_seasons(records):
    """One coherent source snapshot per state/season; never splice revisions."""
    chosen = {}
    for record in records:
        context = record.get('seasonal_context')
        if not context:
            continue
        key = context['key']
        rank = (max(r['date'] for r in context['rows'] if r['cumulative_birds'] is not None),
                record.get('retrieved_at', ''))
        if key not in chosen or rank > chosen[key][0]:
            chosen[key] = (rank, {**context, **{k: record.get(k) for k in
                         ('source_url', 'retrieved_at', 'raw_sha256')}})
    return [chosen[key][1] for key in sorted(chosen)]


def acquire(rows, cache_dir, *, helpers, fetch=False, refresh=False, night_offset=-1, opener=urlopen):
    sample_metadata, iso_date, STATES, digest, stamp, strict_json, write_json = (
        helpers[k] for k in ('sample_metadata', 'iso_date', 'STATES', 'digest', 'stamp', 'strict_json', 'write_json'))
    if night_offset not in (-1, 0):
        raise ValueError("BirdCast night offset must be -1 or 0")
    if refresh and not fetch:
        raise ValueError("Refreshing BirdCast requires fetching")
    records, bindings, resolved = [], {}, {}
    for row in rows:
        meta = sample_metadata(row)
        when = iso_date(meta['collection_date'])
        state = meta['state']
        binding = {'metadata': meta, 'night': None, 'state_code': None}
        bindings[row['sample_id']] = binding
        if when is None:
            binding.update(status='MISSING_DATE', reason='An exact YYYY-MM-DD collection date is required.')
            continue
        if meta['country'] != 'US' or state not in STATES or state in ('AK', 'HI'):
            binding.update(status='UNSUPPORTED_LOCATION', reason='A contiguous-U.S. country/state is required.')
            continue
        night = (when + timedelta(days=night_offset)).isoformat()
        binding.update(night=night, state_code=state)
        key = (state, night)
        if key not in resolved:
            url = f'https://dashboard.birdcast.org/region/US-{state}?night={night}'
            target = Path(cache_dir) / 'birdcast' / f'US-{state}_{night}.json'
            record = {'state_code': state, 'state': STATES[state], 'date': night,
                      'timezone': None, 'birds_crossed': None, 'status': 'UNAVAILABLE',
                      'reason': '', 'source_url': url}
            fallback = None
            try:
                cached = strict_json(target.read_text()) if target.exists() and not refresh else None
                if cached is not None:
                    payload = cached['record']
                    if cached['request_url'] != url or cached['record_sha256'] != digest(json.dumps(payload, sort_keys=True, allow_nan=False).encode()):
                        raise ValueError('BirdCast cache checksum/request mismatch')
                    if payload.get('state_code') != state or payload.get('date') != night or payload.get('status') != 'AVAILABLE':
                        raise ValueError('BirdCast cached record does not match request')
                    if payload.get('seasonal_context'):
                        validate_season(payload['seasonal_context'])
                    fallback = payload
                if cached is None or refresh or (fetch and cached.get('seasonal_schema') != 1):
                    if not fetch:
                        record['reason'] = 'BirdCast snapshot not cached; enable fetching.'
                    else:
                        with opener(url, timeout=60) as response:
                            raw = response.read(8 * 1024 * 1024 + 1)
                        data = page_data(raw)
                        normalized = normalize_page(raw, state, night, data=data)
                        try:
                            normalized['seasonal_context'] = normalize_season(data, state, night, normalized['birds_crossed'])
                            normalized['seasonal_reason'] = ''
                        except (ValueError, TypeError, KeyError) as exc:
                            # A seasonal schema change must not erase a validated nightly total.
                            normalized['seasonal_context'] = None
                            normalized['seasonal_reason'] = f'Seasonal series unavailable or invalid ({type(exc).__name__}); nightly estimate retained.'
                        payload = {**record, **normalized, 'retrieved_at': stamp(), 'raw_sha256': digest(raw)}
                        cached = {'request_url': url, 'record': payload,
                                  'seasonal_schema': 1,
                                  'record_sha256': digest(json.dumps(payload, sort_keys=True, allow_nan=False).encode())}
                        write_json(target, cached)
                if cached is not None:
                    record = cached['record']
            except BirdCastUnavailable as exc:
                if fallback is not None:
                    record = {**fallback, 'seasonal_reason': 'Seasonal upgrade unavailable; retaining the cached nightly estimate.'}
                else:
                    record['reason'] = str(exc)
            except Exception as exc:
                # Do not leak URLs/keys from exception text. Failures are retried next run.
                if fallback is not None:
                    record = {**fallback, 'seasonal_reason': f'Seasonal upgrade failed ({type(exc).__name__}); retaining the cached nightly estimate.'}
                else:
                    record['reason'] = f'BirdCast retrieval or validation failed ({type(exc).__name__}); retry or inspect the source dashboard.'
            records.append(record)
            resolved[key] = record
        record = resolved[key]
        binding.update(status=record['status'], reason=record['reason'], source_url=record['source_url'])
    seasons = collect_seasons(records)
    # Seasonal arrays are deduplicated in the report; cached nightly envelopes
    # retain their original self-contained source evidence.
    records = [{k: v for k, v in r.items() if k != 'seasonal_context'} for r in records]
    return {'status': 'READY' if records else 'NOT_LOADED', 'records': sorted(records, key=lambda r: (r['state_code'], r['date'])),
            'seasons': seasons,
            'bindings': bindings, 'night_offset_days': night_offset,
            'metric': 'Estimated birds crossing the state during the night', 'units': 'birds/night',
            'date_basis': 'Local evening date; sunset to following sunrise', 'geographic_scale': 'state',
            'source_url': 'https://dashboard.birdcast.org/', 'retrieved_on': datetime.now(timezone.utc).date().isoformat(),
            'citation': 'BirdCast Migration Dashboard, Cornell Lab of Ornithology.',
            'reuse_basis': 'Source terms apply; automated retrieval does not confer redistribution rights.',
            'acquisition': 'dashboard_embedded_nuxt_v1',
            'sha256': digest(json.dumps({'records': records, 'seasons': seasons}, sort_keys=True, allow_nan=False).encode())}
