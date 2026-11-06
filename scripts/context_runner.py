"""Local runner context endpoints. Preparation is separate from genomic execution."""
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
from urllib.parse import unquote, urlparse
import context_setup

JOBS = set()
UPLOADS = set()


def busy(run_id):
    return run_id in JOBS or run_id in UPLOADS


def guard_origin(handler):
    origin=handler.headers.get('Origin')
    if origin:
        parsed=urlparse(origin)
        host=urlparse('http://'+handler.headers.get('Host',''))
        if parsed.scheme!='http' or parsed.hostname not in {'localhost','127.0.0.1','::1'} or parsed.port!=host.port:
            raise ValueError('Context preparation must be requested from the local runner page')
    if handler.headers.get('Content-Type','').split(';')[0]!='application/json':
        raise ValueError('Context requests require application/json')


def status(directory,run_id):
    path=directory/'context'/'state.json'
    result=json.loads(path.read_text()) if path.exists() else {'status':'NOT_PREPARED','providers':{}}
    if result.get('status')=='PREPARING' and run_id not in JOBS:
        result={**result,'status':'INTERRUPTED','error':'Runner restarted during preparation; prepare again'}
    return result


def reserve_upload(run_id,api):
    with api['LOCK']:
        if busy(run_id) or api['read_state'](run_id).get('status')!='created':
            raise ValueError('Files cannot change while context is preparing or a run has started')
        UPLOADS.add(run_id)


def finish_upload(run_id,api):
    with api['LOCK']:UPLOADS.discard(run_id)


def handle_get(handler,api):
    match=re.fullmatch(r'/api/runs/([^/]+)/context',handler.parsed().path)
    if not match:return False
    run_id=unquote(match[1]);directory=api['run_dir'](run_id)
    api['read_state'](run_id)
    with api['LOCK']:result=status(directory,run_id)
    handler.json_response(result)
    return True


def provider_executor(run_state,api):
    """Use this run's saved package cache without mutating process-wide settings."""
    environment=os.environ.copy()
    if 'conda_pkgs_dirs' in run_state:
        if run_state['conda_pkgs_dirs']:
            environment['CONDA_PKGS_DIRS']=run_state['conda_pkgs_dirs']
        else:
            environment.pop('CONDA_PKGS_DIRS',None)
    def execute(args,log,timeout=900):
        command=list(args)
        if '--snakefile' in command:
            # Phenology creates a Conda environment, so use the launcher's actual
            # native-platform and executable checks before invoking Snakemake.
            command[0]=api['runtime_preflight']()
        context_setup.command(command,log,timeout=timeout,env=environment)
    return execute


def start(run_id,payload,api):
    directory=api['run_dir'](run_id);metadata=directory/'inputs'/'metadata.tsv';context=directory/'context'
    settings=context_setup.options(payload.get('options'))
    with api['LOCK']:
        run_state=api['read_state'](run_id)
        if busy(run_id) or run_state.get('status')!='created':raise ValueError('Context can be prepared only for an idle, unstarted run')
        if not metadata.is_file():raise ValueError('Upload metadata before preparing context')
        # Validate before starting a background task; no network calls here.
        context_setup.metadata_scope(metadata,settings['days'])
        JOBS.add(run_id)
    def progress(value):context_setup.write(context/'state.json',value)
    try:
        if payload.get('reuse_run_id'):
            source_id=str(payload['reuse_run_id'])
            if source_id==run_id:raise ValueError('Source and destination run must differ')
            with api['LOCK']:
                if busy(source_id):raise ValueError('Source context preparation is still active')
            source=api['run_dir'](source_id)/'context'
            folder,selection=context_setup.selected(source,metadata)
            # A browser source selection must match the prepared selection exactly.
            # Legacy API callers without selected_sources retain their reuse behavior.
            if 'selected_sources' in settings:
                planned=context_setup.options(selection.get('plan',{}).get('options',selection['options']))
                if planned!=settings:raise ValueError('Prepared context settings differ; prepare the selected sources again')
            # Validate external package identities as well as copied snapshot hashes.
            context_setup.configure({},source,metadata)
            target=context/'snapshots'/selection['snapshot_id'];target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():
                with tempfile.TemporaryDirectory(dir=target.parent,prefix='.copy-') as tmp:
                    stage=Path(tmp)/'snapshot';shutil.copytree(folder,stage);stage.rename(target)
            context_setup.write(context/'selection.json',json.loads((source/'selection.json').read_text()))
            context_setup.selected(context,metadata)
            progress({'status':'READY','providers':selection['providers'],'snapshot_id':selection['snapshot_id']})
            with api['LOCK']:JOBS.discard(run_id)
            return status(directory,run_id)
        progress({'status':'PREPARING','providers':{}})
        def work():
            try:
                selection=context_setup.prepare(metadata,context,settings,progress=progress,executor=provider_executor(run_state,api))
                progress({'status':selection['status'],'providers':selection['providers'],
                          'snapshot_id':selection['snapshot_id'],'blocked_sources':selection['blocked_sources']})
            except Exception as error:
                progress({'status':'FAILED','error':str(error),'providers':{}})
            finally:
                with api['LOCK']:JOBS.discard(run_id)
        threading.Thread(target=work,name='context-'+run_id,daemon=True).start()
        return {'status':'PREPARING'}
    except Exception:
        with api['LOCK']:JOBS.discard(run_id)
        raise


def handle_post(handler,api):
    if handler.parsed().path.startswith('/api/context/files/'):
        import context_file_picker
        return context_file_picker.handle_post(handler,api)
    path=handler.parsed().path
    match=re.fullmatch(r'/api/runs/([^/]+)/context',path)
    if path!='/api/context/plan' and not match:return False
    guard_origin(handler);payload=handler.read_json()
    if not isinstance(payload,dict):raise ValueError('Expected a JSON object')
    if match:
        result=start(unquote(match[1]),payload,api)
        handler.json_response(result,202 if result['status']=='PREPARING' else 200)
    else:
        text=payload.get('metadata')
        if not isinstance(text,str):raise ValueError('Metadata TSV text is required')
        with tempfile.TemporaryDirectory(prefix='wings-context-plan-') as tmp:
            metadata=Path(tmp)/'metadata.tsv';metadata.write_text(text,encoding='utf-8')
            result=context_setup.plan(metadata,payload.get('options'))
        handler.json_response(result)
    return True
