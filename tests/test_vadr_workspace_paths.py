"""Execute the actual VADR rule with a simulated Docker/VADR command boundary.

No model download or biological analysis is performed. The fake VADR reproduces
its unquoted esl-reformat invocation, so the old workspace path fails this test.
"""
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def rule_body():
    source = (ROOT / 'Snakefile').read_text()
    rule = source.split('rule vadr_annotate:', 1)[1]
    lines = rule.split('    run:\n', 1)[1].splitlines(keepends=True)
    body = []
    for line in lines:
        if line.strip() and not line.startswith('        '):
            break
        body.append(line)
    return compile(textwrap.dedent(''.join(body)), 'Snakefile:vadr_annotate', 'exec')


class VadrWorkspacePaths(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='wings-vadr-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.body = rule_body()

    def fixture(self, workspace='WINGS Workspace', empty=False):
        base = self.root / workspace / 'runs' / 'fixture' / 'results' / 'SRR41529551' / 'vadr'
        base.mkdir(parents=True)
        fasta = base / 'SRR41529551.vadr_input.fasta'
        fasta.write_text('' if empty else '>test_segment\nACGTACGTACGT\n')
        models = self.root / 'Influenza models'
        models.mkdir(exist_ok=True)
        for suffix in ('minfo', 'cm', 'fa'):
            (models / ('flu.' + suffix)).write_text('test model placeholder\n')
        return dict(
            Path=Path, os=os, shutil=shutil, subprocess=subprocess,
            input=SimpleNamespace(fasta=str(fasta)),
            output=SimpleNamespace(outdir=str(base / 'output'), done=str(base / 'sample.vadr.done')),
            log=[str(base / 'sample.vadr.log')], threads=2,
            wildcards=SimpleNamespace(sample='SRR41529551'),
            params=SimpleNamespace(runtime='docker', image='docker://staphb/vadr:test',
                                   model_dir=str(models), mkey='flu', forcegene='true', fail_soft='false'))

    def docker(self, command, *, cwd, stdout, stderr, text):
        self.assertEqual(command[:3], ['docker', 'run', '--rm'])
        self.assertEqual(command[command.index('--platform')+1], 'linux/amd64')
        self.assertEqual(stderr, subprocess.STDOUT)
        self.assertTrue(text)
        mounts = []
        for i, arg in enumerate(command):
            if arg == '-v':
                host, target, *flags = command[i+1].split(':')
                self.assertTrue(Path(host).exists())
                mounts.append((Path(host), PurePosixPath(target), flags))

        def host_path(container_path):
            path = PurePosixPath(container_path)
            for host, target, flags in sorted(mounts, key=lambda m:len(str(m[1])), reverse=True):
                if path == target or target in path.parents:
                    return host / path.relative_to(target), flags
            self.fail('Path not reachable through a Docker mount: ' + str(path))

        args = command[command.index('v-annotate.pl'):]
        for flag in ('--split', '-r', '--atgonly', '--xnocomp', '--nomisc', '--forcegene'):
            self.assertIn(flag, args)
        self.assertEqual(args[args.index('--cpu')+1], '2')
        self.assertEqual(args[args.index('--alt_fail')+1], 'extrant5,extrant3')
        self.assertEqual(args[args.index('--mkey')+1], 'flu')
        inner_fasta, prefix = args[-2:]
        # Reproduce the exact failure mechanism in the reported VADR log.
        words = shlex.split(f'esl-reformat fasta {inner_fasta} > {prefix}/{prefix}.vadr.in.fa')
        if len(words) != 5 or words[2] != inner_fasta:
            stdout.write('esl-reformat: input path was split by the shell\n')
            return subprocess.CompletedProcess(command, 2)
        work = command[command.index('-w')+1]
        self.assertFalse(any(c.isspace() for c in work), 'VADR cwd must also be space-free')
        source, flags = host_path(inner_fasta)
        self.assertIn('ro', flags)
        model_dir, flags = host_path(args[args.index('--mdir')+1])
        self.assertIn('ro', flags)
        self.assertTrue((model_dir / 'flu.cm').is_file())
        dest, flags = host_path(work)
        self.assertNotIn('ro', flags)
        self.assertEqual(dest.resolve(), Path(cwd).resolve())
        nested = dest / prefix
        nested.mkdir()
        (nested / (prefix + '.vadr.in.fa')).write_bytes(source.read_bytes())
        (nested / (prefix + '.vadr.pass.tbl')).write_text('test annotation output\n')
        stdout.write('simulated VADR path validation passed\n')
        return subprocess.CompletedProcess(command, 0)

    def execute(self, env, effect=None):
        with patch.object(subprocess, 'run', side_effect=effect or self.docker) as run:
            exec(self.body, env)
        return run

    def test_docker_workspace_with_spaces_preserves_input_and_collects_outputs(self):
        env = self.fixture()
        original = Path(env['input'].fasta).read_bytes()
        self.execute(env)
        out = Path(env['output'].outdir)
        self.assertEqual((out / 'SRR41529551.vadr.in.fa').read_bytes(), original)
        self.assertTrue((out / 'SRR41529551.vadr.pass.tbl').is_file())
        self.assertFalse((out / 'SRR41529551').exists())
        self.assertTrue(Path(env['output'].done).is_file())
        self.assertEqual(Path(env['input'].fasta).read_bytes(), original)

    def test_host_quotes_and_unicode_do_not_enter_vadr_shell_arguments(self):
        self.execute(self.fixture("Jim's WINGS Workspace – Alaska"))

    def test_space_free_host_still_works(self):
        self.execute(self.fixture('workspace'))

    def test_auto_runtime_uses_the_fixed_docker_mapping(self):
        env = self.fixture(); env['params'].runtime = 'auto'
        with patch.object(shutil, 'which', side_effect=lambda name:'/bin/docker' if name=='docker' else None):
            self.execute(env)

    def test_hard_failure_propagates_without_success_marker(self):
        env = self.fixture()
        with self.assertRaisesRegex(RuntimeError, 'VADR failed with exit code 7'):
            self.execute(env, lambda command, **kwargs:subprocess.CompletedProcess(command, 7))
        self.assertFalse(Path(env['output'].done).exists())

    def test_existing_fail_soft_option_is_preserved(self):
        env = self.fixture(); env['params'].fail_soft = 'true'
        self.execute(env, lambda command, **kwargs:subprocess.CompletedProcess(command, 7))
        self.assertTrue(Path(env['output'].done).exists())
        self.assertIn('continuing because vadr_fail_soft=true', Path(env['log'][0]).read_text())

    def test_empty_input_skips_vadr(self):
        env = self.fixture(empty=True)
        run = self.execute(env)
        run.assert_not_called()
        self.assertTrue(Path(env['output'].done).exists())
        self.assertIn('VADR skipped', Path(env['log'][0]).read_text())

    def test_missing_models_fail_before_docker(self):
        env = self.fixture(); (Path(env['params'].model_dir) / 'flu.cm').unlink()
        with patch.object(subprocess, 'run') as run:
            with self.assertRaisesRegex(RuntimeError, 'model directory is incomplete'):
                exec(self.body, env)
            run.assert_not_called()

    def test_local_runtime_is_unchanged(self):
        env = self.fixture(); env['params'].runtime = 'local'
        def local(command, **kwargs):
            self.assertEqual(command[0], 'v-annotate.pl')
            self.assertEqual(command[-2], env['input'].fasta)
            self.assertEqual(command[command.index('--mdir')+1], env['params'].model_dir)
            return subprocess.CompletedProcess(command, 0)
        self.execute(env, local)


if __name__ == '__main__':
    unittest.main()
