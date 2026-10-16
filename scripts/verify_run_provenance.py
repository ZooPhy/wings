#!/usr/bin/env python3
"""Verify reproducibility records embedded in WINGS run provenance."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(provenance_path: Path, repo: Path, require_clean: bool = False) -> dict:
    errors = []
    try:
        data = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return {"status": "FAIL", "errors": [f"Cannot read provenance: {error}"]}
    if not isinstance(data, dict):
        return {"status": "FAIL", "errors": ["Provenance must be a JSON object"]}
    attempt = data.get("launcher_attempt")
    if not isinstance(attempt, dict):
        errors.append("No launcher_attempt record; terminal or legacy runs cannot pass attempt verification")
        attempt = {}

    config = attempt.get("effective_config") or {}
    config_content = config.get("content")
    if not isinstance(config_content, str):
        errors.append("Effective configuration content is missing")
    elif sha256_bytes(config_content.encode("utf-8")) != config.get("sha256"):
        errors.append("Embedded effective configuration SHA-256 mismatch")
    config_path = Path(config.get("path", ""))
    if not config_path.is_absolute():
        config_path = (repo / config_path).resolve()
    if config_path.is_file() and sha256_file(config_path) != config.get("sha256"):
        errors.append("Local effective configuration SHA-256 mismatch")

    git = attempt.get("git") or {}
    commit = git.get("commit")
    if not isinstance(commit, str) or len(commit) != 40:
        errors.append("Recorded Git commit is missing or malformed")
    else:
        result = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{commit}^{{commit}}"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode:
            errors.append("Recorded Git commit is unavailable in this repository")

    if require_clean and git.get("dirty") is not False:
        errors.append("Publication verification requires a clean Git worktree at launch")

    diff = git.get("tracked_diff") or {}
    content = diff.get("content")
    if not isinstance(content, str):
        errors.append("Tracked source diff content is missing")
    elif sha256_bytes(content.encode("utf-8")) != diff.get("sha256"):
        errors.append("Tracked source diff SHA-256 mismatch")

    for name, record in (attempt.get("launcher_environment") or {}).items():
        if not isinstance(record, dict) or not record.get("captured"):
            continue
        package_content = record.get("content")
        if not isinstance(package_content, str):
            errors.append(f"Launcher environment content missing: {name}")
        elif sha256_bytes(package_content.encode("utf-8")) != record.get("sha256"):
            errors.append(f"Launcher environment SHA-256 mismatch: {name}")

    return {
        "status": "PASS" if not errors else "FAIL",
        "scope": "record integrity and local availability; does not establish scientific validity",
        "attempt_commit": commit,
        "attempt_dirty": git.get("dirty"),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("provenance", type=Path)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--require-clean", action="store_true",
                        help="fail unless the launch-time Git worktree was clean")
    args = parser.parse_args()
    result = verify(args.provenance.resolve(), args.repo.resolve(), args.require_clean)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
