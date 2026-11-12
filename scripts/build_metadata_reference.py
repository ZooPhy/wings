#!/usr/bin/env python3
"""Synchronize the wizard's host lookup with WINGS' existing host dictionary."""
import argparse
import csv
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    target = args.repo / 'assets/wings-metadata-reference.json'
    reference = json.loads(target.read_text(encoding='utf-8'))
    with (args.repo / 'resources/ebird_host_codes_2025.tsv').open(encoding='utf-8') as handle:
        reference['hosts'] = [{'code': row['host'], 'name': row['ebird_species']}
                              for row in csv.DictReader(handle, delimiter='\t')
                              if row['host'].strip() and row['ebird_species'].strip()]
    expected = json.dumps(reference, ensure_ascii=False, separators=(',', ':')) + '\n'
    if args.check:
        if target.read_bytes() != expected.encode('utf-8'):
            parser.exit(1, 'Run python scripts/build_metadata_reference.py to refresh the host dictionary.\n')
    else:
        target.write_text(expected, encoding='utf-8')
    print('PASS: metadata host lookup matches WINGS host codes.')


if __name__ == '__main__':
    main()
