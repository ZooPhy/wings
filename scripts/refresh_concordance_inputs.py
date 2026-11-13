"""Attach verified refit inputs without replacing saved report comparisons."""
import copy
import json
import math

import refresh_demo_ui as ui


COMPARISON_FIELDS = ('n_samples', 'n_pairs', 'reduced_r2', 'full_r2', 'delta_r2')


def _models_match(saved, rebuilt):
    """Compare cohorts and fits, not randomized p values or display wording."""
    by_key = {(r.get('segment'), r.get('comparison')): r for r in rebuilt}
    if not saved:
        return False
    for original in saved:
        candidate = by_key.get((original.get('segment'), original.get('comparison')))
        if candidate is None or not all(k in original for k in COMPARISON_FIELDS):
            return False
        for key in COMPARISON_FIELDS:
            a, b = original[key], candidate.get(key)
            if a is None or b is None:
                if a is not b:
                    return False
            elif key in ('n_samples', 'n_pairs'):
                if a != b:
                    return False
            elif not math.isclose(a, b, rel_tol=1e-8, abs_tol=1e-10):
                return False
    return True


def _inputs_match(payload, concordance, inputs):
    """Only enable inputs that reproduce the saved comparisons for this run."""
    from build_genomic_ecological_concordance import compare_models, compare_migration_models
    pairs, features = inputs.get('pairs'), inputs.get('sample_features')
    if not isinstance(pairs, list) or not isinstance(features, list) or len(pairs) > 200000:
        return False
    known = {s['sample_id'] for s in payload['samples']}
    ids = [s.get('sample_id') for s in features]
    if len(set(ids)) != len(ids) or not set(ids).issubset(known):
        return False
    if any(p.get('sample_a') not in ids or p.get('sample_b') not in ids for p in pairs):
        return False
    minimum = (concordance.get('readiness') or {}).get('minimum_unique_samples', 8)
    try:
        models = compare_models(pairs, permutations=0, min_unique_samples=minimum)
        if any(r.get('comparison') == 'migration_vs_ecology' for r in concordance['models']):
            models.extend(compare_migration_models(pairs, features, permutations=0, min_unique_samples=minimum))
        return _models_match(concordance['models'], models)
    except (KeyError, TypeError, ValueError):
        return False


def enrich_report(source, concordance_data=None):
    parsed = ui.ReportHTML(source)
    replacements = []
    matched = False
    for block in parsed.blocks:
        if block['kind'] != 'script' or block['attrs'].get('type', '').lower() != 'application/json':
            continue
        try:
            payload = json.loads(parsed.body(block))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get('samples'), list):
            continue
        concordance = payload.get('genomic_ecological_concordance')
        if not isinstance(concordance, dict) or not isinstance(concordance.get('models'), list):
            continue
        existing = concordance.get('interactive_inputs')
        if concordance_data is None and existing and not existing.get('derived_from'):
            continue
        from attach_genomic_ecological_concordance import compact_concordance
        if concordance_data is not None:
            inputs = compact_concordance(concordance_data).get('interactive_inputs')
            if not _models_match(concordance['models'], concordance_data['models']):
                raise ValueError('The concordance.json does not match this report\'s saved comparisons')
            if inputs is None or not _inputs_match(payload, concordance, inputs):
                raise ValueError('The concordance.json inputs do not reproduce this report\'s saved comparisons')
            matched = True
        else:
            # Older runs can use separate phenology/weather files that are not
            # embedded in their report. Rebuilding blindly loses those inputs.
            from build_genomic_ecological_concordance import build_pairs
            pairs, features, _scaling = build_pairs(payload)
            inputs = compact_concordance({**concordance, 'pairs': pairs,
                                         'sample_features': features}).get('interactive_inputs')
            if inputs is not None and _inputs_match(payload, concordance, inputs):
                inputs['derived_from'] = 'Verified against saved comparisons using embedded trees, metadata and ecological context.'
            else:
                inputs = None
        before = copy.deepcopy(payload)
        if inputs is not None:
            inputs['synthetic'] = payload.get('synthetic') is True or (payload.get('ecological_clock') or {}).get('synthetic') is True
            concordance['interactive_inputs'] = inputs
        else:
            # Remove previously reconstructed inputs if they cannot be verified.
            # The browser keeps saved results and offers the original JSON loader.
            concordance.pop('interactive_inputs', None)
        check = copy.deepcopy(payload)
        for value in (before, check):
            value['genomic_ecological_concordance'].pop('interactive_inputs', None)
        if check != before:
            raise ValueError('Saved report analysis changed while adding interactive inputs')
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        encoded = encoded.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        if payload != json.loads(parsed.body(block)):
            replacements.append((block['start'], block['end'], encoded))
    if concordance_data is not None and not matched:
        raise ValueError('No saved concordance comparisons were found in this report')
    for start, end, replacement in sorted(replacements, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source
