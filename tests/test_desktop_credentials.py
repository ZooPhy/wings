import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from wings_credentials import runtime_environment
import context_setup
import context_runner


class CredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.desktop').mkdir()
        self.key = self.root / '.desktop/ebirdst-access-key'
        self.base = {'WINGS_DESKTOP_WORKSPACE': str(self.root), 'NCBI_EMAIL': 'test@example.org'}

    def test_add_later_leaves_key_absent(self):
        self.assertNotIn('EBIRDST_ACCESS_KEY', runtime_environment(self.base))

    def test_native_environment_unchanged(self):
        env = {'EBIRDST_ACCESS_KEY': 'native-fixture'}
        self.assertEqual(runtime_environment(env), env)
        self.assertIsNot(runtime_environment(env), env)

    def test_add_update_remove_without_mutating_existing_job_environment(self):
        self.key.write_text('fixture-key-one')
        old_job = runtime_environment(self.base)
        self.key.write_text('fixture-key-two')
        new_job = runtime_environment(self.base)
        self.assertEqual(old_job['EBIRDST_ACCESS_KEY'], 'fixture-key-one')
        self.assertEqual(new_job['EBIRDST_ACCESS_KEY'], 'fixture-key-two')
        self.assertNotIn('EBIRDST_ACCESS_KEY', self.base)
        self.key.unlink()
        self.assertNotIn('EBIRDST_ACCESS_KEY', runtime_environment(new_job))

    def test_symlink_and_malformed_values_rejected_without_echoing_secret(self):
        target = self.root / 'elsewhere'; target.write_text('fixture-secret')
        self.key.symlink_to(target)
        with self.assertRaises(ValueError): runtime_environment(self.base)
        self.key.unlink()
        self.key.write_text('fixture-secret\nINJECT=value')
        with self.assertRaises(ValueError) as caught: runtime_environment(self.base)
        self.assertNotIn('fixture-secret', str(caught.exception))

    def test_plan_reflects_key_added_later_without_serializing_it(self):
        metadata = self.root / 'metadata.tsv'
        metadata.write_text('sample_id\thost\tcollection_date\tcountry\tstate\tlatitude\tlongitude\nA\tCAGO\t2024-09-15\tUS\tArizona\t33.4\t-112.1\n')
        with patch.dict(os.environ, self.base):
            self.assertEqual(context_setup.plan(metadata, {'selected_sources':['phenology']})['providers']['phenology']['status'], 'NEEDS_ACCESS')
            self.key.write_text('fixture-only-secret')
            result = context_setup.plan(metadata, {'selected_sources':['phenology']})
            self.assertEqual(result['providers']['phenology']['status'], 'PLANNED')
            self.assertNotIn('fixture-only-secret', json.dumps(result))

    def test_context_subprocess_gets_key_snapshot_only_in_environment(self):
        self.key.write_text('fixture-original')
        with patch.dict(os.environ, self.base), patch.object(context_setup, 'command') as command:
            executor = context_runner.provider_executor({}, {})
            self.key.write_text('fixture-replacement')
            executor(['python', 'fixture.py'], self.root / 'context.log')
            self.assertEqual(command.call_args.kwargs['env']['EBIRDST_ACCESS_KEY'], 'fixture-original')
            self.assertNotIn('fixture-original', repr(command.call_args.args))


if __name__ == '__main__': unittest.main()
