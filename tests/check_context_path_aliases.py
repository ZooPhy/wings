#!/usr/bin/env python3
"""Reproduce macOS /var -> /private/var semantics using a temporary symlink.

The runner normally receives canonical storage roots. The old test fixture
bypassed that initialization by assigning an unresolved TemporaryDirectory path.
This check reproduces that failure, verifies the canonical setup, and runs all
context/provenance/genotype/eBird regression suites through the aliased path.
No repository configuration, data, or results are modified.
"""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))


def main():
    with tempfile.TemporaryDirectory(prefix='wings-path-alias-regression-') as temporary:
        root=Path(temporary).resolve()
        real=root/'canonical';real.mkdir()
        alias=root/'alias';alias.symlink_to(real,target_is_directory=True)
        spec=importlib.util.spec_from_file_location('context_alias_runner',ROOT/'scripts/wings_local_runner.py')
        runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
        old_root=alias/'negative-control';old_root.mkdir()
        runner.RUNS_ROOT=old_root
        try:
            runner.run_dir('sample')
        except ValueError as error:
            if 'subpath' not in str(error):raise
        else:
            raise AssertionError('Unresolved negative-control fixture did not reproduce the path-containment error')
        runner.RUNS_ROOT=old_root.resolve()
        assert runner.run_dir('sample')==real/'negative-control'/'sample'
        print('PASS: old unresolved fixture reproduces the error; canonical fixture succeeds.',flush=True)
        previous_tempdir=tempfile.tempdir
        previous_tmpdir=os.environ.get('TMPDIR')
        try:
            tempfile.tempdir=str(alias)
            os.environ['TMPDIR']=str(alias)
            with tempfile.TemporaryDirectory() as probe:
                assert Path(probe)!=Path(probe).resolve(), 'Temporary-path alias was not exercised'
            loader=unittest.TestLoader()
            suite=unittest.TestSuite()
            for pattern in ('test_context*.py','test_genotype*.py','test_provenance_accuracy.py','test_ebird_context_package.py'):
                suite.addTests(loader.discover(str(ROOT/'tests'),pattern=pattern))
            result=unittest.TextTestRunner(verbosity=1).run(suite)
            if not result.wasSuccessful():raise SystemExit(1)
            print(f'PASS: {result.testsRun} checks with aliased temporary directories.',flush=True)
        finally:
            tempfile.tempdir=previous_tempdir
            if previous_tmpdir is None:os.environ.pop('TMPDIR',None)
            else:os.environ['TMPDIR']=previous_tmpdir


if __name__=='__main__':main()
