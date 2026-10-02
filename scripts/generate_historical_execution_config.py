#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path


WORKSPACE_FORMAT = "WINGS_REEXECUTION_WORKSPACE"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(
        f".{path.name}.tmp-{os.getpid()}"
    )

    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        temp.replace(path)
    finally:
        if temp.exists():
            temp.unlink()


def resolve_workspace_path(
    workspace: Path,
    relative_text: str,
) -> Path:
    relative = Path(relative_text)

    if relative.is_absolute():
        raise ValueError(
            f"Workspace path must be relative: {relative_text}"
        )

    resolved = (workspace / relative).resolve()

    try:
        resolved.relative_to(workspace)
    except ValueError as error:
        raise ValueError(
            f"Workspace path escapes workspace: {relative_text}"
        ) from error

    return resolved


def verified_replay_input(
    workspace: Path,
    replay_inputs: dict,
    label: str,
) -> Path:
    record = replay_inputs.get(label)

    if not isinstance(record, dict):
        raise ValueError(
            f"Historical replay input is unavailable: {label}"
        )

    restored_path = str(
        record.get("restored_path", "")
    ).strip()
    expected_sha = str(
        record.get("sha256", "")
    ).strip().lower()

    if not restored_path:
        raise ValueError(
            f"Historical replay input has no restored path: {label}"
        )

    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        raise ValueError(
            f"Historical replay input has invalid SHA-256: {label}"
        )

    path = resolve_workspace_path(
        workspace,
        restored_path,
    )

    if not path.is_file():
        raise FileNotFoundError(
            f"Restored historical input is missing: {path}"
        )

    observed = sha256_file(path)
    if observed != expected_sha:
        raise ValueError(
            f"Restored historical input changed: {label}"
        )

    return path


def safe_symlink(
    source: Path,
    destination: Path,
) -> None:
    source = source.resolve()

    if destination.is_symlink():
        if destination.resolve() != source:
            raise ValueError(
                f"Existing symlink points elsewhere: {destination}"
            )
        return

    if destination.exists():
        raise ValueError(
            f"Refusing to replace existing path: {destination}"
        )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    destination.symlink_to(source)


def safe_pattern_path(
    root: Path,
    rendered: str,
) -> Path:
    relative = Path(rendered)

    if relative.is_absolute():
        raise ValueError(
            f"Input pattern produced absolute path: {rendered}"
        )

    destination = (root / relative).resolve(
        strict=False
    )

    try:
        destination.relative_to(root.resolve())
    except ValueError as error:
        raise ValueError(
            f"Input pattern escapes staging directory: {rendered}"
        ) from error

    return destination


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a safe current-code/historical-inputs "
            "WINGS execution configuration."
        )
    )
    parser.add_argument(
        "--workspace",
        required=True,
        type=Path,
    )
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()

    try:
        manifest_path = (
            workspace / "reexecution_manifest.json"
        )
        manifest = read_json(manifest_path)

        if manifest.get("format") != WORKSPACE_FORMAT:
            raise ValueError(
                f"Invalid re-execution workspace: {workspace}"
            )

        snapshot_id = str(
            manifest.get("snapshot_id", "")
        ).strip()

        if not re.fullmatch(r"[0-9a-f]{64}", snapshot_id):
            raise ValueError(
                f"Invalid historical snapshot ID: {snapshot_id!r}"
            )

        historical_config_path = (
            workspace / "historical_effective_config.json"
        )
        historical_config = read_json(
            historical_config_path
        )

        # JSON round trip gives us a deep copy of the preserved config.
        execution_config = json.loads(
            json.dumps(historical_config)
        )

        replay_inputs = manifest.get("replay_inputs")
        if not isinstance(replay_inputs, dict):
            raise ValueError(
                "Workspace has no restored replay inputs."
            )

        primary_inputs = manifest.get("primary_inputs")
        if not isinstance(primary_inputs, dict) or not primary_inputs:
            raise ValueError(
                "Workspace has no verified primary inputs."
            )

        #
        # Stage raw reads as symlinks.
        #
        reads_pattern = str(
            historical_config.get(
                "reads_pattern",
                "{sample}.fastq.gz",
            )
        )

        if "{sample}" not in reads_pattern:
            raise ValueError(
                "Historical reads_pattern has no {sample} wildcard."
            )

        primary_root = workspace / "primary_inputs"
        primary_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        staged_primary: dict[str, dict[str, object]] = {}

        for sample in sorted(primary_inputs):
            record = primary_inputs[sample]

            if not isinstance(record, dict):
                raise ValueError(
                    f"Invalid primary-input record: {sample}"
                )

            source_text = str(
                record.get("verified_source_path", "")
            ).strip()
            expected_sha = str(
                record.get("sha256", "")
            ).strip().lower()

            source = Path(source_text).expanduser().resolve()

            if not source.is_file():
                raise FileNotFoundError(
                    f"Primary sequencing input disappeared: {source}"
                )

            if sha256_file(source) != expected_sha:
                raise ValueError(
                    "Primary sequencing input changed after workspace "
                    f"preparation: {sample}"
                )

            rendered = reads_pattern.replace(
                "{sample}",
                sample,
            )

            if "{" in rendered or "}" in rendered:
                raise ValueError(
                    "Historical reads_pattern contains unsupported "
                    f"wildcards: {reads_pattern}"
                )

            destination = safe_pattern_path(
                primary_root,
                rendered,
            )

            safe_symlink(
                source,
                destination,
            )

            staged_primary[sample] = {
                "source_path": str(source),
                "workspace_path": destination.relative_to(
                    workspace
                ).as_posix(),
                "sha256": expected_sha,
                "size_bytes": source.stat().st_size,
            }

        #
        # Mandatory metadata boundary.
        #
        metadata_path = verified_replay_input(
            workspace,
            replay_inputs,
            "metadata",
        )

        execution_results = workspace / "results"
        execution_results.mkdir(
            parents=True,
            exist_ok=True,
        )

        execution_config["reads_dir"] = str(
            primary_root
        )
        execution_config["reads_pattern"] = reads_pattern
        execution_config["results_dir"] = str(
            execution_results
        )
        execution_config["metadata_file"] = str(
            metadata_path
        )

        # phylogeny_dir is not necessarily under results_dir in ordinary
        # WINGS configurations, so force it into the isolated result tree.
        execution_config["phylogeny_dir"] = str(
            execution_results / "phylogeny"
        )

        #
        # Record every restored replay artifact in the execution config.
        #
        frozen_inputs: dict[str, str] = {}

        for label in sorted(replay_inputs):
            frozen_inputs[label] = str(
                verified_replay_input(
                    workspace,
                    replay_inputs,
                    label,
                )
            )

        execution_config["historical_reexecution"] = {
            "enabled": True,
            "snapshot_id": snapshot_id,
            "mode": "current_code_historical_inputs",
            "frozen_inputs": frozen_inputs,
        }

        #
        # Public-reference boundary.
        #
        historical_public = (
            historical_config.get("public_references")
            or {}
        )
        if not isinstance(historical_public, dict):
            raise ValueError(
                "Historical public_references config is invalid."
            )

        reference_manifest = replay_inputs.get(
            "public_reference_manifest"
        )
        reference_provenance = replay_inputs.get(
            "public_reference_provenance"
        )

        tree_labels = sorted(
            label
            for label in replay_inputs
            if label.startswith("public_reference_tree_")
        )

        if historical_public.get("enabled"):
            if (
                not isinstance(reference_manifest, dict)
                or not isinstance(reference_provenance, dict)
            ):
                raise ValueError(
                    "Historical public references were enabled but "
                    "their frozen manifest/provenance are unavailable."
                )

        if (
            isinstance(reference_manifest, dict)
            and isinstance(reference_provenance, dict)
        ):
            public_config = dict(historical_public)

            public_config["enabled"] = True
            public_config["build_contextual"] = False

            public_config["manifest"] = str(
                verified_replay_input(
                    workspace,
                    replay_inputs,
                    "public_reference_manifest",
                )
            )
            public_config["provenance"] = str(
                verified_replay_input(
                    workspace,
                    replay_inputs,
                    "public_reference_provenance",
                )
            )

            # Remove source data that would permit accidental rebuilding.
            public_config.pop("source_fasta", None)
            public_config.pop("source_metadata", None)

            frozen_reference_root = (
                workspace
                / "frozen"
                / "public_references"
            )
            tree_dir = (
                frozen_reference_root / "trees"
            )

            tree_pattern = str(
                public_config.get(
                    "tree_pattern",
                    "{segment}_Tree.newick",
                )
            )

            if tree_labels and "{segment}" not in tree_pattern:
                raise ValueError(
                    "Historical public-reference tree pattern "
                    "has no {segment} wildcard."
                )

            for label in tree_labels:
                segment = label.removeprefix(
                    "public_reference_tree_"
                )

                source = verified_replay_input(
                    workspace,
                    replay_inputs,
                    label,
                )

                rendered = tree_pattern.replace(
                    "{segment}",
                    segment,
                )

                if "{" in rendered or "}" in rendered:
                    raise ValueError(
                        "Unsupported public-reference tree wildcard: "
                        f"{tree_pattern}"
                    )

                destination = safe_pattern_path(
                    tree_dir,
                    rendered,
                )

                safe_symlink(
                    source,
                    destination,
                )

            if tree_labels:
                public_config["tree_dir"] = str(
                    tree_dir
                )

            public_config["work_dir"] = str(
                frozen_reference_root
            )

            execution_config[
                "public_references"
            ] = public_config

        #
        # Frozen ecological context.
        #
        if "ecological_context" in replay_inputs:
            ecology = (
                historical_config.get(
                    "ecological_context"
                )
                or {}
            )
            if not isinstance(ecology, dict):
                ecology = {}

            ecology = dict(ecology)
            ecology["enabled"] = True
            ecology["snapshot"] = frozen_inputs[
                "ecological_context"
            ]

            execution_config[
                "ecological_context"
            ] = ecology

        #
        # Frozen surveillance-effort input.
        #
        if "surveillance_effort" in replay_inputs:
            effort = (
                historical_config.get(
                    "surveillance_effort"
                )
                or {}
            )
            if not isinstance(effort, dict):
                effort = {}

            effort = dict(effort)
            effort["enabled"] = True
            effort["file"] = frozen_inputs[
                "surveillance_effort"
            ]

            execution_config[
                "surveillance_effort"
            ] = effort
            execution_config[
                "surveillance_effort_file"
            ] = frozen_inputs[
                "surveillance_effort"
            ]

        #
        # Frozen APHIS outbreak snapshot.
        #
        if "aphis_snapshot" in replay_inputs:
            outbreak = (
                historical_config.get(
                    "outbreak_context"
                )
                or {}
            )
            if not isinstance(outbreak, dict):
                outbreak = {}

            outbreak = dict(outbreak)
            outbreak["enabled"] = True
            outbreak["csv"] = frozen_inputs[
                "aphis_snapshot"
            ]

            if "aphis_provenance" in replay_inputs:
                outbreak["provenance"] = frozen_inputs[
                    "aphis_provenance"
                ]

            execution_config[
                "outbreak_context"
            ] = outbreak

        #
        # Phenology is consumed from the frozen historical product rather
        # than regenerated from the current eBird Status & Trends cache.
        #
        if "phenology" in replay_inputs:
            phenology = (
                historical_config.get("phenology")
                or {}
            )
            if not isinstance(phenology, dict):
                phenology = {}

            phenology = dict(phenology)
            phenology["enabled"] = False

            execution_config["phenology"] = phenology

        #
        # eBird summary/attribution is frozen. Disable all cache-building
        # dependencies and remove external filesystem paths.
        #
        if "ebird_context" in replay_inputs:
            ebird = historical_config.get("ebird") or {}
            if not isinstance(ebird, dict):
                ebird = {}

            ebird = dict(ebird)
            ebird["enabled"] = False
            ebird["build_cache"] = False

            for key in (
                "cache_dir",
                "observations_file",
                "sampling_file",
                "release_dir",
            ):
                ebird.pop(key, None)

            execution_config["ebird"] = ebird

        execution_config_path = (
            workspace / "execution_config.json"
        )

        atomic_write_json(
            execution_config_path,
            execution_config,
        )

        execution_config_sha = sha256_file(
            execution_config_path
        )

        manifest["primary_inputs"] = {
            sample: {
                **primary_inputs[sample],
                "workspace_path": staged_primary[
                    sample
                ]["workspace_path"],
            }
            for sample in sorted(primary_inputs)
        }

        manifest["execution_config"] = {
            "path": "execution_config.json",
            "sha256": execution_config_sha,
        }
        manifest["execution_results_dir"] = (
            execution_results.relative_to(
                workspace
            ).as_posix()
        )
        manifest["execution_config_generated"] = True
        manifest["dry_run_validated"] = False

        # This remains false until a separate Snakemake dry-run validator
        # successfully constructs the complete DAG.
        manifest["launch_ready"] = False

        atomic_write_json(
            manifest_path,
            manifest,
        )

    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
    ) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print(f"Historical snapshot: {snapshot_id}")
    print(
        "Primary sequencing inputs staged: "
        f"{len(staged_primary)}"
    )
    print(
        "Frozen replay inputs mapped: "
        f"{len(frozen_inputs)}"
    )
    print(
        f"Execution config: {execution_config_path}"
    )
    print(
        f"Execution results: {execution_results}"
    )
    print("Execution config generated: YES")
    print("Dry-run validated: NO")
    print("Launch ready: NO")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
