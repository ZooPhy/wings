"""Real synthetic imports: progress must not alter filtered records or validation."""
import argparse
import gzip
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import build_ebird_cache as builder
import ebird_context_package as package


class ImportProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.raw=self.root/'raw';self.raw.mkdir()
        self.metadata=self.root/'metadata.tsv'
        self.metadata.write_text('sample_id\thost\tcollection_date\tcountry\tstate\nsynthetic\tMallard\t2026-07-15\tUS\tArizona\n')
        self.sampling=self.raw/'ebd_sampling_relAug-2026.txt.gz'
        with gzip.open(self.sampling,'wt') as f:
            f.write('SAMPLING EVENT IDENTIFIER\tOBSERVATION DATE\tCOUNTRY CODE\tCOUNTRY\tSTATE CODE\tSTATE\tGROUP IDENTIFIER\tALL SPECIES REPORTED\n'
                    'S1\t2026-07-15\tUS\tUnited States\tUS-AZ\tArizona\t\t1\n'
                    'S2\t2026-07-16\tUS\tUnited States\tUS-AZ\tArizona\t\t1\n'
                    'S3\t2020-07-16\tUS\tUnited States\tUS-AZ\tArizona\t\t1\n')
        self.observations=self.raw/'ebd_relAug-2026.txt.gz'
        with gzip.open(self.observations,'wt') as f:
            f.write('SAMPLING EVENT IDENTIFIER\tCOMMON NAME\tSCIENTIFIC NAME\nS1\tMallard\tAnas platyrhynchos\nS2\tAmerican Coot\tFulica americana\nS3\tSynthetic third species\tSynthetic name\n')
        for name in package.DOCUMENTS:(self.raw/name).write_text('Synthetic test attribution document.\n')

    def args(self,name,progress=None):
        result=argparse.Namespace(command='build',output=self.root/name,documents=self.raw,
            observations=self.observations,sampling=self.sampling,metadata=self.metadata,days=30,
            release='Aug-2026',taxonomy_version='synthetic',acquired_at='unknown')
        if progress is not None:result.progress=progress
        return result

    def test_full_import_relays_progress_and_preserves_results(self):
        values=[];package.prepare(self.args('with-progress',values.append));package.prepare(self.args('without-progress'))
        first=self.root/'with-progress';second=self.root/'without-progress'
        self.assertEqual(gzip.decompress((first/'observations.txt.gz').read_bytes()),gzip.decompress((second/'observations.txt.gz').read_bytes()))
        for name in ('sampling.txt','species_catalog.tsv'):self.assertEqual((first/name).read_bytes(),(second/name).read_bytes())
        manifest=package.verify(first,self.metadata)
        self.assertEqual(manifest['counts'],{'observation_rows':2,'sampling_rows':2,'species':3})
        self.assertEqual(manifest['source_hashes'],package.verify(second,self.metadata)['source_hashes'])
        self.assertTrue(any(value['stage']=='fingerprinting' and value['bytes_processed']==value['total_bytes'] for value in values))
        self.assertTrue(any(value['stage']=='observations' and value['rows_processed']==3 and value['rows_retained']==2 for value in values))
        self.assertTrue(any(value['stage']=='source-verification' for value in values))
        self.assertEqual(values[-1]['stage'],'complete')
        self.assertEqual(set(p.name for p in first.iterdir()),set(package.FILES)|{package.MANIFEST})

    def test_sampling_counts_are_real_and_reported_when_scan_finishes(self):
        values=[];events=set();samples=builder.read_samples(self.metadata,{},30,None)
        count=builder.scan_sampling(self.sampling,samples,self.root/'sampling.txt',events,lambda **value:values.append(value))
        self.assertEqual(count,2);self.assertEqual(events,{'S1','S2'})
        self.assertEqual(values[-1]['rows_processed'],3);self.assertEqual(values[-1]['rows_retained'],2)

    def test_fingerprinting_counts_do_not_change_hash(self):
        values=[];result=package.sha256(self.observations,lambda done,total:values.append((done,total)))
        self.assertEqual(result,hashlib.sha256(self.observations.read_bytes()).hexdigest())
        self.assertEqual(values[-1],(self.observations.stat().st_size,)*2)

    def test_child_failure_still_propagates(self):
        with self.assertRaises(subprocess.CalledProcessError):
            package.run_builder_with_progress([sys.executable,'-c','import sys;sys.exit(4)'],self.root/'missing.json',lambda *_:None)


if __name__=='__main__':unittest.main()
