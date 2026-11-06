#!/usr/bin/env python3
"""Acquire a public snapshot once, or copy an explicitly prepared snapshot exactly."""
import argparse
import json
from pathlib import Path
import tempfile
from refresh_genotype_frequencies import refresh, validate_snapshot, atomic_json


def prepare(seed,output,prepared=False,cache_dir=None,ref='master',max_age_days=7,offline=False):
    seed,output=Path(seed),Path(output)
    if prepared:
        raw=seed.read_bytes();validate_snapshot(json.loads(raw))
        output.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=output.parent,delete=False) as f:
            temporary=Path(f.name);f.write(raw)
        try:temporary.replace(output)
        finally:temporary.unlink(missing_ok=True)
    else:
        atomic_json(output,refresh(seed,Path(cache_dir or '~/.cache/wings/genotype-frequencies'),
                                  ref=ref,max_age_days=max_age_days,offline=offline))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seed',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--prepared',action='store_true');p.add_argument('--offline',action='store_true')
    p.add_argument('--cache-dir',type=Path);p.add_argument('--ref',default='master');p.add_argument('--max-age-days',type=float,default=7)
    args=p.parse_args();prepare(args.seed,args.output,args.prepared,args.cache_dir,args.ref,args.max_age_days,args.offline)


if __name__=='__main__':main()
