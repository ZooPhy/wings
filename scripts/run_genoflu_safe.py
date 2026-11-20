"""Run installed GenoFLU with safe paths, preserving its stdout report format."""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def run(fasta, output, log, executable="genoflu.py"):
    fasta, output, log = (Path(p).resolve() for p in (fasta, output, log))
    output.parent.mkdir(parents=True, exist_ok=True)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as diagnostic:
        try:
            installed = shutil.which(executable)
            if not installed:
                raise FileNotFoundError(f"GenoFLU executable not found: {executable}")
            script = Path(installed).resolve()
            dependencies = script.parent.parent / "dependencies"
            references = dependencies / "fastas"
            key = dependencies / "genotype_key.xlsx"
            if not fasta.is_file() or fasta.stat().st_size == 0:
                raise ValueError(f"Missing or empty input FASTA: {fasta}")
            if not any(references.glob("*.fasta")) or not key.is_file():
                raise FileNotFoundError(f"Missing GenoFLU reference files: {dependencies}")
            # Do not use TMPDIR: desktop workspaces and custom TMPDIR may have spaces.
            # Explicit aliases survive upstream abspath(), unlike its default realpath().
            with tempfile.TemporaryDirectory(prefix="wings-genoflu-", dir="/tmp") as directory:
                work = Path(directory)
                shutil.copyfile(fasta, work / "consensus_all_segments.fasta")
                (work / "references").symlink_to(references, target_is_directory=True)
                (work / "genotype_key.xlsx").symlink_to(key)
                report = work / "stdout.txt"
                diagnostic.write(f"Installed GenoFLU: {script}\nReferences: {references}\n")
                diagnostic.flush()
                with report.open("w") as stdout:
                    result = subprocess.run(
                        [sys.executable, str(script), "-f", "consensus_all_segments.fasta",
                         "-i", str(work / "references"), "-c", str(work / "genotype_key.xlsx")],
                        cwd=work, stdout=stdout, stderr=diagnostic, check=False,
                    )
                diagnostic.write(report.read_text())
                if result.returncode:
                    raise RuntimeError(f"GenoFLU exited with status {result.returncode}")
                if " Genotype --> " not in report.read_text():
                    raise RuntimeError("GenoFLU exited without a genotype result")
                # Existing WINGS consumers parse stdout despite the .tsv suffix.
                # Publish only after success; stderr belongs exclusively in the log.
                with tempfile.NamedTemporaryFile(dir=output.parent, prefix=".genoflu-", delete=False) as handle:
                    pending = Path(handle.name)
                try:
                    shutil.copyfile(report, pending)
                    pending.replace(output)
                finally:
                    pending.unlink(missing_ok=True)
        except Exception as error:
            diagnostic.write(f"\nWINGS GenoFLU error: {error}\n")
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fasta", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--log", required=True)
    args = parser.parse_args()
    run(args.fasta, args.output, args.log)
