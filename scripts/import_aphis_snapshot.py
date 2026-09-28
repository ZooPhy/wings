#!/usr/bin/env python3
"""Validate and copy an APHIS CSV snapshot together with matching provenance."""
import argparse
from datetime import date
import json
import os
from pathlib import Path
import tempfile
from build_surveillance_explorer import build_outbreak_context, APHIS_SOURCE_URL


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, default=Path('resources/aphis/hpai-wild-birds.csv'))
    parser.add_argument('--snapshot-date', type=date.fromisoformat, default=date.today())
    args = parser.parse_args()
    content = args.source.read_bytes()
    context = build_outbreak_context(args.source)
    manifest = {
        'source_url': APHIS_SOURCE_URL,
        'original_filename': args.source.name,
        'sha256': context['sha256'],
        'snapshot_supplied_date': args.snapshot_date.isoformat(),
        'snapshot_date_basis': 'Local import date; not an APHIS release date',
    }
    atomic_write(args.output, content)
    atomic_write(args.output.with_suffix('.provenance.json'), (json.dumps(manifest, indent=2) + '\n').encode())
    print(f"Imported {context['record_count']:,} records; retained {context['repeated_rows_retained']:,} identical repeat rows.")
    print(f"Missing/invalid dates: {context['undated_counts']}")
    print(f"CSV SHA-256: {context['sha256']}")


if __name__ == '__main__':
    main()
