from pathlib import Path


SNAKEFILE = Path(__file__).resolve().parents[1] / "Snakefile"


def test_phylogeny_uses_dynamic_ready_segments():
    source = SNAKEFILE.read_text(encoding="utf-8")

    assert "checkpoint phylogeny_ready_segments:" in source
    assert "def ready_phylogeny_segments(" in source
    assert "def generated_phylogeny_tree_inputs(" in source

    # The full eight-segment tree list must no longer be an unconditional
    # final target when phylogeny is enabled.
    assert '''
if RUN_PHYLOGENY:
    FINAL_TARGETS.extend(
        str(Path(PHYLOGENY_DIR) / PHYLOGENY_PATTERN.format(segment=segment))
        for segment in SEGMENT_SEQUENCE
    )
''' not in source

    assert '''
if RUN_PHYLOGENY:
    FINAL_TARGETS.append(
        f"{RESULTS}/run_summary/phylogeny/complete.done"
    )
''' in source

    # Surveillance Explorer must consume only trees for READY segments.
    assert '''
    if RUN_PHYLOGENY:
        return generated_phylogeny_tree_inputs(_wildcards)
''' in source


def test_phylogeny_complete_allows_zero_ready_segments():
    source = SNAKEFILE.read_text(encoding="utf-8")

    assert "rule phylogeny_complete:" in source
    assert "trees=generated_phylogeny_tree_inputs" in source

    # If no segment reaches the minimum sequence count, the dynamic input
    # function returns an empty list and the completion marker can still
    # be created. This is the expected behavior for a one-sample run.
    assert 'done.write_text("complete\\n", encoding="utf-8")' in source
