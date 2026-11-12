"""Folder detection shares the importer contract and never infers coverage from names."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('folder_context_setup',ROOT/'scripts/context_setup.py')
setup=importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class EbirdFolderCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def raw(self):
        for name in ['ebd_US_relSep-2026.txt','ebd_US_sampling_relSep-2026.txt','terms_of_use.txt','recommended_citation.txt']:
            (self.root/name).write_text('fixture')

    def prepared(self):
        for name in ['context_manifest.json','observations.txt.gz','sampling.txt','species_catalog.tsv','cache_manifest.json','sampling_manifest.json','terms_of_use.txt','recommended_citation.txt']:
            (self.root/name).write_text('fixture')

    def test_raw_download_is_detected_using_the_importer_inventory(self):
        self.raw()
        result=setup.inspect_ebird_folder(str(self.root))
        self.assertEqual((result['kind'],result['status'],result['release']),('download','RECOGNIZED','Sep-2026'))
        self.assertEqual(len(result['files']),4)
        self.assertIn('require your confirmation',result['message'])
        self.assertEqual(setup.ebird_download_files(self.root)[3],result['release'])

    def test_wrong_folder_and_missing_components_are_explicit(self):
        result=setup.inspect_ebird_folder(str(self.root))
        self.assertEqual(result['status'],'INVALID')
        self.assertIn('observations',result['message'])
        self.assertIn('sampling-event',result['message'])
        self.assertIn('terms_of_use.txt',result['message'])
        self.assertEqual(setup.inspect_ebird_folder(str(self.root/'missing'))['status'],'INVALID')

    def test_mismatched_releases_are_rejected(self):
        self.raw()
        (self.root/'ebd_US_sampling_relSep-2026.txt').rename(self.root/'ebd_US_sampling_relAug-2026.txt')
        self.assertIn('same release',setup.inspect_ebird_folder(str(self.root))['message'])

    def test_legacy_package_reports_missing_manifest(self):
        self.prepared();(self.root/'context_manifest.json').unlink()
        result=setup.inspect_ebird_folder(str(self.root))
        self.assertEqual((result['kind'],result['status']),('prepared','INVALID'))
        self.assertIn('context_manifest.json',result['message'])

    def test_prepared_dataset_selected_in_common_field_is_verified(self):
        self.prepared()
        metadata=self.root/'metadata.tsv';metadata.write_text('sample_id\na\n')
        calls=[]
        def verify(root,meta,days):
            calls.append((root,meta,days))
            return {'package_id':'fixture','release':'Sep-2026'}
        with patch.object(setup,'load',return_value={'verify':verify}):
            result=setup.find_ebird(metadata,setup.options({'ebird_source':str(self.root)}))
            self.assertEqual(result['status'],'READY')
            # Reuse needs no raw-download coverage checkbox or rebuild.
            self.assertEqual(setup.import_ebird(metadata,setup.options({'ebird_source':str(self.root)})),str(self.root.resolve()))
        self.assertEqual(len(calls),2)

    def test_invalid_selected_dataset_does_not_fall_back_to_another_cache(self):
        self.prepared()
        with patch.object(setup,'load',return_value={'verify':lambda *_: (_ for _ in ()).throw(ValueError('Metadata dates outside dataset coverage'))}):
            result=setup.find_ebird(self.root/'metadata.tsv',setup.options({'ebird_source':str(self.root)}))
        self.assertEqual(result['status'],'NEEDS_IMPORT')
        self.assertIn('outside dataset coverage',result['reason'])

    def test_raw_import_still_requires_coverage_confirmation(self):
        self.raw()
        with self.assertRaisesRegex(ValueError,'Confirm all-species'):
            setup.import_ebird(self.root/'metadata.tsv',setup.options({'ebird_source':str(self.root)}))

    def test_recaching_builds_unique_outputs_from_original_download(self):
        self.raw();metadata=self.root/'metadata.tsv';metadata.write_text('sample_id\na\n')
        original=(self.root/'ebd_US_relSep-2026.txt').read_bytes();created=[]
        def prepare(args):
            created.append(args);args.output.mkdir(parents=True);(args.output/'new-cache').write_text('fixture')
        opts=setup.options({'ebird_source':str(self.root),'all_species_confirmed':True,'days':14})
        with patch.object(setup,'cache_root',return_value=self.root/'cache'),patch.object(setup,'load',return_value={'prepare':prepare}):
            first=setup.import_ebird(metadata,opts);second=setup.import_ebird(metadata,opts)
        self.assertNotEqual(first,second);self.assertTrue((Path(first)/'new-cache').is_file())
        self.assertEqual((self.root/'ebd_US_relSep-2026.txt').read_bytes(),original)
        self.assertTrue(all(args.metadata==metadata and args.days==14 for args in created))


if __name__=='__main__':unittest.main()
