import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/build_ebirdst_phenology.py'
spec = importlib.util.spec_from_file_location('phenology', SCRIPT)
ph = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ph)

class MissingKeyTests(unittest.TestCase):
    def test_missing_key_cli_writes_valid_unavailable_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base/'metadata.tsv').write_text('sample_id\thost\tcollection_date\tlatitude\tlongitude\tcountry\tstate\nA\tTurkey Vulture\t2025-04-15\t38\t-85\tUS\tKY\nB\tTurkey Vulture\t2025-04-15\t\t\tUS\tKY\n')
            (base/'taxonomy.csv').write_text('CATEGORY,SPECIES_CODE,PRIMARY_COM_NAME,SCI_NAME\nspecies,turvul,Turkey Vulture,Cathartes aura\n')
            env = dict(os.environ)
            env.pop('EBIRDST_ACCESS_KEY', None)
            cmd = [sys.executable, str(SCRIPT), '--metadata', str(base/'metadata.tsv'), '--taxonomy-file', str(base/'taxonomy.csv'), '--cache-dir', str(base/'cache'), '--output', str(base/'output.json')]
            result = subprocess.run(cmd, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('WARNING:', result.stderr)
            data = json.loads((base/'output.json').read_text())
            self.assertEqual(data['profiles'], [])
            self.assertEqual(data['summary']['status_counts'], {'UNAVAILABLE_MISSING_ACCESS_KEY': 2})
            for sample in data['sample_status']:
                self.assertIsNone(sample['collection_week_value'])
                self.assertIn('Unavailable: missing data/access key', sample['reason'])
            (base/'output.json').unlink()
            result = subprocess.run(cmd+['--dry-run'], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('UNAVAILABLE_MISSING_ACCESS_KEY', result.stdout)
            self.assertFalse((base/'output.json').exists())

    def test_partial_cache_preserved_without_key_or_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            cached = base/'cached.tif'
            cached.write_bytes(b'cached fixture')
            samples = [dict(status='PENDING', ebird_species_code='cached', ebird_species='Cached bird'), dict(status='PENDING_REGIONAL', ebird_species_code='missing', ebird_species='Missing bird')]
            with patch.object(ph, 'cached_raster', side_effect=lambda c,y,code,r: cached if code=='cached' else None), patch.object(ph, 'api_get_json', side_effect=AssertionError('unexpected network')), contextlib.redirect_stderr(io.StringIO()):
                rasters, manifest = ph.prepare_rasters(samples, base, 2023, '27km', '', False)
            self.assertEqual(rasters, {'cached': cached})
            self.assertEqual(samples[0]['status'], 'PENDING')
            self.assertEqual(samples[1]['status'], 'UNAVAILABLE_MISSING_ACCESS_KEY')
            self.assertEqual([m['status'] for m in manifest], ['CACHED', 'UNAVAILABLE_MISSING_ACCESS_KEY'])

    def test_key_still_enables_download_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            samples=[dict(status='PENDING', ebird_species_code='bird', ebird_species='Bird')]
            with patch.object(ph, 'cached_raster', return_value=None), patch.object(ph, 'api_get_json', return_value={}) as api, patch.object(ph, 'extract_file_keys', return_value=[]), patch.object(ph, 'choose_key', return_value='weekly.tif'), patch.object(ph, 'download_raster', return_value={}) as download:
                rasters, manifest=ph.prepare_rasters(samples, Path(tmp), 2023, '27km', 'test-placeholder', False)
            api.assert_called_once()
            download.assert_called_once()
            self.assertEqual(manifest[0]['status'], 'DOWNLOADED')

if __name__ == '__main__':
    unittest.main()
