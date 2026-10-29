import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('phenology_retry',ROOT/'scripts/build_ebirdst_phenology.py')
ph=importlib.util.module_from_spec(spec);spec.loader.exec_module(ph)

class DownloadRecoveryTests(unittest.TestCase):
    url='https://example.test/list?key=DO_NOT_PRINT'
    def response(self, raw=b'ok'):
        r=MagicMock();r.__enter__.return_value.read.return_value=raw;return r
    def error(self,code):return HTTPError(self.url,code,'DO_NOT_PRINT',{},None)
    def test_transient_500_then_success(self):
        with patch.object(ph,'urlopen',side_effect=[self.error(500),self.response()]) as request, patch.object(ph.time,'sleep') as sleep, contextlib.redirect_stderr(io.StringIO()) as log:
            self.assertEqual(ph.request_bytes(self.url),b'ok')
        self.assertEqual(request.call_count,2);sleep.assert_called_once_with(1)
        self.assertNotIn('DO_NOT_PRINT',log.getvalue())
    def test_500_exhausts_three_attempts_without_leaking_key(self):
        with patch.object(ph,'urlopen',side_effect=self.error(500)) as request, patch.object(ph.time,'sleep') as sleep, contextlib.redirect_stderr(io.StringIO()) as log:
            with self.assertRaises(ph.RemoteDataUnavailable) as error:ph.request_bytes(self.url)
        self.assertEqual(request.call_count,3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list],[1,2])
        self.assertNotIn('DO_NOT_PRINT',str(error.exception)+log.getvalue())
    def test_authentication_failure_is_not_retried(self):
        for code in (401,403):
            with self.subTest(code=code),patch.object(ph,'urlopen',side_effect=self.error(code)) as request,patch.object(ph.time,'sleep') as sleep:
                with self.assertRaises(ph.RemoteDataUnavailable):ph.request_bytes(self.url)
                self.assertEqual(request.call_count,1);sleep.assert_not_called()
    def test_timeout_and_url_error_retried(self):
        for error in (TimeoutError('DO_NOT_PRINT'),URLError(self.url)):
            with self.subTest(error=type(error).__name__),patch.object(ph,'urlopen',side_effect=error) as request,patch.object(ph.time,'sleep'),contextlib.redirect_stderr(io.StringIO()) as log:
                with self.assertRaises(ph.RemoteDataUnavailable) as exc:ph.request_bytes(self.url)
                self.assertEqual(request.call_count,3)
                self.assertNotIn('DO_NOT_PRINT',str(exc.exception)+log.getvalue())
    def samples(self):return [dict(status=status,ebird_species_code=code,ebird_species=code) for status,code in [('PENDING','cached'),('PENDING','broken'),('PENDING_REGIONAL','broken')]]
    def test_list_failure_preserves_cached_species_and_marks_point_and_region(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);cached=base/'cached.tif';cached.write_bytes(b'cached')
            samples=self.samples()
            with patch.object(ph,'cached_raster',side_effect=lambda c,y,code,r:cached if code=='cached' else None),patch.object(ph,'api_get_json',side_effect=ph.RemoteDataUnavailable('HTTP 500')),contextlib.redirect_stderr(io.StringIO()):
                rasters,manifest=ph.prepare_rasters(samples,base,2023,'27km','placeholder',False)
            self.assertEqual(rasters,{'cached':cached})
            for sample in samples[1:]:
                self.assertEqual(sample['status'],'UNAVAILABLE_DOWNLOAD');self.assertIsNone(sample['collection_week_value'])
            self.assertEqual(samples[0]['status'],'PENDING')
    def test_fetch_failure_does_not_create_cached_file(self):
        with tempfile.TemporaryDirectory() as d:
            samples=self.samples()[1:]
            with patch.object(ph,'api_get_json',return_value=[]),patch.object(ph,'choose_key',return_value='broken.tif'),patch.object(ph,'download_raster',side_effect=ph.RemoteDataUnavailable('HTTP 503')),contextlib.redirect_stderr(io.StringIO()):
                rasters,manifest=ph.prepare_rasters(samples,Path(d),2023,'27km','placeholder',False)
            self.assertEqual(rasters,{})
            self.assertEqual(manifest[0]['status'],'UNAVAILABLE_DOWNLOAD')
            self.assertEqual(list(Path(d).rglob('*.tif')),[])
    def test_invalid_json_is_typed_external_failure(self):
        with patch.object(ph,'request_bytes',return_value=b'<html>unavailable</html>'):
            with self.assertRaises(ph.RemoteDataUnavailable):ph.api_get_json(self.url,'placeholder')
    def test_non_tiff_response_never_enters_cache(self):
        with tempfile.TemporaryDirectory() as d,patch.object(ph,'request_bytes',return_value=b'<html>error</html>'):
            target=Path(d)/'raster.tif'
            with self.assertRaises(ph.RemoteDataUnavailable):ph.download_raster('object','placeholder',target)
            self.assertFalse(target.exists())
    def test_local_write_error_is_not_silenced(self):
        with tempfile.TemporaryDirectory() as d,patch.object(ph,'api_get_json',return_value=[]),patch.object(ph,'choose_key',return_value='broken.tif'),patch.object(ph,'download_raster',side_effect=PermissionError('disk permissions')):
            with self.assertRaises(PermissionError):ph.prepare_rasters(self.samples()[1:],Path(d),2023,'27km','placeholder',False)
    def test_failed_request_writes_valid_output_and_exits_successfully(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            metadata=base/'metadata.tsv'
            metadata.write_text('sample_id\thost\tcollection_date\tlatitude\tlongitude\tcountry\tstate\nA\tCanada Goose\t2025-05-01\t38\t-85\tUS\tKY\n')
            taxonomy=base/'taxonomy.csv'
            taxonomy.write_text('CATEGORY,SPECIES_CODE,PRIMARY_COM_NAME,SCI_NAME\nspecies,cangoo,Canada Goose,Branta canadensis\n')
            output=base/'phenology.json'
            argv=['builder','--metadata',str(metadata),'--taxonomy-file',str(taxonomy),'--cache-dir',str(base/'cache'),'--output',str(output)]
            with patch.object(ph.sys,'argv',argv),patch.dict(ph.os.environ,{'EBIRDST_ACCESS_KEY':'placeholder'}),patch.object(ph,'api_get_json',side_effect=ph.RemoteDataUnavailable('HTTP 500 after 3 attempts')),contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ph.main(),0)
            data=json.loads(output.read_text())
            self.assertEqual(data['profiles'],[])
            self.assertEqual(data['summary']['status_counts'],{'UNAVAILABLE_DOWNLOAD':1})
            self.assertIsNone(data['sample_status'][0]['collection_week_value'])

    def test_no_product_includes_regional_samples(self):
        with tempfile.TemporaryDirectory() as d,patch.object(ph,'api_get_json',return_value=[]),contextlib.redirect_stderr(io.StringIO()):
            samples=self.samples()[1:];ph.prepare_rasters(samples,Path(d),2023,'27km','placeholder',False)
            self.assertTrue(all(s['status']=='NO_STATUS_PRODUCT' for s in samples))

if __name__=='__main__':unittest.main()
