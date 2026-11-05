#!/usr/bin/env python3
"""Build Explorer assets from canonical modules and ordered templates.

Preview: python scripts/build_explorer_assets.py
Verify:  python scripts/build_explorer_assets.py --check
Build:   python scripts/build_explorer_assets.py --write

This does not render reports or modify saved .wings bundles.
"""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

MANIFEST = "scripts/report/explorer-assets.json"
TOKEN = re.compile(r"@@WINGS:([A-Za-z0-9_./-]+(?:#[a-z]+)?)@@")
SUMMARY_BEGIN = "/* WINGS_COMPACT_CONCORDANCE_SUMMARY_BEGIN */"
SUMMARY_END = "/* WINGS_COMPACT_CONCORDANCE_SUMMARY_END */"


def safe_path(repo, relative):
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Unsafe asset path: " + relative)
    target = repo / path
    if target.is_symlink() or not target.resolve().is_relative_to(repo):
        raise ValueError("Asset path escapes the checkout or is a symlink: " + relative)
    return target


def css_part(text, selector):
    if text.count(SUMMARY_BEGIN) != 1 or text.count(SUMMARY_END) != 1:
        raise ValueError("Concordance CSS needs one compact-summary marker pair.")
    start, end = text.index(SUMMARY_BEGIN), text.index(SUMMARY_END)
    if start >= end:
        raise ValueError("Reversed concordance CSS markers.")
    parts = {"base": text[:start], "summary": text[start + len(SUMMARY_BEGIN):end],
             "takeaway": text[end + len(SUMMARY_END):]}
    if selector not in parts or not parts[selector].strip():
        raise ValueError("Unknown or empty CSS section: " + selector)
    return parts[selector].strip()


def render_all(repo):
    repo = Path(repo).resolve()
    manifest = json.loads(safe_path(repo, MANIFEST).read_bytes())
    if manifest.get("schema") != "wings.explorer-assets.v1":
        raise ValueError("Unknown Explorer asset manifest schema.")
    outputs = manifest["outputs"]
    sources = set(manifest["sources"])
    if set(outputs) & sources:
        raise ValueError("An asset cannot be both a canonical source and a generated output.")
    cache = {}

    def read(name):
        return safe_path(repo, name).read_bytes().decode("utf-8")

    def render(name, stack=()):
        if name in stack:
            raise ValueError("Cyclic asset includes: " + " -> ".join(stack + (name,)))
        if name in cache:
            return cache[name]
        if name not in outputs:
            raise ValueError("Unknown generated asset: " + name)
        safe_path(repo, name)
        template = read(outputs[name])

        def include(match):
            reference = match.group(1)
            path, _, selector = reference.partition("#")
            if path in outputs:
                if selector:
                    raise ValueError("Selectors cannot address generated outputs.")
                content = render(path, stack + (name,))
            elif path in sources:
                content = read(path)
                if "@@WINGS:" in content:
                    raise ValueError("Canonical sources cannot contain template directives: " + path)
            else:
                raise ValueError("Undeclared asset source: " + path)
            return css_part(content, selector) if selector else content.strip()

        result = TOKEN.sub(include, template)
        if "@@WINGS:" in result:
            raise ValueError("Unresolved asset template directive in " + name)
        cache[name] = result
        return result

    return {name: render(name).encode("utf-8") for name in outputs}


def plan(repo):
    repo = Path(repo).resolve()
    return {name: content for name, content in render_all(repo).items()
            if not safe_path(repo, name).is_file() or safe_path(repo, name).read_bytes() != content}


def write_outputs(repo, changes):
    repo = Path(repo).resolve()
    for name, content in changes.items():
        path = safe_path(repo, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
                temp = handle.name
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp, mode)
            os.replace(temp, path)
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    changes = plan(args.repo)
    if not changes:
        print("PASS: Explorer assets match their canonical sources.")
        return 0
    print("Generated assets differ:")
    for name in changes:
        print("  " + name)
    if args.check:
        print("Run python scripts/build_explorer_assets.py --write, review, and commit the generated assets.")
        return 1
    if args.write:
        write_outputs(args.repo, changes)
        print("Rebuilt Explorer assets. Existing HTML reports and .wings bundles were not changed.")
    else:
        print("Preview only. Use --write to rebuild.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        sys.exit(1)
