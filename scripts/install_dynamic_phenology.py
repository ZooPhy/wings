#!/usr/bin/env python3
"""Install metadata-driven eBird Status & Trends phenology into WINGS.

Dry-run by default. The installer updates workflow/report source files only; it
never edits config.yaml, analysis results, raw reads, or external eBird caches.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile

HERE = Path(__file__).resolve().parent
KIT = HERE.parent
FILES = (
    "scripts/build_ebirdst_phenology.py",
    "scripts/validate_phenology.py",
    "scripts/report/genome-braid-clock.js",
    "scripts/report/explorer-tabs.js",
    "envs/phenology.yaml",
    "config/phenology.example.yaml",
    "docs/ebirdst-phenology.md",
    "tests/test_dynamic_phenology.py",
    "tests/test_dynamic_phenology.cjs",
    "scripts/install_dynamic_phenology.py",
)
BRAID_BEGIN = "/* WINGS_BRAID_CLOCK_JS_BEGIN */"
BRAID_END = "/* WINGS_BRAID_CLOCK_JS_END */"
TABS_BEGIN = "/* WINGS_EXPLORER_TABS_JS_BEGIN */"
TABS_END = "/* WINGS_EXPLORER_TABS_JS_END */"
CONFIG_BEGIN = "# WINGS_DYNAMIC_PHENOLOGY_CONFIG_BEGIN"
CONFIG_END = "# WINGS_DYNAMIC_PHENOLOGY_CONFIG_END"
RULE_BEGIN = "# WINGS_DYNAMIC_PHENOLOGY_RULE_BEGIN"
RULE_END = "# WINGS_DYNAMIC_PHENOLOGY_RULE_END"
LOADER_BEGIN = "# WINGS_DYNAMIC_PHENOLOGY_LOADER_BEGIN"
LOADER_END = "# WINGS_DYNAMIC_PHENOLOGY_LOADER_END"

CONFIG_BLOCK = r'''# WINGS_DYNAMIC_PHENOLOGY_CONFIG_BEGIN
# Metadata-driven eBird Status & Trends reference annual cycle.
PHENOLOGY_CONFIG = config.get("phenology", {}) or {}
if not isinstance(PHENOLOGY_CONFIG, dict):
    raise ValueError("phenology must be a mapping")
PHENOLOGY_ENABLED = as_bool(PHENOLOGY_CONFIG.get("enabled", False))
PHENOLOGY_VERSION_YEAR = int(PHENOLOGY_CONFIG.get("version_year", 2023))
PHENOLOGY_RESOLUTION = str(PHENOLOGY_CONFIG.get("resolution", "27km")).strip().lower()
PHENOLOGY_REGIONAL_FALLBACK = str(PHENOLOGY_CONFIG.get("regional_fallback", "state")).strip().lower()
if PHENOLOGY_REGIONAL_FALLBACK not in {"none", "state"}:
    raise ValueError("phenology.regional_fallback must be one of: none, state")
if PHENOLOGY_RESOLUTION not in {"3km", "9km", "27km"}:
    raise ValueError("phenology.resolution must be one of: 3km, 9km, 27km")
PHENOLOGY_CACHE = Path(str(
    PHENOLOGY_CONFIG.get("cache_dir")
    or os.environ.get("WINGS_EBIRDST_CACHE")
    or "~/.cache/wings/ebirdst"
)).expanduser().resolve()
if Path(workflow.basedir).resolve() in (PHENOLOGY_CACHE, *PHENOLOGY_CACHE.parents):
    raise ValueError("phenology.cache_dir must be outside the WINGS repository")
PHENOLOGY_HOST_MAP = str(PHENOLOGY_CONFIG.get(
    "host_map_file", "resources/ebird_host_codes_2025.tsv"
))
if not Path(PHENOLOGY_HOST_MAP).is_absolute():
    PHENOLOGY_HOST_MAP = str(Path(workflow.basedir) / PHENOLOGY_HOST_MAP)
PHENOLOGY_TAXONOMY_FILE = str(PHENOLOGY_CONFIG.get("taxonomy_file") or "").strip()
if PHENOLOGY_TAXONOMY_FILE:
    PHENOLOGY_TAXONOMY_FILE = str(Path(PHENOLOGY_TAXONOMY_FILE).expanduser().resolve())
PHENOLOGY_OUTPUT = f"{RESULTS}/run_summary/phenology/wings_phenology.json"
# WINGS_DYNAMIC_PHENOLOGY_CONFIG_END'''

RULE_BLOCK = r'''# WINGS_DYNAMIC_PHENOLOGY_RULE_BEGIN
rule ebirdst_phenology:
    input:
        metadata=f"{RESULTS}/metadata/validated_metadata.tsv",
        host_map=PHENOLOGY_HOST_MAP,
        script="scripts/build_ebirdst_phenology.py",
        taxonomy=([PHENOLOGY_TAXONOMY_FILE] if PHENOLOGY_TAXONOMY_FILE else []),
    output:
        json=PHENOLOGY_OUTPUT
    log:
        f"{RESULTS}/run_summary/phenology/phenology.log"
    conda:
        "envs/phenology.yaml"
    params:
        cache=str(PHENOLOGY_CACHE),
        version=PHENOLOGY_VERSION_YEAR,
        resolution=PHENOLOGY_RESOLUTION,
        regional_fallback=PHENOLOGY_REGIONAL_FALLBACK,
        taxonomy=(
            "--taxonomy-file " + shlex.quote(PHENOLOGY_TAXONOMY_FILE)
            if PHENOLOGY_TAXONOMY_FILE else ""
        ),
    shell:
        r"""
        python {input.script:q} \
          --metadata {input.metadata:q} \
          --host-map {input.host_map:q} \
          --output {output.json:q} \
          --cache-dir {params.cache:q} \
          --version-year {params.version} \
          --resolution {params.resolution:q} \
          --regional-fallback {params.regional_fallback:q} \
          {params.taxonomy} \
          > {log:q} 2>&1
        """
# WINGS_DYNAMIC_PHENOLOGY_RULE_END'''

LOADER_BLOCK = r'''# WINGS_DYNAMIC_PHENOLOGY_LOADER_BEGIN
def load_phenology_snapshot(path: Path, samples: list[dict[str, Any]], metadata: Path) -> dict[str, Any]:
    """Load a derived clock snapshot and reject stale or cross-run bindings."""
    raw = Path(path).read_bytes()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("Phenology snapshot is not valid JSON") from exc
    if data.get("schema_version") != "wings.phenology.v1" or not isinstance(data.get("profiles"), list):
        raise ValueError("Unsupported phenology snapshot; expected wings.phenology.v1")
    if not isinstance(data.get("synthetic"), bool):
        raise ValueError("Phenology snapshot must explicitly declare synthetic")
    recorded = data.get("inputs", {}).get("metadata_sha256")
    current = hashlib.sha256(Path(metadata).read_bytes()).hexdigest()
    if recorded != current:
        raise ValueError("Phenology snapshot does not match the current validated metadata; rebuild phenology")
    sample_ids = {sample["sample_id"] for sample in samples}
    for status in data.get("sample_status", []):
        if status.get("sample_id") not in sample_ids:
            raise ValueError("Phenology sample_status references a sample outside current metadata")
    for profile in data["profiles"]:
        if profile.get("sample_id") not in sample_ids:
            raise ValueError("Phenology profile references a sample outside current metadata")
    data["snapshot_sha256"] = hashlib.sha256(raw).hexdigest()
    data["source_file"] = Path(path).name
    return data
# WINGS_DYNAMIC_PHENOLOGY_LOADER_END'''


def replace_marked(text: str, body: str, begin: str, end: str) -> str:
    if begin in text or end in text:
        if text.count(begin) != 1 or text.count(end) != 1:
            raise ValueError(f"Ambiguous marker block {begin}")
        return re.sub(re.escape(begin) + r".*?" + re.escape(end), lambda _m: body, text, count=1, flags=re.S)
    raise ValueError(f"Expected installed UI marker {begin}; install Genome Braid / Explorer Tabs first")


def inject_or_replace(text: str, block: str, begin: str, end: str, anchor: str, before: bool = False) -> str:
    if begin in text or end in text:
        if text.count(begin) != 1 or text.count(end) != 1:
            raise ValueError(f"Ambiguous marker block {begin}")
        return re.sub(re.escape(begin) + r".*?" + re.escape(end), lambda _m: block, text, count=1, flags=re.S)
    if text.count(anchor) != 1:
        raise ValueError(f"Expected exactly one workflow anchor: {anchor[:60]!r}")
    return text.replace(anchor, block + "\n\n" + anchor if before else anchor + "\n\n" + block, 1)


def patch_snakefile(text: str) -> str:
    ecology_anchor = 'ECOLOGY_ENABLED = as_bool(ECOLOGY_CONFIG.get("enabled", Path(ECOLOGY_JSON).is_file()))'
    text = inject_or_replace(text, CONFIG_BLOCK, CONFIG_BEGIN, CONFIG_END, ecology_anchor, before=False)
    text = inject_or_replace(text, RULE_BLOCK, RULE_BEGIN, RULE_END, "rule surveillance_explorer_data:", before=True)
    needle = '        ecological_loader="scripts/build_ecological_context.py",\n'
    addition = needle + '        phenology=([PHENOLOGY_OUTPUT] if PHENOLOGY_ENABLED else []),\n'
    if 'phenology=([PHENOLOGY_OUTPUT] if PHENOLOGY_ENABLED else [])' not in text:
        if text.count(needle) != 1:
            raise ValueError("Could not locate surveillance_explorer_data ecological_loader input")
        text = text.replace(needle, addition, 1)
    return text


def patch_builder(text: str) -> str:
    text = inject_or_replace(text, LOADER_BLOCK, LOADER_BEGIN, LOADER_END, "def build_payload(", before=True)

    if "    phenology: Path | None = None,\n" not in text:
        anchor = "    reference_loader: Path | None = None,\n) -> dict[str, Any]:"
        if text.count(anchor) != 1:
            raise ValueError("Could not patch build_payload signature")
        text = text.replace(anchor, "    reference_loader: Path | None = None,\n    phenology: Path | None = None,\n) -> dict[str, Any]:", 1)

    if "clock = load_phenology_snapshot(phenology, samples, metadata)" not in text:
        anchor = '        ecology = runpy.run_path(str(loader))["load_snapshot"](ecological_context, samples)\n\n    geolocated ='
        if text.count(anchor) != 1:
            raise ValueError("Could not locate ecological-context load block")
        repl = '        ecology = runpy.run_path(str(loader))["load_snapshot"](ecological_context, samples)\n\n    clock = load_phenology_snapshot(phenology, samples, metadata) if phenology is not None else None\n\n    geolocated ='
        text = text.replace(anchor, repl, 1)

    if '        "ecological_clock": clock,\n' not in text:
        anchor = '        "ecological_context": ecology,\n'
        if text.count(anchor) != 1:
            raise ValueError("Could not locate ecological_context payload key")
        text = text.replace(anchor, anchor + '        "ecological_clock": clock,\n', 1)

    if '    parser.add_argument("--phenology", type=Path)\n' not in text:
        anchor = '    parser.add_argument("--ecological-context", type=Path)\n'
        if text.count(anchor) != 1:
            raise ValueError("Could not locate ecological-context CLI argument")
        text = text.replace(anchor, anchor + '    parser.add_argument("--phenology", type=Path)\n', 1)

    if '        phenology_inputs = list(getattr(snakemake.input, "phenology", []))\n' not in text:
        anchor = '        ecological_loader = Path(snakemake.input.ecological_loader) if ecology else None\n'
        if text.count(anchor) != 1:
            raise ValueError("Could not locate Snakemake ecological input block")
        text = text.replace(anchor, anchor + '        phenology_inputs = list(getattr(snakemake.input, "phenology", []))\n        phenology = Path(phenology_inputs[0]) if phenology_inputs else None\n', 1)

    if '        phenology = args.phenology\n' not in text:
        anchor = '        ecological_context, ecological_loader = args.ecological_context, None\n'
        if text.count(anchor) != 1:
            raise ValueError("Could not locate CLI ecological assignment")
        text = text.replace(anchor, anchor + '        phenology = args.phenology\n', 1)

    if 'phenology=phenology)' not in text and 'phenology=phenology,' not in text:
        anchor = '                            reference_loader=reference_loader)\n'
        if text.count(anchor) != 1:
            raise ValueError("Could not locate build_payload invocation")
        text = text.replace(anchor, '                            reference_loader=reference_loader,\n                            phenology=phenology)\n', 1)
    return text


def plan(repo: Path) -> dict[str, bytes]:
    repo = repo.resolve()
    if not (repo / "Snakefile").is_file():
        raise ValueError("--repo must point to the WINGS repository root")
    required = [
        repo / "scripts/build_surveillance_explorer.py",
        repo / "scripts/report/surveillance-explorer.js",
    ]
    if not all(p.is_file() for p in required):
        raise ValueError("Expected WINGS Explorer source files were not found")

    result = {rel: (KIT / rel).read_bytes() for rel in FILES}
    js = (repo / "scripts/report/surveillance-explorer.js").read_text(encoding="utf-8")
    js = replace_marked(js, BRAID_BEGIN + "\n" + (KIT / "scripts/report/genome-braid-clock.js").read_text().rstrip() + "\n" + BRAID_END, BRAID_BEGIN, BRAID_END)
    js = replace_marked(js, TABS_BEGIN + "\n" + (KIT / "scripts/report/explorer-tabs.js").read_text().rstrip() + "\n" + TABS_END, TABS_BEGIN, TABS_END)
    result["scripts/report/surveillance-explorer.js"] = js.encode()
    result["Snakefile"] = patch_snakefile((repo / "Snakefile").read_text(encoding="utf-8")).encode()
    result["scripts/build_surveillance_explorer.py"] = patch_builder((repo / "scripts/build_surveillance_explorer.py").read_text(encoding="utf-8")).encode()

    for rel in result:
        if not (repo / rel).resolve().is_relative_to(repo):
            raise ValueError(f"Destination escapes repository via symlink: {rel}")
    return {rel: data for rel, data in result.items() if not (repo / rel).is_file() or (repo / rel).read_bytes() != data}


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as fh:
        tmp = Path(fh.name); fh.write(data)
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def apply(repo: Path, changes: dict[str, bytes]) -> Path:
    backup = Path(tempfile.mkdtemp(prefix="wings-dynamic-phenology-backup-"))
    previous: dict[str, bytes | None] = {}
    written: list[str] = []
    for rel in changes:
        path = repo / rel
        previous[rel] = path.read_bytes() if path.is_file() else None
        if previous[rel] is not None:
            atomic_write(backup / rel, previous[rel])
    atomic_write(backup / "backup_manifest.json", json.dumps({
        "repository": str(repo),
        "files": {rel: {"existed": raw is not None, "sha256": hashlib.sha256(raw).hexdigest() if raw else None} for rel, raw in previous.items()},
    }, indent=2).encode())
    try:
        for rel, data in changes.items():
            atomic_write(repo / rel, data); written.append(rel)
    except Exception:
        for rel in reversed(written):
            if previous[rel] is None:
                (repo / rel).unlink(missing_ok=True)
            else:
                atomic_write(repo / rel, previous[rel])
        raise
    return backup


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        changes = plan(args.repo)
        if not changes:
            print("Already installed; no changes needed.")
            return 0
        print("Files to add/update:")
        for rel in changes:
            print("  " + rel)
        print("config.yaml, raw reads, existing analytical outputs, and the external raster cache are not modified.")
        if not args.apply:
            print("Dry-run only. Repeat with --apply after reviewing this list.")
            return 0
        backup = apply(args.repo.resolve(), changes)
        print(f"Installed. Previous source files backed up outside the repo: {backup}")
        print("No commit, push, data download, analysis run, or report rebuild was performed.")
        return 0
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
