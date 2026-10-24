# Semantic-A07 V2: existing 1000-round evidence

Only `v2_active1000_seed1` is published. No 500-round or other historical run data, model weights, images or new experiments are included. All 1000 recorded rounds and all 53 fixed diagnostic rounds are retained, including favorable, unfavorable and neutral observations.

## Files

- `logs/v2_active1000_seed1/`: original Accuracy/CE CSV, manifests, complete scalar journals and collected tables.
- `memory/v2_active1000_seed1/`: all recorded current class candidates, eligibility, past references and actual Memory commits.
- `aggregation/v2_active1000_seed1/`: actual region definitions, applied/virtual source shares and per-round decisions.
- `counterfactual/v2_active1000_seed1/`: existing same-input receiver CE, full counterfactuals, norms and cohort metadata.
- `reports/activation1000/`: existing figures, plot input tables, figure code, selection audits and reports. Outcome-selected examples are labeled; raw observations remain complete.
- `code_used/149c6713c339204ad23fe43952350ae2832b3cd0/`: frozen training code, with snapshot hashes and explicit private-path-only publication redactions.
- `provenance/`: protocol, source checks, schedules, export tools and missing-data documentation.
- `checkpoints/`: inventory and verified hashes only; no binary models.

## Definitions

V2 uses task-classifier true-label probabilities, not Adapter embeddings, for U. Adapter/frozen-head Prototypes are auxiliary observations. At class level, d=max(0,q_post-q_pre), a=max(0,q_post-other_past_reference), u=rho*min(d,a); U is the macro mean of eligible classwise u. It is not mean(rho)*mean(min(d,a)). Missing scores remain blank and do not imply negative contribution. Semantic/ Reliability references are past-only; current observations are committed after scoring.

Tier identities are physical clients 0-39 / 40-69 / 70-99. Seven profiles remain (0.40,2),(0.40,3),(0.40,4),(0.66,2),(0.66,3),(0.66,4),(1.00,2). Duplicate slots preserve separate original SGD updates but do not create independent semantic votes.

The first round is Native. Base A07 uses inverse-square-root tier mass within actual coverage regions, sample weighting within tiers, Native classifier, and A07 BN. Semantic lambda is 0.2 on eligible shared feature/non-BN regions; missing or incomparable evidence is neutral. pi_sem in the exported table is the final applied blended share, not the intermediate (1+U)-normalized target. Virtual shares are distinguished from applied ones. Source mass is filled only from exact existing receiver records.

`utility=CE_before-CE_after` is positive for benefit. `utility_vs_a07=CE_after_A07-CE_after_variant` is positive for improvement over same-input A07. Receiver/cohort records are not independent semantic samples. Probe samples are disjoint from semantic measurement but still belong to original SGD training data; they are not an SGD-held-out validation set. Per-class CE and all-class/common-class definitions remain in original records.

`pre_state_hash` is recorded previous Full state; `client_updates_hash` is an ordered-index hash of already-recorded upload hashes, not a tensor bundle. Counterfactual Accuracy was not recorded. Exact historical uploads cannot be recovered from CSV. See missing_data_report.md.

Large logs are complete lossless gzip streams. `gzip -dc file.jsonl.gz` restores the full public logical content. Original/private-root and public hashes are separately indexed. No numeric observations were changed. The original local/server files were preserved. Single-seed test-oracle peaks and selected positive figures do not establish unbiased generalization or average semantic benefit.
