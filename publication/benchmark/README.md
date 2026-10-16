# WINGS benchmark package

This directory contains the prospective Genome Biology validation protocol and tabular schemas. It contains no benchmark results.

Before executing any comparator:

1. Copy each `*.template.tsv` file to the corresponding filename without `.template`.
2. Replace every placeholder and create the per-dataset input manifests.
3. Have the biological truth definitions, comparator choices, endpoints, exclusions, and numeric acceptance margins reviewed.
4. Commit the frozen protocol and manifests on a dedicated evaluation tag.
5. Run every workflow attempt through the immutable attempt ledger, including failures and changed-parameter retries.

The existing 12-sample run belongs in the real-world case cohort. Its successful completion supports feasibility; without independent truth it does not establish consensus accuracy.
