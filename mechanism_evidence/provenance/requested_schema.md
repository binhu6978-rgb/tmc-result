# SemConsFL 机制有效性证据上传任务（给本地 Codex）

## 任务目标
仅盘点、导出、整理并上传**已有**的 SemConsFL/A07 运行证据到 GitHub。不要改动算法、Method、训练/评价逻辑，不要启动新训练或新探针实验，不要为了得到正相关筛选结果。不要伪造缺失变量或从聚合统计推测不存在的高维张量。

目标仓库：`binhu6978-rgb/tmc_finish_need`。使用一个新目录 `mechanism_evidence/`，不要覆盖当前老版本代码。若运行代码与仓库 main 不同，请单独复制为 `mechanism_evidence/code_used/`，并记录 commit、原始工作树差异和运行入口。

## P0：先做这三件事（必须）

### 1. 运行来源、配置与现有资产
创建 `mechanism_evidence/README.md`、`manifest.json`、`file_inventory.csv`、`runs.csv`。
- 为每个真实运行指定唯一 `run_id`：1000轮语义运行、500轮A07、500轮语义版、既有Receiver探针及既有20轮聚合对照等应分别标识；若属于同一真实运行的后处理可关联到父 `run_id`。
- manifest明确：算法名称及准确代码版本、git SHA/dirty diff、训练入口、配置文件、随机种子、数据集和划分标识/哈希、客户端总数/每轮抽样、Low/Middle/High模型配置、1000/500轮设置、local epoch和优化器、lambda、覆盖区域规则、BN与classifier聚合规则、Memory初始化/更新顺序、评价数据集与是否和语义测量重叠。
- 扫描日志、CSV、JSON、NPZ、PT/PTH/CKPT、safetensors、已有反事实文件及生成脚本。`file_inventory.csv`至少含：`run_id,path,type,size_bytes,sha256,round_range,description,available`。
- 不要把未核实的文件归到同一运行。对于缺失内容明确写 `NOT_SAVED`/`NOT_FOUND`/`UNKNOWN`。

### 2. 逐类别语义证据、Memory状态
如果已保存，导出 `semantic_class_evidence.csv`，一行代表一个 `(run_id,round,source_tier,class_id)`：
`run_id,round,source_tier,class_id,q_pre,q_post,q_other_past,d,a,rho,u,class_support,eligible,anchor_count,history_age,history_variance_or_stability,history_effective_support,memory_snapshot_time`。
所有字段应保留实际代码定义，未知者留空并在 README 声明。不要强行生成伪造的逐类数据。
同时导出未经加工的 `source_rounds.csv`，以及若现存 `memory_updates.csv`（含记忆轮次、更新前后状态/支撑量）。
提供评分计算脚本/源代码，明确 q 来自原任务分类器还是辅助Adapter，以及 q 的计算使用何种数据、哪个模型时刻、类别聚合口径、先评分后更新Memory还是反过来。
若逐类别日志从未保存，只报告缺失，不要根据聚合后的U逆向虚构。

### 3. 实际聚合决策与改变量
如果有逐区域权重日志，导出 `aggregation_weights.csv`，一行 `(run_id,round,region_id,source_tier)`：
`run_id,round,region_id,parameter_family,region_numel,source_tier,source_mass,source_U,pi_A07,pi_sem,delta_pi,semantic_applicable,reason`。
提供 `aggregation_rounds.csv`，含：
`run_id,round,selected_client_ids,selected_tiers,valid_evidence,active,reason,common_classes,lambda,changed_parameters,changed_fraction,difference_l2`。
提供覆盖区域定义、掩码/分组编码说明，并注明共享features、trainable BN、classifier各自的规则。
已有 `all_rounds.csv` 可原样上传，不要重新编造无法从原始日志恢复的 `pi`；若只有汇总权重，请明确限制。

## P1：发现现有检查点/更新就上传；没有就报告缺失

### 4. 固定更新的同轮聚合反事实所需状态
先提供 `checkpoint_inventory.csv`；不要跳过这一步、也不要立刻上传所有大型权重。
重点查找不同训练阶段以及语义激活/未激活轮的以下原始状态：
- `theta_before_t`：聚合前全局模型（包括需要的BN buffer及服务器优化器状态）
- 该轮参与客户端ID/tier/profile、真实本地更新/训练后模型，能对齐到全局区域的参数映射与cover masks
- A07基础份额、真实SemConsFL份额、语义Memory状态及该轮聚合脚本
- 同一 `theta_before_t` + 同一批client updates 所产生的 `theta_after_A07`、`theta_after_Sem`（若已保存，需能核实同一起点）
- 评价集定义与哈希、标签空间、eval mode、CE reduction（mean/sum）、模型参数保存精度
如已有离线聚合/反事实结果，导出逐轮 `fixed_update_counterfactual.csv`：
`run_id,round,eval_set_id,pre_state_hash,client_updates_hash,ce_before,ce_A07,ce_sem,ce_permuted_if_exists,accuracy_A07,accuracy_sem,delta_l2,notes`。
**不要把两条独立训练轨迹同编号轮次当成同起点的反事实。** 如果仅有不同轨迹的accuracy日志，请原样保留并标注非配对反事实。

### 5. 独立效用测量与旧图源数据
上传原样 `receiver_utility_raw.csv`（含原本的39列）、生成探针的代码、探针选轮规则、receiver/client标签及评估集来源、训练侧探针是否与semantic测量数据重叠、`per_class`字段定义、Utility正负号、计算是否归一化。
上传 `all_rounds.csv`, `source_rounds.csv`, `accuracy_each_round.csv`原始版本和所有配置。
如存在旧 `figure8_aggregation_behavior` 的原始逐轮表、生成脚本、状态记录，也一起上传，明确它是否复用了同一global pre-state和client updates。
如有500轮A07/语义版配对结果，请上传原始轮次曲线、run manifest及client participation schedule，说明是否真正同种子、同数据划分、同参与安排。

## 建议目录结构
```
mechanism_evidence/
  README.md
  manifest.json
  file_inventory.csv
  runs.csv
  code_used/                    # 实际训练代码快照及配置，非旧版冒名
  logs/
    all_rounds.csv
    source_rounds.csv
    receiver_utility_raw.csv
    accuracy_each_round.csv
  memory/
    semantic_class_evidence.csv  # 若原始记录存在
    memory_updates.csv           # 若存在
  aggregation/
    aggregation_rounds.csv
    aggregation_weights.csv      # 若存在
    coverage_definition.json
  checkpoints/
    checkpoint_inventory.csv
    ...                         # 仅选择必要状态，优先 Git LFS
  counterfactual/
    fixed_update_counterfactual.csv   # 若既有
    original_figure8_inputs.csv       # 若既有
  provenance/
    configs/
    scripts/
    missing_data_report.md
```

## 必须遵守
1. **不运行新训练、不执行新的离线反事实、未经确认不修改代码**；只复制已有文件、扫描清单和从真实已存日志导出明确可还原的表。
2. **不得按正负效用挑选文件或轮次**；所有已有可用轮次应进入清单。大型状态可以优先列清单，再依据预先固定的轮次抽样上传。
3. 保留原始记录，派生文件放其他目录，并记录脚本和所有过滤条件；不覆盖、不静默改写原始CSV。
4. 仓库可能公开。不得上传原始用户/客户端样本、PII、访问令牌、私有路径或受版权/隐私限制的数据。大于GitHub限制的二进制使用Git LFS或只上清单，绝不能将日志、模型或大文件拆成不可验证的伪内容。
5. 最后在回复中给出：GitHub提交SHA、上传文件树、各类型文件数量、是否发现checkpoint和逐类别Memory日志、是否足以做“固定更新A07 vs SemConsFL”离线反事实；对缺失材料逐项列明。
