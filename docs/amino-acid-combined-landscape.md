# One mutation and coding canvas

The lollipop plot and CDS browser are now a single SVG canvas, with one set of sample/segment and nucleotide zoom controls. Each CDS has its own row: mutation lollipops above its annotated coding blocks, with translated residues shown when zoomed to bases. The detail inspector remains beside this shared canvas. The separate protein plot, sample-track panel and stand-alone segment-browser panel are removed.

## Coordinates and frequency

The horizontal axis is the stored consensus nucleotide coordinate system of the selected **coordinate sample**. Each mutation label still uses the selected reference protein's amino acid numbering. Do not read an amino acid label such as Q74K as nucleotide position 74.

The mutation's reference position is mapped through the coordinate sample's protein alignment and codon map. For a present substitution, insertion or stop gain, the lollipop root is the first nucleotide of its codon in biological coding order. A splice-spanning codon is anchored to its first actual nucleotide; clicking shows all three true positions. Reverse-strand codons retain descending stored-consensus coordinates. No averaging of codon positions across introns is used.

An indel without a physical altered codon in the coordinate sample is shown at a flanking boundary using a hollow diamond. Deleted residues never receive an invented sample codon. If a change is present in other selected samples but absent from the coordinate sample, it can appear at the aligned site; the detail card explicitly identifies it as absent from the coordinate sample. A site with ambiguous residues, a withheld comparison or an unsupported codon map is not projected. The status line counts withheld projections.

Marker height and fractions represent distinct selected carrier samples / distinct selected samples assessed at the reference site. This is the same position-specific frequency as the previous report. Selecting a coordinate sample changes where markers are drawn, not the cohort used for counts. Samples remain independently selectable using the sample chips. Reference sequences are not pooled across incompatible panels.

## Interaction

- The initial segment is chosen to show available changes when coordinate maps exist.
- **Go to protein / reference** navigates to the corresponding segment and highlights its CDS row. All annotated CDS rows on that segment remain visible, including overlapping genes.
- Click a lollipop for evidence, carrier samples and highlighted codon bases in the same plot.
- **Zoom to codon** zooms the shared canvas; **Fit segment** shows all mutation/CDS tracks. **Show bases** shows a nucleotide window around the highlighted site.
- Clicking a translated CDS residue can select its plotted mutation. Search, mutation type and sample filters apply to markers across all CDS rows in view.
- **Save plot SVG** exports the complete combined canvas.

Rebuild an existing report using the same `python scripts/wings_amino_acids.py report` command and sample JSON inputs. This is a presentation update: no amino acid recomputation is needed if the JSON files already contain `segment_sequences` and `codon_map` from the segment-browser update. Older JSON files display an explicit regeneration message instead of a detached plot.

The update preserves the amino acid analysis code and its data schema. It makes no network requests, adds no new phenotype annotations, and does not infer epitope/domain boundaries.
