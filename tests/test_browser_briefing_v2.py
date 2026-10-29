import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import yaml

SPEC = importlib.util.spec_from_file_location(
    'briefing_runner_v2', Path(__file__).resolve().parents[1] / 'scripts/wings_local_runner.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class BrowserBriefingTests(unittest.TestCase):
    def test_disabled_by_default(self):
        self.assertEqual(runner.briefing_options({}), {'enabled': False})

    def test_enabled_configuration(self):
        result = runner.briefing_options({'briefing': True, 'briefing_model': 'custom:20b',
                                         'briefing_audience': 'animal_health'})
        self.assertEqual(result['model'], 'custom:20b')
        self.assertEqual(result['audience'], 'animal_health')
        self.assertEqual(result['mode'], 'staged')
        self.assertFalse(result['allow_remote'])
        self.assertEqual(result['url'], runner.BRIEFING_URL)

    def test_invalid_options(self):
        for options in ({'briefing': 'false'}, {'briefing': True, 'briefing_model': ''},
                        {'briefing': True, 'briefing_model': 'x; echo bad'},
                        {'briefing': True, 'briefing_audience': 'unknown'}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                runner.briefing_options(options)

    def check_with_response(self, payload, status=200):
        connection = Mock()
        connection.getresponse.return_value.status = status
        connection.getresponse.return_value.read.return_value = payload
        with patch.object(runner, 'HTTPConnection', return_value=connection) as factory:
            result = runner.check_briefing_model('custom')
        factory.assert_called_once_with('127.0.0.1', 11434, timeout=5)
        connection.request.assert_called_once_with('GET', '/api/tags')
        connection.close.assert_called_once()
        return result

    def test_installed_default_tag(self):
        result = self.check_with_response(b'{"models":[{"name":"custom:latest"}]}')
        self.assertTrue(result['ready'])

    def test_missing_model(self):
        self.assertFalse(self.check_with_response(b'{"models":[]}')['ready'])

    def test_redirect_not_followed(self):
        self.assertFalse(self.check_with_response(b'', status=302)['ready'])

    def test_malformed_model_list(self):
        for raw in (b'bad json', b'{"models":null}', b'[]', b'x' * (1024 * 1024 + 1)):
            with self.subTest(size=len(raw)):
                self.assertFalse(self.check_with_response(raw)['ready'])

    def test_ollama_unavailable(self):
        connection = Mock()
        connection.request.side_effect = ConnectionRefusedError()
        with patch.object(runner, 'HTTPConnection', return_value=connection):
            self.assertFalse(runner.check_briefing_model('custom')['ready'])
        connection.close.assert_called_once()

    def test_disabled_does_not_contact_ollama(self):
        with patch.object(runner, 'check_briefing_model') as check:
            runner.require_briefing_model({'public_health_interpretation': {'enabled': False}})
        check.assert_not_called()

    def test_failed_check_prevents_start(self):
        with patch.object(runner, 'check_briefing_model', return_value={'ready': False, 'detail': 'Missing model'}):
            with self.assertRaisesRegex(ValueError, 'Missing model'):
                runner.require_briefing_model({'public_health_interpretation': {'enabled': True, 'model': 'custom'}})

    def test_build_config_enables_explorer_and_preserves_other_defaults(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            (root / 'config').mkdir()
            (root / 'config/config.example.yaml').write_text(yaml.safe_dump({
                'coverage_min_depth': 50, 'public_health_interpretation': {'enabled': True, 'extra': 'keep'}}))
            directory = root / 'runs' / 'example'
            (directory / 'inputs/reads').mkdir(parents=True)
            (directory / 'inputs/reads/sample.fastq.gz').touch()
            (directory / 'inputs/metadata.tsv').write_text('sample_id\nsample\n')
            with patch.object(runner, 'RUNS_ROOT', root / 'runs'), patch.object(runner, 'REPO_ROOT', root):
                for enabled in (False, True):
                    runner.write_state('example', {'options': {'briefing': enabled, 'explorer': False}})
                    path, count = runner.build_config('example')
                    config = yaml.safe_load(path.read_text())
                    self.assertEqual(count, 1)
                    self.assertEqual(config['public_health_interpretation']['enabled'], enabled)
                    self.assertEqual(config['public_health_interpretation']['extra'], 'keep')
                    self.assertEqual(config['run_surveillance_explorer'], enabled)
                    self.assertEqual(config['coverage_min_depth'], 50)

    def test_check_http_route(self):
        handler = object.__new__(runner.Handler)
        handler.path = '/api/briefing/check'
        handler.headers = {'Content-Length': '18'}
        handler.rfile = io.BytesIO(b'{"model":"custom"}')
        handler.json_response = Mock()
        with patch.object(runner, 'check_briefing_model', return_value={'ready': True}) as check:
            handler.do_POST()
        check.assert_called_once_with('custom')
        handler.json_response.assert_called_once_with({'ready': True})


if __name__ == '__main__':
    unittest.main()
