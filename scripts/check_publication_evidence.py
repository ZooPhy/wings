#!/usr/bin/env python3
"""Check a publication evidence inventory; never certify scientific validity."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys


SCHEMA = "wings.publication-evidence.v1"
ROLES = {"comparison", "real_data", "reproduction", "environment", "limitations"}
SHA256 = re.compile(r"[0-9a-f]{64}")
COMMIT = re.compile(r"[0-9a-f]{40}")
DISCLAIMER = (
    "This checks inventory completeness and file integrity only. It does not "
    "validate scientific claims, benchmark fairness, data permissions, or journal readiness."
)


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_manifest(manifest, root):
    """Return a JSON-serializable report without modifying inputs."""
    root = Path(root).resolve()
    errors = []
    checked = []
    roles = set()
    identifiers = set()
    paths = set()
    if not isinstance(manifest, dict):
        manifest = {}
        errors.append("Manifest must be a JSON object.")
    if manifest.get("schema_version") != SCHEMA:
        errors.append("Unsupported or missing schema_version.")
    if not isinstance(manifest.get("release_commit"), str) or not COMMIT.fullmatch(manifest["release_commit"]):
        errors.append("release_commit must be a full lowercase 40-character Git commit SHA.")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        errors.append("artifacts must be a list.")
        artifacts = []

    for index, artifact in enumerate(artifacts):
        prefix = "artifacts[{}]".format(index)
        before = len(errors)
        if not isinstance(artifact, dict):
            errors.append(prefix + " must be an object.")
            continue
        identifier = artifact.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            errors.append(prefix + " requires a nonempty id.")
        elif identifier in identifiers:
            errors.append(prefix + " has a duplicate id: " + identifier)
        else:
            identifiers.add(identifier)
        role = artifact.get("role")
        if not isinstance(role, str) or role not in ROLES:
            errors.append(prefix + " has an unsupported role.")
        if not isinstance(artifact.get("description"), str) or not artifact["description"].strip():
            errors.append(prefix + " requires a description of the evidence and its scope.")
        expected = artifact.get("sha256")
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            errors.append(prefix + " requires a lowercase SHA-256 digest.")
        relative = artifact.get("path")
        actual = None
        # POSIX relative paths make the inventory portable. Reject Windows paths
        # as well, even when this validator is running on Unix.
        if (not isinstance(relative, str) or not relative or "\\" in relative
                or ":" in relative or PurePosixPath(relative).is_absolute()
                or ".." in PurePosixPath(relative).parts):
            errors.append(prefix + " requires a relative path inside the evidence root.")
        else:
            try:
                candidate = (root / relative).resolve()
                candidate.relative_to(root)
                if candidate in paths:
                    errors.append(prefix + " duplicates another artifact path.")
                paths.add(candidate)
                if not candidate.is_file():
                    errors.append(prefix + " evidence file is missing or not a regular file: " + relative)
                elif candidate.stat().st_size == 0:
                    errors.append(prefix + " evidence file is empty: " + relative)
                else:
                    actual = sha256_file(candidate)
                    if actual != expected:
                        errors.append(prefix + " SHA-256 mismatch: " + relative)
            except ValueError:
                errors.append(prefix + " path resolves outside the evidence root.")
            except (OSError, RuntimeError) as exc:
                errors.append(prefix + " cannot read evidence: " + str(exc))
        valid = len(errors) == before
        if valid:
            roles.add(role)
        checked.append({"id": identifier, "role": role, "path": relative,
                        "actual_sha256": actual, "valid": valid})

    missing = sorted(ROLES - roles)
    if missing:
        errors.append("Missing verified evidence roles: " + ", ".join(missing))
    return {"schema_version": SCHEMA, "release_commit": manifest.get("release_commit"),
            "inventory_status": "PASS" if not errors else "FAIL",
            "scope": DISCLAIMER, "artifacts": checked,
            "missing_roles": missing, "errors": errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--root", type=Path, help="Evidence root; defaults to the manifest's directory")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(json.dumps({"inventory_status": "FAIL", "scope": DISCLAIMER,
                          "errors": ["Cannot read manifest: " + str(exc)]}, indent=2))
        return 1
    result = check_manifest(manifest, args.root if args.root is not None else args.manifest.parent)
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0 if result["inventory_status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
