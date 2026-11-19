# 研究质量评估

`backend/scripts/evaluate_research.py` 提供可回放的逐结论、逐要求评审流程。
代码复用生产 `validate_answer` 检查原句、引用编号与数字；语义是否得到支持、要求是否满足，
由评审者显式标注。没有评审时支持率为空，确认完成数为零，不让模型自行给自己打分。

## 当前覆盖与边界

`backend/evals/research_tasks_v1.json` 有 10 个合成任务，development／holdout 各 5 个，
覆盖比较条件、否定、冲突、无答案、双语、资料版本、对象范围、资料中的干扰指令和证据边界。
每个任务含固定资料和要求 ID。它们是人工编写的回归样本，不是实际用户任务或生产质量估计。
要求条目应分解原始问题中的明确要求，不额外增加未告知模型的业务条件。
后续可按同一合同加入经过脱敏和人工确认的真实任务，标记 `origin=curated_redacted`。

`--live --route standard|knowledge_collaboration|both` 分别运行普通严格问答、协作或两条路线。
两条路线使用相同的固定资料、编号、问题、模型与基础生成配置，运行上下文各自独立。
协作与生产共用同一组 LangGraph 节点、角色定义、交接和最多一次返工；
评估适配器只读取固定资料，不连接数据库。生产构造入口仍逐节点检查账号、模型、资料归属。
规划员仍会生成检索计划，但评估不据此额外检索，因此测量的是已有证据条件下的角色编排效果与成本。
这不覆盖真实检索、沙箱或完整工作任务流程。
不要把导入任意 JSON 视为已验证真实运行来源。评审者标签也是记录信息，不构成身份认证或独立性证明。

## 离线检查与运行

从 `/tmp` 执行，避免后端默认从工作目录加载生产 `.env`。默认只检查数据集，不请求模型：

```bash
cd /tmp
PYTHONPATH=/home/agent/backend /home/agent/backend/.venv/bin/python \
  /home/agent/backend/scripts/evaluate_research.py
```

显式 `--live` 使用调用者已配置的模型环境，会产生模型调用费用；不从本项目读取或复制密钥。
保存同一次运行快照，后续评分无需重复调用模型：

```bash
PYTHONPATH=/home/agent/backend /home/agent/backend/.venv/bin/python \
  /home/agent/backend/scripts/evaluate_research.py --live \
  --save-runs /tmp/research-runs.json \
  --output /tmp/research-unreviewed.json --packet /tmp/research-review-template.json
```

同时采集两条路线，将上面命令加上 `--route both`。每个案例交替执行顺序，避免始终先运行
同一路线。`--save-runs` 在每个完整路线返回后原子保存；进程中断后，已完成的快照仍可离线评分，
缺失运行保持缺失。新快照在首次调用前写入路线清单，并保存数据集、生成配置和执行管线指纹。
执行指纹包含相关源码、锁文件与模型端点，只保存哈希，不记录密钥或端点原文。
重放拒绝不同版本的数据集；续跑还会校验模型、配置、管线、路线计划和每个已存结果的资料范围。

## 中断后续跑

使用含 `version=research-run-snapshot-v1` 的快照继续采集，输出到新文件，保留原始快照：

```bash
PYTHONPATH=/home/agent/backend /home/agent/backend/.venv/bin/python \
  /home/agent/backend/scripts/evaluate_research.py --live \
  --resume-runs /tmp/research-runs.json --save-runs /tmp/research-runs-continued.json \
  --output /tmp/research-continued-report.json --packet /tmp/research-continued-review.json
```

省略 `--route` 时继承已存路线计划，包括首个案例只完成一条路线的双路线批次。
完成项（含拒答和审校拒绝）不会重新调用。默认保留已记录的错误／超时，只补跑尚无结果的路线。
需要重试错误或超时，在命令中显式加 `--retry-failed`：每次命令只尝试一次，不循环重试，
新的结果替代该路线的最终状态，所有历史尝试仍保存在 `attempts`。结构化输出内部的有界重试仍遵循原执行策略。

新采集的 `--save-runs` 必须使用不存在的路径。目标通过原子操作独占创建，另一进程使用同一路径
会在请求模型前失败；后续更新采用原子替换并刷写文件，权限保持 `0600`。
输入快照、输出快照、评审输入和报告路径不能相同。错误的版本、范围或记录对应关系会在请求模型前失败。

旧格式快照仍可离线评分，但缺少完整执行清单时不能续跑；不要推测原来的模型、代码与路线计划。
模型／配置／管线改变后应作为新批次运行。这里恢复的是完整“案例＋路线”结果，
尚不跨进程恢复评估图内部节点；进程中断时尚未返回的路线从头执行，已经发生但未记下的调用可能重复计费。
生产任务的 PostgreSQL 检查点恢复机制保持原样。

## 人工评审与离线评分

评审包的 `records` 包含问题、要求、原文、已发布结论与引用；`reviews` 是待填表。
复制评审包为另一个文件，例如 `/tmp/research-reviews.json`，填写：

- `reviewer`：评审者标签，不能空白。
- `claims[].support`：`supported`、`unsupported` 或 `uncertain`。
- `requirements[].status`：`satisfied`、`partial`、`missing` 或 `uncertain`。
- `requirements[].claim_ids`：支持该要求的结论 ID。对已回答的任务，标为满足的要求必须关联已评为支持的结论。
- `abstention`：仅拒答可以填写 `correct`、`incorrect` 或 `uncertain`。

保留没有评审的条目为 `null`；`uncertain` 表示已评审但未确认通过。离线计分：

```bash
PYTHONPATH=/home/agent/backend /home/agent/backend/.venv/bin/python \
  /home/agent/backend/scripts/evaluate_research.py \
  --runs /tmp/research-runs.json --reviews /tmp/research-reviews.json \
  --output /tmp/research-reviewed.json --packet /tmp/research-next-template.json
```

指纹绑定问题、要求、资料版本、实际答案及运行元数据；更换输入或答案后必须重新评审。
未知／重复的案例、引用、要求、结论链接和陈旧评审会使评分失败。
报告按全部预期案例计数，未运行的案例不能通过省略而获得成功分。
同一最终答案的语义评审可以继续使用；尝试历史另有哈希和独立成本统计，不会因此丢失失败次数。

报告与评审包使用原子替换写入，权限为 `0600`。评分输出以 ID、判断、计数和运行指标为主，
原文保留在评审包中；输入快照、已填写评审和输出必须使用不同文件，避免覆盖原始证据。
不要将含内部资料的评审包或真实运行快照提交到 Git。

## 接入现有知识库评测

`evaluate_knowledge.py --answers` 保留原来的检索与生成评测，另写入 `research_dataset`
和 `research_trials`，记录同一次生成的结构化结论及当时提供的资料，不再另生成一份答案评分。
未提供细分 `requirements` 的旧案例使用整个原始问题作为单项评审要求。

对已保存的新格式知识库报告生成评审包，无需重跑检索或模型：

```bash
PYTHONPATH=/home/agent/backend /home/agent/backend/.venv/bin/python \
  /home/agent/backend/scripts/evaluate_research.py \
  --knowledge-report /tmp/knowledge-eval-answers.json \
  --output /tmp/knowledge-unreviewed.json --packet /tmp/knowledge-review-template.json
```

完成评审后沿用相同 `--knowledge-report`，添加 `--reviews` 并指定不同输出路径。
旧格式报告没有实际结构化答案快照时，需要重新采集；不通过拆分回答文本来推测原来的结论和证据。
旧报告的 `citation_support_accuracy` 仍为空，实际人工评分见新报告的
`citation_support_accuracy_reviewed`，必须同时查看评审覆盖率。

协作快照必须包含 `collaboration.version`、最终 `approved` 和返工次数 `revisions`。
评分遵守最终发布决定：审校拒绝的草稿即使引用原句正确，也不会恢复成已发布答案。
模型审校通过不会自动填写人工评审。缺失发布决定的旧协作快照需要重新采集或从真实运行记录中补齐，
不能默认通过；普通路线旧快照与评审指纹继续兼容。

## 指标含义

- `claim_review_coverage` 和 `requirement_review_coverage_recorded`：已记录运行中完成评审的覆盖率。
- `citation_support_accuracy_reviewed`：已评审结论中被确认支持的比例，`uncertain` 不算通过。
- `requirement_satisfaction_reviewed`：已评审要求中被确认全部满足的比例，部分满足不算通过。
- `confirmed_success_rate`：以整个划分的预期案例数为分母；只有全部要求满足且所有发布结论得到支持，或拒答被确认正确，才计为确认完成。
- `missing_cases`、`errors`、`abstained`：分别统计缺失运行、执行失败和拒答，不互相替代。
- 时间、token、费用同时报告有记录的案例数；缺失值为空，不能当作零成本。生成服务没有完整报告 token（含结构重试）时，评估快照将用量留空。

`paired_comparison` 按 development／holdout 单独汇总成对比较：
两条路线都必须有记录，且模型、资料顺序／内容和基础生成配置哈希相同。
不符合条件的配对单独计数，不参与比较；缺少配置哈希的旧快照仍可分别评分，不能算作可比较配对。
配对必须评审完成且没有 `uncertain` 才统计哪条路线确认完成；超时或执行错误是已知失败，
未评审或不确定不能自动变成另一条路线获胜。
耗时差记录为“协作减普通”，并同时给出有耗时数据的配对数量；小样本结果不代表统计显著性。

`attempt_summary` 另外汇总所有执行尝试，包括被后续重试替代的错误和超时。
`first_attempt_completed_cases` 只表示首次执行返回完成结果（包括拒答），不是答案正确数；
`completed_after_retry_cases` 表示通过显式重试才返回完成的案例。
最终答案质量仍由 `summary` 和人工评审决定。
逐案例记录 `attempt_count`、`prior_execution_failures` 与 `attempts_sha256`，
不允许在一次已完成的结果之后继续重试以挑选更好答案，或在历史中更换资料／模型／配置。

已知时间、token 和费用使用 `measured_*` 字段，附带有记录的尝试数量；
只有该组所有尝试都有数据时，`total_latency_ms`、`total_input_tokens`、`total_output_tokens`
和 `total_cost_usd` 才提供完整总数。有一项缺失就保留为空，不能把只知道的部分当成总成本。
`paired_comparison.retried_pairs` 标记经历过重试的配对；
`median_total_attempt_collaboration_minus_standard_ms` 另外比较包含失败重试的累计执行耗时。
原 `median_collaboration_minus_standard_ms` 仍只比较最终尝试，两者应结合查看。

对未知问题，`evaluate_knowledge` 的超时和服务错误不再计入正确拒答。
确认完成率为零也可能来自尚未评审，必须同时查看运行数、错误数和评审覆盖率。

## 本地验证（2026-11-19）

完整单元套件 756 项通过、133 项按环境条件跳过，源码覆盖率 63.41%。
研究评估／原生调用／模型配置／执行策略专项 98 项通过、2 项按环境条件跳过。
Ruff 和改动文件格式检查通过；类型检查无错误，保留 47 条既有警告。
原有合成、跨页证据、双语三套数据集的 60／16／40 个案例均通过新快照合同兼容检查。

验证包括陈旧评审、否定关系误判、缺失运行、未知 token 用量、超时误计拒答和离线回放。
测试中的生成调用使用离线替身；未运行付费模型基准，也没有真实任务质量分数。
本轮没有数据库迁移、推送、镜像构建或部署。

协作采集补充验证：完整单元回归 775 项通过、133 项按环境条件跳过，源码覆盖率 64.18%；
临时 PostgreSQL 的生产协作／持久聊天／执行策略专项 35 项通过。
随后补充的评估与原生执行专项 62 项通过、2 项按环境条件跳过，包含不确定评审不判胜负、
跨角色／重试用量缺失、旧普通路线指纹兼容、协作发布门槛、恢复时不重复已完成角色、
中断后的快照保存及数据集版本不匹配拒绝。
Ruff、格式和类型检查通过，仍有 47 条既有类型警告；临时数据库已清理。
这里验证的是执行与计分机制，模型使用离线替身，真实路线效果对比仍待采集与评审。

批次续跑补充验证：完整单元套件 811 项通过、133 项按环境条件跳过，源码覆盖率 64.44%。
新增用例覆盖完成项／拒答保留、只补缺失路线、显式且有界的失败重试、保留原始快照、
配置／管线／资料范围失效、历史记录与最终结果对应、累计重试耗时和费用、未知用量保持未知，
以及并发抢占同一输出路径时只有一个创建者成功。
Ruff、格式与类型检查通过，保留 47 条既有类型警告。
本轮只验证离线执行与计分逻辑，没有调用付费模型、修改生产数据库、推送或部署。
