# Content-fitted protein plot spacing

Protein rows are packed using their SVG geometry and text bounds, with 12 SVG units at the top/bottom and 18 between rows. Browser SVG getBBox measurements keep visible mutation labels, axes, reference identity, amino acid letters and HA regions inside the exported view. Non-rendering test environments use conservative geometry estimates.

An available comparison with no visible mutations reserves no lollipop or rotated-label headroom. Alignment-uncertainty shading contracts to the baseline in that view. Proteins with unavailable calls still use compact HTML notices and do not reserve plotting rows. Filtering, zoom and displayed-sample changes recompute the layout.

This update changes display spacing only. Mutation calls, comparisons, references, exports' underlying data and settings are preserved. Rebuild only the report from existing saved results.
