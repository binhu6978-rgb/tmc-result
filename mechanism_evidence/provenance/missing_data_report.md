# 1000-round saved-state limitations

- Existing final recovery checkpoint and verified Full-state hashes are inventoried; no model weights are uploaded by user request.
- Historical per-slot upload tensors and historical A07/V2 post-aggregation Full states were NOT_SAVED. Existing scalar CE, update norms and hashes are retained; arbitrary new historical counterfactuals cannot be reconstructed from CSV.
- Raw images, materialized probes, private sample indices and credentials are excluded.
- Probe Accuracy was not recorded: fields remain blank. Probe CE is available for the fixed 53 diagnostic rounds.
- Source masses absent from the original records remain blank; no inverse estimates were made from normalized shares.
- Missing runtime uncommitted diffs remain NOT_SAVED. Exact executed source hashes are checked separately.
- This release contains only the 1000-round run. The 500-round runs and other historical executions are outside the latest requested scope, not deleted from original storage.
