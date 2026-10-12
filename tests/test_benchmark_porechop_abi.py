"""Verify benchmark behavior with a synthetic tool, not real sequencing data."""
import gzip
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import venv
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/benchmark_porechop_abi.py"
spec = importlib.util.spec_from_file_location("benchmark", SCRIPT)
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)

TOOL = '''
import os, sys, shutil, json
from types import SimpleNamespace
from .abinitio import launch_ab_initio

def get_arguments():
    return SimpleNamespace(threads=int(sys.argv[sys.argv.index('--threads')+1]), input='input.fastq')
def load_reads(*args): return ['fixture'], ['fixture'], 'fastq'
def record(name, threads):
    with open('thread_calls.jsonl', 'a') as handle:
        handle.write(json.dumps({'phase': name, 'threads': threads})+'\\n')
def find_matching_adapter_sets(check_reads, threads):
    record('adapter_search', threads)
    if os.environ.get('FIXTURE_DIFFERENT_SEARCH') and threads == 1:
        os.environ['FIXTURE_DIFFERENT_OUTPUT'] = '1'
    return ['fixture']
def find_adapters_at_read_ends(reads, threads):
    record('end_trimming', threads)
    if os.environ.get('FIXTURE_FAIL_ENDS'): raise ValueError('fixture trimming failure')
def find_adapters_in_read_middles(reads, threads): record('middle_trimming', threads)
def output_reads(*args):
    if not os.environ.get('FIXTURE_NO_OUTPUT'):
        shutil.copyfile('input.fastq', 'trimmed.fastq')
        if os.environ.get('FIXTURE_DIFFERENT_OUTPUT'):
            with open('trimmed.fastq','a') as handle: handle.write('fixture difference\\n')
def main():
    args=get_arguments()
    launch_ab_initio(args)
    reads, checks, kind=load_reads()
    find_matching_adapter_sets(checks, args.threads)
    find_adapters_at_read_ends(reads, args.threads)
    find_adapters_in_read_middles(reads, args.threads)
    output_reads(reads)
if os.environ.get('FIXTURE_UNSUPPORTED'): output_reads = None
'''

ABI = '''
import os, subprocess, sys
from pathlib import Path
def execApproxCounter(*args):
    code="import math; [math.sqrt(i) for i in range(150000)]"
    if os.environ.get('FIXTURE_LONG_COUNT'):
        code="import os,time,pathlib; pathlib.Path(os.environ['FIXTURE_PID_FILE']).write_text(str(os.getpid())); time.sleep(30)"
    subprocess.run([sys.executable, '-c', code], check=True)
    Path('abi_tmp').mkdir(exist_ok=True)
    Path('abi_tmp/count_start_0').write_text('fixture count\\n')
def build_graph(*args): return {}
def generic_build(*args): return []
def launch_ab_initio(args):
    execApproxCounter(args, 'abi_tmp/count', 'fixture.config', 1, 1)
    build_graph()
    generic_build()
    return []
'''

COUNTER = '''#!/usr/bin/env python3
import json, sys
from pathlib import Path
args=sys.argv[1:]
out=args[args.index('-o')+1]
Path(out).parent.mkdir(exist_ok=True)
Path(out+'_start_0').write_text('fixture count\\n')
Path('counter_argv.json').write_text(json.dumps(args))
'''


def fastq(path, lengths=(4, 5, 6)):
    data = b"".join(f"@read-{i}\n".encode() + b"A" * n + b"\n+\n" + b"I" * n + b"\n"
                    for i, n in enumerate(lengths))
    path.write_bytes(data)
    return data


class BenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.storage = tempfile.TemporaryDirectory(prefix="wings-benchmark-tests-")
        cls.root = Path(cls.storage.name)
        cls.repo = cls.root / "fixture repo"
        cls.env_dir = cls.repo / ".snakemake/conda/fixture"
        venv.EnvBuilder(with_pip=False).create(cls.env_dir)
        cls.python = cls.env_dir / "bin/python"
        purelib = subprocess.check_output([str(cls.python), "-c",
                                          "import sysconfig; print(sysconfig.get_path('purelib'))"], text=True).strip()
        package = Path(purelib) / "porechop_abi"
        package.mkdir()
        (package / "__init__.py").write_text("")
        (package / "version.py").write_text("__version__ = '0.5.1-fixture'\n")
        (package / "porechop_abi.py").write_text(TOOL)
        (package / "abinitio.py").write_text(ABI)

    @classmethod
    def tearDownClass(cls):
        cls.storage.cleanup()

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(dir=self.root))
        self.input = self.folder / "input with spaces.fastq"
        self.data = fastq(self.input)
        self.subset = self.folder / "subset.fastq"

    def environment(self, **extra):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        env.update(extra)
        return env

    def test_bounded_prefix_is_complete_and_original_unchanged(self):
        result = benchmark.subset_fastq(self.input, self.subset, 100, 9)
        self.assertEqual((result["reads"], result["bases"], result["stop_reason"]), (2, 9, "base_limit"))
        self.assertEqual(self.input.read_bytes(), self.data)
        self.assertEqual(len(self.subset.read_bytes().splitlines()), 8)

    def test_gzip_and_crlf_produce_same_subset_and_digest(self):
        archive = self.folder / "reads.bin"
        with gzip.open(archive, "wb") as handle:
            handle.write(self.data.replace(b"\n", b"\r\n"))
        a = benchmark.subset_fastq(self.input, self.subset, 2, 100)
        b = benchmark.subset_fastq(archive, self.folder / "gzip.fastq", 2, 100)
        self.assertEqual(a["sha256"], b["sha256"])

    def test_malformed_fastq_is_rejected(self):
        self.input.write_bytes(b"@a\nAAAA\n+\nII\n")
        with self.assertRaisesRegex(ValueError, "Invalid"):
            benchmark.subset_fastq(self.input, self.subset, 5, 100)

    def test_subset_never_overwrites_existing_file(self):
        self.subset.write_bytes(b"keep")
        with self.assertRaises(FileExistsError):
            benchmark.subset_fastq(self.input, self.subset, 5, 100)
        self.assertEqual(self.subset.read_bytes(), b"keep")

    def test_detects_installed_snakemake_environment(self):
        executable, env = benchmark.resolve_environment(self.repo, None)
        self.assertEqual(executable, self.python)
        self.assertEqual(Path(env["CONDA_PREFIX"]), self.env_dir)
        self.assertNotIn("PYTHONPATH", env)

    def test_real_worker_instruments_phases_preserving_output(self):
        benchmark.subset_fastq(self.input, self.subset, 3, 100)
        row = benchmark.run_trial(self.python, self.environment(), self.subset,
                                  self.folder / "trial with spaces", 4, 10)
        self.assertEqual(row["status"], "complete")
        self.assertEqual(row["threads"], 4)
        self.assertEqual(row["porechop_abi_version"], "0.5.1-fixture")
        self.assertEqual(len(row["phases"]), len(benchmark.PHASES) + len(benchmark.DETAILS))
        for label in benchmark.PHASES.values():
            self.assertEqual(row["phases"][label]["successful_calls"], 1)
        self.assertEqual((Path(row["directory"]) / "trimmed.fastq").read_bytes(), self.data)
        self.assertGreater(row["cpu_children_seconds"], 0)
        self.assertGreater(row["peak_self_rss_mib"], 0)

    def test_worker_failure_keeps_completed_phase_measurements(self):
        benchmark.subset_fastq(self.input, self.subset, 3, 100)
        row = benchmark.run_trial(self.python, self.environment(FIXTURE_FAIL_ENDS="1"), self.subset,
                                  self.folder / "failed", 1, 10)
        self.assertEqual(row["status"], "failed")
        self.assertIn("fixture trimming failure", row["error"])
        self.assertEqual(row["phases"]["adapter_discovery"]["successful_calls"], 1)
        self.assertEqual(row["phases"]["end_trimming"]["successful_calls"], 0)
        self.assertNotIn("output_sha256", row)

    def test_success_exit_without_output_is_reported_as_failure(self):
        benchmark.subset_fastq(self.input, self.subset, 3, 100)
        row = benchmark.run_trial(self.python, self.environment(FIXTURE_NO_OUTPUT="1"), self.subset,
                                  self.folder / "no-output", 1, 10)
        self.assertEqual(row["status"], "failed")
        self.assertIn("without creating trimmed.fastq", row["error"])

    def test_incompatible_tool_hooks_fail_before_processing(self):
        benchmark.subset_fastq(self.input, self.subset, 3, 100)
        row = benchmark.run_trial(self.python, self.environment(FIXTURE_UNSUPPORTED="1"), self.subset,
                                  self.folder / "unsupported", 1, 10)
        self.assertEqual(row["status"], "failed")
        self.assertIn("Unsupported Porechop_ABI entry points: output_reads", row["error"])
        self.assertEqual(row["phases"], {})

    def test_timeout_stops_native_descendant_and_retains_partial_report(self):
        benchmark.subset_fastq(self.input, self.subset, 3, 100)
        pid_file = self.folder / "child.pid"
        row = benchmark.run_trial(self.python,
                                  self.environment(FIXTURE_LONG_COUNT="1", FIXTURE_PID_FILE=str(pid_file)),
                                  self.subset, self.folder / "timeout", 1, 1)
        self.assertEqual(row["status"], "timeout")
        self.assertEqual(row["active_phase"], "discovery_native_counting")
        self.assertTrue(pid_file.is_file())
        process = subprocess.run(["ps", "-p", pid_file.read_text(), "-o", "stat="],
                                 capture_output=True, text=True)
        # A reparented zombie can briefly remain on Linux; it is no longer executing.
        self.assertTrue(not process.stdout.strip() or process.stdout.strip().startswith("Z"))
        self.assertTrue((self.folder / "timeout/trial_summary.json").is_file())

    def test_keyboard_interrupt_cancels_trial(self):
        benchmark.subset_fastq(self.input, self.subset, 3, 100)
        original_wait = subprocess.Popen.wait
        calls = 0
        def interrupted_wait(process, *args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise KeyboardInterrupt
            return original_wait(process, *args, **kwargs)
        with patch.object(subprocess.Popen, "wait", interrupted_wait):
            row = benchmark.run_trial(self.python, self.environment(), self.subset,
                                      self.folder / "cancelled", 1, 10)
        self.assertEqual(row["status"], "cancelled")
        self.assertTrue(row["interrupted"])
        self.assertNotEqual(row["process_exit_code"], 0)

    def test_cli_runs_sequential_trials_and_writes_reports(self):
        root = self.folder / "reports with spaces"
        command = [sys.executable, str(SCRIPT), "--input", str(self.input), "--repo", str(self.repo),
                   "--reads", "3", "--max-bases", "100", "--threads", "1", "4", "--min-free-gb", "0",
                   "--timeout-seconds", "10", "--output-root", str(root)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        reports = list(root.glob("*/summary.json"))
        self.assertEqual(len(reports), 1)
        summary = json.loads(reports[0].read_text())
        self.assertEqual([row["threads"] for row in summary["trials"]], [1, 4])
        self.assertEqual(summary["trials"][0]["output_sha256"], summary["trials"][1]["output_sha256"])
        self.assertEqual(self.input.read_bytes(), self.data)
        self.assertTrue(reports[0].with_name("phase_times.tsv").is_file())

    def test_disk_guard_does_not_create_output_folder(self):
        root = self.folder / "no-space"
        usage = type("Usage", (), {"free": 1})()
        with patch.object(benchmark.shutil, "disk_usage", return_value=usage):
            with self.assertRaisesRegex(RuntimeError, "disk space"):
                benchmark.main(["--input", str(self.input), "--repo", str(self.repo),
                                "--output-root", str(root)])
        self.assertFalse(root.exists())

    def make_manifest(self):
        binaries = {}
        for name in ('serial_build', 'openmp_build'):
            path = self.folder / (name + ' with spaces')
            path.write_text(COUNTER + '\n# ' + name + '\n')
            path.chmod(0o755)
            binaries[name] = {'path': str(path), 'sha256': benchmark.file_hash(path)}
        tool = next((self.env_dir / 'lib').glob('python*/site-packages/porechop_abi/porechop_abi.py'))
        manifest = {'schema_version': 'wings.porechop_openmp_build.v1',
                    'installed_python': str(self.python), 'binaries': binaries,
                    'installed_tool_source_sha256': benchmark.file_hash(tool)}
        path = self.folder / 'build_manifest.json'
        path.write_text(json.dumps(manifest))
        return path, manifest

    def test_counter_override_preserves_cli_and_output(self):
        path, manifest = self.make_manifest()
        variants, _ = benchmark.counter_variants(path, self.python)
        benchmark.subset_fastq(self.input, self.subset, 3, 100)
        row = benchmark.run_trial(self.python, self.environment(), self.subset,
                                  self.folder / 'override', 4, 10, variants[2],
                                  manifest['installed_tool_source_sha256'])
        self.assertEqual(row['status'], 'complete', row)
        self.assertEqual(row['backend'], 'openmp_build')
        argv = json.loads((self.folder / 'override/counter_argv.json').read_text())
        self.assertEqual(argv[0], 'input.fastq')
        self.assertEqual(argv[argv.index('-nt')+1], str(min(4, os.cpu_count())))
        self.assertIn('count_start_0', row['discovery_file_hashes'])
        self.assertEqual((self.folder / 'override/trimmed.fastq').read_bytes(), self.data)

    def test_manifest_tampering_is_rejected(self):
        path, manifest = self.make_manifest()
        Path(manifest['binaries']['openmp_build']['path']).write_text(COUNTER + '# changed\n')
        with self.assertRaisesRegex(ValueError, 'differs from build manifest'):
            benchmark.counter_variants(path, self.python)

    def test_mismatched_environment_is_rejected(self):
        path, _ = self.make_manifest()
        with self.assertRaisesRegex(ValueError, 'same Porechop_ABI environment'):
            benchmark.counter_variants(path, Path(sys.executable))

    def test_comparison_cli_runs_all_control_variants(self):
        manifest_path, _ = self.make_manifest()
        root = self.folder / 'comparison'
        result = subprocess.run([sys.executable, str(SCRIPT), '--input', str(self.input),
                                 '--python', str(self.python), '--counter-build', str(manifest_path),
                                 '--threads', '1', '4', '--reads', '3', '--max-bases', '100',
                                 '--min-free-gb', '0', '--output-root', str(root)],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        summary = json.loads(next(root.glob('*/summary.json')).read_text())
        labels = [(row['backend'], row['threads']) for row in summary['trials']]
        self.assertEqual(labels, [('installed', 1), ('installed', 4), ('serial_build', 1),
                                  ('openmp_build', 1), ('openmp_build', 4)])
        self.assertTrue(all(row['status'] == 'complete' for row in summary['trials']))
        self.assertIn('Discovery intermediate hashes: identical', result.stdout)

    def previous_benchmark(self):
        manifest_path, manifest = self.make_manifest()
        benchmark.subset_fastq(self.input, self.subset, 3, 100)
        previous = {'schema_version': 'wings.porechop_benchmark.v1',
                    'subset': {'reads': 3, 'bases': 15, 'size_bytes': self.subset.stat().st_size,
                               'sha256': benchmark.file_hash(self.subset)},
                    'input': str(self.input), 'python_executable': str(self.python),
                    'counter_build': manifest, 'limits': {'reads': 3, 'bases': 100}}
        path = self.folder / 'summary.json'
        path.write_text(json.dumps(previous))
        return path

    def phase_command(self, previous, root):
        return [sys.executable, str(SCRIPT), '--reuse-benchmark', str(previous),
                '--phase-thread-comparison', '--threads', '4', '--repeats', '2',
                '--min-free-gb', '0', '--output-root', str(root)]

    def test_phase_pair_reuses_exact_subset_alternates_order_and_checks_outputs(self):
        previous = self.previous_benchmark()
        # The original file can disappear; this experiment uses the preserved subset.
        self.input.unlink()
        original_counter = benchmark.file_hash(self.folder / 'openmp_build with spaces')
        root = self.folder / 'phase comparison'
        result = subprocess.run(self.phase_command(previous, root), capture_output=True,
                                text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        path = next(root.glob('*/summary.json'))
        summary = json.loads(path.read_text())
        self.assertEqual([r['allocation'] for r in summary['trials']],
                         ['uniform', 'phase_split', 'phase_split', 'uniform'])
        self.assertEqual([r['repeat'] for r in summary['trials']], [1, 1, 2, 2])
        self.assertEqual((path.parent / 'subset.fastq').read_bytes(), self.data)
        self.assertEqual(summary['planned_trials'], 4)
        self.assertTrue(summary['output_comparison']['all_pairs_match'])
        self.assertIn('Completed trials: 4/4', result.stdout)
        self.assertIn('Final trimmed output hashes: identical', result.stdout)
        for row in summary['trials']:
            calls = [json.loads(line) for line in
                     (Path(row['directory']) / 'thread_calls.jsonl').read_text().splitlines()]
            self.assertEqual([c['threads'] for c in calls],
                             [1 if row['allocation'] == 'phase_split' else 4, 4, 4])
            native_args = json.loads((Path(row['directory']) / 'counter_argv.json').read_text())
            self.assertEqual(native_args[native_args.index('-nt') + 1], str(min(4, os.cpu_count())))
        self.assertEqual(benchmark.file_hash(self.folder / 'openmp_build with spaces'), original_counter)

    def test_phase_wrapper_changes_only_threads_and_does_not_mutate_namespace(self):
        from types import SimpleNamespace
        namespace = SimpleNamespace(threads=4, threshold=91, input='unchanged')
        def launch_ab_initio(args):
            self.assertEqual((args.threads, args.threshold, args.input), (2, 91, 'unchanged'))
            raise ValueError('test error')
        with self.assertRaisesRegex(ValueError, 'test error'):
            benchmark.phase_thread_wrapper(launch_ab_initio, 2, True)(namespace)
        self.assertEqual(namespace.threads, 4)
        def search(check_reads, verbosity, end_size, scoring_scheme_vals, print_dest,
                   adapter_threshold, threads):
            return (check_reads, verbosity, end_size, scoring_scheme_vals, print_dest,
                    adapter_threshold, threads)
        wrapped = benchmark.phase_thread_wrapper(search, 1)
        self.assertEqual(wrapped('reads', 2, 150, 'scores', 'dest', 91, 4),
                         ('reads', 2, 150, 'scores', 'dest', 91, 1))
        self.assertEqual(wrapped('reads', 2, 150, 'scores', 'dest', 91, threads=4)[-1], 1)

    def test_phase_wrapper_rejects_incompatible_signature(self):
        with self.assertRaisesRegex(RuntimeError, 'Unsupported thread-control signature'):
            benchmark.phase_thread_wrapper(lambda reads: None, 1)

    def test_reuse_rejects_changed_subset_before_creating_report_folder(self):
        previous = self.previous_benchmark()
        self.subset.write_bytes(b'changed')
        root = self.folder / 'tampered'
        result = subprocess.run(self.phase_command(previous, root), capture_output=True,
                                text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('differs from its recorded hash', result.stderr)
        self.assertFalse(root.exists())

    def test_phase_output_difference_is_explicit_and_exits_two(self):
        previous = self.previous_benchmark()
        root = self.folder / 'different outputs'
        result = subprocess.run(self.phase_command(previous, root), capture_output=True,
                                text=True, timeout=30,
                                env=self.environment(FIXTURE_DIFFERENT_SEARCH='1'))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('Final trimmed output hashes: differ', result.stdout)
        self.assertIn('NOT VERIFIED', result.stdout)
        summary = json.loads(next(root.glob('*/summary.json')).read_text())
        self.assertFalse(summary['output_comparison']['all_pairs_match'])

    def test_phase_budget_rejects_oversubscription_before_output(self):
        previous = self.previous_benchmark()
        root = self.folder / 'oversubscribed'
        result = subprocess.run(self.phase_command(previous, root) + ['--discovery-threads', '8'],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 2)
        self.assertIn('cannot exceed', result.stderr)
        self.assertFalse(root.exists())

    def test_empty_hashes_or_incomplete_trials_do_not_claim_equivalence(self):
        rows = [{'allocation': 'uniform', 'status': 'complete'},
                {'allocation': 'phase_split', 'status': 'complete'}]
        result = benchmark.compare_outputs({'trials': rows})
        self.assertFalse(result['all_pairs_match'])
        rows[1]['status'] = 'failed'
        self.assertFalse(benchmark.compare_outputs({'trials': rows})['pairs'][0]['complete'])
        for row in rows:
            row.update(status='complete', output_sha256='same', discovery_file_hashes={'counter': 'same'})
        self.assertFalse(benchmark.compare_outputs({'trials': rows, 'planned_trials': 4})['all_pairs_match'])
        self.assertTrue(benchmark.compare_outputs({'trials': rows, 'planned_trials': 2})['all_pairs_match'])


if __name__ == "__main__":
    unittest.main()
