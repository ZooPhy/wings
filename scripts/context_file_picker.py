"""User-initiated native picker and read-only folder browser for the local runner.

No file contents are returned. Browsing stays within advertised runner roots.
"""
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import threading
from urllib.parse import urlparse

KINDS={'ebird_download','ebird_package','aphis_csv'}
PAGE_SIZE=100
NATIVE_LOCK=threading.Lock()
SCRIPTS={
    'ebird_download':'POSIX path of (choose folder with prompt "Choose the extracted eBird download folder")',
    'ebird_package':'POSIX path of (choose folder with prompt "Choose previously prepared WINGS eBird data")',
    'aphis_csv':'POSIX path of (choose file with prompt "Choose an APHIS wild-bird detection CSV" of type {"csv"})',
}


def browser_origin(handler):
    """Require a same-origin loopback browser request before listing local paths."""
    origin=handler.headers.get('Origin','')
    parsed=urlparse(origin)
    host=urlparse('http://'+handler.headers.get('Host',''))
    allowed={'localhost','127.0.0.1','::1'}
    if (not origin or parsed.scheme!='http' or parsed.hostname not in allowed
            or host.hostname not in allowed or parsed.hostname!=host.hostname
            or parsed.port!=host.port or parsed.path or parsed.query or parsed.fragment
            or parsed.username or parsed.password):
        raise ValueError('Open the picker from the local WINGS runner page.')
    if handler.headers.get('Content-Type','').split(';')[0]!='application/json':
        raise ValueError('The picker requires a JSON browser request.')


def roots(api):
    home=Path.home().resolve()
    repo=Path(api['REPO_ROOT']).resolve()
    candidates=[('Downloads',home/'Downloads'),('Documents',home/'Documents'),('Home',home),
                ('WINGS project',repo),('Project parent',repo.parent),('WINGS runs',Path(api['RUNS_ROOT']))]
    candidates += [('Mounted volumes',Path('/Volumes')),('Mounted data',Path('/mnt')),('Removable media',Path('/media')),('Data',Path('/data'))]
    for raw in os.environ.get('WINGS_BROWSE_ROOTS','').split(os.pathsep):
        if raw.strip():
            path=Path(raw).expanduser().resolve();candidates.append((path.name or str(path),path))
    result=[];seen=set()
    for label,path in candidates:
        path=path.resolve()
        if path==Path(path.anchor) or path in seen or not path.is_dir() or not os.access(path,os.R_OK|os.X_OK):continue
        seen.add(path)
        result.append({'id':hashlib.sha256(str(path).encode()).hexdigest()[:20],'label':label,'path':str(path)})
    return result


def location(api,payload):
    choices=roots(api);root=next((r for r in choices if r['id']==payload.get('root_id')),None)
    if root is None:raise ValueError('Choose a folder location from the list.')
    relative=payload.get('relative','')
    if not isinstance(relative,str) or len(relative)>4096 or '\x00' in relative:raise ValueError('Invalid folder selection.')
    rel=Path(relative)
    if rel.is_absolute() or any(part=='..' or part.startswith('.') for part in rel.parts):raise ValueError('Invalid folder selection.')
    base=Path(root['path']).resolve()
    try:path=(base/rel).resolve()
    except (OSError,RuntimeError) as error:raise ValueError('Invalid folder selection.') from error
    if not path.is_relative_to(base) or any(part.startswith('.') for part in path.relative_to(base).parts):raise ValueError('That folder is outside the selected location.')
    return root,path


def kind(payload):
    value=payload.get('kind')
    if not isinstance(value,str) or value not in KINDS:raise ValueError('Unknown file picker type.')
    return value


def browse(api,payload):
    purpose=kind(payload);root,path=location(api,payload)
    if not path.is_dir():raise ValueError('Choose an existing folder.')
    offset=payload.get('offset',0)
    if type(offset) is not int or offset<0:raise ValueError('Invalid folder page.')
    base=Path(root['path']);entries=[]
    try:
        with os.scandir(path) as stream:
            for index,entry in enumerate(stream):
                if index>=20000:raise ValueError('This folder is too large to browse. Choose a narrower location.')
                if entry.name.startswith('.'):continue
                candidate=Path(entry.path)
                try:
                    resolved=candidate.resolve()
                    if not resolved.is_relative_to(base) or any(part.startswith('.') for part in resolved.relative_to(base).parts):continue
                    is_dir=candidate.is_dir()
                    if not is_dir and not (purpose=='aphis_csv' and candidate.is_file() and candidate.suffix.lower()=='.csv'):continue
                    entries.append({'name':entry.name,'relative':str(candidate.relative_to(base)),'directory':is_dir})
                except (OSError,RuntimeError):continue
    except PermissionError as error:raise ValueError('WINGS cannot open that folder. Choose another location.') from error
    entries.sort(key=lambda row:(not row['directory'],row['name'].casefold(),row['name']))
    relative=str(path.relative_to(base));relative='' if relative=='.' else relative
    parent=str(Path(relative).parent) if relative else None
    if parent=='.':parent=''
    return {'status':'BROWSE','root_id':root['id'],'path':str(path),'relative':relative,'parent':parent,
            'entries':entries[offset:offset+PAGE_SIZE],'offset':offset,'next_offset':offset+PAGE_SIZE if offset+PAGE_SIZE<len(entries) else None}


def select(api,payload):
    purpose=kind(payload);_,path=location(api,payload)
    valid=path.is_file() and path.suffix.lower()=='.csv' if purpose=='aphis_csv' else path.is_dir()
    if not valid:raise ValueError('Choose a CSV file.' if purpose=='aphis_csv' else 'Choose a folder.')
    return {'status':'SELECTED','path':str(path)}


def native_available():
    return sys.platform=='darwin' and not os.environ.get('SSH_CONNECTION') and Path('/usr/bin/osascript').is_file()


def native(api,payload):
    purpose=kind(payload)
    fallback=lambda:{'status':'BROWSE','roots':roots(api)}
    if not native_available():return fallback()
    if not NATIVE_LOCK.acquire(blocking=False):raise ValueError('A folder chooser is already open.')
    try:
        try:
            result=subprocess.run(['/usr/bin/osascript','-e',SCRIPTS[purpose]],capture_output=True,text=True,timeout=180)
        except (OSError,subprocess.TimeoutExpired):return fallback()
        if result.returncode:
            if '(-128)' in result.stderr:return {'status':'CANCELLED'}
            return fallback()
        # The native dialog is the explicit user selection; it may select any
        # accessible path, including an external volume outside browser roots.
        raw=result.stdout.rstrip('\r\n')
        if not raw:return {'status':'CANCELLED'}
        path=Path(raw).resolve()
        valid=path.is_file() and path.suffix.lower()=='.csv' if purpose=='aphis_csv' else path.is_dir()
        if not valid:raise ValueError('Choose a CSV file.' if purpose=='aphis_csv' else 'Choose an existing folder.')
        return {'status':'SELECTED','path':str(path)}
    finally:NATIVE_LOCK.release()


def handle_post(handler,api):
    route=handler.parsed().path
    if not route.startswith('/api/context/files/'):return False
    browser_origin(handler)
    payload=handler.read_json()
    if not isinstance(payload,dict):raise ValueError('Expected a JSON object.')
    action=route.rsplit('/',1)[-1]
    if action=='roots':result={'status':'BROWSE','roots':roots(api)}
    elif action=='native':result=native(api,payload)
    elif action=='browse':result=browse(api,payload)
    elif action=='select':result=select(api,payload)
    else:raise ValueError('Unknown picker action.')
    handler.json_response(result)
    return True
