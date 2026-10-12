"""Exercise production wrapper and config promotion with a synthetic tool."""
import importlib.util
import ast
from concurrent.futures import ThreadPoolExecutor
import json
import os
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import run_porechop_accelerated as acceleration
import configure_porechop_acceleration as configuration

TOOL = '''
import os, sys, json, shutil
from pathlib import Path
from types import SimpleNamespace
from . import abinitio
def record(label, threads, output):
    with (Path(output).parent/'stage_threads.jsonl').open('a') as h:
        h.write(json.dumps({'stage': label, 'threads': threads})+'\\n')
def find_matching_adapter_sets(check_reads, verbosity, end_size, scoring_scheme_vals, print_dest, adapter_threshold, threads):
    record('search', threads, check_reads.output)
    assert adapter_threshold == 90 and end_size == 150
    return []
def find_adapters_at_read_ends(reads, threads): record('ends', threads, reads.output)
def find_adapters_in_read_middles(reads, threads): record('middle', threads, reads.output)
def main():
    args=SimpleNamespace(input=sys.argv[sys.argv.index('-i')+1], output=sys.argv[sys.argv.index('-o')+1], threads=int(sys.argv[sys.argv.index('--threads')+1]), temp_dir=sys.argv[sys.argv.index('-tmp')+1])
    assert '-abi' in sys.argv
    abinitio.execApproxCounter(args, str(Path(args.temp_dir)/'fixture-count'), 'fixture.config', 3, 1)
    find_matching_adapter_sets(args, 1, 150, 'unchanged scoring', sys.stderr, 90, args.threads)
    find_adapters_at_read_ends(args, args.threads)
    find_adapters_in_read_middles(args, args.threads)
    if os.environ.get('FIXTURE_FAIL'): raise ValueError('fixture execution failure')
    if os.environ.get('FIXTURE_EXIT_ZERO'): raise SystemExit(0)
    if not os.environ.get('FIXTURE_NO_OUTPUT'):
        shutil.copyfile(args.input, args.output)
'''
ABI = '''
def execApproxCounter(*args, **kwargs):
    raise RuntimeError('installed fixture counter should have been replaced')
'''
COUNTER = '''#!/usr/bin/env python3
import json,sys,os,time
from pathlib import Path
args=sys.argv[1:]
output=Path(args[args.index('-o')+1])
if os.environ.get('FIXTURE_COLLISION_CHECK'):
    with output.open('x') as h: h.write('fixture count')
    time.sleep(0.3)
else:
    output.write_text('fixture count')
(output.parent.parent/'fixture-count.argv.json').write_text(json.dumps(args))
'''


class AccelerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = tempfile.TemporaryDirectory(prefix="wings-acceleration-tests-")
        cls.root = Path(cls.storage.name)
        cls.env = cls.root / 'fixture env'
        venv.EnvBuilder(with_pip=False).create(cls.env)
        cls.python = cls.env / 'bin/python'
        purelib = subprocess.check_output([str(cls.python), '-c',
                    "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip()
        cls.package = Path(purelib) / 'porechop_abi'
        cls.package.mkdir()
        (cls.package/'__init__.py').write_text('')
        (cls.package/'version.py').write_text("__version__='0.5.1'\n")
        (cls.package/'porechop_abi.py').write_text(TOOL)
        (cls.package/'abinitio.py').write_text(ABI)

    @classmethod
    def tearDownClass(cls):
        cls.storage.cleanup()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=self.root))
        self.repo = self.folder / 'repo with spaces'
        (self.repo/'scripts').mkdir(parents=True)
        for name in ('run_porechop_accelerated.py', 'configure_porechop_acceleration.py'):
            shutil.copy2(SCRIPTS/name, self.repo/'scripts'/name)
        self.config = self.repo/'config.yaml'
        self.config.write_text('porechop_mem_mb: 12000\nother_setting: keep\n')
        self.input = self.folder/'reads with spaces.fastq'
        self.input.write_text('@fixture\nACGT\n+\nIIII\n')
        self.output = self.folder/'output with spaces'/'trimmed.fastq'
        self.build = self.folder/'build'
        (self.build/'bin').mkdir(parents=True)
        self.library = self.env/'lib/fixture-libomp'
        self.library.write_text('fixture library')
        binaries = {}
        for name in ('serial_build', 'openmp_build'):
            binary = self.build/'bin'/('approx_counter_'+name)
            binary.write_text(COUNTER)
            binary.chmod(0o755)
            binaries[name] = {'path': str(binary), 'sha256': acceleration.file_hash(binary)}
        (self.build/'UPSTREAM-LICENSE.txt').write_text('fixture license')
        self.manifest = {'schema_version': 'wings.porechop_openmp_build.v1',
            'installed_python': str(self.python), 'source_commit': acceleration.SOURCE_COMMIT,
            'source_archive_sha256': acceleration.ARCHIVE_SHA256,
            'installed_tool_source_sha256': acceleration.file_hash(self.package/'porechop_abi.py'),
            'binaries': binaries, 'openmp_library': str(self.library),
            'openmp_library_sha256': acceleration.file_hash(self.library),
            'openmp_probe': {'threads': 4, 'openmp_version': 201811}}
        self.manifest_path = self.build/'build_manifest.json'
        self.write_manifest()

    def write_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest))

    def execute(self, threads=4, search=1, destination=None, **extra):
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        env.update(extra)
        return subprocess.run([str(self.python), str(SCRIPTS/'run_porechop_accelerated.py'),
            '--counter-build', str(self.manifest_path), '--threads', str(threads),
            '--adapter-search-threads', str(search), '--input', str(self.input),
            '--output', str(destination or self.output)], env=env, capture_output=True, text=True, timeout=15)

    def test_cli_preserves_output_and_thresholds_and_records_allocated_threads(self):
        original = acceleration.file_hash(self.package/'porechop_abi.py')
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertEqual(self.output.read_bytes(), self.input.read_bytes())
        calls = [json.loads(s) for s in (self.output.parent/'stage_threads.jsonl').read_text().splitlines()]
        self.assertEqual([r['threads'] for r in calls], [1, min(4, os.cpu_count()), min(4, os.cpu_count())])
        native = json.loads((self.output.parent/'fixture-count.argv.json').read_text())
        self.assertEqual(native[native.index('-nt')+1], str(min(4, os.cpu_count())))
        self.assertEqual(native[native.index('-mr')+1], '3')
        self.assertEqual(Path(native[0]).resolve(), self.input.resolve())
        provenance = json.loads(self.output.with_name(self.output.name+'.porechop-provenance.json').read_text())
        self.assertEqual(provenance['status'], 'complete')
        self.assertEqual(provenance['phase_threads']['adapter_search'], 1)
        self.assertEqual(provenance['output_bytes'], self.input.stat().st_size)
        temporary = Path(provenance['temporary_directory'])
        self.assertEqual(temporary.parent, self.output.parent.resolve())
        self.assertFalse(temporary.exists())
        self.assertFalse(provenance['temporary_directory_retained'])
        self.assertEqual(provenance['argv'][provenance['argv'].index('-tmp')+1], str(temporary))
        self.assertEqual(acceleration.file_hash(self.package/'porechop_abi.py'), original)

    def test_one_core_caps_all_stages_even_when_search_requested_four(self):
        result = self.execute(threads=1, search=4)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        calls = [json.loads(s) for s in (self.output.parent/'stage_threads.jsonl').read_text().splitlines()]
        self.assertEqual([r['threads'] for r in calls], [1, 1, 1])
        native = json.loads((self.output.parent/'fixture-count.argv.json').read_text())
        self.assertEqual(native[native.index('-nt')+1], '1')

    def test_symlinked_input_directory_uses_same_file_and_preserves_output(self):
        alias = self.folder / 'input directory alias'
        alias.symlink_to(self.folder, target_is_directory=True)
        self.input = alias / self.input.name
        result = self.execute()
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        native = json.loads((self.output.parent/'fixture-count.argv.json').read_text())
        self.assertEqual(Path(native[0]).resolve(), self.input.resolve())
        self.assertEqual(self.output.read_bytes(), self.input.read_bytes())

    def test_invalid_binary_fails_before_processing(self):
        Path(self.manifest['binaries']['openmp_build']['path']).write_text(COUNTER+'# changed\n')
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('hash differs', result.stderr)
        self.assertFalse(self.output.parent.exists())

    def test_wrong_environment_and_source_build_are_rejected(self):
        self.manifest['installed_python'] = '/another/env/bin/python'
        self.write_manifest()
        result = self.execute()
        self.assertIn('another conda environment', result.stderr)
        self.manifest['installed_python'] = str(self.python)
        self.manifest['source_commit'] = 'wrong source'
        self.write_manifest()
        result = self.execute()
        self.assertIn('validated Porechop_ABI source', result.stderr)
        self.assertFalse(self.output.parent.exists())

    def test_changed_library_and_tool_source_are_rejected(self):
        self.library.write_text('changed runtime')
        result = self.execute()
        self.assertIn('runtime is missing or changed', result.stderr)
        self.library.write_text('fixture library')
        self.manifest['installed_tool_source_sha256'] = 'wrong hash'
        self.write_manifest()
        result = self.execute()
        self.assertIn('source differs', result.stderr)

    def test_failed_execution_and_zero_exit_without_output_keep_failed_provenance(self):
        for extra, message in (({'FIXTURE_FAIL': '1'}, 'fixture execution failure'),
                               ({'FIXTURE_EXIT_ZERO': '1'}, 'without creating its output')):
            result = self.execute(**extra)
            self.assertNotEqual(result.returncode, 0)
            provenance = json.loads(self.output.with_name(self.output.name+'.porechop-provenance.json').read_text())
            self.assertEqual(provenance['status'], 'failed')
            self.assertIn(message, provenance['error'])
            self.assertTrue(provenance['temporary_directory_retained'])
            self.assertTrue(Path(provenance['temporary_directory']).is_dir())

    def test_overlapping_jobs_have_distinct_counter_intermediates(self):
        outputs = [self.output.parent/'first.fastq', self.output.parent/'second.fastq']
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.execute, threads=1, destination=output,
                                   FIXTURE_COLLISION_CHECK='1') for output in outputs]
            results = [future.result() for future in futures]
        for result in results:
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        records = [json.loads(output.with_name(output.name+'.porechop-provenance.json').read_text())
                   for output in outputs]
        self.assertNotEqual(records[0]['temporary_directory'], records[1]['temporary_directory'])
        for output, record in zip(outputs, records):
            self.assertEqual(output.read_bytes(), self.input.read_bytes())
            self.assertFalse(Path(record['temporary_directory']).exists())

    def test_existing_output_is_not_overwritten(self):
        self.output.parent.mkdir()
        self.output.write_text('keep')
        result = self.execute()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_text(), 'keep')

    def make_benchmark(self):
        rows = []
        for repeat in (1, 2):
            for name, search in (('uniform', 4), ('phase_split', 1)):
                rows.append({'repeat': repeat, 'allocation': name, 'status': 'complete',
                    'output_sha256': 'matching bytes', 'discovery_file_hashes': {'counter': 'same'},
                    'backend': 'openmp_build',
                    'counter_sha256': self.manifest['binaries']['openmp_build']['sha256'],
                    'tool_source_sha256': self.manifest['installed_tool_source_sha256'],
                    'phase_threads': {'discovery': 4, 'adapter_search': search, 'trimming': 4}})
        value = {'schema_version': 'wings.porechop_benchmark.v1', 'subset': {'reads': 20000},
                 'counter_build': self.manifest, 'trials': rows, 'planned_trials': 4,
                 'output_comparison': {'all_pairs_match': True, 'pairs': [{'repeat': 1}, {'repeat': 2}]}}
        path = self.folder/'pilot-summary.json'
        path.write_text(json.dumps(value))
        return path

    def test_promotes_build_and_updates_only_local_settings_with_backup(self):
        pilot = self.make_benchmark()
        before = self.config.read_bytes()
        manifest, backup = configuration.configure(self.repo, pilot, self.folder/'cache')
        config = yaml.safe_load(self.config.read_text())
        self.assertEqual((config['porechop_threads'], config['porechop_adapter_search_threads']), (4, 1))
        self.assertEqual(config['porechop_mem_mb'], 12000)
        self.assertEqual(config['other_setting'], 'keep')
        self.assertEqual(backup.read_bytes(), before)
        self.assertEqual(config['porechop_counter_build'], str(manifest))
        promoted = json.loads(manifest.read_text())
        for record in promoted['binaries'].values():
            self.assertTrue(Path(record['path']).is_file())
            self.assertEqual(acceleration.file_hash(Path(record['path'])), record['sha256'])
        self.assertTrue((manifest.parent/'UPSTREAM-LICENSE.txt').is_file())
        # Removing the benchmark build cannot remove the promoted counter.
        shutil.rmtree(self.build)
        result = subprocess.run([str(self.python), str(SCRIPTS/'run_porechop_accelerated.py'),
            '--counter-build', str(manifest), '--validate-only'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)

    def test_rejected_benchmark_never_changes_config(self):
        pilot = self.make_benchmark()
        data = json.loads(pilot.read_text())
        data['trials'][-1]['output_sha256'] = 'different'
        pilot.write_text(json.dumps(data))
        before = self.config.read_bytes()
        with self.assertRaisesRegex(ValueError, 'outputs differ'):
            configuration.configure(self.repo, pilot, self.folder/'cache')
        self.assertEqual(self.config.read_bytes(), before)
        self.assertFalse((self.folder/'cache').exists())

    def test_corrupt_counter_does_not_enable_config_and_removes_staging_cache(self):
        pilot = self.make_benchmark()
        Path(self.manifest['binaries']['serial_build']['path']).write_text('corrupt')
        before = self.config.read_bytes()
        with self.assertRaisesRegex(ValueError, 'recorded build hash'):
            configuration.configure(self.repo, pilot, self.folder/'cache')
        self.assertEqual(self.config.read_bytes(), before)
        self.assertEqual(list((self.folder/'cache').iterdir()), [])

    def test_web_config_inherits_only_porechop_settings(self):
        spec = importlib.util.spec_from_file_location('fixture_wings_runner', SCRIPTS/'wings_local_runner.py')
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        (self.repo/'config').mkdir()
        (self.repo/'config/config.example.yaml').write_text('other_setting: example\n')
        self.config.write_text('porechop_threads: 4\nporechop_adapter_search_threads: 1\nporechop_counter_build: /cache/build.json\nother_setting: local\n')
        run = self.folder/'run'
        (run/'inputs/reads').mkdir(parents=True)
        (run/'inputs/reads/fixture.fastq.gz').write_text('fixture')
        (run/'inputs/metadata.tsv').write_text('sample_id\nfixture\n')
        with patch.object(runner, 'REPO_ROOT', self.repo), patch.object(runner, 'run_dir', return_value=run), patch.object(runner, 'read_state', return_value={'cores': 1, 'max_parallel_jobs': 1}):
            path, count = runner.build_config('fixture')
        config = yaml.safe_load(path.read_text())
        self.assertEqual(config['porechop_threads'], 4)
        self.assertEqual(config['porechop_adapter_search_threads'], 1)
        self.assertEqual(config['porechop_counter_build'], '/cache/build.json')
        self.assertEqual(config['other_setting'], 'example')
        self.assertEqual(count, 1)
        command = runner.workflow_command('snakemake', path, {'cores': 4, 'max_parallel_jobs': 1})
        self.assertEqual(command[command.index('--cores')+1], '4')
        self.assertEqual(command[command.index('--resources')+1], 'wings_task_slots=1')

    def run_rule_shell(self, enabled, threads):
        # Execute the exact rule's shell body; real Snakemake DAG validation is separate.
        source = (ROOT/'Snakefile').read_text()
        rule = source.split('rule porechop:', 1)[1].split('rule fastplong:', 1)[0]
        shell_literal = rule.split('    shell:\n', 1)[1].strip().split('\n\n\n#', 1)[0]
        shell = ast.literal_eval(shell_literal)
        # The execution sandbox cannot expose /dev/fd for Bash process substitution.
        # Replace only log mirroring in this harness; execute both actual command branches.
        shell = shell.replace('exec > >(tee -a {log:q}) 2>&1', 'exec >> {log:q} 2>&1')
        class Value:
            def __init__(self, value): self.value = value
            def __format__(self, spec):
                if spec == 'q':
                    values = self.value if isinstance(self.value, list) else [self.value]
                    return ' '.join(shlex.quote(str(value)) for value in values)
                return str(self.value)
        params = SimpleNamespace(accelerated=int(enabled), adapter_search_threads=1)
        input_values = SimpleNamespace(fastq=Value(self.input),
            runner=Value(SCRIPTS/'run_porechop_accelerated.py'),
            counter_build=Value([self.manifest_path] if enabled else []))
        shell = shell.format(input=input_values, output=SimpleNamespace(trimmed=Value(self.output)),
                             log=Value(self.output.parent/'porechop.log'), params=params,
                             threads=threads, PORECHOP_CMD='porechop_abi')
        stub_dir = self.folder/'stub-bin'
        stub_dir.mkdir()
        stub = stub_dir/'porechop_abi'
        stub.write_text('#!/usr/bin/env python3\nimport json,sys,shutil\nfrom pathlib import Path\n'
                        "args=sys.argv[1:]; output=Path(args[args.index('-o')+1]); "
                        "output.with_suffix('.installed-argv.json').write_text(json.dumps(args)); "
                        "shutil.copyfile(args[args.index('-i')+1],output)\n")
        stub.chmod(0o755)
        env = os.environ.copy()
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        env['PATH'] = str(self.python.parent)+os.pathsep+str(stub_dir)+os.pathsep+env.get('PATH','')
        result = subprocess.run(['bash', '-c', shell], env=env, capture_output=True, text=True, timeout=15)
        log = self.output.parent/'porechop.log'
        if log.is_file():
            result.stderr += log.read_text()
        return result

    def test_disabled_rule_shell_preserves_installed_command_and_quoted_paths(self):
        result = self.run_rule_shell(False, 1)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        arguments = json.loads(self.output.with_suffix('.installed-argv.json').read_text())
        self.assertEqual(arguments, ['-abi', '--threads', '1', '-i', str(self.input), '-o', str(self.output)])
        self.assertEqual(self.output.read_bytes(), self.input.read_bytes())

    def test_enabled_rule_shell_passes_allocated_threads_to_wrapper(self):
        result = self.run_rule_shell(True, 4)
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        self.assertFalse(self.output.with_suffix('.installed-argv.json').exists())
        self.assertEqual(self.output.read_bytes(), self.input.read_bytes())
        calls = [json.loads(s) for s in (self.output.parent/'stage_threads.jsonl').read_text().splitlines()]
        self.assertEqual([r['threads'] for r in calls], [1, min(4, os.cpu_count()), min(4, os.cpu_count())])


if __name__ == '__main__':
    unittest.main()
