"""Add refit inputs to a saved report using its existing trees and metadata."""
import copy
import json

import refresh_demo_ui as ui


def enrich_report(source):
    parsed = ui.ReportHTML(source)
    replacements = []
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
        if concordance.get('interactive_inputs'):
            continue
        # Import NumPy only when an older report needs inputs reconstructed.
        from build_genomic_ecological_concordance import build_pairs
        from attach_genomic_ecological_concordance import compact_concordance
        pairs, features, _scaling = build_pairs(payload)
        inputs = compact_concordance({**concordance, 'pairs': pairs,
                                     'sample_features': features}).get('interactive_inputs')
        if inputs is None:
            continue
        inputs['synthetic'] = payload.get('synthetic') is True or (payload.get('ecological_clock') or {}).get('synthetic') is True
        inputs['derived_from'] = 'Existing embedded trees, sample metadata and ecological context; no new trees or observations.'
        before = copy.deepcopy(payload)
        concordance['interactive_inputs'] = inputs
        check = copy.deepcopy(payload)
        del check['genomic_ecological_concordance']['interactive_inputs']
        if check != before:
            raise ValueError('Saved report analysis changed while adding interactive inputs')
        # Escaped markup cannot terminate a JSON script element.
        encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        encoded = encoded.replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
        replacements.append((block['start'], block['end'], encoded))
    for start, end, replacement in sorted(replacements, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source
