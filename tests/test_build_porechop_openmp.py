import hashlib
import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import build_porechop_openmp as builder


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='wings-openmp-build-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.prefix = self.root / 'existing environment'
        (self.prefix / 'include').mkdir(parents=True)
        (self.prefix / 'lib').mkdir()
        (self.prefix / 'include/omp.h').write_text('fixture header')
        (self.prefix / 'lib/libomp.dylib').write_bytes(b'fixture library')
        self.source = self.root / 'source'
        self.source.mkdir()
        for name, content in [('porechop_abi/porechop_abi.py', 'fixture source'),
                               ('porechop_abi/ab_initio_src/approx_counter.cpp', 'int main() {}'),
                               ('porechop_abi/include/seqan/seq_io.h', 'fixture header'),
                               ('LICENSE', 'fixture license')]:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)

    def archive(self, unsafe=False):
        archive = self.root / 'source.tar.gz'
        with tarfile.open(archive, 'w:gz') as handle:
            if unsafe:
                info = tarfile.TarInfo('../escape.txt')
                info.size = 4
                handle.addfile(info, io.BytesIO(b'evil'))
            else:
                handle.add(self.source, arcname='Porechop_ABI-pinned')
        return archive, builder.file_hash(archive)

    def test_source_checksum_is_checked_before_extraction(self):
        archive, _ = self.archive()
        target = self.root / 'extract'
        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            builder.unpack_source(archive, target, '0' * 64)
        self.assertFalse(target.exists())

    def test_verified_source_archive_has_expected_layout(self):
        archive, digest = self.archive()
        target = builder.unpack_source(archive, self.root / 'extract', digest)
        self.assertTrue((target / 'porechop_abi/include/seqan/seq_io.h').is_file())

    def test_tar_path_traversal_is_rejected(self):
        archive, digest = self.archive(unsafe=True)
        with self.assertRaises(tarfile.FilterError):
            builder.unpack_source(archive, self.root / 'extract', digest)
        self.assertFalse((self.root / 'escape.txt').exists())

    def test_optimized_builds_only_differ_in_openmp_flags_and_output(self):
        source = self.source / 'porechop_abi/ab_initio_src/approx_counter.cpp'
        plain = builder.compile_command('clang++', source, self.source, self.prefix,
                                         self.root / 'serial', False)
        omp = builder.compile_command('clang++', source, self.source, self.prefix,
                                       self.root / 'parallel', True)
        stripped = [value for value in omp[:-1] if value not in ('-Xpreprocessor', '-fopenmp', '-lomp')]
        self.assertEqual(plain[:-1], stripped)
        self.assertIn('-O2', plain)
        self.assertNotIn('-ffast-math', omp)

    def test_build_creates_manifest_and_preserves_installed_counter(self):
        installed = self.prefix / 'installed_counter'
        installed.write_bytes(b'original counter')
        info = {'tool_source_sha256': builder.file_hash(self.source / 'porechop_abi/porechop_abi.py'),
                'counter': str(installed), 'counter_sha256': builder.file_hash(installed)}
        output = self.root / 'isolated build'
        output.mkdir()
        def compile_fixture(command, log, timeout):
            binary = Path(command[command.index('-o') + 1])
            if binary.name == 'openmp_probe':
                binary.write_text('#!/usr/bin/env python3\nprint(\'{"threads":4,"openmp_version":201511}\')\n')
            else:
                binary.write_text('#!/bin/sh\nexit 0\n# ' + binary.name + '\n')
            binary.chmod(0o755)
            log.write_text(repr(command))
        def output_fixture(command, **kwargs):
            if command[0] == 'otool':
                return '@rpath/libomp.dylib\n' if 'openmp_build' in command[-1] else 'libSystem.B.dylib\n'
            return 'Apple clang fixture\n'
        with patch.object(builder, 'compile_logged', side_effect=compile_fixture), \
             patch.object(builder.subprocess, 'check_output', side_effect=output_fixture):
            manifest = builder.build(self.prefix, output, self.source, 'clang++', 10, info)
        self.assertEqual(installed.read_bytes(), b'original counter')
        self.assertEqual(set(manifest['binaries']), {'serial_build', 'openmp_build'})
        self.assertTrue((output / 'build_manifest.json').is_file())
        self.assertTrue((output / 'UPSTREAM-LICENSE.txt').is_file())

    def test_mismatched_installed_source_prevents_compilation(self):
        output = self.root / 'blocked'
        output.mkdir()
        with self.assertRaisesRegex(ValueError, 'does not match'):
            builder.build(self.prefix, output, self.source, 'clang++', 10, {'tool_source_sha256': '0' * 64})
        self.assertFalse((output / 'bin').exists())

    @unittest.skipUnless(sys.platform.startswith('linux') and shutil.which('g++'), 'Linux GCC OpenMP probe')
    def test_actual_openmp_probe_compiles_and_forms_team_on_linux(self):
        source = self.root / 'probe.cpp'
        source.write_text(builder.SMOKE_SOURCE)
        binary = self.root / 'probe'
        result = subprocess.run(['g++', '-std=c++17', '-fopenmp', str(source), '-o', str(binary)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(subprocess.check_output([str(binary)], text=True))
        self.assertEqual(value['threads'], 4)
        self.assertGreater(value['openmp_version'], 0)


if __name__ == '__main__':
    unittest.main()
