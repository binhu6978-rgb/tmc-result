# Final TMC IV-E mechanism figure: comprehensive rebuild

最终图：`figure_mechanism_case.pdf` / `figure_mechanism_case.png`。旧图与原始实验CSV完全保留，本目录独立保存重构版。

## 案例复核

继续使用真实Round989、Full接收者32（Low能力物理客户端）。本轮上传来自Middle/High，Low来源缺席。固定56个训练侧probe样本、28个评价类别，其中11类与语义共同集合相交；来源侧共44个有效语义类别。实际修改区域R0-R6，R0仅作为来源份额示例。

重新检视的筛选规则与先前保持一致：318个固定receiver-round案例中198个真实激活，145个具有至少2个接收共同类别；23个在两个类别口径下都正向且超过置换/L2控制；其中2个还同时超过两个Memory数值项控制。优先按共同类别支持量排序，Round989/receiver32（11类、44语义类）优于Round991/receiver42（9类、33语义类），没有改成追求最大CE收益。此筛选是回顾性的正向案例选择，不是独立验证或总体均值估计。

## 四个面板的科学编码

### (a) 类别热力图

6个展示类按两个真实来源的u总和取前6，平局按类别ID，再按ID排序；全部44类原始记录仍然导出。每格为q_post减过去其他能力层reference_q，正负符号、数值和零中心发散色图一致。对称对数色标的线性区间为+/-0.001概率，不删除、截断或重写极值；目的是让小差异可辨，而非改变任务分数。Low行显示missing，绝不填零。颜色在这里编码有符号变量；行名颜色编码来源身份。Adapter Prototype并未进入当前U。

### (b) 双Memory证据分解

采用按能力来源分组的水平条形图，取代三点折线。所有44个有效类参与：d=mean(max(q_post-q_pre,0))；m=mean(min(d_c,a_c))；U=mean(rho_c*min(d_c,a_c))。每项真实数值直接标注，并展示平均rho、每类独立当前客户端支持n及历史年龄。绝不用mean(rho)*mean(m)替代逐类校准。

### (c) 绝对来源份额与真实pp变化

上部堆叠条显示R0中A07和V2的实际百分比，Middle/High使用同一颜色和纹理。下部单独显示以零为中心的真实变化（pp），因此可以看清约0.002687pp的小变化，同时不掩盖绝对份额几乎不变的事实。完整聚合效用不能归因于这个单一区域。

### (d) 线性单案例效用与独立背景轴

主轴只使用线性CE改善，单位x1e-6；A07零线和全部六个原始控制保留，两个类别口径同时显示。蓝色表示所选接收者的Low能力身份，而非上传来源。

下部独立背景轴保留每个方法的全部318个固定诊断receiver-round值，绘制median/IQR及min-max whiskers，绝不以95%CI替代，也不剔除负面或中性案例；各方法的原始背景点全部保存在CSV。symlog仅用于独立背景轴，线性区间为+/-1e-6 CE，不与主图混成一个跨度过大的轴。

Without SM*只移除历史优势约束，Without RM*只移除rho乘数；共同类别和历史资格mask保持固定。这是同输入数值项控制，不是完整无Memory训练消融。在背景集合中，Without RM*的最大收益0.00348727确实高于V2最大值0.00161601，完整保留于背景箱须及CSV。

## 质量验收结果

- 7.16 x 7.9英寸，单页纯矢量PDF；PNG为3222 x 3555，实际450dpi。
- PDF实际嵌入字体仅TimesNewRomanPS-BoldMT（TrueType子集47868 bytes），无其他回退字体。
- PDF文本流实际字号严格为8、9、10pt；没有更小字号或图内大标题。
- 120个文本框：自动重叠0、裁切0；已按实际7.16英寸显示宽度（96dpi）和170dpi渲染人工核验。
- 彩色与灰度检查完成。统一能力颜色、来源名、纹理、填充/空心及形状提供冗余区分。灰度检查不被表述为完整色觉障碍认证。
- 66个数据字段及36个数值标签独立对照原CSV校验通过；6个原始文件SHA均未变化。
- 旧PDF和PNG的历史SHA校验通过。
- 9个测试通过，包含逐类Reliability校准不等价于均值乘积、Low缺失非零、背景中RM控制优于V2的案例不能丢弃等检查。

程序记录见`QUALITY_CHECK.json`、`printed_values.json`和`text_extents.json`。PDF字体检查针对实际资源与文本流，而非仅查看Matplotlib配置。

## 实际效用与解释范围

所选案例全probe类：V2相对A07的CE改善+7.35233438e-7，共同类+1.38168054e-6。当前案例两个口径均超过置换、L2和两个数值项控制。效应很小、只来自单个seed与训练侧样本，未进行高精度模型重算。可以描述“这一选中案例展示了完整计算链和有利的接收端响应”，不能据此声称双Memory在整条训练轨迹上提高性能、语义评分总体有效、R0独自导致收益或统计显著的泛化优势。先前完整结果和No-Go报告保持原状。

## 文件与复现

- `plot_mechanism_tmc_final.py`：完整独立绘图脚本，与tools/中主版本一致。
- `audit_tmc_mechanism_figure.py`：独立数据、字体、字号、矢量性、边界审计。
- `panel_a_semantic.csv`：含Low缺失标记的全部热力图格子。
- `panel_b_memory.csv`：两个来源的6个阶段值、rho/support/history。
- `panel_c_shares.csv`：来源百分比与pp变化。
- `panel_d_utility.csv`：全部12个单案例效用点。
- `panel_d_background_statistics.csv`：6方法全体背景的min/Q1/median/Q3/max。
- `selected_case_*.csv`、`all_diagnostic_utility_context.csv`：原始完整案例和背景。
- `plot_data.json`：可直接重绘的原始数据及选择元数据。
- `CAPTION.md`：英文论文Caption。
- `QUALITY_CHECK.json` / `tests.log` / `QUALITY_CHECK.md`：验收记录。

在仓库根目录执行：

```bash
python tools/plot_mechanism_tmc_final.py --output /path/to/new_output --font /path/to/timesbd.ttf
# 只调整当前生成图版面/重绘；不会覆盖旧图或实验数据：
python tools/plot_mechanism_tmc_final.py --output /path/to/new_output --font /path/to/timesbd.ttf --redraw
python tools/audit_tmc_mechanism_figure.py docs/evidence/semantic_a07_v2/activation1000/results /path/to/new_output
```

脚本副本也可运行，但需显式设置--root指向原始results目录。Windows默认使用C:/Windows/Fonts/timesbd.ttf；字体文件不随代码分发。审计需要pypdf/Pillow，绘图需要Matplotlib/NumPy。没有修改算法或运行SGD。

## 本轮Skill使用

使用find-skills检索并读取以下规范，未安装额外训练工具：

- [scientific-visualization](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/scientific-visualization/SKILL.md)及其publication_guidelines：数据与变换分层、尺度、缺失、数值和文件检查。
- [Matplotlib](https://github.com/K-Dense-AI/scientific-agent-skills/blob/main/skills/matplotlib/SKILL.md)：对象式Axes布局、分面与固定物理尺寸输出。
- 内置PDF skill：生成后实际渲染核验。

相关软件引用：Kassis, T., Agarwal, V., He, Y., Patel, D., and Brueckner, A. M. (2026). Scientific Agent Skills: A Library of Procedural Knowledge for Research Agents. https://doi.org/10.48550/arXiv.2609.00065 。仅记录绘图软件参考，不是SemConsFL算法证据。
