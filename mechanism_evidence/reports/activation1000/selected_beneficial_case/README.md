# Selected Beneficial Case Study

- Figure: selected_beneficial_case.pdf / .png
- Caption: CAPTION.md
- Explanation and limitations: CASE_REPORT.md
- Exact criteria and source hashes: selection_metadata.json
- Every evaluated candidate round: candidate_selection_audit.csv
- Original selected category observations: semantic_evidence_raw.csv
- Original source scores: source_scores_raw.csv
- All adjusted regional shares: all_adjusted_regions_raw.csv
- Exact selected counterfactual records: full_counterfactual_case_raw.csv
- Displayed share summary: feature_union_shares.csv
- Every displayed receiver point: paired_utilities.csv
- Reproduction script: plot_selected_beneficial_case.py (also tools/plot_semantic_selected_beneficial.py)

Run from the repository root, with a new output directory:

```bash
python tools/plot_semantic_selected_beneficial.py --output /path/to/new_case_directory
```

No SGD, algorithm modification or source-data overwrite. Displayed aggregates are derived from unchanged original CSV rows. Source-level scores and Full receiver utility are matched at the entire changed-region union, not at a single parameter region. The numerical-term controls keep the original validity mask.
