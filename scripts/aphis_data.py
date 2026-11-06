"""Fetch the official APHIS CSV once per preparation; pin validated run evidence.

No sample metadata is sent to APHIS. Cache entries are immutable pairs of CSV and
provenance, published with an atomic pointer only after validation succeeds.
"""
from datetime import datetime, timezone
import csv
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib import error, request
from urllib.parse import urlsplit
import uuid

SOURCE_PAGE = 'https://www.aphis.usda.gov/livestock-poultry-disease/avian/avian-influenza/hpai-detections/wild-birds'
# Identified in the official page's data-csv-url attribute, 2026-11-06.
CSV_URL = 'https://www.aphis.usda.gov/sites/default/files/hpai-wild-birds.csv'
MAX_BYTES = 30 * 1024 * 1024
SCHEMA = 'wings.aphis-acquisition.v1'


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def official_url(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.hostname == 'www.aphis.usda.gov'
            and parsed.port in (None, 443) and not parsed.username and not parsed.password)


class OfficialRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not official_url(newurl):
            raise ValueError('APHIS redirected outside the official HTTPS host')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_csv():
    opener = request.build_opener(OfficialRedirect())
    req = request.Request(CSV_URL, headers={
        'User-Agent': 'WINGS/1.0 (+https://github.com/ZooPhy/wings)',
        'Accept': 'text/csv, text/plain;q=0.9, */*;q=0.1',
    })
    with opener.open(req, timeout=30) as response:
        if response.status != 200 or not official_url(response.url):
            raise ValueError('Unexpected APHIS response')
        if 'html' in response.headers.get('Content-Type', '').lower():
            raise ValueError('APHIS returned HTML instead of CSV')
        length = response.headers.get('Content-Length')
        if length and int(length) > MAX_BYTES:
            raise ValueError('APHIS download exceeds the size limit')
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('APHIS download exceeds the size limit')
        if length and len(data) != int(length):
            raise ValueError('Incomplete APHIS download')
        return data, {'response_url': response.url,
                      'http_last_modified': response.headers.get('Last-Modified'),
                      'http_etag': response.headers.get('ETag')}


def validate(data, provenance=None):
    from build_surveillance_explorer import build_outbreak_context
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Empty or oversized APHIS CSV')
    if provenance is not None and provenance.get('sha256') != digest(data):
        raise ValueError('APHIS CSV and provenance hashes differ')
    # Use the production parser, including headers, row shape and date handling.
    with tempfile.TemporaryDirectory(prefix='wings-aphis-validate-') as temporary:
        path = Path(temporary) / 'aphis.csv'
        path.write_bytes(data)
        try:
            parsed = build_outbreak_context(path)
        except csv.Error as exc:
            raise ValueError('Malformed APHIS CSV') from exc
    if not parsed['record_count']:
        raise ValueError('APHIS CSV contains no detection records')
    if not any(value['max'] for value in parsed['date_ranges'].values()):
        raise ValueError('APHIS CSV has no usable collection or detection dates')
    return parsed


def read_file(path):
    with Path(path).open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('APHIS file exceeds the size limit')
    return data


def local_snapshot(path):
    data = read_file(path)
    sidecar = Path(path).with_suffix('.provenance.json')
    provenance = json.loads(read_file(sidecar)) if sidecar.is_file() else None
    if provenance is not None and not isinstance(provenance, dict):
        raise ValueError('Invalid APHIS provenance')
    parsed = validate(data, provenance)
    return data, dict(provenance or {}), parsed


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_cache(cache, data, provenance):
    cache.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    stage = Path(tempfile.mkdtemp(dir=cache, prefix='.preparing-'))
    try:
        (stage / 'aphis.csv').write_bytes(data)
        atomic_json(stage / 'aphis.provenance.json', provenance)
        proof = digest((stage / 'aphis.provenance.json').read_bytes())
        stage.rename(cache / token)
        atomic_json(cache / 'latest.json', {'snapshot_id': token, 'provenance_sha256': proof})
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def read_cache(cache):
    pointer = json.loads(read_file(cache / 'latest.json'))
    token = pointer.get('snapshot_id', '')
    if not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{32}', token):
        raise ValueError('Invalid APHIS cache pointer')
    folder = cache / token
    for path in (folder, folder / 'aphis.csv', folder / 'aphis.provenance.json'):
        if path.is_symlink():
            raise ValueError('Invalid symlink in APHIS cache')
    proof = read_file(folder / 'aphis.provenance.json')
    if digest(proof) != pointer.get('provenance_sha256'):
        raise ValueError('APHIS cache provenance changed')
    data, provenance, parsed = local_snapshot(folder / 'aphis.csv')
    if provenance.get('download_url') != CSV_URL or not provenance.get('retrieved_at'):
        raise ValueError('APHIS cache has no verified download provenance')
    return data, provenance, parsed


def failure_reason(exc):
    if isinstance(exc, error.HTTPError):
        return 'http_' + str(exc.code)
    if isinstance(exc, (TimeoutError, error.URLError)):
        return 'network_error'
    return 'invalid_or_unreadable_source'


def prepare(output, cache, *, network, override=None, bundled=None):
    """Return acquisition metadata; output must be a new per-run staging folder."""
    output, cache = Path(output), Path(cache)
    attempted_at = now() if network and not override else None
    refresh_status = 'override' if override else 'offline'
    issues = []
    chosen = None
    if override:
        # Explicit user choices never silently fall back to a different source.
        chosen = local_snapshot(Path(override).expanduser())
        mode = 'user'
    elif network:
        try:
            data, headers = fetch_csv()
            parsed = validate(data)
            retrieved = now()
            provenance = {
                'schema': SCHEMA, 'source_url': SOURCE_PAGE, 'download_url': CSV_URL,
                **headers, 'sha256': digest(data), 'retrieved_at': retrieved,
                'snapshot_supplied_date': retrieved[:10],
                'snapshot_date_basis': 'WINGS retrieval date; not an APHIS release date',
                'record_count': parsed['record_count'], 'date_ranges': parsed['date_ranges'],
            }
            chosen = data, provenance, parsed
            mode, refresh_status = 'download', 'downloaded'
        except (OSError, ValueError, http.client.HTTPException) as exc:
            refresh_status = 'failed'
            issues.append({'step': 'download', 'reason': failure_reason(exc)})
        if chosen is not None:
            try:
                save_cache(cache, data, provenance)
            except (OSError, ValueError):
                # Successful evidence acquisition remains usable if cache is unwritable.
                issues.append({'step': 'cache_write', 'reason': 'not_saved'})
    if chosen is None:
        try:
            chosen = read_cache(cache)
            mode = 'cache'
        except (OSError, ValueError, TypeError, AttributeError):
            issues.append({'step': 'cache_read', 'reason': 'no_valid_cache'})
    if chosen is None and bundled is not None:
        try:
            chosen = local_snapshot(Path(bundled))
            mode = 'bundled'
        except (OSError, ValueError):
            issues.append({'step': 'bundled', 'reason': 'no_valid_snapshot'})
    if chosen is None:
        return {'status': 'UNAVAILABLE', 'source_mode': None,
                'refresh_status': refresh_status, 'refresh_attempted_at': attempted_at,
                'reason': 'APHIS could not be retrieved and no valid saved snapshot is available.',
                'issues': issues}
    data, provenance, parsed = chosen
    acquisition = {'source_mode': mode, 'refresh_status': refresh_status,
                   'refresh_attempted_at': attempted_at, 'prepared_at': now(), 'issues': issues}
    provenance.update({'sha256': digest(data), 'size_bytes': len(data),
                       'record_count': parsed['record_count'], 'date_ranges': parsed['date_ranges'],
                       'acquisition': acquisition})
    provenance.setdefault('source_url', SOURCE_PAGE)
    # Unknown local import dates stay unknown. A failed refresh never advances them.
    output.mkdir(parents=True, exist_ok=True)
    (output / 'aphis.csv').write_bytes(data)
    atomic_json(output / 'aphis.provenance.json', provenance)
    return {'status': 'READY', **acquisition, 'record_count': parsed['record_count'],
            'snapshot_date': provenance.get('snapshot_supplied_date'),
            'retrieved_at': provenance.get('retrieved_at'),
            'date_ranges': parsed['date_ranges'],
            'reason': 'Validated APHIS snapshot saved for this run.'}
