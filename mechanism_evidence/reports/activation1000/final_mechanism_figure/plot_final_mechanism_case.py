"""Four-panel, explicitly outcome-selected mechanism case. Original data remain immutable."""
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


def draw(bundle,out):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.colors as colors
    from matplotlib.lines import Line2D
    import numpy as np
    meta=bundle['metadata'];rd=meta['round'];cid=meta['receiver'];tier_names=['Low','Middle','High']
    palette=['#4477AA','#AA6F15','#00796B'];classes=meta['displayed_classes']
    style={'font.family':'Times New Roman','font.size':9,'axes.titlesize':9.5,'axes.labelsize':8.5,
        'xtick.labelsize':8,'ytick.labelsize':8,'legend.fontsize':7.3,'pdf.fonttype':42,'savefig.dpi':450,
        'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.65,'figure.facecolor':'white'}
    with plt.rc_context(style):
        fig=plt.figure(figsize=(7.16,6.35))
        a=fig.add_axes([.083,.610,.365,.280]);b=fig.add_axes([.600,.610,.365,.280])
        c=fig.add_axes([.083,.115,.365,.300]);d=fig.add_axes([.600,.115,.365,.300])
        a.set_title('(a) Class-wise task semantic evidence',loc='left',pad=10)
        matrix=np.full((3,len(classes)),np.nan)
        for row in bundle['categories']:
            if int(row['category']) in classes:
                matrix[int(row['tier']),classes.index(int(row['category']))]=1000*(float(row['q_post'])-float(row['reference_q']))
        vmax=float(np.nanmax(np.abs(matrix)))
        cmap=plt.get_cmap('PuOr_r').copy();cmap.set_bad('#EEEEEE')
        norm=colors.TwoSlopeNorm(vmin=-vmax,vcenter=0,vmax=vmax)
        # Explicit rectangles keep the delivered heatmap fully vector.
        from matplotlib.patches import Rectangle
        for i in range(3):
            for j in range(len(classes)):
                v=matrix[i,j];color='#EEEEEE' if not np.isfinite(v) else cmap(norm(v))
                a.add_patch(Rectangle((j-.5,i-.5),1,1,facecolor=color,edgecolor='white',lw=.6))
                if np.isfinite(v):a.text(j,i,f'{v:+.1f}',ha='center',va='center',fontsize=7,color='white' if abs(v)>.67*vmax else '#111111')
        for g in meta['absent_tiers']:a.text((len(classes)-1)/2,g,'No current upload source (missing)',ha='center',va='center',fontsize=7.5,color='#555555')
        a.set(xlim=(-.5,len(classes)-.5),ylim=(2.5,-.5),xticks=range(len(classes)),xticklabels=classes,
              yticks=range(3),yticklabels=tier_names,xlabel=f'Class ID: top8 of {meta["total_valid_semantic_classes"]} valid classes by total u')
        color_axis=fig.add_axes([.083,.535,.365,.018])
        cb=fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),cax=color_axis,orientation='horizontal')
        if cb.solids is not None:cb.solids.set_rasterized(False)
        cb.set_label('Task margin: q(post) - past other-tier reference (x 1e-3)',fontsize=7.4);cb.ax.tick_params(labelsize=7)
        a.spines['bottom'].set_visible(False);a.spines['left'].set_visible(False)
        b.set_title('(b) Dual-Memory calibration',loc='left',pad=10)
        for row in bundle['scores']:
            g=int(row['tier']);values=[1000*float(row[k]) for k in ('d','memory_limited','U')]
            b.plot(range(3),values,color=palette[g],marker='o' if g==1 else 's',lw=1.6,ms=5,
                label=f'{tier_names[g]} (mean rho={float(row["rho"]):.3f})')
            for x,y in enumerate(values):
                offset=(6,-2) if x==0 and g==1 else (-8,8) if g==1 else (6,8)
                b.annotate(f'{y:.3f}',(x,y),xytext=offset,textcoords='offset points',
                    ha='right' if g==1 and x>0 else 'left',fontsize=7.5,color=palette[g])
        b.set(xticks=range(3),xticklabels=['Task gain\nD','Past-reference limit\nM = mean min(d,a)','Reliability\nU = mean(rho m)'],
            ylabel='Source evidence (x 1e-3)',xlim=(-.35,2.40),ylim=(0,max(1000*float(r['d']) for r in bundle['scores'])*1.30))
        b.axhline(0,color='.4',lw=.5);b.grid(axis='y',color='.92',lw=.5)
        b.legend(frameon=False,loc='upper right',fontsize=7.4)
        fig.text(.7825,.495,'Per-class calibration precedes the macro-average;\nall44 eligible classes retained in this panel.',ha='center',fontsize=7.3)
        c.set_title('(c) Semantic-guided source contributions',loc='left',pad=10)
        c.set(xlim=(-.25,1.25),ylim=(0,100),xticks=[0,1],xticklabels=['A07 base','Semantic-A07'],
            yticks=[0,25,50,75,100],ylabel='Actual region share (%)')
        c.grid(axis='y',color='.92',lw=.5)
        for row in bundle['representative_shares']:
            g=int(row['tier']);v=[100*float(row['pi_before']),100*float(row['pi_after'])]
            c.plot([0,1],v,color=palette[g],lw=1.7,marker='o' if g==1 else 's',ms=5)
            c.text(0,v[0]+4.5,f'{v[0]:.6f}%',color=palette[g],ha='center',fontsize=8)
            c.text(1,v[1]-6.5,f'{v[1]:.6f}%',color=palette[g],ha='center',fontsize=8)
            c.text(.5,81 if g==1 else 17,f'{tier_names[g]}: {float(row["delta_pp"]):+.6f} pp',ha='center',color=palette[g],fontsize=8.3)
        c.text(.5,.97,f'Representative shared region R{meta["representative_shared_region"]}',transform=c.transAxes,ha='center',va='top',fontsize=8)
        fig.text(.2655,.025,'Utility in (d) evaluates all modified regions R0-R6;\nR0 illustrates shares, not isolated causal attribution.',ha='center',fontsize=7.1)
        d.set_title('(d) Realized utility with diagnostic context',loc='left',pad=10)
        random=np.random.default_rng(20261023)
        method_names=['A07','V2 real','No M limit','No rho factor','Shuffled','L2-matched']
        for i,m in enumerate(METHODS):
            background=[1e6*r['utility_vs_a07'] for r in bundle['context'] if r['method']==m]
            d.scatter(background,i+random.uniform(-.19,.19,len(background)),s=6,c='#B7BDC2',alpha=.30,linewidths=0,zorder=1)
            for metric,offset,marker,fill in [('all',-.075,'D',True),('common',.075,'s',False)]:
                row=next(r for r in bundle['paired'] if r['method']==m and r['metric']==metric)
                value=1e6*row['utility_vs_a07']
                d.scatter([value],[i+offset],s=33,marker=marker,edgecolors='#00796B',
                    facecolors='#00796B' if fill else 'white',linewidths=1,zorder=4)
        d.set_xscale('symlog',linthresh=1,linscale=1,base=10)
        d.axvline(0,color='#555555',lw=.7,zorder=2)
        d.set(yticks=range(6),yticklabels=method_names,ylim=(5.55,-2.30),
            xlabel='CE improvement vs. A07 (x 1e-6)\nsymlog: linear between -1 and +1')
        d.grid(axis='x',color='.93',lw=.5)
        handles=[Line2D([],[],marker='o',ls='',color='#B7BDC2',ms=3,label=f'All {meta["background_cases"]} fixed cases (all classes)'),
            Line2D([],[],marker='D',ls='',color='#00796B',ms=4,label=f'Selected receiver {cid}: all probe classes'),
            Line2D([],[],marker='s',ls='',color='#00796B',mfc='white',ms=4,label='Same receiver: shared semantic classes')]
        d.legend(handles=handles,frameon=False,loc='upper right',bbox_to_anchor=(1,1.02),fontsize=6.6,handletextpad=.3)
        title='From Class-wise Semantic Evidence to Capability-Balanced Aggregation'
        fig.suptitle(title+'\n'+f'Selected Beneficial Case Study: round {rd}, Full receiver {cid}',fontsize=10.1)
        for ext in ('png','pdf'):fig.savefig(out/f'figure_mechanism_case.{ext}',facecolor='white',dpi=450)
        plt.close(fig)


def document(bundle,out):
    meta=bundle['metadata'];paired=bundle['paired']
    table=[]
    for m in METHODS:
        vals={r['metric']:r['utility_vs_a07'] for r in paired if r['method']==m}
        table.append(f'| {m} | {vals["all"]:.10g} | {vals["common"]:.10g} |')
    caption=f'''**From class-wise semantic evidence to capability-balanced aggregation: a favorable mechanistic case study.** Selected from the real1,000-round V2 run (round {meta['round']}, Full receiver {meta['receiver']}). (a) Signed task-response margins relative to past other-tier references for the top8 of44 valid classes, ranked by summed class evidence u; Low is absent. (b) Current task gain D, Semantic-Memory-limited M, and Reliability-calibrated U, using all44 classes and per-class calibration before averaging. (c) Exact A07 and V2 shares in representative region R0. (d) Same-input CE improvement relative to A07: highlighted markers show the selected receiver under all-class and shared-class metrics; grey points retain all318 fixed diagnostic receiver-round cases. The signed axis is symlog with linear range +/-1e-6 CE. Numerical-term controls retain the original validity mask. This outcome-selected beneficial example explains mechanism operation, not the average1,000-round effect. Utility evaluates the complete modified region union R0-R6; it is not attributed solely to R0. Probes are training-side and disjoint from scoring samples.'''
    (out/'CAPTION.md').write_text(caption,encoding='utf-8')
    report=f'''# Final IV-E Mechanism Case Figure

## 选中案例

真实第{meta['round']}轮，Full接收者{meta['receiver']}，原日志队列名{meta['cohort']}，{meta['probe_examples']}个固定probe样本、{meta['total_receiver_classes']}个评价类别，其中{meta['common_receiver_classes']}类与语义共同集合相交。当前真实上传来源为Middle/High；Low缺席，图中明确标missing。代表性共享区域R0，实际聚合修改范围为R0-R6。R0的作用仅为份额示例，完整效用不能归因于R0。

## 文件梳理

| 原表 | 对应信息 |
|---|---|
| used_categories.csv | q_pre/q_post、过去其他能力层reference_q/round、support、rho、d/a/u、两套历史有效性细节 |
| source_rounds.csv | 实际共同类宏平均D/M/U和rho |
| region_shares.csv | 每个真实参数覆盖区域的pi_before/pi_after及实际差值 |
| all_rounds.csv | 实际激活、中性原因及数值干预大小 |
| full_counterfactual_raw.csv | 同一Full接收模型的A07、V2、两个Memory数值项控制、置换与L2控制的成对CE |
| receiver_utility_raw.csv | 来源物理身份、真实区域上传支持、方向及区域注入；这里只用于身份核对，不冒充Full反事实收益 |

## 选择规则及数量

{json.dumps(meta['candidate_counts'],ensure_ascii=False,indent=2)}

本轮采用回顾性正向案例筛选：覆盖原53轮、两个原日志cohort共318个receiver-round案例；要求语义真实激活、共同接收类别不少于2类、V2在两种口径下均正向且均胜过置换和L2。优先选择两种Memory数值项控制均被V2超过者，再按共同类别支持量、总语义支持量、最早轮次和最小接收者ID排序。23个候选中2个同时符合双Memory正向比较，第989轮/接收者32比第991轮/接收者42拥有更多共同接收类别（11对9）及语义类别（44对33）。没有按最大CE收益选取。cohort名只是原记录标识，本例被用于筛选后不是独立确认样本。

Panel(a)按每类在真实来源上的u总和选前8类，平局按类别ID，按ID排序显示；共44个合格类的原始证据全量导出。前8类覆盖总u的{100*meta['displayed_evidence_fraction']:.2f}%。Panel(b)使用全部44类，不能用(a)子集代替正式U。历史比较及rho都有过去轮次记录，已验证公式和宏平均与CSV一致。

## 实际效用（CE下降为正，单位CE，不是百分比）

| 方法 | 全部probe类 | 共同语义类 |
|---|---:|---:|
{chr(10).join(table)}

No M limit=mean(rho*d)，No rho factor=mean(min(d,a))，两者保持原有效类/历史mask，是同输入数值项反事实，不是重新训练的无Memory算法。置换保留原有效集合，但不是与V2精确等幅的权重向量；L2控制匹配整体聚合更新L2。不能把这些控制外推为Memory在整条训练轨迹上的效用已获验证。

## 四个面板与可写结论

(a) 类别功能响应相对旧来源参考的优势；(b) 双Memory将当前正向变化校准成实际U；(c) 同轮同上传的R0份额数值重分配；(d) 全部修改区域联合聚合后的真实接收端CE、两个口径和全部固定案例背景。来源、时间和接收模型已匹配，未将不同实验口径强行连接。

可以写：“在这一选出的后期案例中，类别条件任务证据经历史参考与可靠性校准后改变来源份额，并在固定训练侧接收端探针上取得优于相同输入控制的CE改善。”

不能写：“代表1000轮平均收益”“双Memory总体有效”“统计显著泛化提升”“R0单独导致完整收益”“Adapter证明语义收益”。此处效应很小（V2全类CE下降约7.35e-7），属于单个seed、单接收者、训练侧评价的回顾性案例。背景灰点保留全部正负和中性案例，318点不是318个独立FL实验。现有全样本No-Go和旧图完整保留。

## 复现

```bash
python tools/plot_final_mechanism_case.py --output /path/to/new_output
# 已导出数据仅重绘（覆盖本图文件，不修改数据）：
python tools/plot_final_mechanism_case.py --output /path/to/new_output --redraw
```

输出包括矢量PDF、450dpi PNG、完整case原始CSV、类别证据、全部区域份额、每一个背景点、候选审计和plot_data.json。不读取官方测试集、不新增SGD、不改V2、不改原CSV、不覆盖旧图。

## 绘图技能与版式

使用find-skills检索并读取[K-Dense scientific-visualization](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-visualization/SKILL.md)，CLI搜索约2.3K installs，库约54.1K stars（2026-10-23查询）。使用其可追溯变换、原观测叠加、缺失值、矢量输出与渲染核验流程；未安装额外包。

7.16英寸双栏宽度、嵌入字体及矢量PDF参考[IEEE尺寸建议](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/resolution-and-size/)与[字体/格式说明](https://journals.ieeeauthorcenter.ieee.org/create-your-ieee-journal-article/create-graphics-for-your-article/file-formatting/)。正式上传前仍需按当期模板核对。

Software reference: Kassis, T., Agarwal, V., He, Y., Patel, D., and Brueckner, A. M. (2026). *Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents*. https://doi.org/10.48550/arXiv.2609.00065 (metadata checked2026-10-23). 此条记录绘图辅助来源，不是SemConsFL实验证据。
'''
    (out/'README.md').write_text(report,encoding='utf-8')
    (out/'ALT_TEXT.md').write_text('Four-panel selected case. Only Middle and High currently upload. Historical semantic advantage and reliability reduce task gains into U; High has larger U. R0 share moves by about0.002687 percentage points from Middle to High. At receiver32, both all-class and shared-class CE improve relative to A07 and every numerical control. Grey background preserves all318 diagnostic receiver-round cases, including negative and neutral effects. The selected effect is small and does not describe the average trajectory.',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--root',type=Path,default=ROOT/'docs/evidence/semantic_a07_v2/activation1000/results')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--redraw',action='store_true')
    args=parser.parse_args()
    bundle=json.loads((args.output/'plot_data.json').read_text()) if args.redraw else prepare(args.root,args.output)
    draw(bundle,args.output);document(bundle,args.output)
    print(json.dumps(bundle['metadata'],indent=2))


if __name__=='__main__':main()
