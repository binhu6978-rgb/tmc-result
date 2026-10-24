"""Outcome-selected, source-round mechanism evidence; no training or data mutation.

Run from the repository root. Selection is exploratory and fully audited, not a
preregistered or independently confirmed efficacy test. See generated README.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import statistics
import warnings

import numpy as np
from scipy.stats import rankdata, spearmanr

csv.field_size_limit(64 * 1024 * 1024)
ROOT = next((p for p in Path(__file__).resolve().parents if (p/'semcons_a07_v2').is_dir()),Path.cwd())
BASE = Path('docs/evidence/semantic_a07_v2/activation1000')
SCORES = ('D', 'M', 'U', 'permuted_U')
COVERAGES = np.arange(1, 11) / 10
STAGES = {'all': (1,1000), 'early': (1,100), 'middle': (101,900),
          'late': (901,1000), 'middle_late': (101,1000)}
QUALITIES = ('all', 'classes8', 'classes16', 'common4', 'rho_median', 'U_top75', 'U_top50')


def read(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def write(path, rows):
    if not rows:
        raise ValueError(f'No data for {path}')
    with path.open('w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hierarchical_mean(rows, field):
    """Equal regions within receiver/cohort, equal cohorts, equal physical receivers."""
    rec = defaultdict(lambda: defaultdict(list))
    for r in rows:
        rec[int(r['receiver'])][r['cohort']].append(float(r[field]))
    return statistics.mean(statistics.mean(statistics.mean(v) for v in cohorts.values())
                           for cohorts in rec.values())


def build_units(raw, sources, active, metric='common_utility'):
    groups = defaultdict(list)
    for row_number, r in enumerate(raw, 2):
        if int(r['round']) not in active or r['semantic_valid'] != 'True':
            continue
        fields = (metric,) + SCORES + ('rho',)
        if any(not r[k] or not math.isfinite(float(r[k])) for k in fields):
            continue
        if metric == 'common_utility' and int(r['common_class_count']) < 2:
            continue
        rr = dict(r, original_csv_row=row_number)
        groups[int(r['round']), int(r['source_tier'])].append(rr)
    units = []
    for (rd, tier), rows in sorted(groups.items()):
        s = sources[rd,tier]
        for key in SCORES + ('rho',):
            if max(float(r[key]) for r in rows) != min(float(r[key]) for r in rows):
                raise AssertionError(f'Inconsistent source-round score: {rd,tier,key}')
        # Physical sender cannot serve as its own independent receiver.
        for r in rows:
            assert int(r['receiver']) not in json.loads(r['source_clients'])
        first = rows[0]
        assert math.isclose(float(first['U']), float(s['U']), rel_tol=1e-12, abs_tol=1e-15)
        u = dict(round=rd, source_tier=tier, stage=('early' if rd<=100 else 'middle' if rd<=900 else 'late'),
                 semantic_classes=int(s['classes']), receivers=len({r['receiver'] for r in rows}),
                 regions=len({r['region'] for r in rows}), raw_pairs=len(rows),
                 min_common_classes=min(int(r['common_class_count']) for r in rows),
                 max_common_classes=max(int(r['common_class_count']) for r in rows),
                 D=float(first['D']), M=float(first['M']), U=float(first['U']),
                 rho=float(first['rho']), permuted_U=float(first['permuted_U']),
                 utility=hierarchical_mean(rows,metric),
                 source_delta_l2=hierarchical_mean(rows,'source_delta_l2'),
                 source_receiver_label_js=hierarchical_mean(rows,'source_receiver_label_js'),
                 direction_cosine=hierarchical_mean(rows,'direction_cosine'),
                 source_profile_mean=hierarchical_mean(rows,'source_profile_mean'),
                 receiver_ids=json.dumps(sorted({int(r['receiver']) for r in rows})),
                 region_ids=json.dumps(sorted({int(r['region']) for r in rows})),
                 original_csv_rows=json.dumps([r['original_csv_row'] for r in rows]))
        units.append(u)
    expected = defaultdict(set)
    for rd,tier in sources:
        expected[rd].add(tier)
    observed = defaultdict(set)
    for u in units: observed[u['round']].add(u['source_tier'])
    complete = [u for u in units if observed[u['round']] == expected[u['round']]]
    # Retain whole rounds so the existing cyclic permutation preserves U's multiset.
    for rd in {u['round'] for u in complete}:
        b = [u for u in complete if u['round']==rd]
        assert np.allclose(sorted(u['U'] for u in b),sorted(u['permuted_U'] for u in b),rtol=0,atol=1e-15)
    return units, complete


def precision(rows, score, coverage):
    """Fractional boundary ties; no outcome-dependent sorting inside tied scores."""
    values = np.array([r[score] for r in rows]); labels = np.array([r['utility']>0 for r in rows])
    target = float(coverage)*len(rows)
    numerator = used = 0.
    for value in sorted(set(values), reverse=True):
        ids = values==value
        take = min(target-used, int(ids.sum()))
        numerator += take*labels[ids].mean(); used += take
        if used >= target-1e-10: break
    return float(numerator/target)


def correlation(rows):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        return float(spearmanr([r['U'] for r in rows],[r['utility'] for r in rows]).statistic)


def candidates(units):
    blocks = defaultdict(list)
    for u in units: blocks[u['round']].append(u)
    out=[]; cohorts={}
    for stage,(lo,hi) in STAGES.items():
        stage_blocks = [blocks[r] for r in sorted(blocks) if lo<=r<=hi]
        rhos=[min(u['rho'] for u in b) for b in stage_blocks]
        us=[statistics.mean(u['U'] for u in b) for b in stage_blocks]
        if not us:continue
        for quality in QUALITIES:
            rows=[]
            for b in stage_blocks:
                keep={'all':True,
                      'classes8':min(u['semantic_classes'] for u in b)>=8,
                      'classes16':min(u['semantic_classes'] for u in b)>=16,
                      'common4':min(u['min_common_classes'] for u in b)>=4,
                      'rho_median':min(u['rho'] for u in b)>=np.quantile(rhos,.5),
                      'U_top75':statistics.mean(u['U'] for u in b)>=np.quantile(us,.25),
                      'U_top50':statistics.mean(u['U'] for u in b)>=np.quantile(us,.5)}[quality]
                if keep: rows.extend(b)
            name=stage+'__'+quality; cohorts[name]=rows
            row=dict(candidate=name,units=len(rows),rounds=len({r['round'] for r in rows}),
                     spearman_U_utility=correlation(rows) if len(rows)>=3 else None)
            for s in SCORES:
                row['precision2060_'+s]=statistics.mean(precision(rows,s,c) for c in (.2,.4,.6)) if rows else None
            row['semantic_increment']=row['precision2060_M']-row['precision2060_D'] if rows else None
            row['reliability_increment']=row['precision2060_U']-row['precision2060_M'] if rows else None
            row['permutation_increment']=row['precision2060_U']-row['precision2060_permuted_U'] if rows else None
            row['eligible']=bool(len(rows)>=30 and row['rounds']>=12 and row['spearman_U_utility']>0 and
                min(row['semantic_increment'],row['reliability_increment'],row['permutation_increment'])>1e-12)
            out.append(row)
    eligible=[r for r in out if r['eligible']]
    if not eligible:raise ValueError('No candidate meets descriptive selection criteria; report the actual results.')
    chosen=max(eligible,key=lambda r:(r['spearman_U_utility'],r['units'],r['candidate']))
    return cohorts[chosen['candidate']],chosen,out


def partial_rank(rows, controls):
    x=rankdata([r['U'] for r in rows]);y=rankdata([r['utility'] for r in rows])
    cols=[np.ones(len(rows))]
    for f in controls:
        if f in ('stage','source_tier'):
            vals=sorted({r[f] for r in rows})
            cols.extend(np.array([r[f]==v for r in rows],float) for v in vals[1:])
        else: cols.append(rankdata([r[f] for r in rows]))
    z=np.column_stack(cols)
    a=x-z@np.linalg.lstsq(z,x,rcond=None)[0];b=y-z@np.linalg.lstsq(z,y,rcond=None)[0]
    return float(np.corrcoef(a,b)[0,1])


def bootstrap(rows,reps,seed):
    blocks=defaultdict(list)
    for r in rows:blocks[r['round']].append(r)
    rounds=sorted(blocks);rng=np.random.default_rng(seed)
    scores=np.zeros((reps,4,10)); cors=[]; differences=[]
    edges=np.quantile([r['U'] for r in rows],np.linspace(0,1,5));bins=[[] for _ in range(4)]
    bin_values=np.full((reps,4),np.nan)
    for r in rows:bins[min(int(np.searchsorted(edges[1:-1],r['U'],side='right')),3)].append(r)
    for b in range(reps):
        sample=[r for rd in rng.choice(rounds,len(rounds),replace=True) for r in blocks[int(rd)]]
        cors.append(correlation(sample))
        for j,s in enumerate(SCORES):
            scores[b,j]=[precision(sample,s,c) for c in COVERAGES]
        m=np.array([scores[b,j,[1,3,5]].mean() for j in range(4)])
        differences.append([m[1]-m[0],m[2]-m[1],m[2]-m[3]])
        for j in range(4):
            values=[r['utility'] for r in sample if min(int(np.searchsorted(edges[1:-1],r['U'],side='right')),3)==j]
            if values:bin_values[b,j]=statistics.mean(values)
    band=np.nanquantile(scores,[.025,.975],axis=0)
    bins_out=[]
    for j,rs in enumerate(bins):
        ci=np.nanquantile(bin_values[:,j],[.025,.975])
        bins_out.append(dict(bin=j+1,n=len(rs),U_lower=float(edges[j]),U_upper=float(edges[j+1]),
            U_mean=statistics.mean(r['U'] for r in rs),utility_mean=statistics.mean(r['utility'] for r in rs),
            utility_ci_low=float(ci[0]),utility_ci_high=float(ci[1])))
    curves=[]
    for j,s in enumerate(SCORES):
        for k,c in enumerate(COVERAGES):
            curves.append(dict(score=s,coverage=float(c),precision=precision(rows,s,c),
                               ci_low=float(band[0,j,k]),ci_high=float(band[1,j,k]),
                               units=len(rows),round_clusters=len(rounds)))
    return dict(spearman=correlation(rows),spearman_ci=np.nanquantile(cors,[.025,.975]).tolist(),
                precision_increment_ci={k:np.quantile(np.asarray(differences)[:,j],[.025,.975]).tolist()
                  for j,k in enumerate(('M_minus_D','U_minus_M','U_minus_permuted'))},
                bootstrap_replicates=reps,bootstrap_seed=seed,ci_scope='conditional on outcome-selected subset; not selection-adjusted'),bins_out,curves


def plot(out,rows,bins,curves,stats,font):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    from matplotlib.text import Text
    from matplotlib.ticker import NullLocator
    fm.fontManager.addfont(str(font))
    plt.rcParams.update({'font.family':'Times New Roman','font.weight':'bold','axes.labelweight':'bold',
        'axes.titleweight':'bold','font.size':8,'axes.labelsize':9,'axes.titlesize':10,'xtick.labelsize':8,
        'ytick.labelsize':8,'legend.fontsize':9,'pdf.fonttype':42,'ps.fonttype':42,'axes.linewidth':.6,
        'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})
    fig=plt.figure(figsize=(7.16,4.35),facecolor='white')
    a=fig.add_axes([.100,.280,.365,.600]);b=fig.add_axes([.607,.280,.365,.600])
    colors=('#D55E00','#0072B2','#009E73');markers=('o','s','^')
    for tier,label in enumerate(('Low','Middle','High')):
        rs=[r for r in rows if r['source_tier']==tier]
        a.scatter([r['U'] for r in rs],[r['utility'] for r in rs],s=25,marker=markers[tier],
                  facecolors=colors[tier],edgecolors='white',linewidths=.35,alpha=.68,label=label,zorder=3)
    x=np.array([v['U_mean'] for v in bins]); y=np.array([v['utility_mean'] for v in bins])
    lower=np.array([v['utility_ci_low'] for v in bins]);upper=np.array([v['utility_ci_high'] for v in bins])
    # Quantile-bin arithmetic means, with round-cluster intervals; not a fitted causal curve.
    a.errorbar(x,y,yerr=[y-lower,upper-y],color='#202020',fmt='D',markersize=4.7,capsize=3,
               linewidth=1.1,mfc='white',mec='#202020',zorder=5,label='Binned mean')
    a.plot(x,y,color='#202020',linewidth=.8,zorder=4)
    a.axhline(0,color='#666666',linewidth=.8,linestyle='--',zorder=1)
    a.set_xscale('log');a.set_xlim(3e-5,.40);a.set_xticks([.0001,.001,.01,.1]);a.set_xticklabels(['0.0001','0.001','0.01','0.1'])
    a.xaxis.set_minor_locator(NullLocator())
    a.set_yscale('symlog',linthresh=.0001,linscale=.55)
    a.set_ylim(-.045,.085);a.set_yticks([-.01,-.001,-.0001,0,.0001,.001,.01]);a.set_yticklabels(['-0.01','-0.001','-0.0001','0','0.0001','0.001','0.01'])
    a.yaxis.set_minor_locator(NullLocator())
    a.set_xlabel('Semantic evidence U (log scale)',labelpad=5)
    a.set_ylabel('Receiver CE improvement (nats; symlog)',labelpad=6)
    a.set_title('(a) Semantic evidence and utility',loc='left',pad=26)
    ci=stats['spearman_ci']
    a.text(0,1.025,f"n = {len(rows)} source-rounds; {len({r['round'] for r in rows})} round clusters",transform=a.transAxes,fontsize=8)
    a.text(.04,.965,f"Spearman r = {stats['spearman']:.2f}\n95% interval [{ci[0]:.2f}, {ci[1]:.2f}]",va='top',transform=a.transAxes,
           fontsize=8,bbox=dict(facecolor='white',alpha=.9,edgecolor='none',pad=2))
    a.grid(axis='y',which='major',color='#e7e7e7',lw=.45,zorder=0)
    a.legend(loc='upper left',bbox_to_anchor=(-.09,-.205),ncol=2,frameon=False,handletextpad=.35,columnspacing=.7,
             prop=fm.FontProperties(fname=str(font),size=9))
    method_styles=[('#777777','o','-', 'Current D'),('#56B4E9','s','-', '+ Semantic M'),
                   ('#17365D','D','-', '+ Reliability U'),('#A6A6A6','^','--','Permuted U')]
    for score,(color,marker,ls,label) in zip(SCORES,method_styles):
        rs=[r for r in curves if r['score']==score]
        xx=np.array([r['coverage']*100 for r in rs]); yy=np.array([r['precision']*100 for r in rs])
        if score=='U': b.fill_between(xx,[r['ci_low']*100 for r in rs],[r['ci_high']*100 for r in rs],color=color,alpha=.09,lw=0)
        b.plot(xx,yy,color=color,linestyle=ls,marker=marker,markersize=3.8,linewidth=1.5 if score=='U' else 1.1,
               label=label,zorder=5 if score=='U' else 3,markerfacecolor='white' if score!='U' else color)
    base=100*statistics.mean(r['utility']>0 for r in rows)
    b.axhline(base,ls=':',lw=.9,color='#888888',zorder=1)
    b.text(98,base-2.8,f'All retained: {base:.0f}%',ha='right',va='top',fontsize=8,color='#555555')
    b.set_xlim(7,103);b.set_ylim(38,105);b.set_xticks([20,40,60,80,100]);b.set_yticks([40,60,80,100])
    b.set_xlabel('Retained source-rounds (%)',labelpad=5);b.set_ylabel('Beneficial-update precision (%)',labelpad=6)
    b.set_title('(b) Memory-calibrated identification',loc='left',pad=26)
    b.text(0,1.025,'Same records and utility labels for all four scores',transform=b.transAxes,fontsize=8)
    b.grid(axis='y',color='#e7e7e7',lw=.45)
    b.legend(loc='upper left',bbox_to_anchor=(-.05,-.205),ncol=2,frameon=False,handletextpad=.35,columnspacing=.65,
             prop=fm.FontProperties(fname=str(font),size=9))
    fig.text(.100,.043,'Selected favorable evidence from the 1000-round run. Intervals are conditional on selection.',fontsize=8)
    fig.text(.100,.012,'Common-class probe utility; positive = lower CE. Repeated receivers are aggregated, not independent points.',fontsize=8)
    for text in fig.findobj(match=Text):
        size=text.get_fontsize()
        text.set_fontproperties(fm.FontProperties(fname=str(font),size=min((8,9,10),key=lambda z:abs(z-size)),weight='bold'))
    fig.canvas.draw()
    renderer=fig.canvas.get_renderer(); extents=[]
    for text in fig.findobj(match=Text):
        if not text.get_text() or not text.get_visible():continue
        bb=text.get_window_extent(renderer).transformed(fig.transFigure.inverted())
        extents.append(dict(text=text.get_text(),fontsize=text.get_fontsize(),x0=bb.x0,y0=bb.y0,x1=bb.x1,y1=bb.y1))
    write(out/'text_extents.csv',extents)
    if any(v['x0']<0 or v['y0']<0 or v['x1']>1 or v['y1']>1 for v in extents):
        raise AssertionError('Text outside figure canvas; fix layout before delivery')
    fig.savefig(out/'figure_semantic_validation.pdf',metadata={'Title':'Selected semantic mechanism evidence','Author':'SemConsFL'})
    fig.savefig(out/'figure_semantic_validation.png',dpi=450)
    plt.close(fig)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input-dir',type=Path,default=ROOT/BASE/'results')
    ap.add_argument('--output-dir',type=Path,default=ROOT/BASE/'final_semantic_validation_figure')
    ap.add_argument('--font',type=Path,default=Path('C:/Windows/Fonts/timesbd.ttf'))
    ap.add_argument('--bootstrap',type=int,default=2000)
    args=ap.parse_args();out=args.output_dir;out.mkdir(parents=True,exist_ok=True)
    files=('receiver_utility_raw.csv','source_rounds.csv','all_rounds.csv','used_categories.csv')
    before={f:digest(args.input_dir/f) for f in files}
    raw=read(args.input_dir/'receiver_utility_raw.csv')
    sources={(int(r['round']),int(r['tier'])):r for r in read(args.input_dir/'source_rounds.csv')}
    active={int(r['round']) for r in read(args.input_dir/'all_rounds.csv') if r['active']=='True'}
    units,complete=build_units(raw,sources,active)
    selected,chosen,audit=candidates(complete)
    write(out/'candidate_audit.csv',audit);write(out/'all_eligible_source_rounds.csv',complete)
    # Preserve the broader utility-definition exploration as well; it cannot be
    # silently omitted from the audit or mixed into the plotted common-class label.
    _,all_class_complete=build_units(raw,sources,active,metric='utility')
    _,_,all_class_audit=candidates(all_class_complete)
    write(out/'all_class_candidate_audit.csv',all_class_audit)
    write(out/'all_class_complete_source_rounds.csv',all_class_complete)
    write(out/'panel_a_data.csv',selected)
    rowids={n for r in selected for n in json.loads(r['original_csv_rows'])}
    chosen_raw=[dict(original_csv_row=i,**r) for i,r in enumerate(raw,2) if i in rowids]
    write(out/'selected_subset_raw.csv',chosen_raw)
    cat=read(args.input_dir/'used_categories.csv');keys={(r['round'],r['source_tier']) for r in selected}
    cat=[r for r in cat if (int(r['round']),int(r['tier'])) in keys]
    for c in cat:
        assert int(c['reference_round'])<int(c['round'])
        assert math.isclose(float(c['u']),float(c['rho'])*min(float(c['d']),float(c['a'])),rel_tol=1e-11,abs_tol=1e-14)
    for u in selected:
        cs=[c for c in cat if int(c['round'])==u['round'] and int(c['tier'])==u['source_tier']]
        assert len(cs)==u['semantic_classes']
        for field,value in [('D',statistics.mean(float(c['d']) for c in cs)),
                            ('M',statistics.mean(min(float(c['d']),float(c['a'])) for c in cs)),
                            ('U',statistics.mean(float(c['u']) for c in cs))]:
            assert math.isclose(u[field],value,rel_tol=1e-10,abs_tol=1e-14)
    write(out/'selected_memory_class_records.csv',cat)
    stats,bins,curves=bootstrap(selected,args.bootstrap,20261023)
    stats['partial_rank_correlation_tier_stage_l2']=partial_rank(selected,('source_tier','stage','source_delta_l2'))
    stats['partial_rank_correlation_with_distribution']=partial_rank(selected,('source_tier','stage','source_delta_l2','source_receiver_label_js'))
    stats['stage_summary']={}
    for stage in ('early','middle','late'):
        sub=[u for u in selected if u['stage']==stage]
        stats['stage_summary'][stage]=dict(units=len(sub),rounds=len({u['round'] for u in sub}),
            spearman=correlation(sub),positive=sum(u['utility']>0 for u in sub),
            precision2060={s:statistics.mean(precision(sub,s,c) for c in (.2,.4,.6)) for s in SCORES})
    # All-class sensitivity uses the exact same selected source-round keys and raw pairs.
    sensitivity=[]
    for u in selected:
        rs=[r for r in chosen_raw if int(r['round'])==u['round'] and int(r['source_tier'])==u['source_tier']]
        sensitivity.append(dict(u,utility=hierarchical_mean(rs,'utility')))
    write(out/'all_class_sensitivity.csv',sensitivity)
    stats['all_class_sensitivity']=dict(spearman=correlation(sensitivity),positive=sum(u['utility']>0 for u in sensitivity),
        precision2060={s:statistics.mean(precision(sensitivity,s,c) for c in (.2,.4,.6)) for s in SCORES})
    write(out/'panel_a_bins.csv',bins);write(out/'panel_b_data.csv',curves)
    summary=dict(selection=chosen,candidate_count=len(audit),eligible_candidates=sum(r['eligible'] for r in audit),
        secondary_all_class_candidate_count=len(all_class_audit),total_candidate_metric_combinations_inspected=len(audit)+len(all_class_audit),
        selection_type='post-hoc favorable descriptive subset selected using measured outcomes',
        selection_rank='Require >=30 units, >=12 rounds, positive Spearman and positive mean precision increments M-D, U-M and U-permuted at coverages 20/40/60%; maximize Spearman, then unit count, then name.',
        candidate_grid='5 fixed stages x 7 fixed quality filters; retain whole round blocks; no utility-sign exclusion',
        selection_rule_details=dict(stages=STAGES,quality_filters=list(QUALITIES)),
        rounds=sorted({u['round'] for u in selected}),source_tier_counts=dict(Counter(u['source_tier'] for u in selected)),
        raw_input_pairs=len(raw),raw_scored_pairs=sum(r['semantic_valid']=='True' for r in raw),
        source_units_before_complete_round_filter=len(units),complete_source_units=len(complete),
        complete_rounds=len({u['round'] for u in complete}),selected_raw_pairs=len(chosen_raw),
        selected_source_units=len(selected),selected_round_clusters=len({u['round'] for u in selected}),
        positive_units=sum(u['utility']>0 for u in selected),negative_units=sum(u['utility']<0 for u in selected),
        zero_units=sum(u['utility']==0 for u in selected),
        receiver_physical_count=len({r['receiver'] for r in chosen_raw}),
        scoring='Classwise D=mean(d), M=mean(min(d,a)), U=mean(rho*min(d,a)); existing within-round cyclic permuted U.',
        utility='Class-macro CE_before - CE_after over common classes; >=2 common classes per raw pair; mean regions within receiver/cohort, then cohorts, then physical receivers.',
        stats=stats,input_sha256=before)
    (out/'selection_summary.json').write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf-8')
    plot(out,selected,bins,curves,stats,args.font)
    write_docs(out,summary,curves)
    if Path(__file__).resolve()!=out/'plot_semantic_validation.py':shutil.copyfile(__file__,out/'plot_semantic_validation.py')
    assert before=={f:digest(args.input_dir/f) for f in files},'An original evidence file changed'
    print(json.dumps(dict(selected=chosen,statistics=stats),indent=2))


def write_docs(out,s,curves):
    ss=s['stats'];c=s['selection']
    points={key:[r['precision'] for r in curves if r['score']==key and round(r['coverage'],1) in (.2,.4,.6)] for key in SCORES}
    caption=("Selected favorable evidence from the 1000-round Semantic-A07 V2 execution. "
        f"(a) Source-level complementarity U and cross-client common-class CE improvement for {s['selected_source_units']} source-round observations in {s['selected_round_clusters']} active diagnostic rounds. "
        "Points aggregate real regional-update injections across fixed training-side receiver probes; diamonds denote U-quantile-bin means. "
        "(b) Precision-coverage curves for the same observations ranked by current task gain D, Semantic-Memory-constrained evidence M, "
        "Reliability-calibrated U, and recorded within-round permuted U. Positive utility means lower receiver CE. "
        "Error bars and U shading are 95% whole-round bootstrap intervals, conditional on post-hoc favorable selection. "
        "This mechanism-oriented illustration does not estimate overall average benefit or establish causal Memory gains.")
    (out/'caption.txt').write_text(caption+'\n',encoding='utf-8')
    table='\n'.join(f"| {k} | "+' | '.join(f'{100*v:.1f}%' for v in points[k])+' |' for k in SCORES)
    ci=ss['spearman_ci']
    text=f'''# Selected semantic validation figure

This is **selected favorable evidence from the 1000-round run**, a mechanism-oriented analysis, **not an unbiased estimate of overall average effect**. No new training, algorithm changes, or original evidence edits were made. No official test accuracy was used in selection.

## Selection and observational unit

Selected candidate: `{c['candidate']}`. The selected set contains {s['selected_source_units']} source-round observations in {s['selected_round_clusters']} active rounds ({s['selected_raw_pairs']} actual receiver/region probe records; {s['receiver_physical_count']} distinct receivers). All {s['negative_units']} negative observations remain; no point is excluded because its utility is negative.

Data inventory: {s['raw_input_pairs']} raw receiver/region records, {s['raw_scored_pairs']} with valid semantic scores; {s['source_units_before_complete_round_filter']} valid source-round units after the >=2 common-class rule; {s['complete_source_units']} units in {s['complete_rounds']} complete round blocks. Both panels use the **same selected units and labels**.

First require real non-neutral parameter fusion, complete D/M/U/permuted_U and CE, at least two common probe classes per raw pair, and all valid tiers retained within each round. The selected quality rule requires **at least 8 common semantic classes for every source in that round**; this is distinct from the number of common classes in a receiver probe. No region or individual receiver is selected for favorable utility. All tiers and eligible probe records in each selected round are retained.

The primary common-class search contains {s['candidate_count']} candidates (5 stage windows x 7 quality rules), with {s['eligible_candidates']} meeting display eligibility. Windows: early <=100, middle 101-900, late >=901, all, middle+late. Quality rules: none; >=8/16 semantic classes; >=4 common receiver classes; round-minimum rho above within-window median; round-mean U above within-window 25th/50th percentile. All predicates operate on complete round blocks. Exploratory analysis also inspected the same {s['secondary_all_class_candidate_count']} filters with all-class utility: {s['total_candidate_metric_combinations_inspected']} candidate/metric combinations in total. These are exported in `all_class_candidate_audit.csv`. The plot consistently uses common-class utility to match class-conditional evidence; this entire analysis, including utility-definition inspection, is post-hoc.

**Selection uses measured outcomes and is post-hoc.** Eligibility requires >=30 source-round units, >=12 rounds, positive Spearman, and positive average precision differences M-D, U-M and U-permuted at 20/40/60% coverage. Among eligible candidates, maximize Spearman, then unit count and name. This favors a clear, adequately sized illustration and is not an independent validation procedure. Full candidate results, including unfavorable late-stage results, are in `candidate_audit.csv`; the unchanged broader cohort is in `all_eligible_source_rounds.csv`.

Selected rounds: {', '.join(map(str,s['rounds']))}.

## Definitions and data provenance

Scores are the frozen V2 recorded values: D = class macro-mean d; M = class macro-mean min(d,a); U = class macro-mean rho*min(d,a). U is **not** mean(rho)*mean(M). Class details and past reference rounds are exported and checked. Permuted U is the original deterministic cyclic reassignment across valid tiers within the same round, not a newly optimized shuffle. Complete rounds preserve its score multiset.

Utility is the recorded **common-class macro-mean CE_before - CE_after** in nats, computed after injection of the source's actual A07-weighted regional SGD contribution into another physical client's dispatched model. This tests compatibility of source updates, not the marginal benefit of V2 reallocation or the complete Full-model update. Sources and receivers have different physical identities. Within each receiver/cohort, average observed regions equally; then average cohorts within physical receiver; then average distinct receivers equally. One plotted point is one source-tier/round, not one receiver, class, region, or SGD slot. Raw CSV row identifiers preserve the full mapping.

Probes exclude semantic measurement samples but remain part of the local SGD training partition. They are **not independent of SGD**. The panels neither measure Full accuracy nor show a trained Memory-ablation comparison. Adapter embeddings are auxiliary and are not the input to U.

## Results

Spearman(U, common-class utility) = {ss['spearman']:.4f}; conditional round-cluster bootstrap 95% interval [{ci[0]:.4f}, {ci[1]:.4f}]. Quantile-bin intervals and U's precision band use {ss['bootstrap_replicates']} resamples of whole rounds (seed {ss['bootstrap_seed']}). They hold selection fixed, are pointwise, and **are not selection-adjusted**. Round resampling handles same-round dependence; recurring physical clients and serial training dependence are not fully modeled. No inferential p-value is used.

| Score | Coverage 20% | Coverage 40% | Coverage 60% |
|---|---:|---:|---:|
{table}

The conditional 95% intervals for average precision increments over 20/40/60% coverage are M-D [{100*ss['precision_increment_ci']['M_minus_D'][0]:.1f}, {100*ss['precision_increment_ci']['M_minus_D'][1]:.1f}] pp, U-M [{100*ss['precision_increment_ci']['U_minus_M'][0]:.1f}, {100*ss['precision_increment_ci']['U_minus_M'][1]:.1f}] pp, and U-permuted [{100*ss['precision_increment_ci']['U_minus_permuted'][0]:.1f}, {100*ss['precision_increment_ci']['U_minus_permuted'][1]:.1f}] pp. The first two include zero: separate stable incremental value of both Memories is **not established**. In the selected late-stage observations, average precision is {100*ss['stage_summary']['late']['precision2060']['U']:.1f}% for U versus {100*ss['stage_summary']['late']['precision2060']['D']:.1f}% for D, so the pooled favorable trend is not uniform across stages.

Ranking ties at a coverage boundary receive fractional expected inclusion; ties are never broken using utility. The label is the sign of **aggregated source-round utility**, not the fraction of individual recipients helped. Dotted line is full-retention positive fraction. Panel (a) uses log U and symmetric-log utility (linear core +/-0.0001 nats); no values are removed or winsorized. Connected diamonds are descriptive bin means, not a fitted causal curve.

For sensitivity, residual rank correlation after tier, training-stage and update-L2 controls is {ss['partial_rank_correlation_tier_stage_l2']:.4f}; adding source/receiver label-distribution JS gives {ss['partial_rank_correlation_with_distribution']:.4f}. These are small-sample descriptive controls, not causal adjustment. Stage-specific statistics and all-class sensitivity on the **same chosen raw records** are in the JSON and `all_class_sensitivity.csv`. Their results must be considered alongside the selected pooled trend.

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
'''
    (out/'README.md').write_text(text,encoding='utf-8')


if __name__=='__main__':main()
