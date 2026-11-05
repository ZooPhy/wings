#!/usr/bin/env python3
"""Prepare, migrate, inspect, and validate portable WINGS eBird context packages.

No downloads are performed. Preparation requires matching local EBD/SED data.
Original records stay in the user's external package, not in report bundles.
"""
import argparse
import calendar
import csv
from datetime import date, datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import runpy
import shutil
import subprocess
import sys
import tempfile

SCHEMA = 'wings.ebird-context.v1'
VERSION = '1.0.0'
MANIFEST = 'context_manifest.json'
CACHE_FILES = ('observations.txt.gz', 'sampling.txt', 'species_catalog.tsv',
               'cache_manifest.json', 'sampling_manifest.json')
DOCUMENTS = ('terms_of_use.txt', 'recommended_citation.txt')
FILES = CACHE_FILES + DOCUMENTS


class ContextError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def package_id(manifest):
    return hashlib.sha256(canonical({k: v for k, v in manifest.items() if k != 'package_id'})).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')


def regular(root, name):
    path = root / name
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise ContextError('INCOMPLETE', 'Missing, empty, or symlinked package file: ' + name)
    return path


def filter_api():
    return runpy.run_path(str(Path(__file__).with_name('filter_ebird_for_wings.py')))


def validate_scope(scopes):
    if not isinstance(scopes, list) or not scopes:
        raise ContextError('INVALID_SCOPE', 'No geographic/date coverage recorded')
    for scope in scopes:
        if not isinstance(scope, dict) or not all(isinstance(scope.get(k), str) for k in ('country','state','start','end')):
            raise ContextError('INVALID_SCOPE', 'Malformed geographic/date coverage')
        if not scope['country'] or date.fromisoformat(scope['start']) > date.fromisoformat(scope['end']):
            raise ContextError('INVALID_SCOPE', 'Invalid country or coverage dates')


def legacy_inventory(cache, documents=None):
    cache = Path(cache).resolve()
    docs = Path(documents).resolve() if documents else cache
    missing = [str((docs if name in DOCUMENTS else cache) / name)
               for name in FILES
               if not ((docs if name in DOCUMENTS else cache) / name).is_file()
               or ((docs if name in DOCUMENTS else cache) / name).stat().st_size == 0]
    return {'cache_dir': str(cache), 'missing': missing,
            'note': 'Migration copies files into a new package; release, acquisition date, taxonomy, and all-species source coverage must be supplied or explicitly recorded as unknown where allowed.'}


def read_cache_contract(root):
    obs = json.loads(regular(root, 'cache_manifest.json').read_text())
    sed = json.loads(regular(root, 'sampling_manifest.json').read_text())
    for name in ('metadata_sha256', 'days'):
        if name not in obs or obs[name] != sed.get(name):
            raise ContextError('MISMATCH', 'Observation and sampling cache ' + name + ' differ')
    if not isinstance(obs['days'], int) or not 0 <= obs['days'] <= 365:
        raise ContextError('INVALID_SCOPE', 'Invalid cache date-window size')
    validate_scope(obs.get('coverage_scopes'))
    for item, field in ((obs, 'observation_rows'), (obs, 'species'), (sed, 'sampling_rows')):
        if not isinstance(item.get(field), int) or item[field] < 0:
            raise ContextError('INVALID_COUNTS', 'Missing/invalid cache count: ' + field)
    return obs, sed


def verify(root, metadata=None, days=30, expected_release=None):
    root = Path(root).expanduser().resolve()
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        missing = legacy_inventory(root)['missing']
        raise ContextError('LEGACY_OR_MISSING', 'No context_manifest.json. Prepare or migrate this directory. Missing components: ' + (', '.join(Path(p).name for p in missing) or 'none; migration metadata is still required'))
    manifest = json.loads(regular(root, MANIFEST).read_text())
    if manifest.get('schema') != SCHEMA:
        raise ContextError('SCHEMA', 'Unsupported eBird context schema')
    if manifest.get('package_id') != package_id(manifest):
        raise ContextError('INTEGRITY', 'Context manifest identity does not match its contents')
    if not re.fullmatch(r'[A-Z][a-z]{2}-\d{4}', str(manifest.get('release', ''))):
        raise ContextError('RELEASE', 'Package release must be Mon-YYYY')
    if expected_release and expected_release != manifest['release']:
        raise ContextError('RELEASE', 'Configured release differs from package release')
    if manifest.get('taxonomic_scope') != 'all-species-source':
        raise ContextError('TAXONOMIC_SCOPE', 'Reporting frequencies require a declared all-species source')
    if set(manifest.get('files', {})) != set(FILES):
        raise ContextError('INVENTORY', 'Package file inventory is incomplete or unexpected')
    for name in FILES:
        path = regular(root, name)
        record = manifest['files'][name]
        if path.stat().st_size != record.get('size_bytes') or sha256(path) != record.get('sha256'):
            raise ContextError('INTEGRITY', 'Checksum/size mismatch: ' + name)
    for name in DOCUMENTS:
        if not (root / name).read_text(encoding='utf-8-sig').strip():
            raise ContextError('INCOMPLETE', 'Empty attribution document: ' + name)
    obs, sed = read_cache_contract(root)
    if manifest['coverage_scopes'] != obs['coverage_scopes']:
        raise ContextError('INVALID_SCOPE', 'Package and cache geographic/date coverage differ')
    if manifest['counts'] != {'observation_rows': obs['observation_rows'], 'sampling_rows': sed['sampling_rows'], 'species': obs['species']}:
        raise ContextError('INVALID_COUNTS', 'Package and cache counts differ')
    if metadata is not None:
        api = filter_api()
        samples = api['read_samples'](Path(metadata), {}, days, None)
        try:
            api['check_cache_scope'](samples, root / 'observations.txt.gz')
        except ValueError as error:
            raise ContextError('OUT_OF_SCOPE', str(error)) from error
    validate_release_coverage(manifest["release"], manifest["coverage_scopes"])
    return manifest


def boolean(value, name):
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ('true', 'false'):
        return value.lower() == 'true'
    raise ValueError(name + ' must be true or false')


def resolve_context(config, metadata, repo=None):
    """Read-only preflight for explicit reuse/off modes. Legacy config is external."""
    mode = str(config.get('mode', 'reuse')).lower()
    if mode not in ('reuse', 'off'):
        raise ValueError('ebird.mode must be legacy, reuse, or off')
    required = boolean(config.get('required', False), 'ebird.required')
    if mode == 'off':
        if required:
            raise ValueError('ebird.required cannot be true with mode: off')
        return {'schema': 'wings.ebird-status.v1', 'status': 'DISABLED', 'reason': 'eBird context disabled by configuration', 'mode': mode, 'required': False}
    days = int(config.get('days', 30))
    if not 0 <= days <= 365:
        raise ValueError('ebird.days must be between 0 and 365')
    radius = config.get('radius_km')
    if radius is not None and (not math.isfinite(float(radius)) or not 0 < float(radius) <= 1000):
        raise ValueError('ebird.radius_km must be finite, positive, and at most 1000')
    if config.get('build_cache') not in (None, False, 'false'):
        raise ValueError('Prepare packages separately; reuse mode cannot build_cache')
    if not config.get('context_dir'):
        raise ValueError('ebird.context_dir is required in reuse mode')
    root = Path(config['context_dir']).expanduser().resolve()
    if repo is not None and root.is_relative_to(Path(repo).resolve()):
        raise ValueError('Keep eBird context packages outside the WINGS checkout')
    status = {'schema': 'wings.ebird-status.v1', 'mode': mode, 'required': required,
              'context_dir': str(root), 'days': days}
    try:
        manifest = verify(root, metadata, days, config.get('release'))
    except (OSError, ValueError, KeyError, TypeError) as error:
        reason = str(error)
        if required:
            raise ValueError('Required eBird context is unavailable: ' + reason) from error
        status.update(status='UNAVAILABLE', code=getattr(error, 'code', 'INVALID'), reason=reason)
    else:
        status.update(status='READY', reason='Validated portable eBird package', release=manifest['release'],
                      package_id=manifest['package_id'], manifest_sha256=sha256(root / MANIFEST),
                      package_manifest=manifest)
    return status


def validate_rows(root, obs, sed):
    """Migration/build checks cached rows against the recorded counts and schema."""
    api = filter_api()
    checks = [('observations.txt.gz', {'SAMPLING EVENT IDENTIFIER', 'COMMON NAME', 'SCIENTIFIC NAME'}, obs['observation_rows']),
              ('sampling.txt', {'SAMPLING EVENT IDENTIFIER', 'OBSERVATION DATE', 'COUNTRY CODE', 'COUNTRY', 'STATE CODE', 'STATE', 'GROUP IDENTIFIER', 'ALL SPECIES REPORTED'}, sed['sampling_rows']),
              ('species_catalog.tsv', {'common_name', 'scientific_name', 'observation_rows'}, obs['species'])]
    for name, required, expected in checks:
        count = sum(1 for _ in api['tsv_rows'](root / name, required, literal_quotes=True))
        if count != expected:
            raise ContextError('INVALID_COUNTS', f'{name}: recorded {expected} rows but found {count}')


def check_release(release, names):
    if not re.fullmatch(r'[A-Z][a-z]{2}-\d{4}', release):
        raise ValueError('Release must be Mon-YYYY, for example Aug-2026')
    datetime.strptime(release, '%b-%Y')
    for name in names:
        found = re.findall(r'rel([A-Z][a-z]{2}-\d{4})', str(name))
        if any(value != release for value in found):
            raise ValueError('Source filename release conflicts with --release: ' + str(name))


def validate_release_coverage(release, scopes):
    month = datetime.strptime(release, '%b-%Y')
    end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1]).isoformat()
    if any(scope['end'] > end for scope in scopes):
        raise ContextError('OUT_OF_RELEASE', 'Requested coverage extends past the source release month: ' + release)


def seal(root, release, taxonomy, acquired, source_hashes, origin):
    obs, sed = read_cache_contract(root)
    check_release(release, [obs.get('source_observations'), obs.get('source_sampling'), sed.get('source_sampling')])
    for name in DOCUMENTS:
        if not regular(root, name).read_text(encoding='utf-8-sig').strip():
            raise ValueError('Attribution documents must contain text: ' + name)
    validate_rows(root, obs, sed)
    validate_release_coverage(release, obs['coverage_scopes'])
    if acquired != 'unknown':
        date.fromisoformat(acquired)
    if not taxonomy.strip():
        raise ValueError('Specify taxonomy version, or explicitly use unknown')
    manifest = {'schema': SCHEMA, 'release': release, 'taxonomy_version': taxonomy,
                'taxonomic_scope': 'all-species-source', 'scope_evidence': 'user-declared source selection; geographic/date cache coverage recorded by builder',
                'acquired_at': None if acquired == 'unknown' else acquired,
                'prepared_at': datetime.now(timezone.utc).isoformat(), 'preparer_version': VERSION,
                'preparer_sha256': sha256(Path(__file__)),
                'filter_sha256': sha256(Path(__file__).with_name('filter_ebird_for_wings.py')),
                'cache_builder_sha256': sha256(Path(__file__).with_name('build_ebird_cache.py')),
                'origin': origin, 'source_hashes': source_hashes,
                'coverage_scopes': obs['coverage_scopes'], 'preparation_days': obs['days'],
                'counts': {'observation_rows': obs['observation_rows'], 'sampling_rows': sed['sampling_rows'], 'species': obs['species']},
                'files': {name: {'sha256': sha256(regular(root, name)), 'size_bytes': (root / name).stat().st_size} for name in FILES}}
    manifest['package_id'] = package_id(manifest)
    write_json(root / MANIFEST, manifest)
    verify(root)
    return manifest


def prepare(args):
    output = args.output.expanduser().resolve()
    if output.exists():
        raise ValueError('Destination already exists; use a new package directory')
    repo = Path(__file__).resolve().parents[1]
    if output.is_relative_to(repo):
        raise ValueError('Keep packages outside the WINGS checkout')
    docs = args.documents.expanduser().resolve()
    for name in DOCUMENTS:
        regular(docs, name)
    if args.command == 'migrate':
        cache = args.cache.expanduser().resolve()
        missing = legacy_inventory(cache, docs)['missing']
        if missing:
            raise ValueError('Cannot migrate; missing components:\n' + '\n'.join(missing))
    else:
        check_release(args.release, [args.observations, args.sampling])
        if not 0 <= args.days <= 365:
            raise ValueError('--days must be between 0 and 365')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.wings-ebird-prepare-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'package'
        stage.mkdir()
        sources = None
        if args.command == 'migrate':
            for name in CACHE_FILES:
                shutil.copyfile(regular(cache, name), stage / name)
        else:
            original_hashes = {name: sha256(path) for name, path in [('observations', args.observations), ('sampling', args.sampling)]}
            subprocess.run([sys.executable, str(Path(__file__).with_name('build_ebird_cache.py')),
                            '--metadata', str(args.metadata), '--observations', str(args.observations),
                            '--sampling', str(args.sampling), '--cache-dir', str(stage), '--days', str(args.days)], check=True)
            # Original builder writes a combined manifest; add the sampling contract.
            obs = json.loads((stage / 'cache_manifest.json').read_text())
            write_json(stage / 'sampling_manifest.json', {key: obs[key] for key in ('source_sampling', 'metadata_sha256', 'days', 'sampling_rows')})
            sources = {name: {'sha256': value, 'identity': str(getattr(args, name).resolve())} for name, value in original_hashes.items()}
            for name in original_hashes:
                if sha256(getattr(args, name)) != original_hashes[name]:
                    raise ValueError('Source changed during preparation: ' + name)
        for name in DOCUMENTS:
            shutil.copyfile(regular(docs, name), stage / name)
        manifest = seal(stage, args.release, args.taxonomy_version, args.acquired_at, sources, args.command)
        if output.exists():
            raise ValueError('Destination appeared during preparation; preserving it')
        stage.rename(output)
    print('Prepared package:', output)
    print('Package ID:', manifest['package_id'])
    if args.command == 'migrate':
        print('Original source hashes were not reconstructed; cache files are fingerprinted.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    inspect = sub.add_parser('inspect', help='List missing legacy cache components without changing files')
    inspect.add_argument('--cache', type=Path, required=True)
    inspect.add_argument('--documents', type=Path)
    check = sub.add_parser('validate')
    check.add_argument('--context-dir', type=Path, required=True)
    check.add_argument('--metadata', type=Path)
    check.add_argument('--days', type=int, default=30)
    check.add_argument('--release')
    for name in ('build', 'migrate'):
        command = sub.add_parser(name)
        command.add_argument('--output', type=Path, required=True)
        command.add_argument('--documents', type=Path, required=True)
        command.add_argument('--release', required=True)
        command.add_argument('--taxonomy-version', required=True)
        command.add_argument('--acquired-at', required=True, help='YYYY-MM-DD or unknown')
        command.add_argument('--confirm-all-species', action='store_true', required=True, help='Attest that source EBD included all species for the cache geographic/date scope')
        if name == 'migrate':
            command.add_argument('--cache', type=Path, required=True)
        else:
            command.add_argument('--observations', type=Path, required=True)
            command.add_argument('--sampling', type=Path, required=True)
            command.add_argument('--metadata', type=Path, required=True)
            command.add_argument('--days', type=int, default=30)
    args = parser.parse_args()
    if args.command == 'inspect':
        print(json.dumps(legacy_inventory(args.cache, args.documents), indent=2))
    elif args.command == 'validate':
        manifest = verify(args.context_dir, args.metadata, args.days, args.release)
        print('PASS: valid eBird context package', manifest['package_id'])
    else:
        prepare(args)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, csv.Error, EOFError, subprocess.SubprocessError) as error:
        print('ERROR:', error, file=sys.stderr)
        sys.exit(1)
