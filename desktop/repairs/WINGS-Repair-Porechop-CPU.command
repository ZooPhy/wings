#!/bin/bash
# Rebuild and replace the diagnosed incompatible Porechop counter only after checks.
# Requires idle WINGS service; no host Python/Conda or user reads required.
set -euo pipefail
umask 077
docker_bin=""
for candidate in /Applications/Docker.app/Contents/Resources/bin/docker "$HOME/Applications/Docker.app/Contents/Resources/bin/docker" "$HOME/.docker/bin/docker" /usr/local/bin/docker; do
    if [[ -x "$candidate" ]]; then docker_bin="$candidate"; break; fi
done
if [[ -z "$docker_bin" ]]; then docker_bin="$(command -v docker || true)"; fi
[[ -n "$docker_bin" ]] || { echo 'Docker Desktop was not found. Start it and retry.'; exit 1; }
docker_cmd=("$docker_bin")
if [[ -n "${DOCKER_HOST:-}" ]]; then
    [[ "$DOCKER_HOST" == unix://* ]] || { echo 'Use the local Docker Desktop engine for this check.'; exit 1; }
    docker_cmd+=(--host "$DOCKER_HOST")
elif "$docker_bin" context inspect desktop-linux >/dev/null 2>&1; then
    docker_cmd+=(--context desktop-linux)
fi
endpoint="$("${docker_cmd[@]}" context inspect --format '{{.Endpoints.docker.Host}}')"
if [[ -z "${DOCKER_HOST:-}" && "$endpoint" != unix://* ]]; then
    echo 'The selected Docker engine is remote. Select Docker Desktop and retry.'; exit 1
fi
containers="$("${docker_cmd[@]}" ps --filter label=org.wings.desktop.workspace --format '{{.ID}}')"
[[ -n "$containers" ]] || { echo 'Open WINGS and leave its service running, then retry. Do not start a job.'; exit 1; }
count="$(printf '%s\n' "$containers" | wc -l | tr -d '[:space:]')"
[[ "$count" == 1 ]] || { echo 'More than one WINGS service is running. Leave only the affected service running and retry.'; exit 1; }
printf 'WINGS counter repair v2: baseline CPU build and verified help-text fix. Keep this terminal open.\n'
"${docker_cmd[@]}" exec -i "$containers" /opt/conda/bin/python - <<'PYTHON_REPAIR'
"""Build and validate one baseline x86-64 counter inside the WINGS controller."""
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import resource
import shutil
import signal
import stat
import subprocess
import tarfile
import tempfile
import time
import urllib.request

COMMIT = '0bc9f17f31d4ec1dcbab4796871cc09324cc143b'
ARCHIVE_SHA256 = '10a179639ff4db0899ea43843ede4c4e48abd7e1b5edc16e84e9a573aa18041c'
ORIGINAL_SHA256 = '38fd3f1a12bf190e0549c8daac273efe8a7d2948ae0ce66022b8504f4804c3c8'
URL = 'https://github.com/bonsai-team/Porechop_ABI/archive/' + COMMIT + '.tar.gz'

def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()

def write_json(path, value):
    tmp = path.with_name(path.name + '.tmp')
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    os.replace(tmp, path)

def check_idle():
    for process in Path('/proc').iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid(): continue
        try: args = (process/'cmdline').read_bytes().split(b'\0')
        except (FileNotFoundError, ProcessLookupError, PermissionError): continue
        names = {Path(a.decode(errors='replace')).name for a in args[:3] if a}
        if names.intersection({'snakemake', 'porechop_abi', 'approx_counter',
                              'run_porechop_abi.py', 'run_porechop_accelerated.py'}):
            raise RuntimeError('An analysis is still active. Finish or stop jobs in the browser, then retry.')

def capture(command, log, timeout=30):
    with log.open('wb') as handle:
        process = subprocess.Popen(command, stdout=handle, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        started = time.monotonic()
        while True:
            try:
                code = process.wait(timeout=min(10, timeout))
                break
            except subprocess.TimeoutExpired:
                elapsed = int(time.monotonic()-started)
                if elapsed >= timeout:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    raise RuntimeError('Timed out; see ' + str(log))
                print('  Still working (' + str(elapsed) + ' seconds)…', flush=True)
            except BaseException:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
    return code

def download(path):
    request = urllib.request.Request(URL, headers={'User-Agent':'WINGS-counter-repair/1'})
    with urllib.request.urlopen(request, timeout=60) as src, path.open('xb') as dst:
        total=0
        while True:
            chunk=src.read(1024*1024)
            if not chunk:break
            total+=len(chunk)
            if total > 100*1024*1024: raise RuntimeError('Source archive exceeds size limit')
            dst.write(chunk)
    if sha(path) != ARCHIVE_SHA256:
        raise RuntimeError('Source archive checksum mismatch; nothing installed')

def extract(archive, target):
    with tarfile.open(archive, 'r:gz') as t:
        members=t.getmembers()
        if sum(m.size for m in members) > 512*1024*1024 or len(members)>30000:
            raise RuntimeError('Unexpected source archive size')
        if any(m.issym() or m.islnk() or not(m.isfile() or m.isdir()) for m in members):
            raise RuntimeError('Unexpected source archive member type')
        t.extractall(target, members=members, filter='data')
    roots=list(target.iterdir())
    if len(roots)!=1 or not roots[0].is_dir():raise RuntimeError('Unexpected source layout')
    return roots[0]

def compiler_command(source, candidate, zlib, headers=None):
    return ['/usr/bin/g++', '-O2', '-DNDEBUG', '-std=c++17', '-DSEQAN_HAS_ZLIB=1',
            '-march=x86-64', '-mtune=generic', '-mno-avx', '-mno-avx2',
            '-mno-avx512f', '-mno-fma', '-fopenmp',
            '-I', str(source/'porechop_abi/include'),
            *(['-I', str(headers)] if headers else []),
            str(source/'porechop_abi/ab_initio_src/approx_counter.cpp'),
            str(zlib), '-lrt',
            '-Wl,--disable-new-dtags,-rpath,/usr/lib/x86_64-linux-gnu:/lib/x86_64-linux-gnu',
            '-o', str(candidate)]

def repair_help_text(source):
    path=source/'porechop_abi/ab_initio_src/approx_counter.cpp'
    before=path.read_bytes()
    old=rb'/!\\ If this option is set'
    if before.count(old)!=1:
        raise RuntimeError('Expected help-text defect not found exactly once; nothing installed')
    after=before.replace(old,b'Warning: If this option is set')
    path.write_bytes(after)
    return {'description':'Replace trailing backslash in skip_end help warning; counting code unchanged',
            'path':'porechop_abi/ab_initio_src/approx_counter.cpp',
            'original_sha256':hashlib.sha256(before).hexdigest(),
            'patched_sha256':hashlib.sha256(after).hexdigest()}

def synthetic_reads(path):
    rng=random.Random(19073)
    start='AATGTACTTCGTTCAGTTACGTATTGCT'
    end='GCAATACGTAACTGAACGAAGT'
    sequences=[start+''.join(rng.choices('ACGT', k=250))+end for _ in range(256)]
    with gzip.open(path, 'wt') as f:
        for i in range(50000):
            seq=sequences[i%len(sequences)]
            f.write('@synthetic_'+str(i)+'\n'+seq+'\n+\n'+'I'*len(seq)+'\n')

def validate(candidate, config, scratch, record_dir):
    print('Checking the rebuilt counter starts…', flush=True)
    help_log=record_dir/'candidate-help.log'
    help_code=capture([str(candidate),'--help'], help_log)
    text=help_log.read_text(errors='replace').lower()
    if help_code != 0 or not any(word in text for word in ('usage','help','options')):
        raise RuntimeError('Rebuilt counter failed the help check (exit '+str(help_code)+'); see '+str(help_log))
    print('Testing compressed synthetic reads (no user data)…', flush=True)
    reads=scratch/'synthetic.fastq.gz';synthetic_reads(reads)
    output=scratch/'smoke-counts'
    command=[str(candidate),str(reads),'-v','1','--config',str(config),
             '-o',str(output),'-nt','1','-mr','1']
    code=capture(command, record_dir/'synthetic-count.log', timeout=180)
    files=[p for p in scratch.glob('smoke-counts*') if p.is_file() and p.stat().st_size]
    if code != 0 or not files:
        raise RuntimeError('Synthetic count test failed (exit '+str(code)+'); original counter retained. See '+str(record_dir/'synthetic-count.log'))
    return {'help_exit':help_code, 'synthetic_exit':code,
            'synthetic_input_sha256':sha(reads),
            'synthetic_outputs':{p.name:sha(p) for p in files},'synthetic_command':command}

def install(candidate, target, record_dir, manifest):
    check_idle()
    if sha(target) != ORIGINAL_SHA256:
        raise RuntimeError('Installed counter changed during preparation; no replacement performed')
    backup=record_dir/'approx_counter.original'
    shutil.copy2(target, backup)
    if sha(backup)!=ORIGINAL_SHA256:raise RuntimeError('Backup verification failed')
    manifest.update(original_counter=str(target),backup=str(backup),
                    original_sha256=ORIGINAL_SHA256,candidate_sha256=sha(candidate),status='validated')
    write_json(record_dir/'repair.json',manifest)
    fd, name=tempfile.mkstemp(prefix='.wings-counter-', dir=target.parent)
    os.close(fd);stage=Path(name);replaced=False
    try:
        shutil.copyfile(candidate,stage)
        stage.chmod(stat.S_IMODE(target.stat().st_mode))
        if sha(stage)!=sha(candidate):raise RuntimeError('Staged binary verification failed')
        os.replace(stage,target);replaced=True
        code=capture([str(target),'--help'], record_dir/'installed-help.log')
        if code != 0:raise RuntimeError('Installed counter failed its startup check')
        manifest.update(status='installed',installed_sha256=sha(target))
        write_json(record_dir/'repair.json',manifest)
    except BaseException:
        if replaced:
            shutil.copyfile(backup,stage);stage.chmod(stat.S_IMODE(backup.stat().st_mode))
            os.replace(stage,target)
            manifest['status']='rolled_back'
            write_json(record_dir/'repair.json',manifest)
        raise
    finally:
        if stage.exists():stage.unlink()

def main():
    resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    if platform.system()!='Linux' or platform.machine()!='x86_64':
        raise RuntimeError('Run this repair inside the WINGS Linux AMD64 controller')
    check_idle()
    workspace=Path.cwd().parents[2]
    envroot=workspace/'cache/snakemake/conda-platforms/linux-x86_64'
    if not envroot.is_dir():raise RuntimeError('WINGS environment cache not found')
    targets={}
    for metadata in envroot.glob('*/conda-meta/porechop_abi-*.json'):
        package=json.loads(metadata.read_text())
        if package.get('version')!='0.5.1':continue
        for p in metadata.parent.parent.glob('lib/python*/site-packages/porechop_abi/approx_counter'):
            p=p.resolve()
            if not p.is_relative_to(metadata.parent.parent.resolve()):
                raise RuntimeError('Counter resolves outside its environment; no replacement performed')
            if p.is_file() and sha(p)==ORIGINAL_SHA256:targets[p]=(package,metadata.parent.parent)
    if len(targets)!=1:
        raise RuntimeError('Expected exactly one installed counter matching the diagnostic; found '+str(len(targets))+'. Nothing changed.')
    target=next(iter(targets));package,env_prefix=targets[target]
    if not Path('/usr/bin/g++').is_file():raise RuntimeError('Controller compiler unavailable')
    zlib=next((p for p in (Path('/usr/lib/x86_64-linux-gnu/libz.so.1'),Path('/lib/x86_64-linux-gnu/libz.so.1')) if p.is_file()),None)
    if zlib is None:raise RuntimeError('System zlib unavailable; nothing installed')
    cache=workspace/'cache/porechop-counter-repairs';cache.mkdir(parents=True,exist_ok=True)
    lock=cache/'.repair-lock'
    try:lock.mkdir()
    except FileExistsError:raise RuntimeError('A repair lock exists. Confirm no repair is active before removing '+str(lock))
    try:
        record_dir=Path(tempfile.mkdtemp(prefix='baseline-',dir=cache))
        print('Repair logs and backup: '+str(record_dir),flush=True)
        if capture([str(target),'--help'],record_dir/'original-help.log') != -signal.SIGILL:
            raise RuntimeError('Counter no longer reproduces SIGILL; no replacement performed')
        with tempfile.TemporaryDirectory(prefix='wings-counter-build-',dir='/tmp') as temp:
            scratch=Path(temp)
            print('Downloading and verifying the pinned Porechop_ABI source…',flush=True)
            archive=scratch/'source.tar.gz'
            cached=next((p for p in sorted(cache.glob('baseline-*/source.tar.gz'))
                         if p.is_file() and sha(p)==ARCHIVE_SHA256),None)
            if cached:
                shutil.copyfile(cached,archive)
                print('Using the checksum-verified source from the earlier repair.',flush=True)
            else:download(archive)
            source=extract(archive,scratch/'source')
            if sha(source/'porechop_abi/porechop_abi.py')!=sha(target.parent/'porechop_abi.py'):
                raise RuntimeError('Installed Python source differs from the pinned source; no replacement performed')
            help_patch=repair_help_text(source)
            candidate=scratch/'approx_counter'
            # Copy just zlib's public headers; do not mix Conda compiler headers
            # or runtime libraries into the system GCC build.
            header_dirs=[Path('/usr/include'),env_prefix/'include',Path('/opt/conda/include')]
            header_source=next((p for p in header_dirs if (p/'zlib.h').is_file() and (p/'zconf.h').is_file()),None)
            if header_source is None:
                raise RuntimeError('zlib development headers unavailable; original counter retained')
            headers=scratch/'zlib-headers';headers.mkdir()
            for name in ('zlib.h','zconf.h'):shutil.copyfile(header_source/name,headers/name)
            command=compiler_command(source,candidate,zlib,headers)
            manifest={'schema':'wings.counter_baseline_repair.v2',
                      'help_text_patch':help_patch,
                      'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      'source_commit':COMMIT,'source_archive_sha256':ARCHIVE_SHA256,
                      'compile_command':command,'compiler':subprocess.check_output(['/usr/bin/g++','--version'],text=True),
                      'conda_package':{k:package.get(k) for k in ('name','version','build','build_number','subdir')}}
            write_json(record_dir/'repair.json',dict(manifest,status='building'))
            print('Compiling a baseline x86-64 counter; this can take several minutes…',flush=True)
            if capture(command,record_dir/'build.log',timeout=600)!=0:
                raise RuntimeError('Compilation failed; original counter retained. See '+str(record_dir/'build.log'))
            shutil.copyfile(archive,record_dir/'source.tar.gz')
            shutil.copyfile(source/'LICENSE',record_dir/'UPSTREAM-LICENSE.txt')
            shutil.copyfile(source/'porechop_abi/ab_initio_src/approx_counter.cpp',record_dir/'approx_counter.patched.cpp')
            shutil.copy2(candidate,record_dir/'approx_counter.candidate')
            try:
                manifest['checks']=validate(candidate,target.parent/'ab_initio.config',scratch,record_dir)
            except Exception as error:
                write_json(record_dir/'repair.json',dict(manifest,status='validation_failed',error=str(error)))
                raise
            install(candidate,target,record_dir,manifest)
        print('PASS: baseline counter installed after startup and synthetic counting checks.',flush=True)
        print('Original binary and build provenance retained at '+str(record_dir),flush=True)
        print('Resume the failed run in the existing WINGS browser. No input or job settings changed.',flush=True)
    finally:lock.rmdir()

if __name__=='__main__':
    try:main()
    except Exception as error:
        raise SystemExit('REPAIR STOPPED: '+str(error))
PYTHON_REPAIR
