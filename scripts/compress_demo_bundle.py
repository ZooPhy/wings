"""Generate the public gzip demo, or verify it matches the source byte for byte."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile


def digest(stream):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return result.digest()


def verify(source, output):
    if source.is_file():
        with source.open("rb") as original, gzip.open(output, "rb") as compressed:
            if digest(original) != digest(compressed):
                raise ValueError("Compressed demo differs from source; regenerate it.")
        return "identical decompressed bytes"
    # Git checkouts may intentionally contain only the compressed demo.
    # Read to EOF to verify gzip integrity and validate the portable bundle.
    with gzip.open(output, "rt", encoding="utf-8") as compressed:
        bundle = json.load(compressed)
    if not isinstance(bundle, dict) or bundle.get("format") != "WINGS_REPORT_BUNDLE" or bundle.get("version") != 1:
        raise ValueError("Invalid compressed WINGS demo bundle.")
    samples = bundle.get("samples")
    summary = bundle.get("run_summary")
    summary_html = summary if isinstance(summary, str) else summary.get("html") if isinstance(summary, dict) else None
    if not isinstance(samples, dict) or not samples or bundle.get("sample_count") != len(samples) or not isinstance(summary_html, str):
        raise ValueError("Invalid compressed demo samples or run summary.")
    for sample in samples.values():
        markup = sample if isinstance(sample, str) else sample.get("html") if isinstance(sample, dict) else None
        if not isinstance(markup, str):
            raise ValueError("Invalid sample HTML in compressed demo.")
    return "gzip integrity and WINGS bundle structure (local source absent)"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[1] / "demo/wings_demo.wings")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    source = args.source
    output = args.output or source.with_suffix(source.suffix + ".gz")
    if source.resolve() == output.resolve():
        parser.error("Source and output must be different files.")
    if not args.check:
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as target:
                temporary = Path(target.name)
                with source.open("rb") as original, gzip.GzipFile(filename="", mode="wb", fileobj=target, compresslevel=6, mtime=0) as compressed:
                    shutil.copyfileobj(original, compressed, 1024 * 1024)
            verify(source, temporary)
            os.chmod(temporary, 0o644)
            temporary.replace(output)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    checked = verify(source, output)
    print(f"Verified {checked}: {output}")
    if source.is_file():
        print(f"Source: {source.stat().st_size:,} bytes; gzip: {output.stat().st_size:,} bytes")
    else:
        print(f"Gzip: {output.stat().st_size:,} bytes; compressed-only checkout supported")


if __name__ == "__main__":
    main()
