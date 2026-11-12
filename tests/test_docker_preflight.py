"""Runtime selection, bounded daemon probes, and start/resume rejection before launch."""
import ast
import email.message
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
TREE=ast.parse((ROOT/'scripts/wings_local_runner.py').read_text())


class DockerPreflightTests(unittest.TestCase):
    def setUp(self):
        self.scope=dict(Path=Path,shutil=shutil,subprocess=subprocess,utc_now=lambda:'test-time')
        functions=[node for node in TREE.body if isinstance(node,ast.FunctionDef) and node.name in {'check_docker','require_docker','launch_attempt'}]
        exec(compile(ast.Module(body=functions,type_ignores=[]),'<docker preflight>','exec'),self.scope)
        self.check=self.scope['check_docker']
        self.available={'docker'}
        self.which=patch.object(shutil,'which',side_effect=lambda name:'/bin/'+name if name in self.available else None)
        self.which.start();self.addCleanup(self.which.stop)

    def test_stopped_engine_is_not_ready_and_probe_is_bounded(self):
        with patch.object(subprocess,'run',return_value=types.SimpleNamespace(returncode=1)) as probe:
            result=self.check({'irma_runtime':'docker','run_vadr':False})
        self.assertFalse(result['ready']);self.assertEqual(result['status'],'engine_unavailable')
        self.assertIn('Start Docker Desktop',result['message']);self.assertEqual(probe.call_args.kwargs['timeout'],8)
        self.assertEqual(probe.call_args.args[0],['/bin/docker','info','--format','{{.ServerVersion}}'])
        self.assertNotIn('shell',probe.call_args.kwargs)

    def test_running_engine_is_ready(self):
        with patch.object(subprocess,'run',return_value=types.SimpleNamespace(returncode=0)):
            self.assertTrue(self.check({'irma_runtime':'docker','run_vadr':False})['ready'])
            self.scope['require_docker']({'irma_runtime':'docker','run_vadr':False})

    def test_missing_cli_and_timeout_are_actionable(self):
        self.available.clear();self.assertEqual(self.check({'irma_runtime':'docker'})['status'],'missing_runtime')
        self.available.add('docker')
        with patch.object(subprocess,'run',side_effect=subprocess.TimeoutExpired('docker',8)):
            self.assertEqual(self.check({'irma_runtime':'docker'})['status'],'timeout')

    def test_hpc_runtime_does_not_require_docker(self):
        self.available={'apptainer'}
        with patch.object(subprocess,'run') as probe:
            result=self.check({'irma_runtime':'auto','vadr_runtime':'auto'})
        self.assertTrue(result['ready']);self.assertFalse(result['required']);probe.assert_not_called()

    def test_vadr_auto_prefers_docker_even_when_irma_uses_apptainer(self):
        self.available={'apptainer','docker'}
        with patch.object(subprocess,'run',return_value=types.SimpleNamespace(returncode=1)):
            result=self.check({'irma_runtime':'auto','vadr_runtime':'auto'})
        self.assertEqual(result['required_by'],['VADR']);self.assertFalse(result['ready'])
        with patch.object(subprocess,'run') as probe:
            self.assertTrue(self.check({'irma_runtime':'auto','vadr_runtime':'auto'},run_vadr=False)['ready'])
        probe.assert_not_called()

    def test_local_tools_are_supported_and_bad_selections_rejected(self):
        self.available={'IRMA','v-annotate.pl'}
        with patch.object(subprocess,'run') as probe:
            self.assertTrue(self.check({'irma_runtime':'local','vadr_runtime':'auto'})['ready'])
        probe.assert_not_called()
        with self.assertRaises(ValueError):self.check({'irma_runtime':'invalid'})
        with self.assertRaises(ValueError):self.check({},run_vadr='false')

    def test_start_and_resume_are_stopped_before_process_creation(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();(root/'execution_config.yaml').write_text('fixture')
            self.scope.update(LOCK=threading.RLock(),PROCESSES={},
                context_runner=types.SimpleNamespace(busy=lambda _:False),runtime_preflight=lambda:'snakemake',
                require_briefing_model=lambda _:None,
                build_config=lambda _:(root/'execution_config.yaml',1),
                run_dir=lambda _:root,yaml=types.SimpleNamespace(safe_load=lambda _: {'irma_runtime':'docker','run_vadr':False}))
            with patch.object(subprocess,'run',return_value=types.SimpleNamespace(returncode=1)),patch.object(subprocess,'Popen') as launch:
                for resume in [False,True]:
                    self.scope['read_state']=lambda _,resuming=resume:{'status':'failed' if resuming else 'created'}
                    with self.subTest(resume=resume),self.assertRaisesRegex(ValueError,'Docker engine is unavailable'):
                        self.scope['launch_attempt']('saved-run',resume=resume)
                launch.assert_not_called()

    def test_endpoint_rejects_cross_origin_requests(self):
        handler=next(node for node in TREE.body if isinstance(node,ast.ClassDef) and node.name=='Handler')
        method=next(node for node in handler.body if isinstance(node,ast.FunctionDef) and node.name=='do_POST')
        self.scope.update(json=json,context_runner=types.SimpleNamespace(handle_post=lambda *_:False))
        exec(compile(ast.Module(body=[method],type_ignores=[]),'<docker endpoint>','exec'),self.scope)
        headers=email.message.Message();headers['Host']='localhost:8765';headers['Origin']='https://unrelated.example';headers['Content-Type']='application/json'
        result={}
        fake=types.SimpleNamespace(headers=headers,parsed=lambda:types.SimpleNamespace(path='/api/docker/check'),
            error_response=lambda error,status:result.update(status=status),read_json=lambda:(_ for _ in ()).throw(AssertionError('Must reject before reading payload')))
        self.scope['do_POST'](fake);self.assertEqual(result['status'],403)


if __name__=='__main__':unittest.main()
