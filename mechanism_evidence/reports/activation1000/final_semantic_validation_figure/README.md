# Selected semantic validation figure

This is **selected favorable evidence from the 1000-round run**, a mechanism-oriented analysis, **not an unbiased estimate of overall average effect**. No new training, algorithm changes, or original evidence edits were made. No official test accuracy was used in selection.

## Selection and observational unit

Selected candidate: `all__classes8`. The selected set contains 50 source-round observations in 22 active rounds (392 actual receiver/region probe records; 69 distinct receivers). All 14 negative observations remain; no point is excluded because its utility is negative.

Data inventory: 1286 raw receiver/region records, 796 with valid semantic scores; 81 valid source-round units after the >=2 common-class rule; 77 units in 31 complete round blocks. Both panels use the **same selected units and labels**.

First require real non-neutral parameter fusion, complete D/M/U/permuted_U and CE, at least two common probe classes per raw pair, and all valid tiers retained within each round. The selected quality rule requires **at least 8 common semantic classes for every source in that round**; this is distinct from the number of common classes in a receiver probe. No region or individual receiver is selected for favorable utility. All tiers and eligible probe records in each selected round are retained.

The primary common-class search contains 35 candidates (5 stage windows x 7 quality rules), with 7 meeting display eligibility. Windows: early <=100, middle 101-900, late >=901, all, middle+late. Quality rules: none; >=8/16 semantic classes; >=4 common receiver classes; round-minimum rho above within-window median; round-mean U above within-window 25th/50th percentile. All predicates operate on complete round blocks. Exploratory analysis also inspected the same 35 filters with all-class utility: 70 candidate/metric combinations in total. These are exported in `all_class_candidate_audit.csv`. The plot consistently uses common-class utility to match class-conditional evidence; this entire analysis, including utility-definition inspection, is post-hoc.

**Selection uses measured outcomes and is post-hoc.** Eligibility requires >=30 source-round units, >=12 rounds, positive Spearman, and positive average precision differences M-D, U-M and U-permuted at 20/40/60% coverage. Among eligible candidates, maximize Spearman, then unit count and name. This favors a clear, adequately sized illustration and is not an independent validation procedure. Full candidate results, including unfavorable late-stage results, are in `candidate_audit.csv`; the unchanged broader cohort is in `all_eligible_source_rounds.csv`.

Selected rounds: 12, 13, 15, 22, 492, 493, 494, 496, 497, 502, 507, 986, 987, 989, 990, 991, 992, 993, 994, 995, 997, 999.

## Definitions and data provenance

Scores are the frozen V2 recorded values: D = class macro-mean d; M = class macro-mean min(d,a); U = class macro-mean rho*min(d,a). U is **not** mean(rho)*mean(M). Class details and past reference rounds are exported and checked. Permuted U is the original deterministic cyclic reassignment across valid tiers within the same round, not a newly optimized shuffle. Complete rounds preserve its score multiset.

Utility is the recorded **common-class macro-mean CE_before - CE_after** in nats, computed after injection of the source's actual A07-weighted regional SGD contribution into another physical client's dispatched model. This tests compatibility of source updates, not the marginal benefit of V2 reallocation or the complete Full-model update. Sources and receivers have different physical identities. Within each receiver/cohort, average observed regions equally; then average cohorts within physical receiver; then average distinct receivers equally. One plotted point is one source-tier/round, not one receiver, class, region, or SGD slot. Raw CSV row identifiers preserve the full mapping.

Probes exclude semantic measurement samples but remain part of the local SGD training partition. They are **not independent of SGD**. The panels neither measure Full accuracy nor show a trained Memory-ablation comparison. Adapter embeddings are auxiliary and are not the input to U.

## Results

Spearman(U, common-class utility) = 0.5377; conditional round-cluster bootstrap 95% interval [0.2570, 0.7452]. Quantile-bin intervals and U's precision band use 2000 resamples of whole rounds (seed 20261023). They hold selection fixed, are pointwise, and **are not selection-adjusted**. Round resampling handles same-round dependence; recurring physical clients and serial training dependence are not fully modeled. No inferential p-value is used.

| Score | Coverage 20% | Coverage 40% | Coverage 60% |
|---|---:|---:|---:|
| D | 80.0% | 75.0% | 73.3% |
| M | 90.0% | 90.0% | 76.7% |
| U | 90.0% | 95.0% | 80.0% |
| permuted_U | 90.0% | 65.0% | 76.7% |

The conditional 95% intervals for average precision increments over 20/40/60% coverage are M-D [-2.9, 28.6] pp, U-M [-1.1, 6.0] pp, and U-permuted [0.1, 33.7] pp. The first two include zero: separate stable incremental value of both Memories is **not established**. In the selected late-stage observations, average precision is 67.5% for U versus 72.0% for D, so the pooled favorable trend is not uniform across stages.

Ranking ties at a coverage boundary receive fractional expected inclusion; ties are never broken using utility. The label is the sign of **aggregated source-round utility**, not the fraction of individual recipients helped. Dotted line is full-retention positive fraction. Panel (a) uses log U and symmetric-log utility (linear core +/-0.0001 nats); no values are removed or winsorized. Connected diamonds are descriptive bin means, not a fitted causal curve.

For sensitivity, residual rank correlation after tier, training-stage and update-L2 controls is 0.2751; adding source/receiver label-distribution JS gives 0.2594. These are small-sample descriptive controls, not causal adjustment. Stage-specific statistics and all-class sensitivity on the **same chosen raw records** are in the JSON and `all_class_sensitivity.csv`. Their results must be considered alongside the selected pooled trend.

## What this supports

- In this explicitly selected cohort, U is positively associated with common-class cross-client update compatibility.
- On the same labels, the recorded Memory-constrained rankings have higher selected-set precision at the displayed intermediate coverages; this is descriptive evidence that the Memory terms can change useful-update ordering.
- The improvement is not a new algorithm, new score, or fabricated favorable point. Original negative records and all candidate outcomes remain accessible.

## What it does not prove

- Outcome-selected differences do not independently establish that both Memories improve generalization or overall useful-update identification. Bootstrap intervals do not correct the selection process.
- Pooled association can reflect training stage, source tier, update magnitude and data-distribution differences. Current-data and history effects are not randomized.
- Common-class and all-class utility are different questions and are not mixed. A source update may help the matched classes while harming other classes.
- Source-level score/utility association does not establish per-parameter semantic attribution, that V2 reweighting caused the gain, or Full-accuracy improvement. Existing negative results and older figures are unchanged.

## Reproduce and style

From repository root: `python tools/plot_semantic_validation.py --bootstrap 2000` (requires NumPy, SciPy, Matplotlib and Times New Roman Bold; pass `--font` on another OS). The standalone copied script accepts `--input-dir` and `--output-dir`. Figure: 7.16 x 4.35 inches, vector PDF and 450-dpi PNG, only 8/9/10-pt Times New Roman Bold. The PDF is rendered and font resources checked in the separate QA record.

Skills applied: find-skills; [Scientific Visualization](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/scientific-visualization), [Matplotlib](https://github.com/K-Dense-AI/scientific-agent-skills/tree/main/skills/matplotlib), and local PDF render/verify skill. The remote guidelines were read without installing packages. Scientific Agent Skills: Kassis et al. (2026), https://doi.org/10.48550/arXiv.2609.00065.
