"""Parse both modes and resolve the enabled phylodynamics DAG without running tools."""
import json
from pathlib import Path
import subprocess
import tempfile

repo=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='wings-dag-check-') as tmp:
    root=Path(tmp)
    config={'reads_dir':str(root/'reads'),'results_dir':str(root/'results'),
            'metadata_file':str(root/'metadata.tsv'),'run_summary':False,
            'run_nanoplot':False,'run_vadr':False,'run_genoflu':False}
    (root/'reads').mkdir()
    (root/'metadata.tsv').write_text('sample_id\tcollection_date\thost\tcountry\tstate\n')
    config_path=root/'config.yaml'
    for enabled in (False,True):
        if enabled:
            config['public_references']=dict(enabled=False)
            config['phylodynamics']=dict(enabled=True,strategies=['balanced'],replicates=1, references=dict(source='ncbi',subtypes=['H5']))
            (root/'public.fasta').write_text('>reference\nACGT\n')
            (root/'public.tsv').write_text('accession\nreference\n')
        config_path.write_text(json.dumps(config))
        command=['snakemake','--snakefile',str(repo/'Snakefile'),'--directory',str(root),
                 '--configfile',str(config_path),'--cores','1']
        result=subprocess.run(command+['--list-rules'],check=True,text=True,capture_output=True)
        assert ('phylodynamic_reference_selection' in result.stdout)==enabled,result.stdout
        if enabled:
            # Source code inputs are repository-relative; symlink in the isolated work directory.
            for folder in ('scripts','envs','rules','assets'):
                if (repo/folder).exists() and not (root/folder).exists():(root/folder).symlink_to(repo/folder,target_is_directory=True)
            result=subprocess.run(command+['--dry-run',str(root/'results/run_summary/phylodynamics/summary.json')],
                                  text=True,capture_output=True)
            if result.returncode:
                raise RuntimeError(result.stdout+'\n'+result.stderr)
            assert 'phylodynamic_replicate' in result.stdout,result.stdout
            assert 'phylodynamic_reference_snapshot' in result.stdout,result.stdout
            assert 'assign_public_reference_genotypes' not in result.stdout,result.stdout
print('PASS: disabled and enabled workflow parsing; enabled inference DAG resolved.')
