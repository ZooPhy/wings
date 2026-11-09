"""WINGS report-bundle container format.

A ``.wings`` bundle is a JSON document holding the rendered run summary, every
rendered sample report, and the embedded run provenance record.

Schema version 1 stores each sample report as a complete standalone HTML
string.  Because every report is rendered by the same Quarto template, the
reports share a large byte-identical prefix (document head, jQuery, Bootstrap,
the base64 icon font) and a smaller byte-identical suffix (closing scripts).
In a 30-sample run that shared material accounts for roughly 60 MB of the
bundle.

Schema version 2 stores the shared prefix and suffix once under ``shared`` and
keeps only the per-sample middle section.  This is a storage change only: a
reader reconstructs each report by concatenating

    shared.report_prefix + samples[sid].html_mid + shared.report_suffix

and obtains the original HTML character for character.  No report content,
provenance field, or analysis output is altered, summarised, or dropped.

Readers built on this module accept both versions.  A v1 bundle is detected by
the absence of a ``shared`` key and is read unchanged, so bundles produced
before this change keep opening.

Typical use in the writer::

    from wings_bundle_format import pack_bundle
    bundle = pack_bundle(bundle_v1_dict)

Typical use in a reader::

    from wings_bundle_format import read_bundle, sample_html
    bundle = read_bundle(path)
    html = sample_html(bundle, "12-11-2025_barcode03")
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple

__all__ = [
    "BUNDLE_FORMAT",
    "SCHEMA_VERSION",
    "BundleFormatError",
    "pack_bundle",
    "unpack_bundle",
    "sample_html",
    "iter_sample_html",
    "read_bundle",
    "write_bundle",
    "verify_roundtrip",
]

BUNDLE_FORMAT = "WINGS_REPORT_BUNDLE"
SCHEMA_VERSION = 2

# Deduplicating two reports that share only a few hundred bytes costs more in
# structural overhead than it saves, and makes the stored form harder to read
# by hand for no benefit.  Below this threshold the bundle stays at v1.
MIN_SHARED_BYTES = 4096

_GZIP_MAGIC = b"\x1f\x8b"


class BundleFormatError(ValueError):
    """Raised when a bundle does not match either supported schema."""


# ---------------------------------------------------------------------------
# Shared-chunk detection
# ---------------------------------------------------------------------------
def _common_prefix_length(values) -> int:
    """Return the length of the longest prefix common to every string."""
    if not values:
        return 0
    shortest = min(values, key=len)
    limit = len(shortest)
    index = 0
    while index < limit:
        character = shortest[index]
        if any(value[index] != character for value in values):
            break
        index += 1
    return index


def _common_suffix_length(values, reserved: int) -> int:
    """Return the longest common suffix length that does not overlap the prefix.

    ``reserved`` is the number of leading characters already claimed by the
    common prefix.  Keeping the two regions disjoint is what guarantees that
    ``prefix + mid + suffix`` reconstructs the original for every report,
    including the shortest one.
    """
    if not values:
        return 0
    limit = min(len(value) for value in values) - reserved
    if limit <= 0:
        return 0
    index = 0
    while index < limit:
        character = values[0][-1 - index]
        if any(value[-1 - index] != character for value in values):
            break
        index += 1
    return index


def _shared_chunks(reports) -> Tuple[str, str]:
    """Return the (prefix, suffix) shared by every rendered sample report."""
    if len(reports) < 2:
        return "", ""
    prefix_length = _common_prefix_length(reports)
    suffix_length = _common_suffix_length(reports, prefix_length)
    if prefix_length + suffix_length < MIN_SHARED_BYTES:
        return "", ""
    first = reports[0]
    return first[:prefix_length], first[len(first) - suffix_length:]


# ---------------------------------------------------------------------------
# Pack / unpack
# ---------------------------------------------------------------------------
def pack_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``bundle`` in schema version 2.

    Every key other than ``samples`` and ``version`` is carried through
    untouched, so provenance, the run summary, and any future top-level
    sections are preserved exactly.  An already-packed bundle is returned
    unchanged.
    """
    if not isinstance(bundle, dict):
        raise BundleFormatError("bundle must be a JSON object")
    if "shared" in bundle:
        return bundle

    samples = bundle.get("samples") or {}
    if not isinstance(samples, dict):
        raise BundleFormatError("bundle 'samples' must be a JSON object")

    sample_ids = list(samples)
    reports = []
    for sample_id in sample_ids:
        entry = samples[sample_id]
        if not isinstance(entry, dict) or "html" not in entry:
            raise BundleFormatError(
                f"sample {sample_id!r} has no 'html' field to pack"
            )
        reports.append(entry["html"])

    prefix, suffix = _shared_chunks(reports)
    if not prefix and not suffix:
        # Nothing worth sharing; leave the bundle in its v1 form rather than
        # emit a v2 bundle that older readers would reject for no gain.
        return bundle

    packed_samples = {}
    end_offset = len(suffix)
    for sample_id, html in zip(sample_ids, reports):
        entry = dict(samples[sample_id])
        entry.pop("html", None)
        entry["html_mid"] = html[len(prefix):len(html) - end_offset]
        packed_samples[sample_id] = entry

    packed = dict(bundle)
    packed["version"] = SCHEMA_VERSION
    packed["shared"] = {"report_prefix": prefix, "report_suffix": suffix}
    packed["samples"] = packed_samples
    return packed


def unpack_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``bundle`` in schema version 1, with full ``html`` per sample."""
    if not isinstance(bundle, dict):
        raise BundleFormatError("bundle must be a JSON object")
    if "shared" not in bundle:
        return bundle

    samples = bundle.get("samples") or {}
    expanded = {}
    for sample_id in samples:
        entry = dict(samples[sample_id])
        entry.pop("html_mid", None)
        entry["html"] = sample_html(bundle, sample_id)
        expanded[sample_id] = entry

    plain = dict(bundle)
    plain.pop("shared", None)
    plain["version"] = 1
    plain["samples"] = expanded
    return plain


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def sample_html(bundle: Dict[str, Any], sample_id: str) -> str:
    """Return the complete rendered HTML report for one sample.

    Works on both schema versions, so callers never branch on the version.
    """
    samples = bundle.get("samples") or {}
    if sample_id not in samples:
        raise KeyError(sample_id)
    entry = samples[sample_id]

    if "html" in entry:
        return entry["html"]

    shared = bundle.get("shared")
    if shared is None or "html_mid" not in entry:
        raise BundleFormatError(
            f"sample {sample_id!r} has neither 'html' nor a shared-chunk form"
        )
    return (
        shared.get("report_prefix", "")
        + entry["html_mid"]
        + shared.get("report_suffix", "")
    )


def iter_sample_html(bundle: Dict[str, Any]) -> Iterator[Tuple[str, str]]:
    """Yield ``(sample_id, html)`` for every sample report in the bundle."""
    for sample_id in bundle.get("samples") or {}:
        yield sample_id, sample_html(bundle, sample_id)


def read_bundle(path) -> Dict[str, Any]:
    """Load a ``.wings`` bundle, transparently handling gzip-compressed files."""
    raw = Path(path).read_bytes()
    if raw[:2] == _GZIP_MAGIC:
        raw = gzip.decompress(raw)
    bundle = json.loads(raw.decode("utf-8"))
    if bundle.get("format") != BUNDLE_FORMAT:
        raise BundleFormatError(
            f"not a WINGS report bundle: format={bundle.get('format')!r}"
        )
    return bundle


def write_bundle(bundle: Dict[str, Any], path, compress: bool = False) -> int:
    """Write ``bundle`` to ``path``; return the number of bytes written."""
    payload = json.dumps(bundle, ensure_ascii=False).encode("utf-8")
    if compress:
        payload = gzip.compress(payload, 6)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(payload)
    return len(payload)


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------
def verify_roundtrip(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Pack a bundle and confirm every report reconstructs character for character.

    Returns a report with the per-sample result and the byte sizes, and raises
    ``BundleFormatError`` if any sample fails to reconstruct exactly.  This is
    the check that makes the storage change safe to adopt: it compares full
    strings, not hashes or lengths.
    """
    original = unpack_bundle(bundle)
    packed = pack_bundle(original)

    mismatched = []
    for sample_id in original.get("samples") or {}:
        expected = original["samples"][sample_id]["html"]
        if sample_html(packed, sample_id) != expected:
            mismatched.append(sample_id)
    if mismatched:
        raise BundleFormatError(
            "reports did not reconstruct exactly: " + ", ".join(sorted(mismatched))
        )

    for key in original:
        if key in {"samples", "version", "shared"}:
            continue
        if json.dumps(packed.get(key), sort_keys=True) != json.dumps(
            original[key], sort_keys=True
        ):
            raise BundleFormatError(f"top-level section {key!r} was altered by packing")

    original_bytes = len(json.dumps(original, ensure_ascii=False).encode("utf-8"))
    packed_bytes = len(json.dumps(packed, ensure_ascii=False).encode("utf-8"))
    shared = packed.get("shared") or {}
    return {
        "samples": len(original.get("samples") or {}),
        "all_reports_exact": True,
        "shared_prefix_chars": len(shared.get("report_prefix", "")),
        "shared_suffix_chars": len(shared.get("report_suffix", "")),
        "v1_bytes": original_bytes,
        "v2_bytes": packed_bytes,
        "saved_bytes": original_bytes - packed_bytes,
    }


# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
def _format_row(label: str, value) -> str:
    if isinstance(value, int):
        return f"{label:<24}{value:>16,}"
    return f"{label:<24}{value:>16}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect, migrate, and verify WINGS report bundles."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)

    pack = subcommands.add_parser("pack", help="rewrite a bundle in schema v2")
    pack.add_argument("input")
    pack.add_argument("--output", required=True)
    pack.add_argument("--gzip", action="store_true", help="gzip the output")

    unpack = subcommands.add_parser("unpack", help="rewrite a bundle in schema v1")
    unpack.add_argument("input")
    unpack.add_argument("--output", required=True)
    unpack.add_argument("--gzip", action="store_true", help="gzip the output")

    verify = subcommands.add_parser(
        "verify", help="confirm every report reconstructs exactly"
    )
    verify.add_argument("input")

    stats = subcommands.add_parser("stats", help="report bundle composition")
    stats.add_argument("input")

    args = parser.parse_args(argv)
    bundle = read_bundle(args.input)

    if args.command == "pack":
        result = verify_roundtrip(bundle)
        written = write_bundle(pack_bundle(bundle), args.output, args.gzip)
        print(_format_row("samples", result["samples"]))
        print(_format_row("v1 bytes", result["v1_bytes"]))
        print(_format_row("v2 bytes", result["v2_bytes"]))
        print(_format_row("saved", result["saved_bytes"]))
        print(_format_row("written", written))
        print("all reports verified byte-identical")
        return 0

    if args.command == "unpack":
        written = write_bundle(unpack_bundle(bundle), args.output, args.gzip)
        print(_format_row("written", written))
        return 0

    if args.command == "verify":
        result = verify_roundtrip(bundle)
        for key, value in result.items():
            print(_format_row(key, value))
        return 0

    if args.command == "stats":
        samples = bundle.get("samples") or {}
        total = sum(len(html) for _, html in iter_sample_html(bundle))
        print(_format_row("schema version", bundle.get("version", 1)))
        print(_format_row("samples", len(samples)))
        print(_format_row("run summary chars", len(bundle.get("run_summary", {}).get("html", ""))))
        print(_format_row("sample report chars", total))
        if "shared" in bundle:
            shared = bundle["shared"]
            print(_format_row("shared prefix", len(shared.get("report_prefix", ""))))
            print(_format_row("shared suffix", len(shared.get("report_suffix", ""))))
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
