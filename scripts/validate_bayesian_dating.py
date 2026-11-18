#!/usr/bin/env python3
"""Exercise BEAST 2.7.7 and ArviZ on synthetic fixtures before any research chains."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from phylodynamic_bayesian import write, digest, resolve_beast_command

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--command-json',default='["beast"]');a=p.parse_args()
if not importlib.util.find_spec('arviz'):raise SystemExit('ArviZ is missing from the dedicated dating environment.')
repo=Path(__file__).resolve().parents[1]
print('BEAST command:', json.dumps(resolve_beast_command(json.loads(a.command_json))), flush=True)
env=dict(os.environ,WINGS_TEST_BAYESIAN_TOOLS='1',WINGS_BAYESIAN_COMMAND=json.dumps(json.loads(a.command_json)))
subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-p','test_phylodynamics_bayesian.py','-v'],cwd=repo,env=env,check=True)
import arviz
write(a.output,dict(status='passed',beast='2.7.7',arviz=arviz.__version__,fixture='synthetic only',
    code_sha256={str(p.relative_to(repo)):digest(p) for p in [repo/'scripts/WingsBeast.java',repo/'scripts/phylodynamic_bayesian.py',repo/'tests/test_phylodynamics_bayesian.py']}))
print('BEAST XML, short-chain topology/date logging and ArviZ diagnostics passed synthetic integration checks.')
