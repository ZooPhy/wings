import argparse
import importlib.util
from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('amino_embed', ROOT / 'scripts/wings_amino_acids.py')
aa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aa)


class Nodes(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.templates = []
        self.frames = []
        self.scripts = []
        self.active = None
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        if tag == 'template':
            self.templates.append(dict(attrs))
        elif tag == 'iframe':
            self.frames.append(dict(attrs))
        elif tag == 'script':
            self.active = []

    def handle_data(self, data):
        if self.active is not None:
            self.active.append(data)

    def handle_endtag(self, tag):
        if tag == 'script' and self.active is not None:
            self.scripts.append(''.join(self.active))
            self.active = None


class AminoEmbedTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.report = Path(folder.name) / 'run.html'
        self.amino = Path(folder.name) / 'amino.html'
        # Tree Studio constructs a popup document inside a JavaScript string.
        self.popup = 'const popup = `<html><body><main>Tree</main></body></html>`;'
        self.run_source = '<!doctype html><html><body><script>' + self.popup + '</script></body></html>'
        self.amino_script = 'const marker = `M ${1} ${2}`;'
        self.amino_source = '<html><body><main>AA</main><script>' + self.amino_script + '</script></body></html>'
        self.report.write_text(self.run_source)
        self.amino.write_text(self.amino_source)
        self.args = argparse.Namespace(report=self.report, amino=self.amino)

    def test_template_is_an_html_node_and_popup_script_is_unchanged(self):
        aa.embed(self.args)
        parsed = Nodes(self.report.read_text())
        self.assertEqual(parsed.templates, [{'id': 'wings-amino-acid-dashboard-0'}])
        self.assertEqual(parsed.scripts, [self.popup])
        self.assertEqual(len(parsed.frames), 1)
        self.assertEqual(parsed.frames[0]['sandbox'], 'allow-scripts allow-downloads')
        embedded = Nodes(parsed.frames[0]['srcdoc'])
        self.assertEqual(embedded.scripts[0], self.amino_script)
        self.assertEqual(len(embedded.scripts), 2)
        self.assertEqual(self.amino.read_text(), self.amino_source)

    def test_height_bridge_ignores_popup_body_string_in_amino_report(self):
        self.amino.write_text('<html><body><script>' + self.popup + '</script></body></html>')
        aa.embed(self.args)
        embedded = Nodes(Nodes(self.report.read_text()).frames[0]['srcdoc'])
        self.assertEqual(embedded.scripts[0], self.popup)
        self.assertEqual(len(embedded.scripts), 2)
        self.assertIn('wings-amino-height', embedded.scripts[1])

    def test_repeated_embedding_is_byte_identical(self):
        aa.embed(self.args)
        first = self.report.read_bytes()
        aa.embed(self.args)
        self.assertEqual(self.report.read_bytes(), first)

    def test_body_case_comments_and_styles_do_not_change_insertion(self):
        before = '<HTML><BODY><!-- </body> --><style>.x::after{content:"</body>"}</style>'
        source = before + '<main>Run</main></BODY >\n</HTML>'
        self.report.write_text(source)
        aa.embed(self.args)
        result = self.report.read_text()
        self.assertTrue(result.startswith(before))
        self.assertLess(result.index('<main>Run</main>'), result.index('<!-- WINGS_AMINO_ACIDS_BEGIN -->'))
        self.assertTrue(result.endswith('</BODY >\n</HTML>'))

    def test_missing_real_run_body_fails_without_writing(self):
        source = '<script>' + self.popup + '</script>'
        self.report.write_text(source)
        with self.assertRaisesRegex(ValueError, 'Run report must have exactly one'):
            aa.embed(self.args)
        self.assertEqual(self.report.read_text(), source)

    def test_missing_real_amino_body_fails_without_writing(self):
        self.amino.write_text('<script>' + self.popup + '</script>')
        with self.assertRaisesRegex(ValueError, 'Amino acid report must have exactly one'):
            aa.embed(self.args)
        self.assertEqual(self.report.read_text(), self.run_source)

    def test_duplicate_document_body_fails_without_writing(self):
        source = '<html><body></body><body></body></html>'
        self.report.write_text(source)
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            aa.embed(self.args)
        self.assertEqual(self.report.read_text(), source)

    @unittest.skipUnless(shutil.which('node'), 'Node.js is not installed')
    def test_embedded_run_and_amino_javascript_pass_node_syntax_check(self):
        aa.embed(self.args)
        outer = Nodes(self.report.read_text())
        scripts = outer.scripts + Nodes(outer.frames[0]['srcdoc']).scripts
        for code in scripts:
            with self.subTest(script=code[:40]):
                result = subprocess.run([shutil.which('node'), '--check'], input=code, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
