#!/usr/bin/env python3
"""Install the tabbed WINGS Surveillance Explorer shell. Dry-run by default."""
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
    "scripts/report/explorer-tabs.js",
    "scripts/report/explorer-tabs.css",
    "scripts/install_explorer_tabs.py",
    "tests/test_explorer_tabs.cjs",
    "docs/explorer-tabs.md",
)
JS_BEGIN = "/* WINGS_EXPLORER_TABS_JS_BEGIN */"
JS_END = "/* WINGS_EXPLORER_TABS_JS_END */"
CSS_BEGIN = "/* WINGS_EXPLORER_TABS_CSS_BEGIN */"
CSS_END = "/* WINGS_EXPLORER_TABS_CSS_END */"
HOOK_BEGIN = "// WINGS_EXPLORER_TABS_HOOK_BEGIN"
HOOK_END = "// WINGS_EXPLORER_TABS_HOOK_END"
BRAID_CALL = "globalThis.WINGS_BRAID_CLOCK.mountExplorer(explorer);"


def replace_block(text: str, body: str, begin: str, end: str, prepend: bool) -> str:
    if begin in text or end in text:
        if text.count(begin) != 1 or text.count(end) != 1:
            raise ValueError(f"Ambiguous existing block {begin}; no files changed.")
        text = re.sub(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", "", text, count=1, flags=re.S)
    block = begin + "\n" + body.rstrip() + "\n" + end + "\n"
    return block + text if prepend else text.rstrip() + "\n\n" + block


def patch_js(text: str, module: str) -> str:
    if HOOK_BEGIN in text or HOOK_END in text:
        if text.count(HOOK_BEGIN) != 1 or text.count(HOOK_END) != 1:
            raise ValueError("Ambiguous existing Explorer-tabs hook; no files changed.")
        text = re.sub(
            r"\s*" + re.escape(HOOK_BEGIN) + r".*?" + re.escape(HOOK_END),
            "",
            text,
            count=1,
            flags=re.S,
        )
    if text.count(BRAID_CALL) != 1:
        raise ValueError(
            "Expected exactly one Genome Braid mount hook. Install/retain Genome Braid first; no files changed."
        )
    hook = (
        BRAID_CALL
        + "\n        " + HOOK_BEGIN
        + "\n        globalThis.WINGS_EXPLORER_TABS.mount(explorer);"
        + "\n        " + HOOK_END
    )
    text = text.replace(BRAID_CALL, hook, 1)
    return replace_block(text, module, JS_BEGIN, JS_END, prepend=True)


def plan(repo: Path) -> dict[str, bytes]:
    repo = repo.resolve()
    if not (repo / "Snakefile").is_file():
        raise ValueError("--repo must point to the WINGS repository root (Snakefile not found).")
    js_path = repo / "scripts/report/surveillance-explorer.js"
    css_path = repo / "scripts/report/surveillance-explorer.css"
    if not js_path.is_file() or not css_path.is_file():
        raise ValueError("Surveillance Explorer assets were not found.")

    result = {rel: (KIT / rel).read_bytes() for rel in FILES}
    module_js = (KIT / "scripts/report/explorer-tabs.js").read_text(encoding="utf-8")
    module_css = (KIT / "scripts/report/explorer-tabs.css").read_text(encoding="utf-8")
    result["scripts/report/surveillance-explorer.js"] = patch_js(
        js_path.read_text(encoding="utf-8"), module_js
    ).encode()
    result["scripts/report/surveillance-explorer.css"] = replace_block(
        css_path.read_text(encoding="utf-8"), module_css, CSS_BEGIN, CSS_END, prepend=False
    ).encode()

    for rel in result:
        if not (repo / rel).resolve().is_relative_to(repo):
            raise ValueError(f"Destination escapes repository via symlink: {rel}")
    return {
        rel: data
        for rel, data in result.items()
        if not (repo / rel).is_file() or (repo / rel).read_bytes() != data
    }


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        stream.write(data)
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def apply(repo: Path, changes: dict[str, bytes]) -> Path:
    backup = Path(tempfile.mkdtemp(prefix="wings-explorer-tabs-backup-"))
    existing: dict[str, bytes | None] = {}
    written: list[str] = []
    for rel in changes:
        path = repo / rel
        existing[rel] = path.read_bytes() if path.is_file() else None
        if existing[rel] is not None:
            atomic_write(backup / rel, existing[rel])
    manifest = {
        "repository": str(repo.resolve()),
        "files": {
            rel: {
                "existed": data is not None,
                "sha256": hashlib.sha256(data).hexdigest() if data is not None else None,
            }
            for rel, data in existing.items()
        },
    }
    atomic_write(backup / "backup_manifest.json", json.dumps(manifest, indent=2).encode())
    try:
        for rel, data in changes.items():
            atomic_write(repo / rel, data)
            written.append(rel)
    except Exception:
        for rel in reversed(written):
            if existing[rel] is None:
                (repo / rel).unlink(missing_ok=True)
            else:
                atomic_write(repo / rel, existing[rel])
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
        print("No Snakefile, config.yaml, README, sequences, results, phylogenies, or analysis outputs are changed.")
        if not args.apply:
            print("Dry-run only. Repeat with --apply after reviewing this list.")
            return 0
        backup = apply(args.repo.resolve(), changes)
        print(f"Installed. Previous versions backed up outside the repo: {backup}")
        print("No commit, push, analysis run, or report rebuild was performed.")
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
