# Medaka status reporting

This document describes the missing-model handling and the corresponding run
report labels. The report summarizes recorded statuses; it does not recover
missing basecaller metadata or establish consensus accuracy.

## How to read the sample table

| Column | Meaning |
| --- | --- |
| Medaka Polished | Consensus status is `SUCCESS` and source is `MEDAKA`. |
| IRMA Fallback | Consensus source is `IRMA_FALLBACK`; this is not a successfully Medaka-polished result. |
| Medaka Failed | At least one recorded inference, consensus, or variant status is `FAILED`. Each segment is counted once. |
| Skipped: model unavailable | A recorded status identifies the missing-model condition. Each segment is counted once, even if multiple stages record it. |

The missing-model count uses inference or variant status `SKIPPED_NO_MODEL`, or
consensus status `UNPOLISHED` with reason `medaka_model_unavailable`. A generic
fallback result or an absent status file is not sufficient evidence of this reason.

These columns are not mutually exclusive. For example, eight missing-model
segments with recorded fallback results can appear as 0 polished, 8 IRMA fallback,
0 failed, and 8 skipped because the model was unavailable. That represents eight
segments, not sixteen. The review explanation states why polishing was skipped.

Only recorded evidence is counted. Zero failures does not mean polishing
completed, and missing status files do not establish success. Existing quality
control and other review reasons remain relevant.

## Missing-model handling and error handling

The resolver reserves exit code `3` for valid inspected input records without
the expected model metadata. This does not establish why the metadata is absent
or that it is absent from records beyond the inspected portion. Empty or malformed
input, unreadable input, missing files, and unexpected software errors must remain
distinct from ordinary metadata absence.

The current workflow records the missing-model condition as `SKIPPED_NO_MODEL`.
When a fallback consensus is produced for that condition, its status is
`UNPOLISHED`, its source is `IRMA_FALLBACK`, and its reason is
`medaka_model_unavailable`. The report preserves these distinctions and flags the
sample for review.

The current missing-model branch is independent of `medaka_fail_soft`: it can
continue with an unpolished fallback even when `medaka_fail_soft` is `false`.
That setting governs the separate handling of execution failures. Consequently,
`medaka_fail_soft=false` does not guarantee that every reported consensus was
Medaka-polished. This documentation records the existing behavior; the reporting
patch does not change that behavior.

## Report outputs

The run-level summary includes `medaka_skipped_no_model_segments`. The sample
table labels this count "Skipped: model unavailable". A positive count contributes
to `review_required` and an explicit missing-model explanation in `review_reason`,
including in the existing summary and review exports.

Existing generated HTML and report bundles retain their original contents until
the report is regenerated through the project's normal reporting process.
