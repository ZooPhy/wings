# Porechop native repairs

These manual utilities accompany the desktop 0.1.14 source snapshot. They are
not invoked automatically by the launcher, installer or workflow.

`WINGS-Repair-Porechop-Native.command` (v4) supersedes the counter-only repair
for the reported Linux AMD64 native-library failures on Apple Silicon.
Keep Docker and the WINGS service running with no active jobs. The utility
first requires an installed native probe to reproduce SIGILL. It builds all
four native components from checksum-pinned upstream source with baseline
x86-64 flags, corrects the help-text warning, uses the bundled zlib headers,
and disables the optional SeqAn version check. Analysis defaults are retained.

It tests compatibility, alignment, consensus, trimming and a complete synthetic
inference-to-trimming run before installation and repeats checks afterward.
Original binaries are backed up; failed installation checks trigger rollback.
The script modifies the selected workspace's environment, not the source repo.
Resume a failed job only after PASS. Other environments and new installations
are not repaired by running this utility once.

Local validation: header isolation, real counting of 50,000 synthetic gzip reads,
native compatibility/alignment/MSA/consensus/trimming probes, and rollback tests.
The complete Python pipeline must pass in the target environment; it was not
validated end-to-end in the preparation environment, which lacked NetworkX.
The affected Mac reported that v4 was running, but its final outcome is pending.

Do not describe an automatically repaired desktop release as available until
this work is integrated into setup and exercised on the supported host matrix.
Upstream source and GPL license are retained by the repair with build provenance.
