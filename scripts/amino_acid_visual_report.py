"""Render WINGS protein results as a portable interactive SVG application."""
import html
import json
from pathlib import Path


def render_visual(data, tsv, output):
    names=[s['sample'] for s in data['samples']]
    if len(names)!=len(set(names)):
        raise ValueError('Report inputs contain duplicate sample IDs')
    assets=Path(__file__).parent/'report'
    css=(assets/'amino-acid-visual.css').read_text()
    js=(assets/'amino-acid-visual.js').read_text()
    safe=lambda obj:json.dumps(obj,ensure_ascii=True).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    text='''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>WINGS · Amino acid landscape</title><style>'''+css+'''</style></head><body>
<main><header><div><p class="eyebrow">WINGS / PROTEIN VARIATION</p><h1>Mutation &amp; coding landscape</h1><p class="intro">Explore protein changes. Each protein track uses its own reference amino acid positions; click a mutation for codon and nucleotide details.</p></div><div class="exports"><button id="download-svg">Save plot SVG</button><button id="download-tsv">Download TSV</button><button id="download-json">Download JSON</button></div></header>
<div id="stats" class="stats" aria-label="Report summary"></div>
<section class="panel controls" aria-label="Plot controls"><div><label for="search">Find a mutation or sample</label><input id="search" type="search" placeholder="Change, sample, position or evidence…"></div><div><label for="kind">Change type</label><select id="kind"><option value="all">All changes</option><option value="substitution">Substitutions</option><option value="insertion">Insertions</option><option value="deletion">Deletions</option><option value="stop_gain">Nonsense mutations</option></select></div><div><label for="frequency">Observed in samples</label><select id="frequency" title="Observed carriers divided by all selected samples. Missing or uncertain calls cannot meet the cutoff."><option value="80" selected>At least 80%</option><option value="0">All frequencies</option><option value="10">At least 10%</option><option value="25">At least 25%</option><option value="50">At least 50%</option><option value="90">At least 90%</option><option value="100">100%</option></select></div></section>
<section class="cohort-toolbar" aria-label="Comparison sample selection"><details class="sample-picker"><summary><span id="cohort-count">Comparison samples</span> · Edit selection</summary><div class="sample-picker-body"><label for="sample-search">Find samples</label><input id="sample-search" type="search" placeholder="Search barcode or collection date"><div class="section-label"><button id="all-samples" class="text-button">Select all samples</button><button id="no-samples" class="text-button">Clear selection</button></div><div id="samples" class="sample-list"></div></div></details></section>
<div class="workspace"><section tabindex="-1" id="segment-browser" class="panel plot-panel" aria-label="Combined mutation and coding landscape"><div class="plot-heading"><div><p class="eyebrow">MUTATIONS + CODING SEQUENCES</p><h2 id="plot-title">Mutation and coding landscape</h2><p id="reference-note" class="muted"></p></div></div>
<div class="genome-navigation"><div class="constellation-wrap"><p class="eyebrow">Genome constellation</p><div id="constellation-wheel" aria-label="Genome segment navigator"></div><p class="wheel-hint">Select a segment</p></div><div class="genome-controls"><label for="nav-sample">Displayed sample</label><select id="nav-sample"></select><p id="segment-summary" class="segment-summary" aria-live="polite"></p><select id="browser-record" hidden aria-hidden="true" tabindex="-1"></select><div id="comparison-reference" class="comparison-reference" aria-label="Comparison reference sequences"></div><div class="zoom"><label>From aa<input id="browser-from" type="number" min="1"></label><label>To aa<input id="browser-to" type="number" min="1"></label><button id="browser-zoom">Zoom</button><button id="browser-fit">Fit proteins</button><button id="browser-bases">Show residues</button></div></div></div>
<div class="legend"><span id="mutation-color-key" class="color-key"></span><span>● Observed change</span><span>◎ Cited annotation</span><span>◇ Insertion / deletion</span><span id="alignment-key" hidden>▧ Gray bands: uncertain alignment positions</span></div>
<p id="browser-message" role="status"></p><div id="browser-source" aria-live="polite"></div><div id="browser-plot" class="svg-scroll"></div>
</section>
</div>
<dialog id="mutation-dialog" aria-labelledby="mutation-dialog-title"><div class="dialog-heading"><h2 id="mutation-dialog-title">Mutation &amp; codon details</h2><button id="close-mutation-dialog" type="button" aria-label="Close mutation details">Close ×</button></div><div id="detail" aria-live="polite"></div><div id="browser-codon" aria-live="polite"></div></dialog>
<noscript>Enable JavaScript to explore this report. The TSV and JSON outputs are available beside the HTML file.</noscript></main>
<script id="aa-data" type="application/json">'''+safe(data)+'''</script><script id="aa-tsv" type="application/json">'''+safe(tsv)+'''</script><script>'''+js+'''</script></body></html>'''
    if data.get('demonstration'):
        text=text.replace('<main>', '<main><p class="panel"><strong>Synthetic demonstration — not sample results.</strong> All sequences, references, and changes shown here are illustrative.</p>',1)
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    Path(output).write_text(text)
