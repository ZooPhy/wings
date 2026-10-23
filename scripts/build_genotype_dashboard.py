#!/usr/bin/env python3
"""Embed the existing genotype page and public snapshot in a portable report."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import re
from pathlib import Path


def collection_month(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}", value):
            date.fromisoformat(value + "-01")
            return value
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return date.fromisoformat(value).isoformat()[:7]
    except ValueError:
        pass
    return None


def recorded_call(record):
    """Copy recorded classifications, including explicit non-assignment states."""
    if not isinstance(record, dict):
        return "no_result", None, "NOT_RECORDED"
    status = str(record.get("status") or "NOT_RECORDED").strip().upper()
    call = str(record.get("call") or "").strip()
    if status == "DISABLED_BY_CONFIG":
        return "disabled", None, status
    if status in {"H5_OR_NA_INDETERMINATE", "NOT_ELIGIBLE", "INELIGIBLE"}:
        return "not_eligible", None, status
    if status.startswith("SKIPPED") or status == "NOT_RUN":
        return "not_run", None, status
    if status in {"ERROR", "FAILED"} or status.startswith("FAILED_"):
        return "failed", None, status
    if status in {"NOT_ASSIGNED", "UNASSIGNED"}:
        return "unassigned", None, status
    if status in {"RECORDED", "ASSIGNED"}:
        if call.lower() in {"not assigned", "unassigned", "unknown", "indeterminate", "not available"}:
            return "unassigned", None, status
        if not call:
            return "missing_call", None, status
        if not re.fullmatch(r"(?:[A-Z]\d+(?:\.\d+)*|Minor\d+)", call):
            return "unrecognized_call", None, status
        return "assigned", call, status
    return "no_result", None, status


def wings_snapshot(explorer: Path) -> dict:
    raw = explorer.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("samples"), list):
        raise ValueError("WINGS explorer must contain a samples array")
    host_names = defaultdict(set)
    for context in data.get("ebird_contexts", []):
        if isinstance(context, dict) and context.get("host") and context.get("species"):
            host_names[str(context["host"])].add(str(context["species"]))
    def text(value):
        value = str(value or "").strip()
        return "" if value.casefold() in {"unknown", "not recorded", "na", "n/a", "none", "null"} else value
    seen, groups, statuses = {}, Counter(), Counter()
    duplicates = 0
    for sample in data["samples"]:
        if not isinstance(sample, dict) or not text(sample.get("sample_id")):
            raise ValueError("Each WINGS sample needs a sample_id")
        sample_id = text(sample["sample_id"])
        status, call, raw_status = recorded_call(sample.get("genotype"))
        host = text(sample.get("host_common_name")) or text(sample.get("host_species"))
        code = text(sample.get("host"))
        if not host:
            names = host_names.get(code, set())
            host = next(iter(names)) if len(names) == 1 else code or "Not recorded"
        location = " / ".join(text(sample.get(key)) for key in ("country", "state") if text(sample.get(key))) or "Not recorded"
        record = (collection_month(sample.get("collection_date")), host, location, status, call, raw_status)
        if sample_id in seen:
            if seen[sample_id] != record:
                raise ValueError(f"Conflicting WINGS records for sample {sample_id}")
            duplicates += 1
            continue
        seen[sample_id] = record
        groups[record] += 1
        statuses[status] += 1
    return {
        "schema_version": "wings.genotype-frequencies.v1", "unit": "WINGS sample", "has_metadata": True,
        "universe": "Unique sample_id values in this WINGS run",
        "audit": {"included_samples": len(seen), "assigned_samples": statuses["assigned"],
                  "duplicate_records_collapsed": duplicates, "status_counts": dict(statuses)},
        "sources": [{"name": explorer.name, "sha256": hashlib.sha256(raw).hexdigest()}],
        "groups": [{"month": month, "host": host, "location": location, "status": status,
                    "genotype": call, "recorded_status": raw_status, "n": n}
                   for (month, host, location, status, call, raw_status), n in sorted(groups.items(), key=lambda item: str(item[0]))],
    }


RESIZE_SCRIPT = """document.addEventListener("DOMContentLoaded", () => {
  const main = document.querySelector("main");
  const measure = () => requestAnimationFrame(() => {
    if (!main || main.getBoundingClientRect().width < 1) return;
    parent.postMessage({type:"wings-genotype-height",
      height:Math.ceil(main.offsetTop + main.getBoundingClientRect().height + 24)}, "*");
  });
  if (typeof ResizeObserver !== "undefined" && main) new ResizeObserver(measure).observe(main);
  addEventListener("message", event => {
    if (event.source === parent && event.data?.type === "wings-genotype-measure") measure();
  });
  addEventListener("resize", measure);
  measure();
});
"""


def inline_script(text: str) -> str:
    return re.sub(r"</script", r"<\\/script", text, flags=re.IGNORECASE)


def build_dashboard(page: Path, styles: list[Path], script: Path, snapshot: Path, explorer: Path | None = None) -> str:
    raw = snapshot.read_bytes()
    if len(raw) > 25_000_000:
        raise ValueError("Genotype snapshot exceeds 25 MB")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("schema_version") != "wings.genotype-frequencies.v1":
        raise ValueError("Expected a WINGS genotype-frequency snapshot")
    data["report_snapshot"] = {"file_name": snapshot.name, "sha256": hashlib.sha256(raw).hexdigest()}
    source = page.read_text(encoding="utf-8")
    main = re.search(r"<main\b[^>]*>.*?</main>", source, flags=re.DOTALL | re.IGNORECASE)
    if main is None:
        raise ValueError("Genotype page has no main content")
    content = main.group(0).replace(
        '<a href="docs/genotype-frequencies.md" target="_blank" rel="noopener noreferrer">Refresh instructions</a>',
        "This report includes the public-data snapshot saved when its HTML was rendered.",
    )
    css = "\n".join(path.read_text(encoding="utf-8") for path in styles)
    if re.search(r"</style", css, re.IGNORECASE):
        raise ValueError("Unexpected closing style tag in chart CSS")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    local_script = ""
    if explorer is not None:
        local = json.dumps(wings_snapshot(explorer), ensure_ascii=False, separators=(",", ":"))
        local = local.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
        local_script = f'<script type="application/json" id="wings-genotype-local-data">{local}</script>'
    javascript = script.read_text(encoding="utf-8")
    if '"wings-genotype-frequency-data"' not in javascript:
        raise ValueError("Chart JavaScript needs embedded-snapshot support")
    return (
        '<!DOCTYPE html>\n<html lang="en"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Genotype frequencies | WINGS report</title>'
        f'<style>{css}</style></head><body>{content}'
        f'<script type="application/json" id="wings-genotype-frequency-data">{payload}</script>'
        f'{local_script}'
        f'<script>{inline_script(javascript)}</script>'
        f'<script>{RESIZE_SCRIPT}</script></body></html>\n'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", type=Path, required=True)
    parser.add_argument("--styles", type=Path, nargs="+", required=True)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--explorer-json", type=Path, help="Existing run explorer; copies recorded sample genotypes")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    html = build_dashboard(args.page, args.styles, args.script, args.snapshot, args.explorer_json)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(html, encoding="utf-8")
    temporary.replace(args.output)
    print(f"Embedded genotype dashboard: {args.output}")


if __name__ == "__main__":
    main()
