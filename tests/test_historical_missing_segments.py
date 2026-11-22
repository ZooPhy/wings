"""Regression tests for historical-stability checkpoint dependencies.

Run from the repo root with unittest discovery. The optional workflow test
requires Snakemake on PATH; it uses synthetic files, never real reads/Conda.
"""
import ast
from collections import Counter
import csv
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[1]
SEGMENTS = ("HA", "NA", "PB2", "PB1", "PA", "NP", "MP", "NS")
HELPERS = (
    "irma_segments_dir", "irma_manifest_path", "_manifest_rows",
    "segments_for_sample", "run_medaka_status_inputs", "fasta_path", "bam_path",
)


def function_source(source, name):
    match = re.search(r"^def " + re.escape(name) + r"\(.*?(?=^[^\s)#]|\Z)",
                      source, re.M | re.S)
    if match is None:
        raise AssertionError("Missing production function: " + name)
    ast.parse(match.group())
    return match.group()


def historical_input(source):
    rule = source.split("\nrule historical_stability:\n", 1)[1]
    rule = rule.split("\n    output:", 1)[0]
    match = re.search(r"^        variant_status=(.*?)(?=^        \w+=)",
                      rule, re.M | re.S)
    if match is None:
        raise AssertionError("Missing historical variant_status dependency")
    expression = match.group(1).strip().removesuffix(",")
    ast.parse(expression, mode="eval")
    return expression


def expand_for_test(pattern, **values):
    # Allows the old Cartesian dependency to execute as a negative control.
    import itertools
    return [pattern.format(**dict(zip(values, items)))
            for items in itertools.product(*values.values())]


class HistoricalMissingSegmentsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="wings historical ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = (ROOT / "Snakefile").read_text()
        self.outputs = {}
        self.pending = set()
        self.lookups = []
        self.ns = dict(Path=Path, csv=csv, SimpleNamespace=SimpleNamespace,
                       SEGMENT_SEQUENCE=SEGMENTS, RESULTS=str(self.root),
                       SAMPLES=["partial", "complete", "empty"],
                       expand=expand_for_test,
                       checkpoints=SimpleNamespace(normalize_irma_outputs=
                           SimpleNamespace(get=self.checkpoint)))
        for name in HELPERS:
            exec(function_source(self.source, name), self.ns)
        self.dependency = eval(historical_input(self.source), self.ns)
        self.make_sample("partial", ("HA", "PB1", "MP", "NS"))
        self.make_sample("complete", SEGMENTS)
        self.make_sample("empty", ())

    def checkpoint(self, *, sample):
        self.lookups.append(sample)
        if sample in self.pending:
            raise RuntimeError("fixture checkpoint pending: " + sample)
        return SimpleNamespace(output=self.outputs[sample])

    def make_sample(self, sample, ready):
        segments = self.root / sample / "irma" / "segments"
        segments.mkdir(parents=True, exist_ok=True)
        manifest = segments.parent / "manifest.tsv"
        with manifest.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["segment", "status",
                                                        "coverage_median"], delimiter="\t")
            writer.writeheader()
            for segment in SEGMENTS:
                writer.writerow(dict(segment=segment,
                                     status="READY" if segment in ready else "MISSING",
                                     coverage_median=5 if segment == "PB1" else 100))
                if segment in ready:
                    folder = segments / segment
                    folder.mkdir(exist_ok=True)
                    (folder / "consensus.fasta").write_text(">fixture\nACGT\n")
                    (folder / "alignment.bam").write_bytes(b"fixture, not a BAM")
        self.outputs[sample] = SimpleNamespace(segments=segments, manifest=manifest)

    def test_historical_input_is_deferred_until_checkpoint(self):
        self.assertTrue(callable(self.dependency))
        self.pending.add("partial")
        with self.assertRaisesRegex(RuntimeError, "checkpoint pending"):
            self.dependency(SimpleNamespace())

    def test_partial_complete_and_empty_samples(self):
        actual = self.dependency(SimpleNamespace())
        expected = [str(self.root / sample / "medaka" / segment / "variants.status.tsv")
                    for sample, segments in [("partial", ("HA", "PB1", "MP", "NS")),
                                             ("complete", SEGMENTS), ("empty", ())]
                    for segment in segments]
        self.assertEqual(actual, expected)
        self.assertEqual(set(self.lookups), {"partial", "complete", "empty"})

    def test_checkpoint_reevaluation_observes_new_ready_segment(self):
        before = self.dependency(SimpleNamespace())
        self.make_sample("partial", ("HA", "NA", "PB1", "MP", "NS"))
        after = self.dependency(SimpleNamespace())
        self.assertEqual(set(after) - set(before), {
            str(self.root / "partial/medaka/NA/variants.status.tsv")})

    def test_all_missing_produces_no_medaka_dependencies(self):
        self.ns["SAMPLES"] = ["empty"]
        self.assertEqual(self.dependency(SimpleNamespace()), [])

    def test_low_coverage_ready_segment_is_retained(self):
        self.assertIn(str(self.root / "partial/medaka/PB1/variants.status.tsv"),
                      self.dependency(SimpleNamespace()))

    def test_missing_status_does_not_become_ready_from_stale_files(self):
        folder = self.outputs["partial"].segments / "NA"
        folder.mkdir()
        (folder / "consensus.fasta").write_text(">stale\nACGT\n")
        (folder / "alignment.bam").write_bytes(b"stale")
        self.assertNotIn(str(self.root / "partial/medaka/NA/variants.status.tsv"),
                         self.dependency(SimpleNamespace()))

    def test_explicit_request_for_missing_fasta_still_fails(self):
        with self.assertRaisesRegex(ValueError, "No normalized FASTA"):
            self.ns["fasta_path"](SimpleNamespace(sample="partial", segment="NA"))

    def test_historical_missing_vcf_remains_incomplete(self):
        comparator = (ROOT / "scripts/compare_historical_interpretation.py").read_text()
        namespace = {"Counter": Counter}
        exec(function_source(comparator, "summarize_variant_layer"), namespace)
        summarize = namespace["summarize_variant_layer"]
        self.assertEqual(summarize({}, [])["status"], "NOT_AVAILABLE")
        result = summarize({"missing": {"category": "variant_vcf", "status": "MISSING"}},
                           [{"status": "MISSING_CURRENT"}])
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertEqual(result["missing_vcf_count"], 1)

    @unittest.skipUnless(shutil.which("snakemake"), "Snakemake not installed")
    def test_actual_checkpoint_workflow(self):
        # Extract the production helpers and historical input expression.
        # Stub only scientific jobs: placeholder files must never reach Medaka.
        preamble = "import csv, json\nfrom pathlib import Path\nfrom types import SimpleNamespace\n"
        preamble += "RESULTS = 'results'\nSAMPLES = ['partial', 'complete', 'empty']\n"
        preamble += "SEGMENT_SEQUENCE = " + repr(SEGMENTS) + "\n"
        preamble += "rule all:\n    input: 'historical.done'\n"
        preamble += "\n".join(function_source(self.source, name) for name in HELPERS)
        fixture = '''
checkpoint normalize_irma_outputs:
    output:
        segments=directory("results/{sample}/irma/segments"),
        manifest="results/{sample}/irma/manifest.tsv"
    run:
        ready = {"partial": ("HA", "PB1", "MP", "NS"), "complete": SEGMENT_SEQUENCE, "empty": ()}[wildcards.sample]
        Path(output.segments).mkdir(parents=True, exist_ok=True)
        with open(output.manifest, "w") as handle:
            handle.write("segment\\tstatus\\n")
            for segment in SEGMENT_SEQUENCE:
                handle.write(segment + "\\t" + ("READY" if segment in ready else "MISSING") + "\\n")
                if segment in ready:
                    folder = Path(output.segments) / segment
                    folder.mkdir(exist_ok=True)
                    (folder / "consensus.fasta").write_text(">fixture\\nACGT\\n")
                    (folder / "alignment.bam").write_bytes(b"fixture")

rule medaka_vcf:
    input:
        fasta=fasta_path,
        bam=bam_path
    output:
        status="results/{sample}/medaka/{segment}/variants.status.tsv"
    shell:
        "printf 'fixture only\\n' > {output.status:q}"

rule historical_stability:
    input:
        variant_status=EXPRESSION
    output:
        "historical.done"
    run:
        Path(output[0]).write_text(json.dumps(list(input.variant_status)))
'''
        for label, expression, success in [
            ("patched", historical_input(self.source), True),
            ("negative", 'expand("results/{sample}/medaka/{segment}/variants.status.tsv", sample=SAMPLES, segment=SEGMENT_SEQUENCE)', False),
        ]:
            directory = self.root / label
            directory.mkdir()
            (directory / "Snakefile").write_text(preamble + fixture.replace("EXPRESSION", expression))
            proc = subprocess.run([shutil.which("snakemake"), "--cores", "1", "--nocolor"],
                                  cwd=directory, text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=180)
            if success:
                self.assertEqual(proc.returncode, 0, proc.stdout)
                paths = json.loads((directory / "historical.done").read_text())
                self.assertEqual(len(paths), 12)
                self.assertFalse(any("/empty/" in p or "/partial/medaka/NA/" in p for p in paths))
            else:
                self.assertNotEqual(proc.returncode, 0, proc.stdout)
                self.assertIn("No normalized FASTA", proc.stdout)


if __name__ == "__main__":
    unittest.main()
