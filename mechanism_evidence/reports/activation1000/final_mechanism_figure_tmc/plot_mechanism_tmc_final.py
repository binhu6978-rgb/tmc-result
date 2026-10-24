"""TMC mechanism figure: immutable evidence, three font sizes, bold embedded text."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
METHODS = ('A07','V2','no_sm','no_rm','permuted','A07_L2_matched')


def read(path):
    with path.open(encoding='utf-8',newline='') as stream:return list(csv.DictReader(stream))


def write(path,records):
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)


def utility(group,method,metric):
    return (float(group[method]['utility_vs_a07']) if metric=='all' else
        float(group[method]['common_utility'])-float(group['A07']['common_utility']))


def choose_case(groups, active, source_classes):
    counts = Counter(all_receiver_round_cases=len(groups))
    audit = []; eligible = []
    for (rd, cid, cohort), methods in sorted(groups.items()):
        if rd not in active or not set(METHODS) <= methods.keys():
            continue
        counts['complete_non_neutral_cases'] += 1
        row = methods['V2']
        if row['semantic_valid'] != 'True' or int(row['common_class_count']) < 2:
            continue
        counts['valid_with_at_least_two_common_receiver_classes'] += 1
        effects = {metric:{m:utility(methods,m,metric) for m in METHODS} for metric in ('all','common')}
        favorable = all(e['V2'] > max(0,e['permuted'],e['A07_L2_matched']) for e in effects.values())
        memory_wins = sum(all(e['V2'] > e[m] for e in effects.values()) for m in ('no_sm','no_rm'))
        audit.append(dict(round=rd,receiver=cid,cohort=cohort,favorable_both_class_metrics=favorable,
            memory_numerical_controls_outperformed=memory_wins,
            common_receiver_classes=int(row['common_class_count']),source_semantic_classes=source_classes[rd],
            all_class_v2_utility=effects['all']['V2'],common_class_v2_utility=effects['common']['V2']))
        if favorable:
            counts['favorable_above_shuffled_and_l2_both_metrics'] += 1
            if memory_wins == 2: counts['also_above_both_memory_controls_both_metrics'] += 1
            eligible.append((memory_wins,int(row['common_class_count']),source_classes[rd],-rd,-cid,
                             (rd,cid,cohort),methods))
    if not eligible:
        raise ValueError('No favorable matched case exists; do not fabricate a replacement.')
    selected = max(eligible,key=lambda r:r[:5])
    return selected[-2],selected[-1],dict(counts),audit


def prepare(root,out):
    csv.field_size_limit(64*1024*1024)
    files = ('used_categories.csv','source_rounds.csv','region_shares.csv','all_rounds.csv',
             'full_counterfactual_raw.csv','receiver_utility_raw.csv')
    hashes = {n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in files}
    data = {n:read(root/n) for n in files}
    groups = defaultdict(dict)
    for r in data['full_counterfactual_raw.csv']:
        key=(int(r['round']),int(r['receiver']),r['cohort'])
        assert r['method'] not in groups[key]; groups[key][r['method']]=r
    active={int(r['round']) for r in data['all_rounds.csv'] if r['active']=='True'}
    classes_by_round={int(r['round']):int(r['classes']) for r in data['source_rounds.csv']}
    key,methods,counts,audit=choose_case(groups,active,classes_by_round)
    rd,cid,cohort=key
    raw=[r for r in data['used_categories.csv'] if int(r['round'])==rd]
    scores=sorted([r for r in data['source_rounds.csv'] if int(r['round'])==rd],key=lambda r:int(r['tier']))
    shares=[r for r in data['region_shares.csv'] if int(r['round'])==rd]
    all_shared=[r for r in shares if r['all_profiles_shared']=='True']
    representative=min(int(r['region']) for r in all_shared)
    chosen_share=sorted([r for r in all_shared if int(r['region'])==representative],key=lambda r:int(r['tier']))
    assert any(abs(float(r['delta_pp']))>0 for r in chosen_share)
    class_set={int(r['category']) for r in raw}
    by_tier=defaultdict(list); category_scores=defaultdict(float)
    for row in raw:
        g=int(row['tier']);c=int(row['category']);d=float(row['d']);a=float(row['a']);rho=float(row['rho'])
        assert int(row['reference_round'])<rd
        assert math.isclose(d,max(0,float(row['q_post'])-float(row['q_pre'])),abs_tol=1e-13)
        assert math.isclose(a,max(0,float(row['q_post'])-float(row['reference_q'])),abs_tol=1e-13)
        assert math.isclose(float(row['u']),rho*min(d,a),abs_tol=1e-14)
        by_tier[g].append(row);category_scores[c]+=float(row['u'])
    shown=sorted(sorted(category_scores,key=lambda c:(-category_scores[c],c))[:8])
    for score in scores:
        values=by_tier[int(score['tier'])]
        assert len(values)==int(score['classes'])
        assert math.isclose(statistics.mean(float(v['u']) for v in values),float(score['U']),abs_tol=1e-14)
    source_ids={c for r in data['receiver_utility_raw.csv'] if int(r['round'])==rd for c in json.loads(r['source_clients'])}
    assert cid not in source_ids
    for field in ('before_ce','probe_examples','receiver_profile','receiver_tier'):
        assert len({methods[m][field] for m in METHODS})==1
    assert int(methods['V2']['receiver_profile'])==6
    supports=[]
    for m in METHODS:
        values=json.loads(methods[m]['per_class']);supports.append([(v['category'],v['count'],v['before_ce']) for v in values])
        common=[v for v in values if v['category'] in class_set]
        assert len(common)==int(methods[m]['common_class_count'])
        assert math.isclose(statistics.mean(v['utility'] for v in common),float(methods[m]['common_utility']),abs_tol=1e-12)
    assert all(v==supports[0] for v in supports)
    paired=[];context=[]
    for m in METHODS:
        for metric in ('all','common'):
            paired.append(dict(round=rd,receiver=cid,method=m,metric=metric,
                utility_vs_a07=utility(methods,m,metric),probe_examples=methods[m]['probe_examples'],
                common_class_count=methods[m]['common_class_count']))
    for (r,c,part),ms in sorted(groups.items()):
        for m in METHODS:
            context.append(dict(round=r,receiver=c,cohort=part,method=m,
                utility_vs_a07=float(ms[m]['utility_vs_a07']),semantic_valid=ms[m]['semantic_valid']))
    metadata=dict(round=rd,receiver=cid,receiver_tier=int(methods['V2']['receiver_tier']),cohort=cohort,
        probe_examples=int(methods['V2']['probe_examples']),common_receiver_classes=int(methods['V2']['common_class_count']),
        total_receiver_classes=len(supports[0]),source_tiers=sorted(by_tier),absent_tiers=sorted(set(range(3))-set(by_tier)),
        source_clients=sorted(source_ids),representative_shared_region=representative,
        all_adjusted_feature_regions=sorted({int(r['region']) for r in shares}),
        total_valid_semantic_classes=len(class_set),displayed_classes=shown,
        displayed_class_rule='Top8 categories by sum of actually used class evidence u across active tiers, ties by class ID; displayed in class-ID order. No CE selection of categories.',
        displayed_evidence_fraction=sum(category_scores[c] for c in shown)/sum(category_scores.values()),
        case_rule='Retrospective outcome selection across BOTH original cohorts. Require valid, actual nonzero fusion, >=2 shared receiver classes, positive CE gain exceeding shuffled and L2 in BOTH metrics. Rank by number of memory numerical-term controls outperformed in BOTH metrics, then shared receiver class count, total source class support, earliest round and lowest receiver ID; never rank by maximum CE gain.',
        selection_is_outcome_conditioned=True,candidate_counts=counts,
        source_file_sha256=hashes,background_cases=len(groups),background_rounds=len({k[0] for k in groups}),
        linkage='Panel c illustrates R0; panel d evaluates the full modified-region union. No R0-specific causal utility attribution.',
        memory_control_semantics='Original valid class/history mask held fixed; no_sm = mean(rho*d), no_rm = mean(min(d,a)); not retrained memory-free methods.',
        probe_scope='SGD training-side, disjoint from scoring samples; not an independent validation set.',
        figure_scope='Selected beneficial mechanistic example, not an unbiased1000-round mean or proof of overall efficacy.')
    out.mkdir(parents=True,exist_ok=False)
    for name,rows in [('selected_case_raw',[methods[m] for m in METHODS]),('selected_case_semantic_evidence',raw),
        ('selected_case_source_scores',scores),('selected_case_share_shift',shares),('selected_case_utility',paired),
        ('all_diagnostic_utility_context',context),('candidate_selection_audit',audit)]:write(out/f'{name}.csv',rows)
    write(out/'displayed_classes.csv',[dict(category=c,aggregate_u=category_scores[c],displayed=c in shown)
        for c in sorted(class_set)])
    bundle=dict(metadata=metadata,scores=scores,categories=raw,representative_shares=chosen_share,
                all_shares=shares,paired=paired,context=context)
    (out/'plot_data.json').write_text(json.dumps(bundle,indent=2),encoding='utf-8')
    assert all(hashlib.sha256((root/n).read_bytes()).hexdigest()==v for n,v in hashes.items())
    return bundle


COLORS = ['#0072B2', '#A96300', '#006B55']
NAMES = ['Low','Middle','High']
HATCHES = ['', '///', '...']


def panel_data(bundle):
    """Auditable values, including the absent-vs-zero distinction."""
    import numpy as np
    scores=defaultdict(float)
    for r in bundle['categories']:scores[int(r['category'])]+=float(r['u'])
    shown=sorted(sorted(scores,key=lambda c:(-scores[c],c))[:6])
    aa=[];bb=[];cc=[];dd=[];hist=[]
    for g in range(3):
        byclass={int(r['category']):r for r in bundle['categories'] if int(r['tier'])==g}
        for category in shown:
            r=byclass.get(category)
            aa.append(dict(tier=g,category=category,missing=r is None,
                signed_task_margin=None if r is None else float(r['q_post'])-float(r['reference_q']),
                q_post=None if r is None else float(r['q_post']),past_reference=None if r is None else float(r['reference_q'])))
    for score in bundle['scores']:
        g=int(score['tier']);rows=[r for r in bundle['categories'] if int(r['tier'])==g]
        rho=[float(r['rho']) for r in rows]
        ages=[json.loads(r[k])['age'] for r in rows for k in ('own_reliability','reference_reliability')]
        support=[int(r['support']) for r in rows]
        expected=[statistics.mean(float(r['d']) for r in rows),statistics.mean(min(float(r['d']),float(r['a'])) for r in rows),
                  statistics.mean(float(r['rho'])*min(float(r['d']),float(r['a'])) for r in rows)]
        actual=[float(score[k]) for k in ('d','memory_limited','U')]
        assert all(math.isclose(a,b,abs_tol=1e-14) for a,b in zip(expected,actual))
        for stage,value in zip(('d','m','U'),actual):
            bb.append(dict(tier=g,stage=stage,value=value,mean_rho=statistics.mean(rho),
                support_min=min(support),support_max=max(support),age_min=min(ages),age_max=max(ages),classes=len(rows)))
    for r in bundle['representative_shares']:
        old,new=float(r['pi_before']),float(r['pi_after']);shift=100*(new-old)
        assert math.isclose(shift,float(r['delta_pp']),abs_tol=1e-12)
        cc.append(dict(tier=int(r['tier']),region=int(r['region']),a07_percent=old*100,v2_percent=new*100,delta_pp=shift))
    for r in bundle['paired']:dd.append(dict(r))
    for method in METHODS:
        vals=[r['utility_vs_a07'] for r in bundle['context'] if r['method']==method]
        q=np.quantile(vals,[0,.25,.5,.75,1])
        hist.append(dict(method=method,n=len(vals),minimum=q[0],q25=q[1],median=q[2],q75=q[3],maximum=q[4]))
    return aa,bb,cc,dd,hist


def draw_tmc(bundle,out,font_path):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager,colors,ticker
    from matplotlib.text import Text
    from matplotlib.patches import Rectangle
    from matplotlib.lines import Line2D
    import numpy as np
    aa,bb,cc,dd,hist=panel_data(bundle);meta=bundle['metadata']
    font_manager.fontManager.addfont(str(font_path))
    style={'font.family':'Times New Roman','font.weight':'bold','font.size':9,
        'axes.titleweight':'bold','axes.labelweight':'bold','axes.titlesize':10,'axes.labelsize':9,
        'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':8,
        'pdf.fonttype':42,'ps.fonttype':42,'savefig.bbox':None,'axes.linewidth':.7,
        'axes.spines.top':False,'axes.spines.right':False,'figure.facecolor':'white','hatch.linewidth':.45}
    with plt.rc_context(style):
        fig=plt.figure(figsize=(7.16,7.9),dpi=100)
        # No large in-figure title; panel labels alone anchor the hierarchy.
        fig.text(.085,.968,'(a) Class-wise semantic evidence',fontsize=10)
        fig.text(.620,.968,'(b) Dual-Memory decomposition',fontsize=10)
        fig.text(.085,.547,'(c) Source contribution reallocation',fontsize=10)
        fig.text(.620,.547,'(d) Paired receiver utility',fontsize=10)
        a=fig.add_axes([.085,.718,.365,.222])
        classes=sorted({r['category'] for r in aa});vmax=max(abs(r['signed_task_margin'])*1000 for r in aa if not r['missing'])
        norm=colors.SymLogNorm(linthresh=1,linscale=.7,vmin=-vmax,vmax=vmax,base=10)
        cmap=plt.get_cmap('PuOr_r').copy()
        text_checks=[]
        for r in aa:
            j=classes.index(r['category']);g=r['tier'];v=None if r['missing'] else r['signed_task_margin']*1000
            fc='#E7E7E7' if v is None else cmap(norm(v))
            a.add_patch(Rectangle((j-.5,g-.5),1,1,fc=fc,ec='white',lw=.8))
            if v is not None:
                # Exact values remain in CSV; on-figure labels round only for readability.
                lum=.2126*fc[0]+.7152*fc[1]+.0722*fc[2]
                txt=a.text(j,g,f'{v:+.1f}',ha='center',va='center',fontsize=8,color='white' if lum<.45 else 'black')
                text_checks.append(dict(panel='a',text=txt.get_text(),value=v,format='+.1f'))
        for g in meta['absent_tiers']:
            a.text((len(classes)-1)/2,g,'No upload source: missing',ha='center',va='center',fontsize=8,color='#555555')
        a.set(xlim=(-.5,len(classes)-.5),ylim=(2.5,-.5),xticks=range(len(classes)),xticklabels=classes,
            yticks=range(3),yticklabels=NAMES,xlabel=f'Class ID: top6 of {meta["total_valid_semantic_classes"]} valid classes')
        for g,t in enumerate(a.get_yticklabels()):t.set_color(COLORS[g])
        a.spines['left'].set_visible(False);a.spines['bottom'].set_visible(False)
        cbax=fig.add_axes([.085,.653,.365,.015])
        cb=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=cbax,orientation='horizontal',ticks=[-100,-10,-1,0,1,10,100])
        cb.ax.set_xticklabels(['-100','-10','-1','0','1','10','100'])
        if cb.solids is not None:cb.solids.set_rasterized(False)
        cb.set_label('Task margin (x 1e-3); symmetric-log color\nLinear color interval: [-1,+1]',fontsize=8,labelpad=4)
        b=fig.add_axes([.650,.661,.315,.276])
        positions={1:[5,4,3],2:[1,0,-1]}
        b.set(ylim=(-1.7,6.8),xlim=(0,max(r['value']*1000 for r in bb)*1.28),
            yticks=[5,4,3,1,0,-1],yticklabels=['d','m','U','d','m','U'],xlabel='Evidence (x 1e-3)')
        for r in bb:
            g=r['tier'];stage=('d','m','U').index(r['stage']);y=positions[g][stage];v=r['value']*1000
            b.barh(y,v,height=.55,color=COLORS[g],hatch=HATCHES[g],edgecolor='white',linewidth=.45)
            b.text(v+.18,y,f'{v:.3f}',va='center',fontsize=8,color=COLORS[g])
            text_checks.append(dict(panel='b',text=f'{v:.3f}',value=v,format='.3f'))
        for g,y in [(1,6),(2,2)]:
            r=next(r for r in bb if r['tier']==g)
            b.text(.01,y,NAMES[g]+f': mean rho={r["mean_rho"]:.3f}; n={r["support_min"]}-{r["support_max"]}',
                transform=b.get_yaxis_transform(),fontsize=8,color=COLORS[g],va='center')
        b.tick_params(axis='y',length=0)
        b.set_xticks([0,4,8,12])
        fig.text(.650,.610,'m = mean min(d,a)\nU = mean[rho(c) min(d(c),a(c))]',fontsize=8,va='top')
        ages=[r['age_max'] for r in bb]
        fig.text(.650,.568,f'Past-only reference age: 1-{max(ages)} rounds',fontsize=8)
        cu=fig.add_axes([.140,.409,.310,.100])
        fig.text(.140,.526,f'R{meta["representative_shared_region"]}: all seven profiles shared',fontsize=8)
        left=np.zeros(2)
        for r in cc:
            g=r['tier'];vals=np.array([r['a07_percent'],r['v2_percent']])
            cu.barh([1,0],vals,left=left,height=.55,color=COLORS[g],hatch=HATCHES[g],ec='white',lw=.5)
            for j,v in enumerate(vals):
                cu.text(left[j]+v/2,1-j,f'{v:.5f}%',ha='center',va='center',fontsize=8,color='white',
                    bbox=dict(facecolor=COLORS[g],edgecolor='none',pad=.35))
                text_checks.append(dict(panel='c_absolute',text=f'{v:.5f}%',value=v,format='.5f'))
            left+=vals
        cu.set(xlim=(0,100),ylim=(-.65,1.65),yticks=[1,0],yticklabels=['A07','V2'],xticks=[0,50,100],xlabel='Absolute contribution (%)')
        cu.tick_params(axis='y',length=0)
        cl=fig.add_axes([.140,.202,.310,.100])
        fig.text(.140,.329,'Same region: actual source-share change',fontsize=8)
        limit=max(abs(r['delta_pp']) for r in cc)*1.5
        for j,r in enumerate(cc):
            v=r['delta_pp'];g=r['tier']
            cl.barh(j,v,height=.55,color=COLORS[g],hatch=HATCHES[g],ec='white',lw=.5)
            cl.text(v/2,j,f'{v:+.6f}',ha='center',va='center',fontsize=8,color='white',
                bbox=dict(facecolor=COLORS[g],edgecolor='none',pad=.25))
            text_checks.append(dict(panel='c_delta',text=f'{v:+.6f}',value=v,format='+.6f'))
        cl.axvline(0,c='#555555',lw=.7)
        cl.set(xlim=(-limit,limit),ylim=(-.65,len(cc)-.35),yticks=range(len(cc)),yticklabels=[NAMES[r['tier']] for r in cc],
               xlabel='Contribution change (pp)')
        cl.invert_yaxis();cl.xaxis.set_major_locator(ticker.FixedLocator([-.004,-.002,0,.002,.004]))
        cl.xaxis.set_major_formatter(ticker.FormatStrFormatter('%.3f'));cl.tick_params(axis='y',length=0)
        for label,r in zip(cl.get_yticklabels(),cc):label.set_color(COLORS[r['tier']])
        fig.text(.085,.122,'R0 shows shares; utility uses the complete\nmodified region union R0-R6.',fontsize=8,va='top')
        fig.text(.085,.063,f'Selected beneficial case: round {meta["round"]},\nFull receiver {meta["receiver"]}; not the trajectory mean.',fontsize=8,va='top')
        du=fig.add_axes([.650,.302,.315,.194])
        names=['A07','V2','Without SM*','Without RM*','Shuffled','L2-matched']
        receiver_color=COLORS[meta['receiver_tier']]
        for i,method in enumerate(METHODS):
            for metric,offset,marker,filled in [('all',-.21,'D',True),('common',.21,'s',False)]:
                row=next(r for r in dd if r['method']==method and r['metric']==metric);v=row['utility_vs_a07']*1e6
                y=i+offset
                du.scatter([v],[y],s=24,marker=marker,facecolors=receiver_color if filled else 'white',
                    edgecolors=receiver_color,lw=1,zorder=3)
                if method!='A07':du.annotate(f'{v:+.3f}',(v,y),xytext=(5,0),textcoords='offset points',va='center',fontsize=8)
                text_checks.append(dict(panel='d',text=f'{v:+.3f}',value=v,format='+.3f'))
        du.axvline(0,color='#555555',lw=.7)
        du.set(yticks=range(6),yticklabels=names,ylim=(5.65,-.65),xlim=(-3.4,3.05),
               xticks=[-3,-2,-1,0,1,2,3],xlabel='Paired CE improvement (x 1e-6)')
        du.tick_params(axis='y',length=0)
        handles=[Line2D([],[],ls='',marker='D',mfc=receiver_color,mec=receiver_color,label='All classes'),
                 Line2D([],[],ls='',marker='s',mfc='white',mec=receiver_color,label='Shared classes')]
        fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.630,.535),ncol=2,frameon=False,
            fontsize=8,columnspacing=.8,handletextpad=.3,handlelength=1)
        dl=fig.add_axes([.650,.110,.315,.111])
        for i,r in enumerate(hist):
            dl.bxp([dict(med=1e6*r['median'],q1=1e6*r['q25'],q3=1e6*r['q75'],
                whislo=1e6*r['minimum'],whishi=1e6*r['maximum'],fliers=[])],positions=[i],
                orientation='horizontal',widths=.5,showfliers=False,patch_artist=True,
                boxprops=dict(fc='#D7DADF',ec='#777777',lw=.6),medianprops=dict(c='#555555',lw=.7),
                whiskerprops=dict(c='#999999',lw=.6),capprops=dict(c='#999999',lw=.6),manage_ticks=False)
            point=next(v for v in dd if v['method']==r['method'] and v['metric']=='all')['utility_vs_a07']*1e6
            dl.scatter([point],[i],s=14,c=receiver_color,marker='D',zorder=3)
        dl.set_xscale('symlog',linthresh=1,linscale=1,base=10)
        dl.axvline(0,c='#555555',lw=.6)
        dl.set(yticks=range(6),yticklabels=['A07','V2','SM*','RM*','Shuf.','L2'],ylim=(5.6,-.6),
               xlabel='Context CE (x 1e-6; symlog)')
        dl.set_xticks([-1000,-1,0,1,1000]);dl.set_xticklabels(['-1000','-1','0','1','1000'])
        dl.tick_params(axis='y',length=0)
        fig.text(.650,.243,'All318 cases: median / IQR / full range',fontsize=8)
        fig.text(.620,.055,'*Memory numerical-term controls; fixed masks.\nPositive CE difference means lower receiver loss.',fontsize=8,va='top')
        # Enforce the actual font face, not just a requested rc family name.
        for t in fig.findobj(Text):
            size=t.get_fontsize();assert size in (8,9,10),(t.get_text(),size)
            fp=font_manager.FontProperties(fname=str(font_path),size=size,weight='bold')
            t.set_fontproperties(fp)
        fig.canvas.draw()
        # Save actual artist extents for an automated text-only overlap/cropping audit.
        renderer=fig.canvas.get_renderer();texts=[]
        for t in fig.findobj(Text):
            if not t.get_visible() or not t.get_text().strip():continue
            extent=t.get_window_extent(renderer);texts.append(dict(text=t.get_text(),size=t.get_fontsize(),
                bbox_points=[v*72/fig.dpi for v in extent.extents]))
        (out/'text_extents.json').write_text(json.dumps(dict(width_points=7.16*72,height_points=7.9*72,texts=texts),indent=2),encoding='utf-8')
        for ext in ('pdf','png'):fig.savefig(out/f'figure_mechanism_case.{ext}',dpi=450,facecolor='white')
        plt.close(fig)
    (out/'printed_values.json').write_text(json.dumps(text_checks,indent=2),encoding='utf-8')
    for name,rows in [('panel_a_semantic',aa),('panel_b_memory',bb),('panel_c_shares',cc),('panel_d_utility',dd),('panel_d_background_statistics',hist)]:write(out/f'{name}.csv',rows)
    return dict(shown_classes=classes,heatmap='SymLogNorm; linear +/-0.001 probability; no clipped values',
        font_path=str(font_path),font_sizes=[8,9,10],palette=COLORS,width_inches=7.16,height_inches=7.9)


def main():
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--root',type=Path,default=ROOT/'docs/evidence/semantic_a07_v2/activation1000/results')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--font',type=Path,default=Path('C:/Windows/Fonts/timesbd.ttf'))
    p.add_argument('--redraw',action='store_true')
    args=p.parse_args();assert args.font.is_file(),'Supply an actual Times New Roman Bold TTF using --font'
    bundle=json.loads((args.output/'plot_data.json').read_text()) if args.redraw else prepare(args.root,args.output)
    style=draw_tmc(bundle,args.output,args.font)
    (args.output/'style_manifest.json').write_text(json.dumps(style,indent=2),encoding='utf-8')
    print(json.dumps(dict(case=bundle['metadata']['round'],receiver=bundle['metadata']['receiver'],style=style),indent=2))


if __name__=='__main__':main()


