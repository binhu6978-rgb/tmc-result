"""One outcome-selected, fully matched whole-aggregation case; no training or invented data."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics

METHODS = ('A07', 'V2', 'no_sm', 'no_rm', 'permuted', 'A07_L2_matched')


def read(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def write(path, records):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader(); writer.writerows(records)


def utility(group, method, metric):
    if metric == 'all':
        return float(group[method]['utility_vs_a07'])
    return float(group[method]['common_utility']) - float(group['A07']['common_utility'])


def select(raw, timeline):
    grouped = defaultdict(lambda: defaultdict(dict))
    for row in raw:
        if row['cohort'] != 'confirmation':
            continue
        bucket = grouped[int(row['round'])][int(row['receiver'])]
        assert row['method'] not in bucket
        bucket[row['method']] = row
    active = {int(r['round']) for r in timeline if r['active'] == 'True'}
    candidates = []; audit = []; counts = Counter(diagnostic_rounds=len(grouped))
    for rd, receivers in sorted(grouped.items()):
        if rd not in active:
            continue
        counts['actually_adjusted_rounds'] += 1
        if len(receivers) != 3 or not all(set(METHODS) <= g.keys() for g in receivers.values()):
            continue
        counts['complete_three_confirmation_receivers'] += 1
        for g in receivers.values():
            assert {int(g[m]['receiver_profile']) for m in METHODS} == {6}
            for key in ('before_ce', 'probe_examples', 'receiver_tier', 'per_class'):
                if key != 'per_class':
                    assert len({g[m][key] for m in METHODS}) == 1
            # Every variant evaluates exactly the same class support.
            supports = [[(v['category'], v['count'], v['before_ce']) for v in json.loads(g[m]['per_class'])] for m in METHODS]
            assert all(x == supports[0] for x in supports)
        means = {m:statistics.mean(utility(g, m, 'all') for g in receivers.values()) for m in METHODS}
        positive = sum(utility(g, 'V2', 'all') > 0 for g in receivers.values())
        positive_controlled = means['V2'] > max(0, means['permuted'], means['A07_L2_matched']) and positive >= 2
        common = all(int(g['V2']['common_class_count']) > 0 for g in receivers.values())
        positive_everywhere = common and all(utility(g, 'V2', metric) > 0
            and utility(g, 'V2', metric) > utility(g, control, metric)
            for g in receivers.values() for metric in ('all', 'common')
            for control in ('permuted', 'A07_L2_matched'))
        if positive_controlled: counts['positive_mean_above_both_controls_at_least_two_positive_receivers'] += 1
        if positive_controlled and common: counts['also_common_classes_for_every_receiver'] += 1
        if positive_everywhere: counts['strict_beneficial_rounds_both_metrics_all_receivers'] += 1
        breadth = min(int(g['V2']['common_class_count']) for g in receivers.values())
        row = dict(round=rd, positive_receiver_count=positive, positive_controlled_mean=positive_controlled,
            common_classes_every_receiver=common, strict_beneficial=positive_everywhere,
            minimum_receiver_common_class_count=breadth,
            mean_v2_all_utility=means['V2'], mean_v2_minus_shuffled=means['V2']-means['permuted'],
            mean_v2_minus_l2=means['V2']-means['A07_L2_matched'])
        audit.append(row)
        if positive_everywhere:
            candidates.append((breadth, rd, receivers))
    if not candidates:
        raise ValueError('No strictly matched beneficial case. See original records; no data are fabricated.')
    # Prefer class-support breadth, not the largest observed gain. Outcome conditioning remains explicit.
    breadth, rd, receivers = max(candidates, key=lambda x:(x[0], -x[1]))
    return rd, receivers, dict(counts), audit


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--root', type=Path, default=Path('docs/evidence/semantic_a07_v2/activation1000/results'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); csv.field_size_limit(64*1024*1024)
    names = ('full_counterfactual_raw.csv', 'all_rounds.csv', 'source_rounds.csv', 'used_categories.csv',
             'region_shares.csv', 'receiver_utility_raw.csv')
    hashes = {n:hashlib.sha256((args.root/n).read_bytes()).hexdigest() for n in names}
    data = {n:read(args.root/n) for n in names}
    rd, receivers, counts, selection = select(data['full_counterfactual_raw.csv'], data['all_rounds.csv'])
    scores = sorted([r for r in data['source_rounds.csv'] if int(r['round']) == rd], key=lambda r:int(r['tier']))
    categories = [r for r in data['used_categories.csv'] if int(r['round']) == rd]
    regions = [r for r in data['region_shares.csv'] if int(r['round']) == rd]
    tiers = sorted(int(r['tier']) for r in scores)
    class_set = {int(r['category']) for r in categories}
    source_ids = {c for r in data['receiver_utility_raw.csv'] if int(r['round']) == rd for c in json.loads(r['source_clients'])}
    assert not set(receivers) & source_ids
    for g in receivers.values():
        for m in METHODS:
            pc = json.loads(g[m]['per_class']); selected = [x for x in pc if x['category'] in class_set]
            assert len(selected) == int(g[m]['common_class_count'])
            assert math.isclose(statistics.mean(x['utility'] for x in selected), float(g[m]['common_utility']), abs_tol=1e-12)
    for score in scores:
        values = [r for r in categories if int(r['tier']) == int(score['tier'])]
        for v in values:
            assert int(v['reference_round']) < rd
            assert math.isclose(float(v['u']), float(v['rho'])*min(float(v['d']),float(v['a'])), abs_tol=1e-14)
        assert math.isclose(statistics.mean(float(v['u']) for v in values),float(score['U']),abs_tol=1e-14)
    by_region = defaultdict(list)
    for r in regions:by_region[int(r['region'])].append(r)
    union_numel = sum(int(v[0]['feature_numel']) for v in by_region.values())
    shares = []
    for tier in tiers:
        item = dict(tier=tier, feature_union_numel=union_numel, regions=json.dumps(sorted(by_region)))
        for side in ('before','after'):
            item['pi_'+side] = sum(int(values[0]['feature_numel'])*sum(float(v['pi_'+side]) for v in values if int(v['tier'])==tier)
                for values in by_region.values()) / union_numel
        item['delta_pp'] = 100*(item['pi_after']-item['pi_before']); shares.append(item)
    for side in ('before','after'):assert math.isclose(sum(s['pi_'+side] for s in shares),1,abs_tol=1e-12)
    paired = []
    for cid, group in sorted(receivers.items()):
        for m in METHODS:
            for metric in ('all','common'):
                paired.append(dict(round=rd,receiver=cid,receiver_tier=int(group[m]['receiver_tier']),method=m,
                    metric=metric,utility_vs_a07=utility(group,m,metric),probe_examples=group[m]['probe_examples'],
                    common_class_count=group[m]['common_class_count']))
    output = args.output; output.mkdir(exist_ok=False,parents=True)
    for name, values in [('candidate_selection_audit',selection),('semantic_evidence_raw',categories),
                         ('source_scores_raw',scores),('all_adjusted_regions_raw',regions),
                         ('full_counterfactual_case_raw',[g[m] for _,g in sorted(receivers.items()) for m in METHODS]),
                         ('feature_union_shares',shares),('paired_utilities',paired)]:write(output/f'{name}.csv',values)
    metadata = dict(round=rd,receiver_ids=sorted(receivers),source_tiers=tiers,source_clients=sorted(source_ids),
        adjusted_feature_regions=sorted(by_region),feature_union_numel=union_numel,semantic_classes=sorted(class_set),
        candidate_counts=counts,source_sha256=hashes,selection_uses_positive_outcomes=True,
        selection_rule='Require actual activation, all three original confirmation Full receivers, common semantic classes for each, and positive V2 utility beating shuffled and L2 controls for EVERY receiver in BOTH class metrics. Choose maximal minimum common-class support; tie: earliest round.',
        matching_scope='All adjusted non-BN feature-region union; whole-Full same-upload aggregate counterfactual. No single-region causal attribution.',
        generalization='Selected beneficial case; not the average1000-round effect or independent confirmation.',
        probe_scope='Original SGD training-side; disjoint from semantic scoring samples, not an SGD holdout.',
        adapter_in_decision=False)
    (output/'selection_metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    draw(output,rd,scores,shares,paired)
    means = {metric:{m:statistics.mean(r['utility_vs_a07'] for r in paired if r['metric']==metric and r['method']==m) for m in METHODS} for metric in ('all','common')}
    (output/'summary.json').write_text(json.dumps(dict(metadata=metadata,equal_receiver_mean_utilities=means),indent=2),encoding='utf-8')
    caption = f'''**Selected Beneficial Case Study (round {rd}).** (a) Task gain D, historical-advantage-limited M, and reliability-calibrated U over {len(class_set)} shared semantic classes. (b) Feature-coordinate-weighted source shares across all modified regions R0-R7. (c) Paired CE improvement versus same-input A07; dots show three fixed Full receivers and diamonds their equal-weight mean. Blue/green denote all probe/shared semantic classes. Positive values indicate lower CE. Numerical-term controls retain the original validity mask. This outcome-selected example satisfies positive V2 response above shuffled and L2 controls for every receiver in both metrics; it does not estimate the 1,000-round average. Probes are training-side, disjoint from scoring samples.'''
    (output/'CAPTION.md').write_text(caption,encoding='utf-8')
    report = f'''# Selected Beneficial Case Study

选中第{rd}轮，来源能力层{tiers}（Middle、High），接收者{sorted(receivers)}（低、中、高能力层各一人，均使用Full网络）。实际语义共同类别数{len(class_set)}。覆盖范围为实际全部调整特征区域{sorted(by_region)}，合计{union_numel}个非BN/非classifier坐标。Full-only和未覆盖区域不被语义修改。

筛选漏斗：{json.dumps(counts,ensure_ascii=False)}。严格正向子集中，选择三个接收者中最小共同类别支持数最大的轮次，平局取最早轮次，未选最大CE收益。案例依赖正向结果筛选；代表的是这一条件下的完整真实计算链，不能代表1000轮总体平均。

三个面板严格使用同一轮、同一组来源和全部被修改区域。面板(b)是完整特征修改并集的坐标加权份额摘要，不是另一个实际权重公式。面板(c)是这次完整同输入聚合的Full模型效用；没有把某一个区域的注入效用冒充完整V2效用。接收者与本轮来源物理身份不重合。共同类别CE和全部类别CE分开保留，所有六个原始控制完整展示。

全部probe类别的等接收者平均CE收益：{json.dumps(means['all'])}。
共同语义类别口径：{json.dumps(means['common'])}。

该案例中V2对三个接收者均优于A07、置换语义与L2尺度控制，支持这一具体实例存在与真实语义对应关系一致的有利来源调整。去SM和去RM控制的收益高于完整V2，因此本例不能证明双Memory提高效用；它只显示两个Memory确实参与评分并保守压缩证据。亦不能将来源级分数归因为逐参数语义价值。Adapter为辅助观测。

数值项控制保留原有效类别/历史资格mask：No M limit使用mean(rho*d)，No rho factor使用mean(min(d,a))，不是两条重新训练的无Memory算法。confirmation仅沿用原日志队列名；本次记录已参与案例筛选，不能再当独立确认数据。

所有原始CSV、旧Figure7/8和以前的负面结果保留；没有新增训练、改变算法、修改原始数值或生成虚假数据。图中三位接收者不等于三个独立FL实验，散点不被用作总体置信区间。完整筛选规则、每轮候选检查及原文件SHA保存在同目录。
'''
    (output/'CASE_REPORT.md').write_text(report,encoding='utf-8')
    for name, sha in hashes.items():assert hashlib.sha256((args.root/name).read_bytes()).hexdigest()==sha
    print(json.dumps(dict(round=rd,counts=counts,means=means,regions=sorted(by_region)),indent=2))


def draw(output,rd,scores,shares,paired):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.family':'DejaVu Serif','font.size':7,'axes.titlesize':8,
        'pdf.fonttype':42,'savefig.dpi':350,'axes.spines.top':False,'axes.spines.right':False})
    fig,axs=plt.subplots(1,3,figsize=(7.2,3.35),gridspec_kw={'width_ratios':[1,1.05,1.55]})
    fig.subplots_adjust(left=.065,right=.985,bottom=.28,top=.78,wspace=.58)
    labels=['Low','Middle','High'];tier_colors=['#3D78A6','#D69A35','#218772']
    x=np.arange(len(scores))
    for j,(key,label,color) in enumerate([('d','D: task gain','#BBC8D2'),('memory_limited','M: history limit','#6C9CB4'),('U','U: calibrated','#258772')]):
        vals=[float(r[key]) for r in scores];positions=x+(j-1)*.23
        axs[0].bar(positions,vals,width=.21,label=label,color=color)
        for pos,v in zip(positions,vals):axs[0].text(pos,v+.012,f'{v:.3f}',ha='center',fontsize=5.7)
    axs[0].set(xticks=x,xticklabels=[labels[int(r['tier'])] for r in scores],ylim=(0,.91),
        ylabel='Mean probability-scale evidence',title='(a) Evidence and dual Memory')
    axs[0].legend(frameon=False,fontsize=5.8,loc='upper right')
    left=np.zeros(2)
    for row in shares:
        g=row['tier'];values=np.array([100*row['pi_before'],100*row['pi_after']])
        axs[1].barh([1,0],values,left=left,height=.45,color=tier_colors[g],label=labels[g])
        for i,v in enumerate(values):axs[1].text(left[i]+v/2,1-i,f'{v:.4f}%',ha='center',va='center',color='white',fontsize=6.3)
        left+=values
    axs[1].set(yticks=[1,0],yticklabels=['A07','V2'],xlim=(0,100),ylim=(-.7,1.8),
        xlabel='Feature-coordinate-weighted\nsource contribution (%)',title='(b) All adjusted feature regions')
    axs[1].legend(frameon=False,fontsize=6,loc='upper center',ncol=2)
    changes='; '.join(f'{labels[r["tier"]]} {r["delta_pp"]:+.4f} pp' for r in shares)
    axs[1].text(.5,.48,changes,transform=axs[1].transAxes,ha='center',fontsize=5.8)
    method_labels=['A07','V2','No M limit','No rho factor','Shuffled','L2-only']
    all_values=[]
    for metric,offset,color,marker,label in [('all',-.15,'#3D78A6','o','All probe classes'),('common',.15,'#218772','s','Shared semantic classes')]:
        for i,m in enumerate(METHODS):
            values=[r for r in paired if r['method']==m and r['metric']==metric]
            ys=[i+offset+(v['receiver_tier']-1)*.05 for v in values]
            vs=[1e4*v['utility_vs_a07'] for v in values];mean=statistics.mean(vs);all_values+=vs
            axs[2].hlines(i+offset,0,mean,color=color,lw=2.5,alpha=.32)
            axs[2].scatter(vs,ys,c=color,s=10,marker=marker,alpha=.75,linewidths=0)
            axs[2].scatter([mean],[i+offset],c=color,s=23,marker='D',edgecolors='white',linewidths=.4)
        axs[2].scatter([],[],c=color,s=12,marker=marker,label=label)
    axs[2].axvline(0,color='.4',lw=.65)
    axs[2].set(yticks=range(6),yticklabels=method_labels,xlim=(min(all_values)-.25,max(all_values)+.25),
        xlabel='Paired CE improvement\nvs. A07 (x 1e-4)',title='(c) Fixed Full-receiver utility')
    axs[2].invert_yaxis();axs[2].legend(frameon=False,fontsize=5.8,loc='lower right')
    fig.suptitle('Selected Beneficial Case Study',fontsize=10.5,y=.965)
    source_names=' / '.join(labels[int(r['tier'])] for r in scores)
    receiver_names=' / '.join(map(str,sorted({r['receiver'] for r in paired})))
    region_ids=json.loads(shares[0]['regions'])
    region_text=f'R{region_ids[0]}-R{region_ids[-1]}' if region_ids==list(range(region_ids[0],region_ids[-1]+1)) else ','.join(f'R{r}' for r in region_ids)
    fig.text(.5,.86,f'Round {rd} | Sources: {source_names} | Full receivers: {receiver_names} | Adjusted regions: {region_text}',ha='center',fontsize=6.9)
    fig.text(.5,.095,'Outcome-selected positive example; not the 1,000-round average. Dots: 3 fixed receivers; diamonds: equal-receiver means.',ha='center',fontsize=6.2)
    for ext in ('pdf','png'):fig.savefig(output/f'selected_beneficial_case.{ext}')
    plt.close(fig)


if __name__=='__main__':main()
