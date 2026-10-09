"""Generate the public gzip demo, or verify it matches the source byte for byte."""
import argparse
import gzip
import hashlib
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
    with source.open("rb") as original, gzip.open(output, "rb") as compressed:
        if digest(original) != digest(compressed):
            raise ValueError("Compressed demo differs from source; regenerate it.")


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
    verify(source, output)
    print(f"Verified identical decompressed bytes: {output}")
    print(f"Source: {source.stat().st_size:,} bytes; gzip: {output.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
