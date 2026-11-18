import subprocess
import tempfile
from pathlib import Path
import unittest
import test_phylogeography_movie_import as original
from build_phylogeography_movie import build, validate

class OfflineImportTests(unittest.TestCase):
    def test_analysis_mode_checks_observed_states(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=build(original.MovieImportTests().fixture(Path(tmp)))
            validate(data,for_analysis=True)
            data['segments'][0]['histories'][0]['root_state']='A'
            with self.assertRaises(subprocess.CalledProcessError):
                validate(data,for_analysis=True)
