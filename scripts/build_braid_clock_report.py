#!/usr/bin/env python3
"""Build an offline Genome Braid / Ecological Clock report from Explorer JSON.

This does not run sequence analysis, alter source trees, or fetch phenology.
A phenology file is optional. Without it, ecological offsets remain unavailable.
"""
from __future__ import annotations
import argparse
from datetime import date
import math
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def load_json(path: Path):
    with path.open(encoding="utf-8-sig") as handle:
        return json.load(handle, object_pairs_hook=unique_object,
                         parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Invalid JSON number: {value}")))


def validate_phenology(raw: object) -> None:
    """Validate source intervals/provenance before embedding any phenology data."""
    if not isinstance(raw, dict) or raw.get("schema_version") != "wings.phenology.v1" or not isinstance(raw.get("profiles"), list) or not isinstance(raw.get("synthetic"), bool):
        raise ValueError("Phenology requires wings.phenology.v1, profiles[], and synthetic boolean.")
    def iso(value):
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("Phenology dates must be ISO YYYY-MM-DD.")
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError("Phenology dates must be ISO YYYY-MM-DD.")
        return result
    seen = set()
    for profile in raw["profiles"]:
        if not isinstance(profile, dict):
            raise ValueError("Every phenology profile must be an object.")
        identifier = profile.get("profile_id")
        if not isinstance(identifier, str) or not identifier.strip() or identifier in seen:
            raise ValueError("Phenology profile IDs must be nonempty and unique.")
        seen.add(identifier)
        for field in ("host", "country", "state"):
            if not isinstance(profile.get("scope", {}).get(field), str) or not profile["scope"][field].strip():
                raise ValueError(f"{identifier}: scope.{field} is required.")
        for field in ("source", "citation", "retrieved_on", "method"):
            if not isinstance(profile.get("provenance", {}).get(field), str) or not profile["provenance"][field].strip():
                raise ValueError(f"{identifier}: provenance.{field} is required.")
        iso(profile["provenance"]["retrieved_on"])
        if profile.get("baseline_kind") not in {"reference_season", "year_specific"}:
            raise ValueError("Unknown phenology baseline_kind.")
        if not isinstance(profile.get("measure"), str) or not profile["measure"].strip() or not isinstance(profile.get("unit"), str) or not profile["unit"].strip():
            raise ValueError("A phenology measure and unit are required.")
        start, end = iso(profile.get("season_start")), iso(profile.get("season_end"))
        if end < start:
            raise ValueError("Phenology season end precedes start.")
        if not isinstance(profile.get("bins"), list):
            raise ValueError("Phenology bins must be a list.")
        previous = None
        for bin_ in profile["bins"]:
            b, e = iso(bin_.get("start")), iso(bin_.get("end"))
            if b > e or b < start or e > end or (previous is not None and b <= previous):
                raise ValueError("Phenology bins must be ordered, nonoverlapping and inside the season.")
            if "value" not in bin_:
                raise ValueError("A bin requires value; use null when missing.")
            value = bin_["value"]
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0):
                raise ValueError("Bin values must be nonnegative finite numbers or null.")
            previous = e
        if profile.get("anchor") is not None:
            anchor = profile["anchor"]
            early, late = iso(anchor.get("earliest")), iso(anchor.get("latest"))
            if early > late or early < start or late > end or not anchor.get("label") or not anchor.get("basis"):
                raise ValueError("Supplied anchors require a valid interval, label and basis.")


def safe_json(value) -> str:
    # Prevent HTML script termination even when identifiers contain markup.
    return (json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


def report_html(payload: dict, assets: Path, *, allow_local_import=True) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get("samples"), list) or not isinstance(payload.get("trees"), dict):
        raise ValueError("Explorer JSON requires samples[] and trees{}.")
    if payload.get("ecological_clock") is not None:
        validate_phenology(payload["ecological_clock"])
    css = (assets / "genome-braid-clock.css").read_text(encoding="utf-8")
    js = (assets / "genome-braid-clock.js").read_text(encoding="utf-8")
    toolbar = '''<div class="standalone-tools"><b>WINGS</b><span>Local evidence workbench</span><label>Open Explorer JSON<input id="open-explorer" type="file" accept=".json,application/json"></label><span id="load-status" role="status">Offline &middot; no upload</span></div>''' if allow_local_import else ""
    return """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; font-src 'none'; base-uri 'none'; form-action 'none'">
<title>WINGS | Genome Braid &amp; Ecological Clock</title>
<style>body{margin:0;background:#eaf0ef;padding:20px;font-family:system-ui,sans-serif}.standalone-tools{max-width:1640px;margin:0 auto 16px;display:flex;gap:18px;align-items:center;color:#52666c;font-size:12px}.standalone-tools b{color:#8c1d40;font-size:19px;letter-spacing:.08em}.standalone-tools label{margin-left:auto;cursor:pointer;padding:8px 12px;background:#fff;border:1px solid #bacdce;border-radius:6px}.standalone-tools input{max-width:190px;margin-left:8px;font-size:11px}#load-status{max-width:300px;overflow-wrap:anywhere}.standalone-error{padding:30px;background:#fff;border:2px solid #8c1d40}.standalone-error p{white-space:pre-wrap}@media(max-width:600px){body{padding:0}.standalone-tools{padding:12px;flex-wrap:wrap}.standalone-tools label{margin-left:0}}</style>
<style>""" + css + """</style></head><body>""" + toolbar + """<main id="observatory"></main>
<script id="wings-braid-data" type="application/json">""" + safe_json(payload) + """</script><script>""" + js + """</script>
<script>
let dashboard;
function showData(data){
  const target=document.getElementById('observatory');
  try{dashboard=WINGS_BRAID_CLOCK.mount(target,data);return true;}
  catch(e){target.replaceChildren();const div=document.createElement('div');div.className='standalone-error';const h=document.createElement('h2');h.textContent='The preview could not read this dataset';const p=document.createElement('p');p.textContent=e.message;div.append(h,p);target.append(div);return false;}
}
showData(JSON.parse(document.getElementById('wings-braid-data').textContent));
document.getElementById('open-explorer')?.addEventListener('change',async function(){
  const f=this.files[0];if(!f)return;
  const status=document.getElementById('load-status');
  try{if(f.size>100000000)throw new Error('Explorer JSON exceeds the 100 MB preview limit.');const d=JSON.parse(await f.text());if(showData(d))status.textContent=f.name+' - local only';else status.textContent='Input validation failed.';}
  catch(e){status.textContent=e.message;}
  this.value='';
});
</script></body></html>"""


def build(explorer: Path, output: Path, assets: Path, phenology: Path | None = None) -> None:
    if output.resolve() in {explorer.resolve(), *( [phenology.resolve()] if phenology else [])}:
        raise ValueError("Output must not overwrite an input file.")
    data = load_json(explorer)
    if not isinstance(data, dict):
        raise ValueError("Explorer JSON must be an object.")
    if phenology:
        raw = load_json(phenology)
        if not isinstance(raw, dict) or raw.get("schema_version") != "wings.phenology.v1" or not isinstance(raw.get("profiles"), list) or not isinstance(raw.get("synthetic"), bool):
            raise ValueError("Phenology requires wings.phenology.v1, profiles[], and synthetic boolean.")
        # Full interval/provenance validation also runs in the browser before rendering.
        data["ecological_clock"] = raw
    data["braid_clock_build"] = {"version": "0.1.0", "explorer_sha256": hashlib.sha256(explorer.read_bytes()).hexdigest(),
                                 "phenology_sha256": hashlib.sha256(phenology.read_bytes()).hexdigest() if phenology else None}
    content = report_html(data, assets)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=output.parent, suffix=".tmp", encoding="utf-8", delete=False) as handle:
        tmp = Path(handle.name)
        handle.write(content)
    try:
        os.replace(tmp, output)
    finally:
        tmp.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--explorer", type=Path, required=True, help="Existing surveillance_explorer.json; never modified")
    parser.add_argument("--phenology", type=Path, help="Optional documented phenology profile JSON")
    parser.add_argument("--output", type=Path, default=Path("results/run_summary/braid_clock.html"))
    parser.add_argument("--assets-dir", type=Path, default=Path(__file__).resolve().parent / "report")
    args = parser.parse_args(argv)
    try:
        build(args.explorer, args.output, args.assets_dir, args.phenology)
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(f"Created offline preview: {args.output}")
    print("Source Explorer JSON and trees were not changed.")
    if not args.phenology:
        print("No external phenology supplied; ecological offsets require a matching profile.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
