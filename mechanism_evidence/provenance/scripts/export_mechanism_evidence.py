"""Export only existing SemConsFL evidence; no model evaluation or training imports.

Public copies redact private filesystem roots/hosts, preserving originals locally.
Original and exported SHA256 values, provenance and exclusions are indexed.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys

csv.field_size_limit(128*1024*1024)
PARTITION='41ab2d3486663ce0100e183ab00565de137f91af07632c236c2ddf60d890ba41'
PROFILES=[[.40,2],[.40,3],[.40,4],[.66,2],[.66,3],[.66,4],[1.,2]]
BIG=20*1024*1024
TEXT={'.json','.jsonl','.csv','.md','.txt','.log','.py','.sh','.toml','.yaml','.yml','.diff','.patch','.json5'}
BINARY={'.pt','.pth','.ckpt','.npz','.npy','.safetensors','.pkl','.pickle','.tar','.zip'}
PRIVATE=[
 (re.compile(r'/home/[A-Za-z0-9_.-]+/TMC_re_e03_scope_components400_20261019'),'PROJECT_ROOT'),
 (re.compile(r'/home/[A-Za-z0-9_.-]+/ICML_finish/data'),'DATASET_ROOT'),
 (re.compile(r'/home/[A-Za-z0-9_.-]+/miniconda3/envs/[A-Za-z0-9_.-]+/bin/python'),'PYTHON_EXECUTABLE'),
 (re.compile(r'/home/[A-Za-z0-9_.-]+'),'PRIVATE_HOME'),
 (re.compile(r'[A-Za-z]:[/\\]+Users[/\\]+[^/\\\s"\x27]+'),'LOCAL_HOME'),
 (re.compile(r'[A-Za-z]:[/\\]+software[/\\]+minico+nda[/\\]+envs[/\\]+[^/\\\s"\x27]+'),'PYTHON_ENV'),
 (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),'IP_ADDRESS_REDACTED'),
]
SECRET=re.compile(r'gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----|(?im:^Authorization\s*:\s*(?:Bearer|token)\s+\S+)')


def sha(data):return hashlib.sha256(data).hexdigest()
def fsha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def load(path):
 with path.open(encoding='utf-8-sig') as f:return json.load(f)
def lines(path):
 opener=gzip.open if path.suffix=='.gz' else open
 with opener(path,'rt',encoding='utf-8') as f:
  for line in f:
   if line.strip():yield json.loads(line)
def readcsv(path):
 with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def csvfile(path,rows,fields=None):
 path.parent.mkdir(parents=True,exist_ok=True)
 fields=fields or list(rows[0])
 with path.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def js(path,value):
 path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def compact(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def neutralize(text):
 count=0
 for pattern,replacement in PRIVATE:
  text,n=pattern.subn(lambda _:replacement,text);count+=n
 # Escaped JSON Windows roots require a second normalization pass.
 text,n=re.subn(r'[A-Za-z]:\\{2,}Users\\{2,}[^\\\s"\x27]+','LOCAL_HOME',text);count+=n
 if SECRET.search(text):raise ValueError('Credential-shaped content encountered; manual review required')
 return text,count


class Export:
 def __init__(self,source,out):
  self.source=source;self.out=out;self.root=out/'mechanism_evidence';self.inventory=[];self.checkpoints=[];self.runs=[];self.snapshots={}
  self.root.mkdir(parents=True,exist_ok=False)
 def record(self,rid,src,dest,original,exported,kind,description,redactions=0,available='UPLOADED',rounds=''):
  self.inventory.append(dict(run_id=rid,path=str(dest.relative_to(self.root)).replace('\\','/'),type=kind,
   size_bytes=dest.stat().st_size if dest.exists() else '',sha256=exported,round_range=rounds,
   description=description,available=available,source_path=str(src).replace('\\','/'),
   source_sha256=original,privacy_redactions=redactions))
 def copy(self,rid,src,rel,description='Existing source file; no outcome filtering',rounds=''):
  if not src.exists():
   self.inventory.append(dict(run_id=rid,path=str(rel),type='missing',size_bytes='',sha256='',round_range=rounds,
    description=description,available='NOT_FOUND',source_path=str(src).replace('\\','/'),source_sha256='',privacy_redactions=0));return
  if src.suffix in BINARY or src.name in ('probe_plans.json','client_partition.json','partitions.json'):
   return self.exclude(rid,src,'WITHHELD_BINARY_OR_SAMPLE_INDEX')
  original=fsha(src);raw=src.read_bytes();isgz=src.suffix=='.gz'
  plain=gzip.decompress(raw) if isgz else raw
  ext=Path(src.stem).suffix if isgz else src.suffix
  redactions=0
  if ext in TEXT or not ext:
   try:text=plain.decode('utf-8-sig')
   except UnicodeDecodeError:
    try:text=plain.decode('gb18030')
    except UnicodeDecodeError:text=None
   if text is not None:
    new,redactions=neutralize(text)
    if redactions:plain=new.encode('utf-8')
  dest=self.root/rel
  compress=isgz or ext=='.jsonl' or len(plain)>BIG
  if compress and not str(dest).endswith('.gz'):dest=Path(str(dest)+'.gz')
  dest.parent.mkdir(parents=True,exist_ok=True)
  data=raw if isgz and not redactions else gzip.compress(plain,compresslevel=6,mtime=0) if compress else plain
  if dest.exists():
   if fsha(dest)!=sha(data):raise FileExistsError('Refuse to replace differing evidence '+str(dest))
  else:dest.write_bytes(data)
  self.record(rid,src.relative_to(self.source) if src.is_relative_to(self.source) else Path(src.name),dest,original,fsha(dest),
   'original_gzip' if isgz and not redactions else 'gzip_lossless' if compress else 'source_copy',
   description+('; privacy-only redacted public copy' if redactions else '; numeric/source bytes unchanged after decompression'),redactions,rounds=rounds)
 def exclude(self,rid,src,reason):
  source_path=str(src.relative_to(self.source)).replace('\\','/')
  if any(r['run_id']==rid and r['source_path']==source_path and r['available']=='PRESENT_LOCAL_NOT_UPLOADED' for r in self.inventory):return
  row=dict(run_id=rid,path=str(src.relative_to(self.source)).replace('\\','/'),type=src.suffix,size_bytes=src.stat().st_size,
   sha256=fsha(src),round_range='',description=reason,available='PRESENT_LOCAL_NOT_UPLOADED',
   source_path=str(src.relative_to(self.source)).replace('\\','/'),source_sha256='',privacy_redactions=0)
  self.inventory.append(row)
  if src.suffix in BINARY:self.checkpoints.append(dict(run_id=rid,path=row['path'],type=src.suffix,size_bytes=row['size_bytes'],sha256=row['sha256'],
    available='PRESENT_LOCAL_NOT_UPLOADED',round='',contains_raw_samples='YES' if 'probe' in src.name else 'UNKNOWN',
    historical_client_updates='YES' if src.name.startswith('raw_round') else 'UNKNOWN',reason=reason))
 def tree(self,rid,src,rel,description='Complete existing evidence directory'):
  if not src.exists():return
  for p in sorted(src.rglob('*')):
   if not p.is_file() or '.git' in p.parts or '__pycache__' in p.parts:continue
   if p.name=='raw_evidence.tar.gz' or p.suffix in {'.tar','.zip'}:continue
   self.copy(rid,p,Path(rel)/p.relative_to(src),description)
 def derived(self,rid,path,rows,description,fields=None):
  dest=self.root/path;csvfile(dest,rows,fields)
  if dest.stat().st_size>BIG:
   gz=Path(str(dest)+'.gz');gz.write_bytes(gzip.compress(dest.read_bytes(),compresslevel=6,mtime=0));dest.unlink();dest=gz
  self.record(rid,'DERIVED_FROM_SAVED_RECORDS',dest,'',fsha(dest),'derived_csv',description)
 def run(self,rid,root,algorithm,rounds,mode='active',commit=None,reference='',notes=''):
  if not root.exists():return
  candidates=[root/n for n in ('v2_manifest.json','observation_manifest.json','run_manifest.json','diagnostic_manifest.json') if (root/n).exists()]
  meta=load(candidates[0]) if candidates else {}
  manifest=load(root/'manifest.json') if (root/'manifest.json').exists() else {}
  commit=commit or meta.get('commit') or meta.get('source_commit') or 'UNKNOWN'
  identity=manifest.get('identity',{})
  self.runs.append(dict(run_id=rid,algorithm=algorithm,rounds=rounds,seed=1,mode=mode,source_commit=commit,
   source_directory=str(root.relative_to(self.source)).replace('\\','/'),paired_reference_run_id=reference,
   parent_run_id='',completion_marker_present=any((root/n).exists() for n in ('completed.json','diagnostic_completed.json')),
   partition_sha256=identity.get('partition_sha256',meta.get('partition_sha256',PARTITION)),
   applied_lambda=(.2 if mode=='active' else 0) if algorithm.startswith('Semantic-A07 V2') else 0 if algorithm.startswith('A07-only') else 'N/A',
   runtime_dirty_diff='NOT_SAVED unless explicit in original manifest',notes=notes))
  self.tree(rid,root,Path('logs')/rid,'Raw per-run logs; complete recorded rounds')
  if (root/'semantic_v2_rounds.jsonl').exists():self.derive_v2(rid,root,mode,manifest)
  self.derive_schedule(rid,root)
  if (root/'iv_e_rounds.jsonl').exists():self.derive_counterfactual(rid,root)

 def derive_schedule(self,rid,root):
  p=root/'regression.jsonl'
  if not p.exists():return
  rows=[]
  for d in lines(p):
   if not d['round']:continue
   slots=d.get('slots',[])
   rows.append(dict(run_id=rid,round=d['round'],slot_order=compact(slots),
    selected_client_ids=compact([c for c,p in slots]),selected_profiles=compact([p for c,p in slots]),
    selected_tiers=compact([0 if c<40 else 1 if c<70 else 2 for c,p in slots]),
    model_state_hashes=compact(d.get('models',[])),rng=compact(d.get('rng',{}))))
  if rows:self.derived(rid,Path('provenance/schedules')/(rid+'.csv'),rows,'Extracted recorded slot order and model/RNG identities, not regenerated sampling')

 def derive_v2(self,rid,root,mode,manifest):
  reg={d['round']:d for d in lines(root/'regression.jsonl')} if (root/'regression.jsonl').exists() else {}
  semantic=[];updates=[];rounds=[];weights=[];past={};snapshots={}
  for d in lines(root/'semantic_v2_rounds.jsonl'):
   rd=d['round'];decision=d['decision'];fusion=d['fusion'];snapshots[rd]=dict(valid=decision['valid'],scores=decision.get('scores',{}),fusion=fusion)
   detail={(int(r['tier']),int(r['category'])):r for r in decision.get('details',[])}
   for current in d['current_task']:
    g,c=int(current['tier']),int(current['category']);e=detail.get((g,c),{});own=e.get('own_reliability',{});other=e.get('reference_reliability',{})
    semantic.append(dict(run_id=rid,round=rd,source_tier=g,class_id=c,q_pre=current['pre'],q_post=current['post'],
      q_other_past=e.get('reference_q',''),d=e.get('d',''),a=e.get('a',''),rho=e.get('rho',''),u=e.get('u',''),
      class_support=current['support'],eligible=bool(decision['valid'] and c in decision.get('classes',[]) and e),
      anchor_count=len(past),history_age=compact({'own':own.get('age'),'reference':other.get('age')}) if own or other else '',
      history_variance_or_stability=compact({'own_stability':own.get('stability'),'reference_stability':other.get('stability')}) if own or other else '',
      history_effective_support=compact({'own':own.get('support'),'reference':other.get('support')}) if own or other else '',
      memory_snapshot_time='before_round_'+str(rd),physical_clients=compact(current['clients']),
      reference_tier=e.get('reference_tier',''),reference_round=e.get('reference_round',''),
      decision_valid=decision['valid'],decision_reason=decision.get('reason',''),
      missing_rule='blank scoring fields = not recorded/computed, never zero-filled'))
   for u in d['tier_commits']:
    k=(int(u['tier']),int(u['category']));old=past.get(k,{})
    updates.append(dict(run_id=rid,round=rd,source_tier=k[0],class_id=k[1],q_before=old.get('q',''),q_after=u['q'],
      observed_q=u['observed_q'],support=u['support'],physical_clients=compact(u['clients']),change=u.get('change'),
      previous_commit_round=old.get('round',''),commit_time='after_aggregation_and_full_evaluation',
      initialization=not bool(old)))
    past[k]=u
   slots=reg.get(rd,{}).get('slots',[])
   changed=fusion.get('changed_parameters',0);full_numel=sum(r['numel'] for r in manifest.get('structural_regions',[]))
   rounds.append(dict(run_id=rid,round=rd,selected_client_ids=compact([c for c,p in slots]),
     selected_tiers=compact([0 if c<40 else 1 if c<70 else 2 for c,p in slots]),selected_profiles=compact([p for c,p in slots]),
     valid_evidence=decision['valid'],active=changed>0,reason=fusion.get('reason',''),common_classes=compact(decision.get('classes',[])),
     **{'lambda':fusion.get('lambda_value','')},changed_parameters=changed,changed_fraction=changed/full_numel if full_numel else '',
     difference_l2=fusion.get('difference_from_a07_l2',0),full_parameter_numel=full_numel))
  self.derived(rid,Path('memory')/rid/'semantic_class_evidence.csv',semantic,'Every recorded current tier/class; absent score/history fields left blank, exact decision eligibility')
  self.derived(rid,Path('memory')/rid/'memory_updates.csv',updates,'Recorded tier commits and prior committed values reconstructed by reading logs only')
  self.derived(rid,Path('aggregation')/rid/'aggregation_rounds.csv',rounds,'Applied fusion only; virtual diagnostics are separately labeled')
  weightpath=root/'source_weights_each_round.jsonl'
  if weightpath.exists():
   for d in lines(weightpath):
    rd=d['round'];s=snapshots[rd];actual=d['applied'];virtual=d['virtual_v2'];slots=reg.get(rd,{}).get('slots',[])
    scored={int(r['region']):r for r in virtual.get('regions',[])}
    applied={int(r['region']):r for r in actual.get('regions',[])}
    for r in d['a07']['regions']:
     members=r.get('slots',[]);tiers=r.get('capability_tiers',[]);shares=r.get('applied_slot_shares',r.get('native_slot_shares'))
     vr=scored.get(int(r['region_id']),{});ar=applied.get(int(r['region_id']),{})
     pis=vr.get('pi_a07',{})
     if not pis and shares and slots:
      by=defaultdict(float)
      for i,w in zip(members,shares):by[0 if slots[i][0]<40 else 1 if slots[i][0]<70 else 2]+=w
      pis={str(k):v for k,v in by.items()}
     for g in tiers:
      pi=pis.get(str(g),'');new=ar.get('pi_new',{}).get(str(g),pi)
      # Missing absolute masses are not inferred from relative shares.
      weights.append(dict(run_id=rid,round=rd,region_id=r['region_id'],parameter_family='shared_feature_non_BN',
       region_numel=vr.get('feature_numel',''),source_tier=g,source_mass='',source_U=s['scores'].get(str(g),s['scores'].get(g,'')),
       pi_A07=pi,pi_sem=new,delta_pi=new-pi if pi!='' and new!='' else '',
       semantic_applicable=bool(len(tiers)>1 and len(r.get('support_profiles',[]))>1),
       reason=ar.get('reason',actual.get('reason','neutral_A07')),applied_mode=mode,
       source_mass_status='NOT_RECORDED_IN_WEIGHT_JOURNAL; diagnostic masses retained in receiver raw table',
       virtual_pi_sem=vr.get('pi_new',{}).get(str(g),'')))
   if weights:self.derived(rid,Path('aggregation')/rid/'aggregation_weights.csv',weights,'Recorded applied/virtual shares; A07 fallback shares summed from logged slot shares; no mass fabrication')
  regions=manifest.get('structural_regions')
  if regions:js(self.root/'aggregation'/rid/'coverage_definition.json',dict(profiles=manifest.get('profiles',PROFILES),regions=regions,
   bounds='Each [lo,hi) prefix rectangle; unspecified trailing dimensions covered in full',BN='A07 unchanged',classifier='Native',first_round='Native',
   slot_duplicates='SGD uploads retained; semantic independent support deduplicated by physical identity',single_tier='Native',uncovered='preserve previous Full coordinates'))

 def derive_counterfactual(self,rid,root):
  reg={d['round']:d for d in lines(root/'regression.jsonl')} if (root/'regression.jsonl').exists() else {}
  rows=[];source_rows=[];full_rows=[];norms=[]
  for d in lines(root/'iv_e_rounds.jsonl'):
   rd=d['round'];pre=reg.get(rd-1,{}).get('models',[]);checks=reg.get(rd,{}).get('local_checks',[])
   index=[{k:c.get(k) for k in ('slot','client','profile','uploaded_state')} for c in checks]
   updates_hash=sha(compact(index).encode()) if index else ''
   for row in d.get('figure7',[]):
    row=dict(row)
    for k in ('source_clients','source_slots','source_profiles','source_slot_shares','per_class'):
     if k in row:row[k]=compact(row[k])
    source_rows.append(row)
   groups=defaultdict(dict)
   for r in d.get('figure8',[]):
    groups[r['receiver'],r.get('cohort','')][r['method']]=r
    rr=dict(r,per_class=compact(r['per_class']));full_rows.append(rr)
   for (cid,cohort),methods in groups.items():
    if not {'A07','V2'}<=methods.keys():continue
    base=methods['A07'];sem=methods['V2'];n=d.get('norms',{}).get('V2',{})
    rows.append(dict(run_id=rid,round=rd,eval_set_id=f'{rid}:receiver_{cid}:{cohort}:P6:fixed_training_probe',
      receiver=cid,cohort=cohort,pre_state_hash=pre[-1] if pre else '',client_updates_hash=updates_hash,
      ce_before=base['before_ce'],ce_A07=base['after_ce'],ce_sem=sem['after_ce'],
      ce_permuted_if_exists=methods.get('permuted',{}).get('after_ce',''),accuracy_A07='',accuracy_sem='',
      delta_l2=n.get('difference_from_a07_l2',''),
      notes='Same pre-state, same uploads and fixed receiver batch; CE-only counterfactual. Update hash is a derived ordered index of recorded per-upload state hashes, not a saved tensor bundle. Virtual V2 may differ from the applied neutral run.'))
   for method,value in d.get('norms',{}).items():norms.append(dict(run_id=rid,round=rd,method=method,**value,l2_control_scale=d.get('l2_control_scale','')))
  if rows:self.derived(rid,Path('counterfactual')/rid/'fixed_update_counterfactual.csv',rows,'Exact existing same-input Full CE results, no new evaluation; unavailable accuracy left blank')
  if norms:self.derived(rid,Path('counterfactual')/rid/'update_scales.csv',norms,'Existing recorded model-update norms/cosines for all controls')
  # Keep native receiver CSVs byte-exact when they already exist; otherwise export
  # the original journal fields without inventing a required column count.
  if source_rows:self.derived(rid,Path('counterfactual')/rid/'journal_receiver_records.csv',source_rows,'Mechanical JSONL-to-CSV export, nested original class records retained',list(dict.fromkeys(k for r in source_rows for k in r)))
  if full_rows:self.derived(rid,Path('counterfactual')/rid/'journal_full_records.csv',full_rows,'Mechanical JSONL-to-CSV export of all existing methods and outcomes',list(dict.fromkeys(k for r in full_rows for k in r)))

 def snapshots_for_runs(self):
  commits=sorted({r['source_commit'] for r in self.runs if re.fullmatch('[0-9a-f]{40}',r['source_commit'])})
  prefix=('Algorithm/','models/','utils/','experiments/','semcons_a07/','semcons_a07_v2/')
  for commit in commits:
   p=subprocess.run(['git','ls-tree','-r','--name-only',commit],cwd=self.source,capture_output=True,text=True)
   if p.returncode:
    self.snapshots[commit]=dict(status='NOT_FOUND_LOCAL_GIT_OBJECT');continue
   names=[]
   for n in p.stdout.splitlines():
    allowed=(n.endswith('.py') and ('/' not in n or n.startswith(prefix)))
    allowed|=(n.startswith('configs/') and n.endswith(('.json','.yaml','.yml')))
    allowed|=(n.startswith('tools/') and n.endswith('.py') and any(x in n for x in ('semantic','semcons','receiver','mature_q','structure_counterfactual','e03')))
    allowed|=(n in ('requirements.txt','environment.yml','LICENSE','LICENSE.md','LICENSE.txt','pyproject.toml'))
    if allowed:names.append(n)
   blobinfo=[]
   for name in names:
    p=subprocess.run(['git','show',f'{commit}:{name}'],cwd=self.source,capture_output=True)
    if p.returncode:raise RuntimeError('Missing frozen source blob')
    raw=p.stdout
    try:text=raw.decode('utf-8')
    except UnicodeDecodeError:text=raw.decode('gb18030')
    clean,count=neutralize(text);published=clean.encode('utf-8') if count else raw
    dest=self.root/'code_used'/commit/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(published)
    original_blob=subprocess.run(['git','rev-parse',f'{commit}:{name}'],cwd=self.source,capture_output=True,text=True,check=True).stdout.strip()
    blobinfo.append(dict(path=name,source_git_blob=original_blob,source_sha256=sha(raw),public_sha256=sha(published),privacy_only_replacements=count))
    self.record('CODE_'+commit[:12],f'git:{commit}:{name}',dest,sha(raw),sha(published),'frozen_source','Original frozen code blob; only private-root/host redactions if indexed',count)
   js(self.root/'code_used'/commit/'snapshot_manifest.json',dict(commit=commit,source_repository='binhu6978-rgb/tmc_finish_need',
     exact_algorithm_snapshot=True,byte_exact_except_indexed_privacy_literals=True,files=blobinfo,
     no_training_run_to_export=True,missing_binary_dependencies='Datasets, checkpoints and private sample indices are excluded'))
   self.snapshots[commit]=dict(status='EXPORTED',files=len(names),manifest=f'code_used/{commit}/snapshot_manifest.json')

 def add_checkpoint_inventory(self):
  p=self.source/'tmp/server_checkpoint_inventory_private.json'
  aliases={'v2_1000':'v2_active1000_seed1','a07_500':'a07_neutral500_seed1','v2_500':'v2_active500_seed1','receiver_fixed5':'receiver_fixed5_seed1'}
  if p.exists():
   for r in load(p):
    row=dict(run_id=aliases[r['run_id']],path=r['path'],type='.pt',size_bytes=r.get('size_bytes',''),sha256=r.get('sha256',''),
     available=r['status'],round=1000 if r['run_id']=='v2_1000' else 500 if r['run_id'].endswith('500') else '',
     contains_raw_samples='NO according to saved recovery writer' if '500' in r['run_id'] or '1000' in r['run_id'] else 'UNKNOWN',
     historical_client_updates='NO; final state only' if r['run_id']!='receiver_fixed5' else 'UNKNOWN',
     reason='Metadata and SHA inventoried first; >100MiB binary retained on server per request; no binary split')
    self.checkpoints.append(row)
  for rid,folder in [('mature_receiver_fixed5_seed1','runs/mature_receiver_q_final5_seed1_20261019'),('e03_final400_anchor','runs/mature_q_inputs')]:
   p=self.source/folder
   if p.exists():
    for f in sorted(p.glob('*.pt')):self.exclude(rid,f,'Raw model/state binary retained locally; source/checkpoint SHA indexed; fixed_probes contains raw images and is never published')
  for rid in ['v2_active1000_seed1','a07_neutral500_seed1','v2_active500_seed1']:
   for item in ['historical_theta_before_per_round','historical_per_slot_upload_tensor_bundles','historical_theta_after_A07_and_Sem_pair']:
    self.checkpoints.append(dict(run_id=rid,path=item,type='state_bundle',size_bytes='',sha256='',available='NOT_SAVED',round='historical',
      contains_raw_samples='N/A',historical_client_updates='NO',reason='Only hashes and scalar counterfactual outcomes retained; cannot reconstruct tensors from CSV'))
  csvfile(self.root/'checkpoints/checkpoint_inventory.csv',self.checkpoints)
  # Remote and absent-state entries also appear in the global file inventory.
  seen={(r['run_id'],r['path']) for r in self.inventory}
  for r in self.checkpoints:
   if (r['run_id'],r['path']) not in seen:
    self.inventory.append(dict(run_id=r['run_id'],path=r['path'],type=r['type'],size_bytes=r['size_bytes'],sha256=r['sha256'],
     round_range=str(r.get('round','')),description=r['reason'],available=r['available'],source_path=r['path'],source_sha256=r['sha256'],privacy_redactions=0))

 def finish(self):
  # Export-time source working tree, separate from unknown runtime dirty state.
  state=subprocess.run(['git','status','--porcelain','--untracked-files=all'],cwd=self.source,capture_output=True,text=True,check=True).stdout
  diff=subprocess.run(['git','diff','HEAD','--'],cwd=self.source,capture_output=True,text=True,check=True).stdout
  state,_=neutralize(state);diff,_=neutralize(diff)
  (self.root/'provenance/source_worktree_at_export.txt').write_text(state,encoding='utf-8')
  (self.root/'provenance/source_tracked_diff_at_export.patch').write_text(diff,encoding='utf-8')
  head=subprocess.run(['git','rev-parse','HEAD'],cwd=self.source,capture_output=True,text=True,check=True).stdout.strip()
  branch=subprocess.run(['git','branch','--show-current'],cwd=self.source,capture_output=True,text=True,check=True).stdout.strip()
  js(self.root/'manifest.json',dict(schema=1,source_repository='binhu6978-rgb/tmc_finish_need',publication_repository='binhu6978-rgb/tmc-result',
    export_source_head=head,export_source_branch=branch,selection='All recorded rounds of listed runs; no utility/sign/accuracy filtering',
    snapshots=self.snapshots,runs=self.runs,profiles=PROFILES,population=[40,30,30],boundaries=[40,70],
    base_protocol=dict(dataset='CIFAR-100',classes=100,alpha=.3,partition_sha256=PARTITION,num_clients=100,slots_per_round=10,
     local_epochs=5,batch=50,optimizer='SGD',lr=.01,lr_decay=.998,momentum=.5,weight_decay=.0001,seed=1,eval='Full P6 every round'),
    V2=dict(score='task classifier true-class probabilities; Adapter only auxiliary',
     d='max(0,q_post-q_pre)',a='max(0,q_post-max_other_past_reference)',U='class macro mean(rho*min(d,a))',
     lambda_value=.2,BN='unchanged A07',classifier='Native',first_round='Native',semantic_scope='multi-tier shared feature non-BN regions',
     semantic_memory='past snapshots; robust physical-client class responses then EMA 0.9; commit after aggregation/evaluation',
     reliability='past support/age/stability; min own/reference/current support use coefficient',
     missing='neutral A07; never zero imputation',
     probe='SGD training-side, disjoint from semantic measurement; independent physical receivers; fixed BN batch'),
    privacy='No raw images, sample-index plans, credentials, private filesystem roots or SSH addresses; public copies may have documented literal-only redactions',
    runtime_dirty_diff='NOT_SAVED where absent in original manifest; export-time git status is not runtime status',
    no_new_training=True,no_new_counterfactual_evaluation=True,checkpoint_policy='Inventory first; >100MiB weights and raw-sample-bearing files excluded; no binary splitting',
    evidence_limits=['1000 V2 and prior V2 prefix are not independent FL seeds','distinct runs and postprocessing kept separate',
     'same-input counterfactuals are not inferred from independent trajectory accuracy curves','counterfactual accuracy missing if not originally recorded']))
  csvfile(self.root/'runs.csv',self.runs)
  self.write_readme()
  # Index all derived/config/readme records not already present in the copy index.
  self.inventory=[r for r in self.inventory if r['path'] not in ('file_inventory.csv','publication_summary.json')]
  indexed={r['path'] for r in self.inventory if r['available']=='UPLOADED'}
  for p in sorted(self.root.rglob('*')):
   if p.is_file() and p.name not in ('file_inventory.csv','publication_summary.json') and p.relative_to(self.root).as_posix() not in indexed:
    self.record('PUBLICATION',Path('DERIVED_OR_PUBLICATION_METADATA'),p,'',fsha(p),'metadata','Export/provenance metadata or existing coverage definition')
  csvfile(self.root/'file_inventory.csv',self.inventory)
  counts=Counter(p.suffix for p in self.root.rglob('*') if p.is_file())
  js(self.root/'publication_summary.json',dict(runs=len(self.runs),files=sum(counts.values()),files_by_extension=dict(counts),
   bytes=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file()),
   checkpoints_indexed=len(self.checkpoints),checkpoint_binaries_uploaded=0,original_source_head=head))

 def write_readme(self):
  text='''# Existing SemConsFL mechanism evidence

This public archive exports existing evidence only. **No new training, forward/effect evaluation, score search or data filtering was performed.** Every recorded round of each listed run is retained, including negative, neutral, missing and failed/preflight records. Result-selected illustrative figures, when present, are explicitly labeled and are not the primary raw evidence.

## Start here

- `runs.csv`: distinct real run identities, frozen source commits and paired references.
- `manifest.json`: algorithm/protocol/partition, score dataflow and aggregation scope.
- `file_inventory.csv`: original/public hashes, sizes, source-relative provenance, exclusions and unknowns.
- `checkpoints/checkpoint_inventory.csv`: checkpoint/update availability; inventory is not a model upload.
- `logs/<run_id>/`: native source logs/CSV/JSON, compressed losslessly where large.
- `memory/<run_id>/`: mechanical exports of recorded current tier/class evidence and Memory commits.
- `aggregation/<run_id>/`: recorded shares/rounds and actual geometry from saved manifests.
- `counterfactual/<run_id>/`: already-computed same-input CE results, all methods and update scales.
- `code_used/<training_commit>/`: frozen source snapshots; path/host-only publication redactions are explicitly indexed.
- `reports/` and `provenance/`: complete pre-existing reports, figures, configurations and export/source state.

## Critical interpretation

The 1000-round run is a single seed1 V2 trajectory. Its earlier prefix is not an independent replication of a separate V2 trajectory. The A07 and V2 500-round runs are separate real trajectories; their same round numbers are **not** themselves fixed-update counterfactuals. Only the records produced by one actual call of the frozen diagnostic on the same `previous` state and real uploads are labeled same-input.

The original seven ResNet profiles are (0.40,2), (0.40,3), (0.40,4), (0.66,2), (0.66,3), (0.66,4), (1.00,2). Capacity tiers are physical clients 0-39 / 40-69 / 70-99, not model-profile indices. Duplicate slots retain separate SGD updates; independent semantic support is deduplicated by physical identity. Region geometry is saved in each available manifest/coverage definition; absent coordinates stay unchanged.

V2 decisions use **task classifier** true-class probabilities. Client Adapter/frozen-head Prototypes are auxiliary observations, not direct inputs to applied U. Each local pre/post measurement shares samples, batch composition and frozen Adapter snapshot. Semantic Memory is read before the round and committed afterward. Reliability reports support/age/stability as an evidence-use coefficient, not calibrated correctness probability. BN stays A07, classifier stays Native, first round stays Native. Missing/incomparable evidence returns A07.

### Table semantics and missingness

`semantic_class_evidence.csv` includes every recorded current `(round,tier,class)` candidate, not only classes used by U. `eligible` is true only for classes actually used in a valid decision. Blank scores/references mean not recorded/computed. `anchor_count` counts committed tier/class references at the beginning of the round. `history_age`, `history_effective_support` and `history_variance_or_stability` contain the actually recorded own/reference JSON summaries; stability is not a variance estimate. U is the macro mean of classwise rho*min(d,a), never mean(rho)*mean(min(d,a)).

`memory_updates.csv` records actual commits and reconstructs the prior committed value by reading earlier commits; it does not rerun the Memory algorithm. `aggregation_weights.csv` distinguishes **applied** and **virtual** shares; neutral runs apply lambda0 even when a virtual V2 counterfactual is logged. `pi_sem` is the final blended applied share, not the intermediate renormalized (1+U) share. Missing absolute source mass is left blank rather than inferred from proportions. Diagnostic-round masses remain in native receiver records. Some first-round/fallback region shares were not individually logged and are not manufactured.

Fixed-update CE tables retain per-receiver/cohort cases. `pre_state_hash` is the existing previous Full-state digest; `client_updates_hash`, when present, is a new SHA256 of the ordered list of already-recorded upload-state hashes, not a saved tensor bundle. Accuracy fields remain blank because CE-only probes did not log accuracy. Effect signs: V2 receiver `utility = CE_before-CE_after` (positive helps); `utility_vs_a07 = CE_after_A07-CE_after_variant`. Earlier receiver-Q diagnostics use `delta_ce = CE_after-CE_before` (positive harms). Their original signs are preserved and their runs are not pooled with V2.

Probe samples in the full-data V2 runs are disjoint from semantic measurement but **remain part of original SGD training data**. They are not an SGD-held-out validation set. Physical receiver IDs are simulator IDs, not real user identities. `per_class` is the original list of category, count, before CE, after CE and utility. Same samples/order/eval/no_grad and BN batch are reused for paired CE. Full-counterfactual probes use different receivers/models from many regional-source probes; they cannot be added into an exact causal parameter decomposition.

## Privacy, compression and fidelity

Original local/server files are unchanged. No raw CIFAR images, materialized probes, private partition/sample-index plans, credentials, private absolute roots or SSH addresses are published. Text requiring publication redaction is clearly indexed with both hashes and replacement counts. Numeric observations are not edited. Unredacted CSV copies preserve source bytes. Large logs are complete **gzip streams**, not artificial splits: `gzip -dc file.jsonl.gz` restores their full public logical content. Source hashes describe original files; public hashes describe stored files, so compression/redaction is explicit.

Raw checkpoints and multi-hundred-MiB upload bundles are inventoried first, as requested, and retained at their verified local/server locations. No .pt/.pth/ckpt, image tensors or binary slices are uploaded. Thus published CE results and logged decisions can be reanalyzed; arbitrary historical model/update injections cannot be regenerated solely from CSV. Existing mature five-batch update bundles are listed separately from V2 histories. No missing tensor is reconstructed from Accuracy or U.

## Frozen source vs current main

Source snapshots come from each recorded training commit in the original repository, not the original repository's main branch or a new reimplementation. `snapshot_manifest.json` lists original blob and SHA256 plus public SHA256 for each file. Most bytes are identical; any changes are literal private-path/host redactions in publication copies, not algorithm edits. Export-time working-tree status/diff are provided separately; absent runtime dirty diffs remain NOT_SAVED/UNKNOWN.

The export script in `provenance/scripts/` uses standard-library parsing, hashing and compression only. It does not import a training loop or run a model. Existing training/report scripts are source snapshots for audit, not a request to run them. Datasets, raw sample plans and required large tensors are intentionally not bundled.

No scientific success is inferred from being archived. Original unfavorable results, neutral rounds and missing evidence remain available. All test-oracle peaks retain that label. No official test result was used to select files or new scoring rules.
'''
  (self.root/'README.md').write_text(text,encoding='utf-8')
  (self.root/'provenance/missing_data_report.md').write_text('''# Missing and withheld material

- Historical per-slot V2 upload tensors, historical pre-Full tensors and all counterfactual post-Full tensors were NOT_SAVED; only recorded hashes, scalar CE and norms are available. Final recovery state is not a historical tensor archive.
- Final 1000/500 recovery files are PRESENT_REMOTE_VERIFIED by fresh metadata/SHA inventory, each over 100MiB. They are inventoried, not split or blindly uploaded.
- Mature five-batch upload bundles are PRESENT_LOCAL, hash inventoried, but each over 100MiB. Materialized `fixed_probes.pt` contains raw images and is excluded.
- Raw sample indices/probe plans and dataset images are withheld; evaluation definitions, seeds, class/count metadata and saved dataset/partition hashes are provided.
- Per-probe counterfactual accuracy was not recorded: accuracy_A07/accuracy_sem are blank, not inferred from CE.
- Absolute per-region source masses are not recorded in every weight journal. They remain blank outside existing observations; no inverse estimate from normalized shares.
- Runtime uncommitted diffs absent from saved manifests are NOT_SAVED. Export-time clean/tracked state is not retroactive proof of runtime cleanliness.
- Proposed extended-holdout or formal experiments without actual completion records are not claimed completed. Protocol documents describe plans; actual runs.csv entries are the verified run directories.
- Standalone earlier Receiver fixed5 raw server folder was not found in the authorized current project; its existing published scalar evidence is still preserved.
''',encoding='utf-8')


def build(source,out):
 e=Export(source,out)
 # Each actual execution receives its own identity. Postprocessing is stored
 # beneath its parent execution, never counted as a new seed or training run.
 r1000=source/'tmp/semantic_activation1000_collected/active/training/a07/active_1000_seed1'
 e.run('v2_active1000_seed1',r1000,'Semantic-A07 V2',1000,commit='149c6713c339204ad23fe43952350ae2832b3cd0')
 e.tree('v2_active1000_seed1',source/'docs/evidence/semantic_a07_v2/activation1000/results','logs/v2_active1000_seed1/collected_results','Original complete 1000-round scalar collection and native CSVs')
 e.tree('v2_active1000_seed1',source/'docs/evidence/semantic_a07_v2/activation1000','reports/activation1000','All existing views, including original and explicitly selected favorable cases')
 for mode,rid in [('neutral','a07_neutral500_seed1'),('active','v2_active500_seed1')]:
  root=source/f'tmp/semantic_pair500_collected/{mode}/training/a07/{mode}_500_seed1'
  e.run(rid,root,'A07-only with observation' if mode=='neutral' else 'Semantic-A07 V2',500,mode,
   commit='49b5b5f86fe61815aa47b09445b27a0c6db2fbee',reference='v2_active500_seed1' if mode=='neutral' else 'a07_neutral500_seed1',
   notes='Separate trajectory; only in-run diagnostic calls are same-input counterfactuals. V2 overlaps 1000-run prefix.')
  e.tree(rid,source/f'docs/evidence/semantic_a07_v2/pair500/results/{mode}',f'logs/{rid}/collected_results')
 for mode in ('reference','neutral','active'):
  for n in (2,20):
   rid=f'v2_short_{mode}_{n}_seed1';root=source/f'tmp/semantic_a07_v2_collected/runs/semantic_a07_v2_short_20261022/a07/{mode}_{n}_seed1'
   e.run(rid,root,'Semantic-A07 V2 short regression',n,mode,reference='' if mode=='reference' else f'v2_short_reference_{n}_seed1')
 for n in (2,20):
  rid=f'v2_iv_e_{n}_seed1';folder=source/f'tmp/semantic_iv_e_collected/runs/semantic_a07_iv_e_20261022/diagnostic_{n}'
  meta=load(folder/'diagnostic_manifest.json')
  e.run(rid,folder/f'training/a07/active_{n}_seed1','Semantic-A07 V2 early IV-E',n,commit=meta['commit'],reference=f'v2_short_active_{n}_seed1')
  e.copy(rid,folder/'diagnostic_manifest.json',Path('provenance')/rid/'diagnostic_manifest.json')
  e.tree(rid,folder,Path('logs')/rid/'diagnostic_parent','Original diagnostic parent protocol/completion and child journals')
 e.tree('v2_iv_e_20_seed1',source/'docs/evidence/semantic_a07_v2/mechanism_iv_e','reports/early_iv_e')
 for revision in ('v1','v2'):
  for mode in ('reference','observe'):
   for n in (2,20):
    rid=f'v1_regression_{revision}_{mode}_{n}_seed1'
    root=source/f'docs/evidence/semcons_a07/regression_{revision}/semcons_a07_regression_{revision}_20261022/a07/{mode}_{n}_seed1'
    e.run(rid,root,'SemCons-A07 V1 observation regression',n,mode,reference='' if mode=='reference' else f'v1_regression_{revision}_reference_{n}_seed1',notes='Earlier revision kept separately, including imperfect preliminary regression evidence')
  e.tree('REGRESSION_SUITE_'+revision,source/f'docs/evidence/semcons_a07/regression_{revision}',Path('provenance')/('regression_suite_'+revision))
 e.tree('SHORT_V2_SUITE',source/'tmp/semantic_a07_v2_collected/runs/semantic_a07_v2_short_20261022','provenance/short_v2_suite')
 e.run('v1_observation400_seed1',source/'docs/evidence/semcons_a07/final','SemCons-A07 V1 observation gamma1',400,'observe',commit='01e8a92049fc096dc977fbbbe64d029ad4de887e',notes='Prototype utility mechanism run; original No-Go results retained')
 mature=source/'runs/mature_receiver_q_final5_seed1_20261019'
 e.run('mature_receiver_fixed5_seed1',mature,'Earlier Q receiver diagnostic from E03 final400',5,'diagnostic',commit=load(mature/'manifest.json')['source_commit'],notes='Five fixed local-update sampling batches; no global rounds401-405, no feedback')
 e.tree('mature_receiver_fixed5_seed1',source/'runs/mature_receiver_q_final5_seed1_20261019_final','reports/mature_receiver_fixed5')
 e.tree('mature_receiver_fixed5_seed1',source/'runs/mature_receiver_q_final5_seed1_20261019_analysis','reports/mature_receiver_fixed5_initial')
 e.copy('e03_final400_anchor',source/'runs/mature_q_inputs/E03_manifest.json','provenance/mature_anchor/E03_manifest.json')
 struct=source/'runs/structure_counterfactual5_20261019'
 e.run('structure_counterfactual5',struct,'Earlier Native/M2/M3/global/regional offline comparison',5,'offline_only',commit=load(struct/'completed.json')['source_commit'],notes='Postprocessing of mature five batches; zero SGD; parent mature_receiver_fixed5_seed1')
 e.runs[-1]['parent_run_id']='mature_receiver_fixed5_seed1'
 receiver_meta=source/'docs/evidence/receiver_ce_fixed5_seed1_20261019.json'
 e.runs.append(dict(run_id='receiver_fixed5_seed1',algorithm='Earlier Q receiver training-side diagnostic',rounds=5,seed=1,mode='diagnostic',
  source_commit='UNKNOWN; original per-file hashes in saved evidence',source_directory='NOT_FOUND_CURRENT_SERVER; existing scalar evidence retained',
  paired_reference_run_id='',parent_run_id='',completion_marker_present=False,partition_sha256=PARTITION,applied_lambda='N/A',runtime_dirty_diff='NOT_SAVED',
  notes='Do not substitute reviewed/final report commit for actual training SHA; earlier Q delta_ce positive means harm'))
 for name in ['receiver_ce_fixed5_seed1_20261019.json','receiver_ce_pairs.csv','receiver_ce_classes.csv']:
  e.copy('receiver_fixed5_seed1',source/'docs/evidence'/name,Path('logs/receiver_fixed5_seed1')/name)
 # All native 500-run reports, source indices and scalar validation (including
 # the original report failure) are retained, not selected by scientific result.
 e.tree('pair500_publication',source/'docs/evidence/semantic_a07_v2/pair500','reports/pair500')
 for name in ['SEMANTIC_A07_V2_DESIGN.md','SEMANTIC_A07_V2_AUDIT.md','SEMANTIC_A07_V2_RESULTS.md',
              'SEMANTIC_A07_PAIR500_PROTOCOL.md','SEMANTIC_A07_PAIR500_RESULTS.md','IV_E_MECHANISM_PROTOCOL.md','IV_E_EXPANDED_PROTOCOL.md',
              'SEMCONS_A07_SOURCE_AUDIT.md','SEMCONS_A07_DESIGN.md','SEMCONS_A07_RESULTS.md','SEMCONS_A07_REVIEWER_ALIGNMENT.md',
              'SEMCONS_A07_FINAL_AUDIT.md','RECEIVER_CE_FIXED_PROBE_DIAGNOSIS.md','MATURE_Q_FINAL_READONLY_VALIDATION.md','STRUCTURE_COUNTERFACTUAL5.md',
              'SEMCONS_MECHANISM_EVIDENCE_PLAN_20261024.md']:
  e.copy('DOCUMENTATION',source/'docs'/name,Path('provenance/reports')/name)
 for p in sorted((source/'configs').glob('*')):
  if p.is_file() and any(x in p.name for x in ('semcons','semantic','receiver','mature_q')):e.copy('CONFIGURATION',p,Path('provenance/configs')/p.name)
 for p in sorted((source/'tools').glob('*.py')):
  if any(x in p.name for x in ('semantic','semcons_a07','receiver_ce','mature_q','structure_counterfactual','mechanism_tmc','final_mechanism_case')):
   e.copy('CURRENT_AUDIT_TOOLS',p,Path('provenance/scripts')/p.name,'Current audit/plot/export tool, distinct from frozen training source')
 e.add_checkpoint_inventory();e.snapshots_for_runs();e.finish()
 (out/'README.md').write_text('''# tmc-result

Public archive of **existing** SemConsFL/A07 mechanism evidence, frozen code snapshots, original scalar records, and documented missing state.

Start with [mechanism_evidence/README.md](mechanism_evidence/README.md), [run registry](mechanism_evidence/runs.csv), [manifest](mechanism_evidence/manifest.json), and [file inventory](mechanism_evidence/file_inventory.csv).

Main 1000-round evidence: [logs](mechanism_evidence/logs/v2_active1000_seed1/), [class-level Memory evidence](mechanism_evidence/memory/v2_active1000_seed1/), [aggregation shares](mechanism_evidence/aggregation/v2_active1000_seed1/), and [same-input counterfactuals](mechanism_evidence/counterfactual/v2_active1000_seed1/).

Paired 500-round and earlier short/receiver diagnostics have distinct run IDs. They are not pooled as independent replicas. Positive, negative and neutral observations are retained. No new training or counterfactual evaluation was performed for this release.

Models, private data and sample-bearing probes are excluded; see [checkpoint inventory](mechanism_evidence/checkpoints/checkpoint_inventory.csv) and [missing data report](mechanism_evidence/provenance/missing_data_report.md). Large scalar logs are losslessly compressed, never fabricated or split.
''',encoding='utf-8')
 (out/'.gitattributes').write_text('* -text\n',encoding='utf-8')
 (out/'.gitignore').write_text('__pycache__/\n*.pyc\n.env\n*.pt\n*.pth\n*.ckpt\n*.safetensors\n',encoding='utf-8')
 return e


def main():
 ap=argparse.ArgumentParser(__doc__);ap.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1]);ap.add_argument('--output-root',type=Path,required=True)
 args=ap.parse_args();e=build(args.source_root.resolve(),args.output_root.resolve())
 print(json.dumps(dict(runs=len(e.runs),indexed_files=len(e.inventory),checkpoints=len(e.checkpoints),snapshot_commits=len(e.snapshots))))


if __name__=='__main__':main()
