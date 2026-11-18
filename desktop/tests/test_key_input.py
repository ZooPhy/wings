"""Backend acceptance locally; execute the exact native handler on macOS."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / 'source'
if not (SOURCE / 'scripts').is_dir(): SOURCE = ROOT.parent
sys.path.insert(0, str(SOURCE / 'scripts'))
from wings_credentials import runtime_environment


class KeyInputTests(unittest.TestCase):
    def test_hyphenated_key_survives_backend_without_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); (root / '.desktop').mkdir()
            value = 'AbC-1234-def-5678'
            (root / '.desktop/ebirdst-access-key').write_text(value)
            self.assertEqual(runtime_environment({'WINGS_DESKTOP_WORKSPACE':temp})['EBIRDST_ACCESS_KEY'], value)

    @unittest.skipUnless(sys.platform == 'darwin', 'Native AppleScript test requires macOS')
    def test_exact_native_handler_preserves_hyphens_and_trims_paste_edges(self):
        source = (ROOT / 'WINGS.applescript').read_text().split('on markEBirdPrompt', 1)[0]
        harness = '''
on expectValue(inputText, expectedText)
    set actualText to my normalizeAccessKey(inputText)
    if (id of actualText) is not equal to (id of expectedText) then error "Normalization changed a fixture key."
end expectValue
on expectRejected(inputText)
    try
        my normalizeAccessKey(inputText)
    on error
        return
    end try
    error "An invalid fixture was accepted."
end expectRejected
on run
    my expectValue("AbC-1234-def-5678", "AbC-1234-def-5678")
    my expectValue("-", "-")
    my expectValue(space & tab & "AbC-123" & return & linefeed, "AbC-123")
    my expectValue((character id 160) & "AbC-123" & (character id 8239), "AbC-123")
    my expectValue((character id 65279) & "AbC-123", "AbC-123")
    my expectValue("A_b.C/+==", "A_b.C/+==")
    my expectRejected("")
    my expectRejected(space & return)
    my expectRejected("Ab C-123")
    my expectRejected("Ab" & linefeed & "C-123")
    my expectRejected("Ab" & (character id 8211) & "123")
    return "PASS"
end run
'''
        result = subprocess.run(['/usr/bin/osascript', '-'], input=source+harness,
            text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'PASS')


if __name__ == '__main__': unittest.main()
