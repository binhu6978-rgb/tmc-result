"""Narrow the public release to the existing 1000-round run, without deleting originals."""
from collections import Counter
from pathlib import Path
import shutil
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.export_mechanism_evidence import load,js,readcsv,csvfile

def run(source):
    out=source/'publication/tmc-result';root=out/'mechanism_evidence'
    backup=source/'tmp/mechanism_publication_allruns_backup'
    assert root.resolve().is_relative_to(source.resolve())
    assert backup.resolve().is_relative_to(source.resolve()) and not backup.exists()
    shutil.move(str(root),str(backup))
    root.mkdir()
    rid='v2_active1000_seed1';commit='149c6713c339204ad23fe43952350ae2832b3cd0'
    def copy(rel):
        src=backup/rel;dst=root/rel;dst.parent.mkdir(parents=True,exist_ok=True)
        if src.is_dir():shutil.copytree(src,dst)
        else:shutil.copy2(src,dst)
    for section in ('logs','memory','aggregation','counterfactual'):copy(f'{section}/{rid}')
    copy('reports/activation1000')
    copy(f'code_used/{commit}')
    for rel in ('provenance/configs/semantic_a07_activation1000.json','provenance/configs/semcons_semantic_a07_v2.json',
                'provenance/schedules/v2_active1000_seed1.csv','provenance/reports/SEMANTIC_A07_V2_DESIGN.md',
                'provenance/server_log_download_verification.json','provenance/source_worktree_at_export.txt',
                'provenance/source_tracked_diff_at_export.patch','provenance/requested_schema.md','provenance/request_target_override.json'):
        copy(rel)
    copy('provenance/scripts/export_mechanism_evidence.py')
    for name in ('audit_mechanism_publication.py','scope_publication_1000_only.py'):
        dst=root/'provenance/scripts'/name;dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/'tools'/name,dst)
    for name in ('report_semantic_activation.py','plot_final_mechanism_case.py','plot_mechanism_tmc_final.py','plot_semantic_validation.py','plot_semantic_selected_beneficial.py','audit_semantic_activation1000.py'):
        copy('provenance/scripts/'+name)
    runs=[r for r in readcsv(backup/'runs.csv') if r['run_id']==rid]
    assert len(runs)==1;csvfile(root/'runs.csv',runs)
    manifest=load(backup/'manifest.json')
    manifest['runs']=[r for r in manifest['runs'] if r['run_id']==rid]
    manifest['snapshots']={commit:manifest['snapshots'][commit]}
    manifest['selection']='Latest user scope: only the 1000-round Semantic-A07 V2 run and its complete existing diagnostics; no 500-round or other historical run data, no model weights'
    manifest['published_full_state_exports']=[]
    manifest['verified_full_states_inventory']=[r for r in manifest.get('verified_full_states_inventory',[]) if r['run_id']==rid]
    manifest['run_manifest_files']={rid:manifest['run_manifest_files'].get(rid,[])}
    manifest['evaluation_definitions']={k:v for k,v in manifest.get('evaluation_definitions',{}).items() if 'mature' not in k.lower()}
    manifest['evidence_limits']=['Single seed1 trajectory, not independent multi-seed evidence','Probe data disjoint from semantic measurement but still SGD training-side','Historical upload tensors were not saved; scalar counterfactual outcomes are existing measurements only','All model weights withheld by user request']
    js(root/'manifest.json',manifest)
    states=[r for r in load(backup/'checkpoints/verified_full_states_inventory.json') if r['run_id']==rid]
    js(root/'checkpoints/verified_full_states_inventory.json',states)
    checkpoints=[r for r in readcsv(backup/'checkpoints/checkpoint_inventory.csv') if r['run_id']==rid]
    csvfile(root/'checkpoints/checkpoint_inventory.csv',checkpoints)
    verification=load(backup/'provenance/runtime_source_verification.json')
    records=[r for r in verification['records'] if r['run_id']==rid]
    assert records and all(r['status']=='FROZEN_COMMIT_BLOB_MATCH' for r in records)
    js(root/'provenance/runtime_source_verification.json',dict(runtime_source_records_inspected=len(records),runtime_source_records_verified=len(records),statuses=dict(Counter(r['status'] for r in records)),all_recorded_hashes_resolved=True,records=records))
    available={r['path']:r for r in readcsv(backup/'file_inventory.csv') if r['available']=='UPLOADED'}
    inventory=[r for r in readcsv(backup/'file_inventory.csv') if r['run_id']==rid and r['available']!='UPLOADED']
    for p in root.rglob('*'):
        if p.is_file() and p.relative_to(root).as_posix() in available:inventory.append(available[p.relative_to(root).as_posix()])
    csvfile(root/'file_inventory.csv',inventory)
    js(root/'provenance/final_publication_policy.json',dict(runs=[rid],rounds=1000,model_weights='EXCLUDED_BY_USER_REQUEST',other_run_data='EXCLUDED_BY_USER_REQUEST',original_files='PRESERVED',new_training=False,new_evaluation=False))
    (root/'provenance/missing_data_report.md').write_text('''# 1000-round saved-state limitations

- Existing final recovery checkpoint and verified Full-state hashes are inventoried; no model weights are uploaded by user request.
- Historical per-slot upload tensors and historical A07/V2 post-aggregation Full states were NOT_SAVED. Existing scalar CE, update norms and hashes are retained; arbitrary new historical counterfactuals cannot be reconstructed from CSV.
- Raw images, materialized probes, private sample indices and credentials are excluded.
- Probe Accuracy was not recorded: fields remain blank. Probe CE is available for the fixed 53 diagnostic rounds.
- Source masses absent from the original records remain blank; no inverse estimates were made from normalized shares.
- Missing runtime uncommitted diffs remain NOT_SAVED. Exact executed source hashes are checked separately.
- This release contains only the 1000-round run. The 500-round runs and other historical executions are outside the latest requested scope, not deleted from original storage.
''',encoding='utf-8')
    (root/'README.md').write_text('''# Semantic-A07 V2: existing 1000-round evidence

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
''',encoding='utf-8')
    (out/'README.md').write_text('''# tmc-result

Public archive of the existing **1000-round Semantic-A07 V2 seed1 run only**. No model weights or 500-round data.

- [1000-round Accuracy / CE CSV](mechanism_evidence/logs/v2_active1000_seed1/accuracy_each_round.csv)
- [Complete raw logs and original tables](mechanism_evidence/logs/v2_active1000_seed1/)
- [Class evidence and Memory](mechanism_evidence/memory/v2_active1000_seed1/)
- [Aggregation decisions and shares](mechanism_evidence/aggregation/v2_active1000_seed1/)
- [Existing same-input counterfactual data](mechanism_evidence/counterfactual/v2_active1000_seed1/)
- [Existing figures and reports](mechanism_evidence/reports/activation1000/)
- [Data definitions and limitations](mechanism_evidence/README.md)
- [File hashes and availability](mechanism_evidence/file_inventory.csv)

No new training or evaluation was performed. Existing positive, negative and neutral observations are preserved.
''',encoding='utf-8')
    print('Scoped release to existing 1000-round run only; all original files retained in local archive')

if __name__=='__main__':run(Path(__file__).resolve().parents[1])
