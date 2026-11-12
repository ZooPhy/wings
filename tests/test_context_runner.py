import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import context_setup as c
import context_runner as routes
from test_context_setup import METADATA, public

class RunnerContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        spec=importlib.util.spec_from_file_location('fixture_runner',ROOT/'scripts/wings_local_runner.py')
        self.runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.runner)
        self.runner.RUNS_ROOT=self.root/'runs';self.runner.RUNS_ROOT.mkdir()
        docker=patch.object(self.runner,'require_docker');docker.start();self.addCleanup(docker.stop)
        self.env=patch.dict(os.environ,{'WINGS_CONTEXT_CACHE':str(self.root/'cache')});self.env.start();self.addCleanup(self.env.stop)
        routes.JOBS.clear();routes.UPLOADS.clear()
        self.addCleanup(routes.JOBS.clear);self.addCleanup(routes.UPLOADS.clear)
    def run_directory(self,name='source'):
        p=self.runner.run_dir(name);(p/'inputs'/'reads').mkdir(parents=True)
        (p/'inputs'/'metadata.tsv').write_text(METADATA)
        for sid in ('A','B'):(p/'inputs'/'reads'/(sid+'.fastq.gz')).write_bytes(b'fixture')
        self.runner.write_state(name,{'run_id':name,'status':'created','options':{'context_setup':True}})
        return p
    def prepared(self,p):
        def executor(args,log,**kwargs):
            Path(log).write_text('fixture');out=Path(args[args.index('--output')+1])
            if 'build_ecological' in args[1]:raise ValueError('weather unavailable in fixture')
            c.write(out,public())
        return c.prepare(p/'inputs'/'metadata.tsv',p/'context',{'network':False,'phenology':False},executor=executor)
    def test_build_config_requires_preparation_and_pins_selection(self):
        p=self.run_directory()
        with self.assertRaises(FileNotFoundError):self.runner.build_config('source')
        result=self.prepared(p);config_path,count=self.runner.build_config('source')
        config=self.runner.yaml.safe_load(config_path.read_text());self.assertEqual(count,2)
        self.assertIn(result['snapshot_id'],config['context_setup']['selection'])
        self.assertFalse(config['genomic_ecological_concordance']['auto_weather'])
    def test_legacy_run_does_not_require_new_context_option(self):
        p=self.run_directory();self.runner.write_state('source',{'status':'created','options':{}})
        path,count=self.runner.build_config('source');self.assertTrue(path.is_file());self.assertEqual(count,2)
    def test_busy_run_cannot_launch_or_accept_upload(self):
        self.run_directory();routes.JOBS.add('source')
        with self.assertRaisesRegex(ValueError,'Wait for context'):self.runner.launch_attempt('source')
        with self.assertRaisesRegex(ValueError,'cannot change'):routes.reserve_upload('source',vars(self.runner))
    def test_upload_blocks_preparation_and_releases(self):
        self.run_directory();routes.reserve_upload('source',vars(self.runner))
        with self.assertRaisesRegex(ValueError,'idle'):routes.start('source',{},vars(self.runner))
        routes.finish_upload('source',vars(self.runner));self.assertFalse(routes.busy('source'))
    def test_reuse_selection_does_not_run_providers_or_genomic_jobs(self):
        source=self.run_directory();selection=self.prepared(source);target=self.run_directory('target')
        with patch.object(c,'prepare',side_effect=AssertionError('download')),patch.object(self.runner,'launch_attempt',side_effect=AssertionError('genomic run')):
            result=routes.start('target',{'reuse_run_id':'source'},vars(self.runner))
        self.assertEqual(result['status'],'READY');self.assertEqual(result['snapshot_id'],selection['snapshot_id'])
        _,copied=c.selected(target/'context',target/'inputs'/'metadata.tsv');self.assertEqual(copied,selection)
        self.assertEqual(self.runner.read_state('target')['status'],'created')
    def test_reuse_rejects_changed_metadata(self):
        self.prepared(self.run_directory());p=self.run_directory('target')
        (p/'inputs'/'metadata.tsv').write_text(METADATA.replace('33.4','33.9'))
        with self.assertRaisesRegex(ValueError,'metadata'):routes.start('target',{'reuse_run_id':'source'},vars(self.runner))
        self.assertFalse(routes.busy('target'))
    def test_restart_reports_interrupted_preparation(self):
        p=self.run_directory();c.write(p/'context'/'state.json',{'status':'PREPARING'})
        self.assertEqual(routes.status(p,'source')['status'],'INTERRUPTED')
    def test_started_run_cannot_be_reprepared(self):
        self.run_directory();self.runner.write_state('source',{'status':'running'})
        with self.assertRaisesRegex(ValueError,'unstarted'):routes.start('source',{},vars(self.runner))
    def test_origin_and_content_type_checks(self):
        for origin in ('https://evil.example','null','http://127.0.0.1:1234'):
            with self.subTest(origin=origin),self.assertRaises(ValueError):
                routes.guard_origin(SimpleNamespace(headers={'Origin':origin,'Host':'127.0.0.1:8765','Content-Type':'application/json'}))
        routes.guard_origin(SimpleNamespace(headers={'Origin':'http://localhost:8765','Host':'127.0.0.1:8765','Content-Type':'application/json'}))
        with self.assertRaises(ValueError):routes.guard_origin(SimpleNamespace(headers={'Content-Type':'text/plain'}))
    def test_resume_revalidates_saved_artifacts_before_spawning(self):
        p=self.run_directory();self.prepared(p);self.runner.build_config('source')
        self.runner.write_state('source',{'status':'failed','options':{'context_setup':True}})
        folder,_=c.selected(p/'context',p/'inputs'/'metadata.tsv');(folder/'genotypes.json').write_text('{}')
        with patch.object(self.runner,'runtime_preflight',return_value='snakemake'),patch.object(self.runner.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'changed'):self.runner.launch_attempt('source',resume=True)
            spawn.assert_not_called()
    def test_background_worker_keeps_run_unstarted(self):
        self.run_directory();entered=threading.Event();release=threading.Event();finished=threading.Event()
        def prepare(*a,**k):
            entered.set();release.wait(3)
            return {'status':'READY','providers':{},'snapshot_id':'fixture','blocked_sources':[]}
        with patch.object(c,'prepare',side_effect=prepare):
            result=routes.start('source',{},vars(self.runner));self.assertEqual(result['status'],'PREPARING');self.assertTrue(entered.wait(2))
            self.assertTrue(routes.busy('source'));self.assertEqual(self.runner.read_state('source')['status'],'created')
            release.set()
            for thread in threading.enumerate():
                if thread.name=='context-source':thread.join(3)
        self.assertFalse(routes.busy('source'));self.assertEqual(routes.status(self.runner.run_dir('source'),'source')['status'],'READY')

    def request(self,method,path,payload=None,body=None,origin=None):
        from email.message import Message
        import io
        handler=object.__new__(self.runner.Handler)
        handler.path=path;handler.headers=Message()
        raw=json.dumps(payload).encode() if payload is not None else (body or b'')
        handler.headers['Content-Length']=str(len(raw))
        handler.headers['Content-Type']='application/json'
        handler.headers['Host']='127.0.0.1:8765'
        if origin is not None:handler.headers['Origin']=origin
        handler.rfile=io.BytesIO(raw)
        replies=[]
        handler.json_response=lambda value,status=200:replies.append((int(status),value))
        getattr(handler,'do_'+method)()
        self.assertEqual(len(replies),1)
        return replies[0]
    def test_actual_health_and_context_get_routes(self):
        self.run_directory()
        code,data=self.request('GET','/api/health')
        self.assertEqual(code,200);self.assertEqual(data['storage_revision'],self.runner.STORAGE_REVISION)
        self.assertEqual(data['runs_root'],str(self.runner.RUNS_ROOT))
        code,data=self.request('GET','/api/runs/source/context')
        self.assertEqual(code,200);self.assertEqual(data['status'],'NOT_PREPARED')
    def test_actual_storage_route_preserves_origin_check(self):
        previous=self.runner.STORAGE_REVISION
        payload={'storage_revision':previous,'runs_dir':str(self.root/'new'),'conda_pkgs_dir':str(self.root/'packages')}
        code,data=self.request('POST','/api/storage',payload,origin='http://wrong.example')
        self.assertEqual(code,403);self.assertEqual(self.runner.STORAGE_REVISION,previous)
        code,data=self.request('POST','/api/storage',payload,origin='http://127.0.0.1:8765')
        self.assertEqual(code,200);self.assertNotEqual(data['storage_revision'],previous)
        self.assertEqual(data['conda_pkgs_dir'],str(self.root/'packages'))
    def test_actual_run_creation_rejects_stale_revision_and_saves_cache(self):
        self.runner.CURRENT_CACHE_DIR=str(self.root/'packages')
        code,data=self.request('POST','/api/runs',{'storage_revision':'stale','options':{'context_setup':True}})
        self.assertEqual(code,400);self.assertIn('Storage settings changed',data['error'])
        self.assertEqual(list(self.runner.RUNS_ROOT.iterdir()),[])
        code,data=self.request('POST','/api/runs',{'storage_revision':self.runner.STORAGE_REVISION,'options':{'context_setup':True}})
        self.assertEqual(code,201)
        saved=self.runner.read_state(data['run_id'])
        self.assertEqual(saved['conda_pkgs_dirs'],str(self.root/'packages'))
        self.assertTrue(saved['options']['context_setup'])
    def test_existing_context_survives_storage_switch_and_can_attach_to_new_run(self):
        source=self.run_directory();selection=self.prepared(source)
        oldroot=self.runner.RUNS_ROOT
        self.runner.update_storage({'storage_revision':self.runner.STORAGE_REVISION,'runs_dir':str(self.root/'new'),'conda_pkgs_dir':''})
        self.assertEqual(self.runner.run_dir('source'),source)
        target=self.run_directory('target')
        self.assertNotEqual(target.parent,oldroot)
        code,data=self.request('POST','/api/runs/target/context',{'reuse_run_id':'source'})
        self.assertEqual(code,200);self.assertEqual(data['snapshot_id'],selection['snapshot_id'])
        self.assertTrue((source/'context'/'selection.json').is_file())
        c.selected(target/'context',target/'inputs'/'metadata.tsv')
    def test_actual_upload_guard_releases_after_success_and_short_body(self):
        p=self.run_directory()
        code,_=self.request('PUT','/api/runs/source/files?kind=metadata&filename=metadata.tsv',body=METADATA.encode())
        self.assertEqual(code,200);self.assertFalse(routes.busy('source'))
        routes.JOBS.add('source')
        code,data=self.request('PUT','/api/runs/source/files?kind=metadata&filename=metadata.tsv',body=b'changed')
        self.assertEqual(code,400);self.assertEqual((p/'inputs'/'metadata.tsv').read_text(),METADATA)
        routes.JOBS.remove('source')
        from email.message import Message
        import io
        handler=object.__new__(self.runner.Handler);handler.path='/api/runs/source/files?kind=metadata&filename=metadata.tsv'
        handler.headers=Message();handler.headers['Content-Length']='100';handler.rfile=io.BytesIO(b'short')
        replies=[];handler.json_response=lambda data,status=200:replies.append(int(status))
        handler.do_PUT();self.assertEqual(replies,[400]);self.assertFalse(routes.busy('source'))
        self.assertEqual((p/'inputs'/'metadata.tsv').read_text(),METADATA)
    def test_context_executor_keeps_saved_cache_and_uses_native_preflight_for_snakemake(self):
        state={'conda_pkgs_dirs':str(self.root/'saved-cache')}
        with patch.dict(os.environ,{'CONDA_PKGS_DIRS':'ambient'}),patch.object(self.runner,'runtime_preflight',return_value='/native/snakemake') as preflight,patch.object(c,'command') as command:
            execute=routes.provider_executor(state,vars(self.runner))
            state['conda_pkgs_dirs']='changed-after-capture'
            execute(['python','weather.py'],self.root/'log')
            preflight.assert_not_called()
            execute(['snakemake','--snakefile','context.smk'],self.root/'log')
            preflight.assert_called_once()
            self.assertEqual(command.call_args.args[0][0],'/native/snakemake')
            self.assertEqual(command.call_args.kwargs['env']['CONDA_PKGS_DIRS'],str(self.root/'saved-cache'))
            self.assertEqual(os.environ['CONDA_PKGS_DIRS'],'ambient')
    def test_context_executor_honors_saved_default_cache_without_mutating_environment(self):
        with patch.dict(os.environ,{'CONDA_PKGS_DIRS':'ambient'}),patch.object(c,'command') as command:
            routes.provider_executor({'conda_pkgs_dirs':None},vars(self.runner))(['python','weather.py'],self.root/'log')
            self.assertNotIn('CONDA_PKGS_DIRS',command.call_args.kwargs['env'])
            self.assertEqual(os.environ['CONDA_PKGS_DIRS'],'ambient')
    def test_context_executor_does_not_launch_when_native_preflight_fails(self):
        with patch.object(self.runner,'runtime_preflight',side_effect=ValueError('wrong platform')),patch.object(c,'command') as command:
            with self.assertRaisesRegex(ValueError,'wrong platform'):
                routes.provider_executor({},vars(self.runner))(['snakemake','--snakefile','context.smk'],self.root/'log')
            command.assert_not_called()
    def test_native_preflight_still_runs_before_launch(self):
        self.run_directory()
        with patch.object(self.runner,'runtime_preflight',side_effect=ValueError('native platform failure')) as check,patch.object(self.runner,'build_config') as build,patch.object(self.runner.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'native platform failure'):self.runner.launch_attempt('source')
            check.assert_called_once();build.assert_not_called();spawn.assert_not_called()
    def test_resume_keeps_saved_config_logs_attempts_cache_and_process_ownership(self):
        from unittest.mock import Mock
        p=self.run_directory();self.prepared(p);config_path,_=self.runner.build_config('source');saved=config_path.read_bytes()
        (p/'snakemake.log').write_text('earlier attempt\n')
        self.runner.write_state('source',{'status':'failed','sample_count':2,'options':{'context_setup':True},'conda_pkgs_dirs':str(self.root/'pinned-cache')})
        process=Mock(pid=123);process.poll.return_value=None
        with patch.object(self.runner,'runtime_preflight',return_value='/native/snakemake'),patch.object(self.runner,'capture_attempt_provenance',side_effect=lambda attempt,*args:attempt/'provenance.json'),patch.object(self.runner.subprocess,'Popen',return_value=process) as spawn,patch.object(self.runner.threading,'Thread'),patch.object(self.runner,'build_config') as build:
            try:
                result=self.runner.launch_attempt('source',resume=True)
                build.assert_not_called();self.assertEqual(config_path.read_bytes(),saved)
                self.assertEqual((p/'snakemake.log').read_text(),'earlier attempt\n')
                state=self.runner.read_state('source');self.assertEqual(len(state['attempts']),2)
                self.assertEqual(state['active_attempt'],result['attempt_id'])
                self.assertEqual(spawn.call_args.kwargs['env']['CONDA_PKGS_DIRS'],str(self.root/'pinned-cache'))
                self.assertIn('--conda-prefix',spawn.call_args.args[0])
                with self.assertRaisesRegex(ValueError,'active launcher'):self.runner.launch_attempt('source',resume=True)
                self.assertEqual(spawn.call_count,1)
            finally:
                if spawn.called:spawn.call_args.kwargs['stdout'].close()
    def test_resume_missing_config_is_rejected(self):
        self.run_directory();self.runner.write_state('source',{'status':'failed'})
        with patch.object(self.runner,'runtime_preflight',return_value='/native/snakemake'),patch.object(self.runner.subprocess,'Popen') as spawn:
            with self.assertRaisesRegex(ValueError,'Saved execution_config'):self.runner.launch_attempt('source',resume=True)
            spawn.assert_not_called()
    def test_native_preflight_checks_conda_platform(self):
        native=str(Path(sys.executable).resolve().parent/'snakemake')
        def which(name):return native if name=='snakemake' else '/fixture/conda'
        for expected,accepted in [('linux-64',True),('osx-64',False)]:
            info=SimpleNamespace(returncode=0,stdout=json.dumps({'root_prefix':str(Path(sys.prefix).resolve()),'platform':expected}))
            with patch.object(self.runner.shutil,'which',side_effect=which),patch.object(self.runner.platform,'system',return_value='Linux'),patch.object(self.runner.platform,'machine',return_value='x86_64'),patch.object(self.runner.subprocess,'run',return_value=info):
                if accepted:self.assertEqual(self.runner.runtime_preflight(),native)
                else:
                    with self.assertRaisesRegex(ValueError,'Conda target platform'):self.runner.runtime_preflight()
    def test_status_parser_preserves_retry_and_partial_line_behavior(self):
        log=self.root/'scheduler.log'
        log.write_text('localrule sample_summary:\n    jobid: 1\nShell command: None\nFinished jobid: 1 (Rule: sample_summary)')
        records,_=self.runner.launcher_status_log(log)
        self.assertEqual(self.runner.stage_progress({'status':'running'},records)['reporting']['completed'],0)
        with log.open('a') as f:f.write('\n')
        records,_=self.runner.launcher_status_log(log)
        self.assertEqual(self.runner.stage_progress({'status':'running'},records)['reporting']['completed'],1)
        retry='Error in rule sample_summary:\n    jobid: 2\nlocalrule sample_summary:\n    jobid: 1\nShell command: None\nFinished jobid: 1 (Rule: sample_summary)\n'
        self.assertEqual(self.runner.stage_progress({'status':'running'},retry)['reporting']['status'],'failed')

if __name__=='__main__':unittest.main()
