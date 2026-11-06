#!/usr/bin/env python3
"""Run isolated production eBird rules and the Explorer builder on synthetic data.

--self-check runs configuration checks without Snakemake.
Default execution requires Snakemake installed; no Conda or downloads are needed.
"""
import argparse
import json
from pathlib import Path
import runpy
import shutil
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]


def pieces(root):
    text=(root/'Snakefile').read_text()
    config=text[text.index('EBIRD_DECLARED ='):text.index('\nVADR_IMAGE =')]
    rules=text[text.index('# WINGS_EBIRD_PACKAGE_STATUS_RULE_V1'):text.index('\nrule ebirdst_phenology:')]
    explorer=text[text.index('rule surveillance_explorer_data:'):text.index('# WINGS_GENOMIC_ECOLOGICAL_CONCORDANCE_RULE_BEGIN')]
    helper=text[text.index('def as_bool('):text.index('\ndef config_path(')]
    return helper,config,rules,explorer


def preamble(settings):
    return '''import json
import shlex
import sys
from pathlib import Path
config = json.loads(Path("settings.json").read_text())
RESULTS = "results"
METADATA_FILE = "metadata.tsv"
def frozen_reexecution_input(label):
    return config.get("frozen", {}).get(label, "")
FROZEN_EBIRD_CONTEXT = frozen_reexecution_input("ebird_context")
FROZEN_EBIRD_TERMS = frozen_reexecution_input("ebird_terms")
FROZEN_EBIRD_CITATION = frozen_reexecution_input("ebird_citation")
'''


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo',type=Path,default=ROOT)
    p.add_argument('--self-check',action='store_true')
    args=p.parse_args();repo=args.repo.resolve()
    helper,config_code,rules,explorer=pieces(repo)
    fixture=runpy.run_path(str(repo/'tests/test_ebird_context_package.py'))
    work=Path(tempfile.mkdtemp(prefix='wings-ebird-integration-')).resolve()
    print('Test directory:',work,flush=True)
    source=work/'source';source.mkdir()
    metadata,raw,package=fixture['build'](source)
    shutil.rmtree(raw)
    moved=work/'portable context';package.rename(moved)
    harness=work/'workflow';(harness/'scripts').mkdir(parents=True)
    (harness/'results/metadata').mkdir(parents=True)
    shutil.copyfile(metadata,harness/'metadata.tsv')
    shutil.copyfile(metadata,harness/'results/metadata/validated_metadata.tsv')
    for name in ('ebird_context_package.py','build_ebird_cache.py','filter_ebird_for_wings.py',
                 'build_surveillance_explorer.py','public_reference_context.py','build_ecological_context.py'):
        shutil.copyfile(repo/'scripts'/name,harness/'scripts'/name)
    (harness/'resources').mkdir()
    shutil.copyfile(repo/'resources/ebird_host_codes_2025.tsv',harness/'resources/ebird_host_codes_2025.tsv')
    settings={'ebird':{'mode':'reuse','context_dir':str(moved),'required':True,'days':30,'host_map_file':'',
                       'fixture_literal':'{segment}/{sample}'}}
    def evaluate(data):
        ns={'config':data,'Path':Path,'sys':sys,'RESULTS':str(harness/'results'),'METADATA_FILE':str(harness/'metadata.tsv'),
            'shlex':shlex,'workflow':SimpleNamespace(basedir=str(harness)),'FROZEN_EBIRD_CONTEXT':data.get('frozen',{}).get('ebird_context',''),
            'frozen_reexecution_input':lambda key:data.get('frozen',{}).get(key,'')}
        exec(helper+'\n'+config_code,ns)
        return ns
    ns=evaluate(settings)
    assert ns['EBIRD_ENABLED'] and ns['EBIRD_PACKAGE_REUSE']
    assert ns['EBIRD_SAMPLING']=='' and ns['EBIRD_RELEASE_DIR']==moved
    optional={'ebird':{**settings['ebird'],'context_dir':str(work/'missing-{segment}'),'required':False}}
    ns=evaluate(optional);assert not ns['EBIRD_ENABLED'] and ns['EBIRD_DECLARED']
    assert ns['EBIRD_PACKAGE_STATUS']['status']=='UNAVAILABLE'
    ns=evaluate({'ebird':{'enabled':False}});assert ns['EBIRD_PACKAGE_MODE']=='legacy' and not ns['EBIRD_ENABLED']
    legacy=evaluate({'ebird':{'enabled':True,'cache_dir':str(work/'cache'),'sampling_file':str(work/'old/source.txt'),
                           'release_dir':str(work/'release'),'host_map_file':''}})
    assert legacy['EBIRD_SAMPLING']==str(work/'old/source.txt') and not legacy['EBIRD_PACKAGE_REUSE']
    frozen=evaluate({'ebird':settings['ebird'],'frozen':{'ebird_status':str(work/'frozen.json')}})
    assert frozen['EBIRD_PACKAGE_MODE']=='frozen' and not frozen['EBIRD_ENABLED']
    assert frozen['EBIRD_STATUS_INPUT']==[str(work/'frozen.json')]
    assert rules.index('if not EBIRD_PACKAGE_REUSE:') < rules.index('rule ebird_sampling_cache:')
    assert rules.index('rule ebird_summary:') > rules.index('rule ebird_sampling_cache:')
    print('PASS: production configuration handles reuse, optional missing, legacy, and frozen modes.',flush=True)
    if args.self_check:
        shutil.rmtree(work)
        return
    executable=shutil.which('snakemake')
    if not executable:
        raise RuntimeError('Snakemake is required for integration execution; self-check passed. Install/use your Snakemake environment.')
    # Only genomic inputs are stubbed; the eBird config, rules, and Explorer rule
    # are extracted unchanged from the installed production Snakefile.
    constants='''REFERENCE_ENABLED = ECOLOGY_ENABLED = PHENOLOGY_ENABLED = SURVEILLANCE_EFFORT_ENABLED = OUTBREAK_ENABLED = RUN_GENOFLU = False
FROZEN_PHENOLOGY = ""
CONTEXT_SELECTION = ""
SAMPLES = []
def surveillance_tree_inputs(wildcards):
    return []
rule all:
    input: "results/run_summary/surveillance_explorer.json"
'''
    # The production Explorer lists two loader files even when they are unused.
    (harness/'Snakefile').write_text(preamble(settings)+helper+'\n'+config_code+'\n'+constants+'\n'+rules+'\n'+explorer)
    runs=[]
    def run(label,data,success=True):
        (harness/'settings.json').write_text(json.dumps(data))
        proc=subprocess.run([executable,'--cores','1','--nolock'],cwd=harness,capture_output=True,text=True)
        (work/(label+'.log')).write_text(proc.stdout+'\n'+proc.stderr)
        if (proc.returncode==0)!=success:
            raise RuntimeError(label+' failed; inspect '+str(work/(label+'.log')))
        runs.append(label)
        if success:
            return json.loads((harness/'results/run_summary/surveillance_explorer.json').read_text())
        return proc.stdout+proc.stderr
    result=run('portable-reuse',settings)
    assert result['ebird_contexts'][0]['reporting_frequency']==0.5
    assert result['ebird_status']['status']=='READY'
    stamp=(harness/'results/run_summary/ebird/context_status.json').stat().st_mtime_ns
    run('unchanged-reuse',settings)
    assert (harness/'results/run_summary/ebird/context_status.json').stat().st_mtime_ns==stamp
    relocated=work/'relocated again';moved.rename(relocated)
    settings['ebird']['context_dir']=str(relocated)
    result=run('relocated-reuse',settings);assert result['ebird_status']['status']=='READY'
    frozen_dir=work/'frozen';frozen_dir.mkdir()
    frozen_paths={}
    for label,name in [('ebird_context','ebird_samples.tsv'),('ebird_terms','terms_of_use.txt'),
                       ('ebird_citation','recommended_citation.txt'),('ebird_status','context_status.json')]:
        shutil.copyfile(harness/'results/run_summary/ebird'/name,frozen_dir/name)
        frozen_paths[label]=str(frozen_dir/name)
    result=run('frozen-replay-with-missing-package',{'ebird':{**optional['ebird'],'required':True},'frozen':frozen_paths})
    assert result['ebird_status']['status']=='READY' and result['ebird_contexts'][0]['reporting_frequency']==0.5
    result=run('optional-missing-with-stale-results',optional)
    assert result['ebird_contexts']==[] and result['ebird_status']['status']=='UNAVAILABLE'
    assert any('eBird context unavailable' in item for item in result['warnings'])
    required={'ebird':{**optional['ebird'],'required':True}}
    result=run('required-missing',required,False);assert 'Required eBird context' in result
    result=run('optional-out-of-scope',{'ebird':{**settings['ebird'],'required':False,'days':31}})
    assert result['ebird_status']['code']=='OUT_OF_SCOPE' and not result['ebird_contexts']
    result=run('legacy-disabled',{'ebird':{'enabled':False}})
    assert result['ebird_status'] is None and not result['ebird_contexts']
    (work/'test_summary.json').write_text(json.dumps({'passed':runs,'synthetic':True,'genomic_analysis_executed':False},indent=2)+'\n')
    print('PASS: isolated Snakemake eBird package integration ('+str(len(runs))+' scenarios).')
    print('Summary:',work/'test_summary.json')


if __name__=='__main__':
    try:main()
    except (OSError,ValueError,AssertionError,RuntimeError) as error:
        print('ERROR:',error,file=sys.stderr);sys.exit(1)
