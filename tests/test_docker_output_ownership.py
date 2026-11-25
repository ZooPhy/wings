"""Run actual IRMA/VADR rule bodies at a mocked container boundary.

These exercise caller mapping and rerun cleanup, without downloading images.
Use the companion smoke check to verify real Docker bind-mount ownership.
"""
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def rule_body(name):
    source = (ROOT / 'Snakefile').read_text()
    rule = re.split(r'^rule ' + re.escape(name) + r':\s*$', source, flags=re.M)[1]
    lines = re.split(r'^    run:\s*$', rule, maxsplit=1, flags=re.M)[1].lstrip('\n').splitlines(True)
    body = []
    for line in lines:
        if line.strip() and not line.startswith('        '):
            break
        body.append(line)
    return compile(textwrap.dedent(''.join(body)), 'Snakefile:' + name, 'exec')


class DockerOutputOwnership(unittest.TestCase):
    def fixture(self, rule, runtime):
        tmp = tempfile.TemporaryDirectory(prefix='wings caller ownership ')
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        fasta = base / 'sample.fasta'
        fasta.write_text('>sample\nACGT\n')
        models = base / 'models'
        models.mkdir()
        for suffix in ('minfo', 'cm', 'fa'):
            (models / ('flu.' + suffix)).write_text('fixture\n')
        result = base / ('project' if rule == 'irma' else 'output')
        result.mkdir()
        (result / 'stale').write_text('must be removed by rerun')
        namespace = dict(Path=Path, os=os, re=re, shlex=shlex, shutil=shutil,
                         subprocess=subprocess, threads=2,
                         wildcards=SimpleNamespace(sample='sample'),
                         log=[str(base / 'analysis.log')])
        if rule == 'irma':
            namespace.update(input=SimpleNamespace(renamed=str(fasta)),
                             output=SimpleNamespace(project=str(result)),
                             params=SimpleNamespace(runtime=runtime, image='docker://example/irma:test', module='FLU'))
        else:
            namespace.update(input=SimpleNamespace(fasta=str(fasta)),
                             output=SimpleNamespace(outdir=str(result), done=str(base / 'sample.vadr.done')),
                             params=SimpleNamespace(runtime=runtime, image='docker://example/vadr:test',
                                                    model_dir=str(models), mkey='flu', forcegene='true', fail_soft='false'))
        return namespace, result

    def run_rule(self, rule, runtime):
        namespace, result = self.fixture(rule, runtime)
        observed = []

        def launch(command, **kwargs):
            observed.append(command)
            if runtime == 'docker':
                self.assertEqual(command[1:3], ['run', '--rm'])
                self.assertEqual(command[command.index('--user')+1], f'{os.getuid()}:{os.getgid()}')
                self.assertEqual(command.count('--user'), 1)
                self.assertIn('HOME=/tmp', command)
                self.assertIn('TMPDIR=/tmp', command)
                # Engine options must precede the image, not become tool arguments.
                image = 'example/irma:test' if rule == 'irma' else 'example/vadr:test'
                self.assertLess(command.index('--user'), command.index(image))
                if rule == 'vadr_annotate':
                    self.assertEqual(command[command.index('--platform')+1], 'linux/amd64')
                    self.assertTrue(any(value.endswith(':/models:ro') for value in command))
            else:
                self.assertNotIn('--user', command)
                self.assertNotIn('HOME=/tmp', command)
            self.assertFalse((result / 'stale').exists())
            result.mkdir(exist_ok=True)
            if rule == 'irma':
                (result / 'assembly.txt').write_text('fixture')
            else:
                nested = result / 'sample'
                nested.mkdir()
                (nested / 'sample.vadr.pass.tbl').write_text('fixture')
            return subprocess.CompletedProcess(command, 0)

        with patch.object(shutil, 'which', side_effect=lambda name: '/tools/' + name), patch.object(subprocess, 'run', side_effect=launch):
            exec(rule_body(rule), namespace)
            # A second invocation must remove and recreate caller-managed outputs.
            (result / 'stale').write_text('old output')
            exec(rule_body(rule), namespace)
        self.assertEqual(len(observed), 2)
        if rule == 'vadr_annotate':
            self.assertTrue((result / 'sample.vadr.pass.tbl').is_file())
            self.assertFalse((result / 'sample').exists())
            self.assertTrue(Path(namespace['output'].done).is_file())
        else:
            self.assertTrue((result / 'assembly.txt').is_file())
        shutil.rmtree(result)
        self.assertFalse(result.exists())

    def test_irma_docker_caller_mapping_and_rerun(self):
        self.run_rule('irma', 'docker')

    def test_vadr_docker_caller_mapping_and_rerun(self):
        self.run_rule('vadr_annotate', 'docker')

    def test_local_irma_unchanged(self):
        self.run_rule('irma', 'local')

    def test_local_vadr_unchanged(self):
        self.run_rule('vadr_annotate', 'local')

    def test_apptainer_irma_unchanged(self):
        self.run_rule('irma', 'apptainer')

    def test_apptainer_vadr_unchanged(self):
        self.run_rule('vadr_annotate', 'apptainer')


if __name__ == '__main__':
    unittest.main()
