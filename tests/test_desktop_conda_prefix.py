"""Stable Conda prefixes and Docker mount construction, without a Docker daemon."""
import ast
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
source=ast.parse((ROOT/'scripts/wings_local_runner.py').read_text())
# Test the actual command builders without starting the HTTP runner or importing
# unrelated UI integrations. No manipulation of sys.modules is needed.
selected=[n for n in source.body if isinstance(n,ast.FunctionDef) and n.name in ('conda_environment_prefix','workflow_command')]
namespace=dict(Path=Path,os=os,platform=platform,REPO_ROOT=Path('/workspace/releases/one/app'),execution_limits=lambda state:(4,2))
exec(compile(ast.Module(body=selected,type_ignores=[]),'<runner command builders>','exec'),namespace)

class PrefixTests(unittest.TestCase):
    def test_desktop_prefix_stable_across_releases_and_host_spaces(self):
        with patch.dict(os.environ,{'WINGS_DESKTOP_CONDA_PREFIX':'/opt/wings-conda-envs'}),patch.object(platform,'system',return_value='Linux'),patch.object(platform,'machine',return_value='x86_64'):
            commands=[]
            for release in ('one','two'):
                namespace['REPO_ROOT']=Path('/Users/test/WINGS Workspace/releases')/release/'app'
                commands.append(namespace['workflow_command']('snakemake',Path('/work/config.yaml'),{}))
            self.assertEqual(commands[0][commands[0].index('--conda-prefix')+1],'/opt/wings-conda-envs/linux-x86_64')
            self.assertEqual(commands[0][commands[0].index('--conda-prefix')+1],commands[1][commands[1].index('--conda-prefix')+1])
            self.assertNotEqual(commands[0][2],commands[1][2])
            self.assertIn('--rerun-incomplete',commands[0])

    def test_native_runner_keeps_existing_prefix(self):
        namespace['REPO_ROOT']=Path('/repo')
        with patch.dict(os.environ,{},clear=True),patch.object(platform,'system',return_value='Darwin'),patch.object(platform,'machine',return_value='arm64'):
            self.assertEqual(namespace['conda_environment_prefix'](),Path('/repo/.snakemake/conda-platforms/darwin-arm64'))

    def test_invalid_override_rejected(self):
        for value in ('relative/path','/path with space','/path\twithtab','/opt/../tmp'):
            with self.subTest(value=value),patch.dict(os.environ,{'WINGS_DESKTOP_CONDA_PREFIX':value}):
                with self.assertRaises(ValueError):namespace['conda_environment_prefix']()

    def test_platforms_remain_separate(self):
        with patch.dict(os.environ,{'WINGS_DESKTOP_CONDA_PREFIX':'/opt/wings-conda-envs'}),patch.object(platform,'system',return_value='Linux'):
            with patch.object(platform,'machine',return_value='x86_64'):a=namespace['conda_environment_prefix']()
            with patch.object(platform,'machine',return_value='aarch64'):b=namespace['conda_environment_prefix']()
            self.assertNotEqual(a,b)

    def test_bash_constructs_mount_as_single_argument_with_spaces(self):
        text=(ROOT/'desktop/desktop.sh').read_text()
        block=text[text.index('# Conda embeds'):text.index("stage 'Verifying workflow source")]
        with tempfile.TemporaryDirectory(prefix='WINGS space ') as tmp:
            preamble='workspace=$1\ninput_mounts=()\nhost_home=/Users/test\nbrowse_roots=/Users\nreference_archive=/tmp/ref\ndocker_cli_arch=arm64\nrepo=/tmp/repo\n'
            result=subprocess.run(['bash','-c',preamble+block+'\nprintf "%s\\0" "${common[@]}"','_',tmp],capture_output=True,check=True)
            args=result.stdout.decode().split('\0')
            self.assertIn('type=bind,source='+tmp+'/cache/conda-envs-v2,target=/opt/wings-conda-envs',args)
            self.assertIn('WINGS_DESKTOP_CONDA_PREFIX=/opt/wings-conda-envs',args)
            self.assertTrue((Path(tmp)/'cache/conda-envs-v2').is_dir())

if __name__=='__main__':unittest.main()
