# Final IV-E Mechanism Case Figure

## 选中案例

真实第989轮，Full接收者32，原日志队列名development，56个固定probe样本、28个评价类别，其中11类与语义共同集合相交。当前真实上传来源为Middle/High；Low缺席，图中明确标missing。代表性共享区域R0，实际聚合修改范围为R0-R6。R0的作用仅为份额示例，完整效用不能归因于R0。

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

{
  "all_receiver_round_cases": 318,
  "complete_non_neutral_cases": 198,
  "valid_with_at_least_two_common_receiver_classes": 145,
  "favorable_above_shuffled_and_l2_both_metrics": 23,
  "also_above_both_memory_controls_both_metrics": 2
}

本轮采用回顾性正向案例筛选：覆盖原53轮、两个原日志cohort共318个receiver-round案例；要求语义真实激活、共同接收类别不少于2类、V2在两种口径下均正向且均胜过置换和L2。优先选择两种Memory数值项控制均被V2超过者，再按共同类别支持量、总语义支持量、最早轮次和最小接收者ID排序。23个候选中2个同时符合双Memory正向比较，第989轮/接收者32比第991轮/接收者42拥有更多共同接收类别（11对9）及语义类别（44对33）。没有按最大CE收益选取。cohort名只是原记录标识，本例被用于筛选后不是独立确认样本。

Panel(a)按每类在真实来源上的u总和选前8类，平局按类别ID，按ID排序显示；共44个合格类的原始证据全量导出。前8类覆盖总u的70.15%。Panel(b)使用全部44类，不能用(a)子集代替正式U。历史比较及rho都有过去轮次记录，已验证公式和宏平均与CSV一致。

## 实际效用（CE下降为正，单位CE，不是百分比）

| 方法 | 全部probe类 | 共同语义类 |
|---|---:|---:|
| A07 | 0 | 0 |
| V2 | 7.352334381e-07 | 1.381680539e-06 |
| no_sm | -2.653788085e-06 | 1.256610796e-06 |
| no_rm | -1.347611292e-06 | 4.21222384e-07 |
| permuted | 1.514584125e-07 | 4.80689447e-07 |
| A07_L2_matched | -1.029556318e-06 | -1.204485836e-06 |

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


## 交付文件索引

- `figure_mechanism_case.pdf` / `.png`：唯一最终四面板图。
- `selected_case_raw.csv`：6项同输入反事实原始记录。
- `selected_case_semantic_evidence.csv`：全部44类、2个真实来源的原始功能与历史证据。
- `selected_case_source_scores.csv`：全类别D/M/U宏平均。
- `selected_case_share_shift.csv`：R0-R6全部实际区域份额，R0用于图示。
- `selected_case_utility.csv`：所有高亮效用点、两个类别口径。
- `all_diagnostic_utility_context.csv`：全部318个receiver-round、6方法的背景点。
- `displayed_classes.csv`：全部44类及前8类选择标记。
- `candidate_selection_audit.csv`：每个合格候选的筛选与数值项控制对照。
- `plot_data.json`：完整绘图数据、转换、口径和原文件SHA。
- `plot_final_mechanism_case.py`：独立入口代码副本（主版本在tools/）。
- `CAPTION.md`：论文图注。
- `tests.log` / `QA.json`：测试、复现、文件和渲染核验。

该细小效应尚未通过高精度模型/CE重算核验，不能由此单例推导稳健或统计显著的收益。共44类的信息与前8类的展示子集分开保留；前8类承载70.15%的总u。
