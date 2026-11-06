# Metadata source cards

The Metadata step uses the same card pattern as Analysis: a checkbox, a title,
a short description, and a concise status. Checked means include the source.
Unchecked means skip its acquisition and omit its evidence from the prepared run.

One **Prepare context** action plans the scope and prepares the selected sources.
Technical provider reasons and per-sample warning lists are not rendered in this
step. They remain in saved context records and logs. Cards show Ready, Partial
coverage, Import needed, Access key needed, Unavailable, or Not selected. Coverage
counts are structured provider metrics, not interpreted diagnostic text.

Advanced settings contain matching windows, the supported seasonal reference,
and folder/file chooser buttons. Local Macs use a native chooser; Linux and SSH
sessions browse folders on the runner computer. Manual paths remain available.
The download folder is the primary eBird import; prepared eBird data is a secondary
option, and compatible caches are reused automatically by default.
There is no browser UI for required-source launch gates. Terminal callers retain
that option. Missing optional data does not prevent genomic analysis. All sources
can be unchecked; preparation still validates metadata and pins an explicit empty
public comparison so the workflow cannot silently use a bundled comparison.

Existing snapshots are not rewritten. After installation, restart an idle runner
and reload the local page. Select inputs, choose source cards and prepare again.
Source caches remain available. Preparation does not launch genomic jobs.

Checks: `node tests/test_context_setup_ui.cjs`, `node tests/test_context_picker_ui.cjs`, and
`python -m unittest discover -s tests -p 'test_context*.py'`.
