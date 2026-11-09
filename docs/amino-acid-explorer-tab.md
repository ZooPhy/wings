# Amino acids in Surveillance Explorer

The Amino acids tab follows Genome. Saved reports are embedded as a portable template and loaded on first activation; tab switches retain cohort, wheel, zoom and filter state. The report has its own sample controls and defaults to All samples / at least 80%.

Refresh an existing demo without rerunning analyses:

    python scripts/install_amino_explorer_tab.py --apply

If the demo has no saved amino acid report, supply --amino-report PATH. The compressed demo is canonical; an existing local uncompressed copy is synchronized but never added to Git by this script.
