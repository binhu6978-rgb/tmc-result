"""Check public archive fidelity, privacy, schemas and saved-state metadata only."""
import argparse
from collections import Counter,defaultdict
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import warnings
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.export_mechanism_evidence import readcsv,csvfile,load,js,fsha

csv.field_size_limit(128*1024*1024)
FORBIDDEN=re.compile(r'(?i)(?:/home/[a-z0-9_.-]+/|[A-Z]:[/\\]+Users[/\\]+[a-z0-9_.-]+|\b(?:\d{1,3}\.){3}\d{1,3}\b|gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)')
def read_any(path):
 opener=gzip.open if path.suffix=='.gz' else open
 with opener(path,'rt',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def find(root,rel):
 p=root/rel
 return p if p.exists() else Path(str(p)+'.gz')
def data_bytes(path):return gzip.decompress(path.read_bytes()) if path.suffix=='.gz' else path.read_bytes()


def observed_round_range(path):
 ext=Path(path.stem).suffix if path.suffix=='.gz' else path.suffix
 if ext not in ('.csv','.jsonl'):return 'NOT_APPLICABLE_METADATA'
 opener=gzip.open if path.suffix=='.gz' else open
 lo=hi=None;field='round'
 with opener(path,'rt',encoding='utf-8-sig',newline='') as f:
  if ext=='.csv':
   reader=csv.DictReader(f)
   if 'round' not in (reader.fieldnames or []):
    if 'round_index' in (reader.fieldnames or []):field='round_index'
    else:return 'NOT_RECORDED_AS_ROUND'
  else:reader=(json.loads(line) for line in f if line.strip())
  for row in reader:
   value=row.get(field) if isinstance(row,dict) else None
   if value is None or not str(value).lstrip('-').isdigit():continue
   value=int(value);lo=value if lo is None else min(lo,value);hi=value if hi is None else max(hi,value)
 return f'{field}:{lo}-{hi}' if lo is not None else 'NOT_RECORDED_AS_ROUND'


def complete_known_fields(root):
 updates={}
 for p in sorted((root/'aggregation').glob('*/aggregation_weights.csv*')):
  rid=p.parent.name;mass={};tables=[]
  for name in ('receiver_utility_raw.csv','figure7_raw.csv'):
   q=root/'logs'/rid/'collected_results'/name
   if q.exists():tables.append(q)
  q=root/'counterfactual'/rid/'journal_receiver_records.csv'
  if q.exists():tables.append(q)
  for table in tables:
   for r in read_any(table):
    key=(r['round'],r['region'],r['source_tier'])
    if key in mass:assert mass[key]==r['source_mass']
    mass[key]=r['source_mass']
  rows=read_any(p);filled=0
  for r in rows:
   r['parameter_family']='feature_non_BN'
   key=(r['round'],r['region_id'],r['source_tier'])
   if key in mass:
    r['source_mass']=mass[key];r['source_mass_status']='RECORDED_IN_EXISTING_RECEIVER_DIAGNOSTIC';filled+=1
  if p.suffix=='.gz':
   import io
   stream=io.StringIO(newline='');w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
   p.write_bytes(gzip.compress(stream.getvalue().encode(),mtime=0))
  else:csvfile(p,rows)
  updates[rid]=filled
 js(root/'provenance/derived_field_completion.json',dict(join='(run_id,round,region,source_tier); exact recorded mass only; no inversion of normalized weights',
   completed_source_mass_rows=updates,metadata_label='parameter_family clarified as feature_non_BN; semantic_applicable separately records whether shared/multi-tier'))


def audit(out,complete=False):
 root=out/'mechanism_evidence'
 if complete:complete_known_fields(root)
 # Index updated mechanical exports and this verifier itself.
 dest=root/'provenance/scripts/audit_mechanism_publication.py';dest.write_bytes(Path(__file__).read_bytes())
 index=readcsv(root/'file_inventory.csv');uploaded={r['path']:r for r in index if r['available']=='UPLOADED'}
 unavailable=[r for r in index if r['available']!='UPLOADED']
 ranges={}
 for p in sorted(root.rglob('*')):
  if not p.is_file() or p.name in ('file_inventory.csv','publication_summary.json','UPLOAD_AUDIT.json'):continue
  rel=p.relative_to(root).as_posix()
  r=uploaded.get(rel,dict(run_id='PUBLICATION',path=rel,type='metadata',round_range='',description='Publication audit/metadata',available='UPLOADED',source_path='DERIVED_OR_PUBLICATION_METADATA',source_sha256='',privacy_redactions=0))
  if r['type']=='derived_csv':r['description']=r['description']+'; exact saved source-mass join if present' if 'aggregation_weights' in rel else r['description']
  digest=fsha(p)
  if digest not in ranges:ranges[digest]=observed_round_range(p)
  r.update(size_bytes=p.stat().st_size,sha256=digest,round_range=ranges[digest]);uploaded[rel]=r
 csvfile(root/'file_inventory.csv',unavailable+list(uploaded.values()))
 hashes=0;original_byte_checks=0;privacy_violations=[];literal_credential_flags=[];syntax_errors=[]
 for rel,r in uploaded.items():
  p=root/rel;assert p.exists() and fsha(p)==r['sha256'];hashes+=1
  assert p.stat().st_size<100*1024*1024,rel
  if r['source_sha256'] and int(r['privacy_redactions'] or 0)==0 and r['type'] in ('source_copy','gzip_lossless','original_gzip','frozen_source','existing_counterfactual_full_state'):
   original_byte_checks+=1
   actual=hashlib.sha256(data_bytes(p)).hexdigest() if r['type']=='gzip_lossless' else fsha(p)
   assert actual==r['source_sha256'],('Source bytes differ',rel)
  ext=Path(p.stem).suffix if p.suffix=='.gz' else p.suffix
  if ext in ('.json','.jsonl','.csv','.md','.txt','.log','.py','.sh','.toml','.diff','.patch'):
   try:text=data_bytes(p).decode('utf-8-sig')
   except UnicodeDecodeError:continue
   if FORBIDDEN.search(text):privacy_violations.append(rel)
   for n,line in enumerate(text.splitlines(),1):
    if re.search(r'''(?i)(?:password|passwd|api_key|access_token)\s*[:=]\s*["'][^"']{6,}["']''',line):literal_credential_flags.append(dict(path=rel,line=n))
   if ext=='.py':
    try:
     with warnings.catch_warnings():
      warnings.simplefilter('ignore',SyntaxWarning);compile(text,rel,'exec')
    except SyntaxError:syntax_errors.append(rel)
 assert not privacy_violations,('Private-root/credential markers still present',privacy_violations)
 # Validate that exact source records and normalized eligible rows agree.
 rid='v2_active1000_seed1'
 original=readcsv(root/'logs'/rid/'collected_results/used_categories.csv')
 records=read_any(find(root,f'memory/{rid}/semantic_class_evidence.csv'))
 selected={(r['round'],r['source_tier'],r['class_id']):r for r in records if r['eligible']=='True'}
 assert len(original)==len(selected)==27085
 comparisons=0
 for r in original:
  e=selected[r['round'],r['tier'],r['category']]
  for a,b in [('q_pre','q_pre'),('q_post','q_post'),('reference_q','q_other_past'),('d','d'),('a','a'),('rho','rho'),('u','u')]:
   assert float(r[a])==float(e[b]);comparisons+=1
  assert int(e['reference_round'])<int(e['round'])
  assert math.isclose(float(e['u']),float(e['rho'])*min(float(e['d']),float(e['a'])),abs_tol=1e-14)
 rounds=readcsv(root/f'aggregation/{rid}/aggregation_rounds.csv')
 assert [int(r['round']) for r in rounds]==list(range(1,1001)) and sum(r['active']=='True' for r in rounds)==602
 assert len(readcsv(root/f'logs/{rid}/accuracy_each_round.csv'))==1000
 for r in readcsv(root/f'logs/{rid}/accuracy_each_round.csv'):assert math.isfinite(float(r['full_accuracy'])) and math.isfinite(float(r['full_ce']))
 weights={(r['round'],r['region_id'],r['source_tier']):r for r in read_any(find(root,f'aggregation/{rid}/aggregation_weights.csv'))}
 shares=readcsv(root/f'logs/{rid}/collected_results/region_shares.csv')
 for s in shares:
  r=weights[s['round'],s['region'],s['tier']]
  assert abs(float(s['pi_before'])-float(r['pi_A07']))<1e-12
  assert abs(float(s['pi_after'])-float(r['pi_sem']))<1e-12
 cf=read_any(find(root,f'counterfactual/{rid}/fixed_update_counterfactual.csv'))
 assert len(cf)==318 and len({r['round'] for r in cf})==53
 assert all(r['accuracy_A07']==r['accuracy_sem']=='' for r in cf)
 for r in cf:assert r['pre_state_hash'] and r['client_updates_hash']
 pts=[p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in ('.pt','.pth','.ckpt','.safetensors')]
 assert not pts,'User requested that model weights are not published'
 # PDFs are generated scientific figures only. Inspect extracted text for roots,
 # not encrypted binary strings; this is read-only and does not redraw anything.
 from pypdf import PdfReader
 pdf_count=0
 for p in root.rglob('*.pdf'):
  pdf_count+=1
  assert not FORBIDDEN.search('\n'.join(page.extract_text() or '' for page in PdfReader(p).pages)),p.name
 report=dict(success=True,indexed_public_hashes_verified=hashes,source_bytes_or_uncompressed_bytes_verified=original_byte_checks,
  privacy_root_or_token_violations=privacy_violations,literal_credential_review_flags=literal_credential_flags,
  source_syntax_review=syntax_errors,eligible_class_records_verified=27085,numeric_class_fields_verified=comparisons,
  current_class_candidates=len(records),aggregation_rounds=1000,active_rounds=602,regional_share_rows_verified=len(shares),
  same_input_full_cases=len(cf),fixed_diagnostic_rounds=53,full_weight_files=len(pts),pdf_text_privacy_checks=pdf_count,
  no_new_training=True,no_new_model_effect_evaluation=True,model_policy='No model weights published, per latest user instruction; verified state hashes retained in inventory')
 js(root/'UPLOAD_AUDIT.json',report)
 files=[p for p in root.rglob('*') if p.is_file()];counts=Counter(p.suffix for p in files)
 js(root/'publication_summary.json',dict(runs=len(readcsv(root/'runs.csv')),files=len(files),files_by_extension=dict(counts),bytes=sum(p.stat().st_size for p in files),
  checkpoint_inventory_rows=len(readcsv(root/'checkpoints/checkpoint_inventory.csv')),published_full_states=len(pts),audit_success=True))
 print(json.dumps(report,indent=2))


if __name__=='__main__':
 ap=argparse.ArgumentParser(__doc__);ap.add_argument('root',type=Path);ap.add_argument('--complete-known-fields',action='store_true')
 args=ap.parse_args();audit(args.root,args.complete_known_fields)
