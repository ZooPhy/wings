from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SNAKEFILE = REPO_ROOT / "Snakefile"


def test_wings_bundle_is_default_target_when_run_summary_enabled():
    text = SNAKEFILE.read_text(encoding="utf-8")

    marker = "INTERPRETATION_ARCHIVE_INPUTS = list(FINAL_TARGETS)"
    start = text.index(marker)

    block = text[start : start + 500]

    assert "if RUN_SUMMARY:" in block
    assert "INTERPRETATION_ARCHIVE_CURRENT" in block
    assert 'f"{RESULTS}/wings_report_bundle.wings"' in block
