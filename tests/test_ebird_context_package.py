"""Offline package and production-report tests. No real eBird records or credentials."""
import argparse
import contextlib
import csv
import importlib.util
import io
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('context_package', ROOT / 'scripts/ebird_context_package.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def fixture(root):
    raw = root / 'raw'; raw.mkdir()
    metadata = root / 'metadata.tsv'
    metadata.write_text('sample_id\thost\tcollection_date\tcountry\tstate\tlatitude\tlongitude\n'
                        'bird1\tMallard\t2026-07-15\tUS\tArizona\t33.4\t-112.1\n')
    sed = raw / 'ebd_sampling_relAug-2026.txt'
    sed.write_text('SAMPLING EVENT IDENTIFIER\tOBSERVATION DATE\tCOUNTRY CODE\tCOUNTRY\tSTATE CODE\tSTATE\tGROUP IDENTIFIER\tALL SPECIES REPORTED\tLATITUDE\tLONGITUDE\n'
                   'S1\t2026-07-15\tUS\tUnited States\tUS-AZ\tArizona\t\t1\t33.4\t-112.1\n'
                   'S2\t2026-07-16\tUS\tUnited States\tUS-AZ\tArizona\t\t1\t33.4\t-112.1\n')
    obs = raw / 'ebd_relAug-2026.txt'
    obs.write_text('SAMPLING EVENT IDENTIFIER\tCOMMON NAME\tSCIENTIFIC NAME\n'
                   'S1\tMallard\tAnas platyrhynchos\nS2\tAmerican Coot\tFulica americana\n')
    for name in mod.DOCUMENTS:
        (raw / name).write_text('SYNTHETIC TEST DOCUMENT. Not an eBird license or citation.\n')
    return metadata, raw, obs, sed


def build(root):
    metadata, raw, obs, sed = fixture(root)
    output = root / 'package'
    args = argparse.Namespace(command='build', output=output, documents=raw, observations=obs,
                              sampling=sed, metadata=metadata, days=30, release='Aug-2026',
                              taxonomy_version='synthetic', acquired_at='2026-09-01')
    with contextlib.redirect_stdout(io.StringIO()):
        mod.prepare(args)
    return metadata, raw, output


def config(package, **overrides):
    return {'mode':'reuse', 'context_dir':str(package), 'required':False, 'days':30, **overrides}


class ContextPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.seed_temp = tempfile.TemporaryDirectory(prefix='wings-context-seed-')
        cls.seed = Path(cls.seed_temp.name)
        build(cls.seed)

    @classmethod
    def tearDownClass(cls):
        cls.seed_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wings-context-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('raw', 'package'):
            shutil.copytree(self.seed / name, self.root / name)
        shutil.copyfile(self.seed / 'metadata.tsv', self.root / 'metadata.tsv')
        self.meta = self.root / 'metadata.tsv'
        self.raw = self.root / 'raw'
        self.package = self.root / 'package'

    def test_complete_package_records_fingerprints_and_scope(self):
        m = mod.verify(self.package, self.meta)
        self.assertEqual(m['counts'], {'observation_rows':2,'sampling_rows':2,'species':2})
        self.assertEqual(set(m['files']), set(mod.FILES))
        self.assertEqual(m['release'], 'Aug-2026')
        self.assertTrue(m['source_hashes']['observations']['sha256'])
        self.assertEqual(m['taxonomic_scope'], 'all-species-source')

    def test_move_and_remove_sources_then_production_summary_and_report(self):
        shutil.rmtree(self.raw)
        moved = self.root / 'moved context'; self.package.rename(moved)
        status = mod.resolve_context(config(moved, required=True), self.meta)
        self.assertEqual(status['status'], 'READY')
        output = self.root / 'summary'
        cmd = [sys.executable, str(ROOT/'scripts/filter_ebird_for_wings.py'), '--metadata', str(self.meta),
               '--observations', str(moved/'observations.txt.gz'), '--sampling', str(moved/'sampling.txt'),
               '--species-catalog', str(moved/'species_catalog.tsv'), '--release', 'Aug-2026', '--days', '30', '--output-dir', str(output)]
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        with (output/'ebird_samples.tsv').open() as f:
            row = next(csv.DictReader(f, delimiter='\t'))
        self.assertEqual(row['complete_checklists'], '2')
        self.assertEqual(row['reporting_checklists'], '1')
        self.assertEqual(row['reporting_frequency'], '0.500000')
        record = self.root/'status.json'; mod.write_json(record,status)
        api=runpy.run_path(str(ROOT/'scripts/build_surveillance_explorer.py'))
        result=api['build_payload'](self.meta,[],[],ebird_samples=output/'ebird_samples.tsv',
              ebird_terms=moved/'terms_of_use.txt',ebird_citation=moved/'recommended_citation.txt',ebird_status=record)
        self.assertEqual(result['ebird_contexts'][0]['reporting_frequency'],0.5)
        self.assertEqual(result['ebird_status']['package_id'],status['package_id'])
        self.assertEqual(len(result['samples']),1)

    def test_optional_missing_documents_is_unavailable(self):
        (self.package/'terms_of_use.txt').unlink()
        status=mod.resolve_context(config(self.package),self.meta)
        self.assertEqual(status['status'],'UNAVAILABLE')
        self.assertIn('terms_of_use',status['reason'])

    def test_required_missing_documents_fails_preflight(self):
        (self.package/'terms_of_use.txt').unlink()
        with self.assertRaisesRegex(ValueError,'Required eBird context'):
            mod.resolve_context(config(self.package,required=True),self.meta)

    def test_unavailable_record_suppresses_stale_summary(self):
        status=self.root/'status.json'
        mod.write_json(status,{'schema':'wings.ebird-status.v1','status':'UNAVAILABLE','reason':'Missing release documents'})
        api=runpy.run_path(str(ROOT/'scripts/build_surveillance_explorer.py'))
        payload=api['build_payload'](self.meta,[],[],ebird_samples=self.package/'not-a-summary.tsv',ebird_status=status)
        self.assertEqual(payload['ebird_contexts'],[])
        self.assertIsNone(payload['ebird_attribution'])
        self.assertTrue(any('Missing release documents' in w for w in payload['warnings']))

    def test_corruption_is_not_used(self):
        path=self.package/'sampling.txt';path.write_bytes(path.read_bytes()+b'changed')
        self.assertEqual(mod.resolve_context(config(self.package),self.meta)['code'],'INTEGRITY')

    def test_manifest_tampering_is_detected(self):
        path=self.package/mod.MANIFEST;m=json.loads(path.read_text());m['release']='Sep-2026';mod.write_json(path,m)
        self.assertEqual(mod.resolve_context(config(self.package),self.meta)['code'],'INTEGRITY')

    def test_release_mismatch_is_rejected(self):
        self.assertEqual(mod.resolve_context(config(self.package,release='Sep-2026'),self.meta)['code'],'RELEASE')

    def test_query_outside_scope_is_unavailable(self):
        self.meta.write_text(self.meta.read_text().replace('Arizona','California'))
        self.assertEqual(mod.resolve_context(config(self.package),self.meta)['code'],'OUT_OF_SCOPE')

    def test_larger_date_window_is_rejected(self):
        self.assertEqual(mod.resolve_context(config(self.package,days=31),self.meta)['code'],'OUT_OF_SCOPE')

    def test_sample_ids_and_pairing_are_not_cache_identity(self):
        self.meta.write_text(self.meta.read_text().replace('bird1','new_independent_sample'))
        self.assertEqual(mod.resolve_context(config(self.package),self.meta)['status'],'READY')

    def test_existing_package_cannot_be_overwritten(self):
        args=argparse.Namespace(command='migrate',output=self.package,documents=self.raw,cache=self.package)
        with self.assertRaisesRegex(ValueError,'already exists'):mod.prepare(args)

    def test_migrate_legacy_cache_preserves_unknown_source_hashes(self):
        (self.package/mod.MANIFEST).unlink()
        args=argparse.Namespace(command='migrate',cache=self.package,documents=self.raw,output=self.root/'migrated',
                               release='Aug-2026',taxonomy_version='unknown',acquired_at='unknown')
        with contextlib.redirect_stdout(io.StringIO()):mod.prepare(args)
        m=mod.verify(args.output,self.meta)
        self.assertIsNone(m['source_hashes']);self.assertIsNone(m['acquired_at'])
        self.assertEqual(m['taxonomy_version'],'unknown')
        self.assertFalse((self.package/mod.MANIFEST).exists())

    def test_incomplete_legacy_migration_explains_missing_components(self):
        (self.package/mod.MANIFEST).unlink()
        (self.raw/'terms_of_use.txt').unlink()
        args=argparse.Namespace(command='migrate',cache=self.package,documents=self.raw,output=self.root/'migrated')
        with self.assertRaisesRegex(ValueError,'terms_of_use.txt'):mod.prepare(args)
        self.assertFalse(args.output.exists())

    def test_legacy_inspect_does_not_modify_files(self):
        before={p.name:p.read_bytes() for p in self.package.iterdir()}
        result=mod.legacy_inventory(self.package)
        self.assertEqual(result['missing'],[])
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.package.iterdir()})

    def test_migration_rejects_sampling_scope_mismatch(self):
        p=self.package/'sampling_manifest.json';data=json.loads(p.read_text());data['days']=31;mod.write_json(p,data)
        with self.assertRaisesRegex(ValueError,'days differ'):mod.read_cache_contract(self.package)

    def test_release_filename_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'conflicts'):mod.check_release('Aug-2026',['ebd_relSep-2026.txt'])

    def test_required_off_is_invalid(self):
        with self.assertRaisesRegex(ValueError,'cannot be true'):mod.resolve_context({'mode':'off','required':True},self.meta)

    def test_off_is_explicit(self):
        self.assertEqual(mod.resolve_context({'mode':'off'},self.meta)['status'],'DISABLED')

    def test_package_file_symlink_is_rejected(self):
        p=self.package/'terms_of_use.txt';p.unlink();p.symlink_to(self.raw/'terms_of_use.txt')
        self.assertEqual(mod.resolve_context(config(self.package),self.meta)['status'],'UNAVAILABLE')

    def test_package_cannot_claim_dates_after_release(self):
        with self.assertRaisesRegex(ValueError, 'past the source release'):
            mod.validate_release_coverage('Aug-2026', [{'end': '2026-09-01'}])

    def test_invalid_radius_is_configuration_error(self):
        with self.assertRaisesRegex(ValueError, 'finite'):
            mod.resolve_context(config(self.package, radius_km=float('nan')), self.meta)

    def test_legacy_explorer_call_still_works(self):
        api=runpy.run_path(str(ROOT/'scripts/build_surveillance_explorer.py'))
        result=api['build_payload'](self.meta,[],[])
        self.assertIsNone(result['ebird_status'])
        self.assertEqual(len(result['samples']),1)


if __name__=='__main__':unittest.main()
