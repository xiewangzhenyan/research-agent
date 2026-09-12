# 原生知识库

知识库的解析、分块、向量计算和检索全部在本项目执行，运行时不调用外部向量服务。对话生成仍使用管理员配置的语言模型；用户选择知识库后，相关原文片段会随问题提供给该模型。

- 中文向量模型：BAAI/bge-small-zh-v1.5，FastEmbed / ONNX，CPU 本地推理；查询使用 BGE 中文检索指令。模型权重缓存在 `agent_rag_models`，业务容器只读挂载且禁止运行时下载。
- 文档：PDF 保留页码，DOCX 包含表格，TXT / Markdown / CSV 支持 UTF-8 和 GB18030。扫描 PDF 暂需预先 OCR。
- 分块：按标点与段落边界拆分，默认目标 450 字、重叠 65 字，支持知识库配置和入库前预览。原文片段、位置、页码与向量保存在 PostgreSQL。
- 检索：默认中文二元词组及英文关键词 BM25 + 余弦相似度，经 RRF 融合，过滤相邻重复片段；也可单独使用关键词或语义模式。排序分数不代表回答正确率。
- 每账号最多 20 个知识库，每库 100 份文件、2400 个片段；每份文件 10 MB、500 页、100 万字符、1200 个片段。一次可选 5 个知识库，候选最多 12000 片段。当前采用有界精确检索，适合个人和中小规模资料；大规模扩展时应迁移索引到 pgvector / 全文索引，而不是移除限额。

## 处理流程与恢复

`pending → parsing → chunking → embedding → ready / failed`。状态来自数据库中的实际任务步骤，不使用模拟百分比。上传先提交持久化任务记录，再派发 Celery。Beat 每 30 秒重新派发排队记录；超过 6 分钟未完成的任务标记失败，可手动重试。任务拥有独立代次 ID，重复消费和旧任务回写受锁与代次检查保护。完成时分块与 ready 状态同事务提交。每个 worker 单并发，向量按 16 条分批处理。

文档与知识库的列举、上传、重试、检索、分块预览、下载和删除均验证账号所有权。删除文档级联删除片段，提交后删除原文件。聊天引用随工具结果保存，历史对话可恢复原文引用。浏览器账号切换会清空私有视图并重建查询缓存。

## 模型预置与部署

模型卷已预置。新环境可先创建模型卷，再用后端镜像以有写权限的用户执行一次模型下载（部署阶段需要网络），之后业务仅只读挂载：

```bash
docker volume create agent_rag_models
docker run --rm --user root -v agent_rag_models:/models agent_backend:dev python -c 'from fastembed import TextEmbedding; m=TextEmbedding("BAAI/bge-small-zh-v1.5",cache_dir="/models",threads=2); print(len(next(m.embed(["模型验证"]))))'
docker compose --env-file backend/.env -f docker-compose.prod.yml build app frontend
docker compose --env-file backend/.env -f docker-compose.prod.yml run --rm --no-deps app alembic upgrade head
docker compose --env-file backend/.env -f docker-compose.prod.yml up -d --no-deps app celery_worker celery_beat flower frontend
```

## 验证

`pytest tests/test_knowledge_index.py` 验证中文编码、Word 表格、扫描 PDF 错误、分块边界与混合检索。`backend/scripts/verify_native_knowledge.py` 只允许在名称以 `_review` 结尾的独立、空测试数据库上运行，需要启动对应 API 和 Celery worker；覆盖上传到就绪、中文改写提问、去重、PDF 页码、失败重试、下载和两个账号的全链路隔离。测试账号和数据仅保存在该临时数据库。

## 界面与动效

首页轨道使用 CSS transform，滚出视口或切到后台即暂停；手机减少动效，`prefers-reduced-motion` 禁用装饰动画。工作区采用深色和薄荷绿默认主题，保留用户主题选择。聊天保持静态阅读背景，引用面板支持原文片段和下载。

## 会话、严格回答与可追溯引用（2026-09-09 第二版）

会话保存 `active_knowledge_base_ids` 和 `knowledge_strict`。从知识库进入聊天时默认开启严格模式，普通聊天不受影响。重新打开会话会恢复范围；失效范围需明确重新选择，不会自动扩大到所有资料或普通问答。WebSocket 不传范围时使用保存的配置，显式空数组才清空。账号切换及跨会话请求具有状态隔离。

短问题结合最近 6 条上下文改写成独立检索问题，保留原始问题，8 秒超时则使用有界追问回退。知识库提问限制为 1500 字，超限明确报错，不再静默截断。严格模式不接受临时聊天附件，需先上传入库或关闭严格模式。

严格回答使用无外部工具的结构化生成：每个结论必须提供真实引用编号和连续原文引句；服务端核对引句及数字后输出，依据不足时说明无法可靠回答。空检索结果直接返回无依据提示。生成上限 90 秒，停止操作可取消生成。严格模式先核对再显示最终答案，普通聊天保留流式输出。引用真实性与数字检查不等于逻辑蕴含证明，复杂推理与冲突资料仍需人工复核。

引用快照独立保存在 `knowledge_citations`，与回答同事务保存；工具结果仅存指针。引用 API 每次验证账号，返回文件 SHA-256 指纹、索引代次、页码或表格位置。PDF 可打开引用页，Word 不伪造页码。重新索引后保留回答时的片段并提示索引变化；删除文档或知识库时清除引用快照及旧工具结果中的原文，保留已生成的会话回答。新引用尚未保存成功时会显示保存错误。

Word 按正文/表格原始顺序解析并记录章节；CSV 正确处理引号、逗号和单元格内换行。表格按逻辑行拆分，片段携带首行表头和行号；纯表头不单独占用检索结果，超长数据行拆成多个片段；超长表头（200 字以上）明确拒绝。暂不推断多层表头，也不处理嵌套表格、页眉页脚及图片 OCR。旧文件需重新处理才能获得新位置元数据。

### 可重复评测

`backend/evals/knowledge_synthetic_v1.json` 包含 12 份合成中文制度/操作资料、60 个问题（36 个直接问题、12 个追问、12 个资料中无答案的问题），固定 development / holdout 划分。评测使用实际本地向量模型及现有 BM25/RRF 排序；追问调用配置的生成模型。只测检索：

```bash
cd backend
python scripts/evaluate_knowledge.py --output /tmp/knowledge-eval.json
# 另测实际严格生成与无答案识别，使用当前配置的语言模型：
python scripts/evaluate_knowledge.py --answers --output /tmp/knowledge-eval-answers.json
```

`scripts/verify_native_knowledge.py` 后可继续运行 `scripts/verify_reliable_knowledge.py`，在隔离数据库验证真实问答、范围恢复及引用删除。

报告中的 recall 为文档级召回率；无答案问题召回相关片段不等于回答有依据。语义层面的引用支持率保留为空，需人工逐结论标注；合成小语料结果不代表真实用户资料质量。上线后的下一步应建立脱敏真实资料评测集，再决定重排、OCR 和向量索引升级的优先级。

## 指定文献与引用阅读

文件列表可直接发起“围绕此文献提问”，聊天中可将范围限定为 1–5 篇文献。范围随会话保存；失效或未处理完成的指定文件会阻止该次问答，不自动切换为全库资料。需要扩大范围时点击“恢复全库范围”。

严格资料模式生成的新回答会保存实际采用的原句，在引用面板中高亮显示。可展开同一索引代次的相邻片段，最多前后各一段；原文重新处理后不混入新分块。旧引用继续保留原文片段，不补造高亮信息。详见 `docs/releases/literature-20260909.md`。

## 中英文科研术语检索

本地术语表 `app/services/knowledge_terms.py` 为中文问题补充英文关键词，也支持表中英文术语查找中文资料。覆盖 LSPR、超表面、折射率灵敏度、检测限、非特异性吸附等 20 个概念。只匹配原始检索问题，不递归扩展；优先长词，限制最多 6 个概念、360 个别名字符。品质因数与 FOM 分开，磷酸盐缓冲液不等同于磷酸盐缓冲盐水，Q、RI 等歧义缩写不扩展。

别名仅参与 BM25，新增词权重为原词的 0.35；别名中的英文停用词不参与计分。向量仍使用原查询，原文及引用快照不被翻译或改写。无需重新处理已有文件。搜索 API 的 `terminology` 与会话检索记录的 `retrieval.terminology` 保存词表版本、此次别名，便于复查；它们不是回答依据。

这是有限术语匹配，不是通用翻译或多语言模型。常用英文问句中的泛词、术语表外表达和文献之间的细粒度区别仍可能影响排序；主题相关的命中不等于资料包含答案。严格模式继续核对原句和数字并允许拒答。合成中英文回归集与原基准可通过同一脚本运行：

```bash
python scripts/evaluate_knowledge.py --dataset evals/knowledge_bilingual_v1.json --no-expansion --output /tmp/bilingual-baseline.json
python scripts/evaluate_knowledge.py --dataset evals/knowledge_bilingual_v1.json --output /tmp/bilingual-expanded.json
python scripts/evaluate_knowledge.py --dataset evals/knowledge_bilingual_v1.json --answers --output /tmp/bilingual-answers.json
```

此集包含 16 份合成资料、32 个有依据的问题和 8 个无答案问题；development / holdout 是预先固定的合成回归划分，不是独立真实论文评测。结果与上线记录见 `docs/releases/bilingual-20260909.md`。该轮未涉及 PDF 版式，后续更新见下文；真实论文评测仍待实施。

## PDF 阅读顺序与提取情况（2026-09-09 更新）

PDF 解析按文字块坐标整理单栏阅读顺序；存在明确中央栏间空白、两侧具有足够多行文字且纵向重叠时，按左栏再右栏读取。跨栏标题、章节和居中页码作为分隔；无法明确判断时不强行分栏。旋转、裁剪页面及超过 2000 个文字块的复杂页面保留内部顺序。页码及每个文字块保留，不翻译、补写或通过版式推断生成文字。此方法不等于通用版面识别，也不识别多栏表格结构和公式语义。

`knowledge_documents.parse_report` 保存本代索引的 PDF 提取情况：总页数、有文字的页数、无文字页、疑似扫描页、识别为双栏的页。文字不足 80 个字符且单张图片覆盖页面至少一半时标记疑似扫描/图片页，不能据此认定该页一定是扫描件；分块拼接的扫描图、带完整错误 OCR 层的页面等仍可能漏检。有文字页数不代表全文完整。全篇无有效文字仍处理失败并提示预先 OCR；加密 PDF 明确提示解除密码保护。

文件列表和新回答的原文依据面板展示提取情况，可展开具体页码。报告按任务代次写入，旧任务不能覆盖新代报告；重新处理清空当前报告并重新生成，历史引用保留回答时的报告。删除原文件时同时清除对应引用快照。已有 PDF 不自动重建，列表提供“重新处理”；旧索引报告为空，不补造历史提取数据。重新处理期间该文档暂停检索。

迁移为 `0031_pdf_report`，本地向量模型不变。`scripts/verify_pdf.py` 仅在 `_review` 隔离数据库验证合成双栏/空白/图片页、真实处理报告、账号隔离、旧任务回写保护及引用报告快照。详见 `docs/releases/pdf-20260909.md`。真实论文评测和 OCR 仍待后续实施。

## 跨页与跨章节的证据保留

相邻位置去重现限定在同一页、同一逻辑位置内。PDF 不同页、Word 不同章节及表格独立行可分别进入相关证据列表，仍受排序和返回数量上限约束。无需重建索引；同页相邻片段仍采用既有去重规则。

`evals/knowledge_evidence_v1.json` 用必要证据页集合验证跨页检索，评测命令为 `python scripts/evaluate_knowledge.py --dataset evals/knowledge_evidence_v1.json --answers`。文档命中不等于证据全部找齐；详细记录见 `docs/releases/evidence-20260909.md`，后续计划见 `docs/knowledge-roadmap.md`。

## 知识库分块设置

每个知识库可设置 `chunk_size`（256–500 字符）和 `chunk_overlap`（0–128，且小于长度的一半），默认 450/65。更新接口为 `PUT /knowledge/bases/{id}/chunking-config`，当前账号必须拥有该知识库。分块仍尽量在句子或段落边界结束，表格保持逐行表头及零跨行重叠。

直接上传与重新处理在任务开始时读取知识库配置；经预览确认的上传使用固定的预览参数。成功后将实际配置写入文件 `chunking_config` 快照。之后修改设置不改变已有索引，文件列表会提示差异；选择“重新处理”后才使用当时的配置重建。正在执行的任务不受中途配置修改影响，历史引用保留原始代次及来源数据。零重叠索引不按相邻位置去重。

迁移 `0032_chunking_config` 为旧的已就绪记录补入先前固定的 450/65。旧格式无需自动重建；参数范围不是上游配置的完整复制，父子块和可选分块策略仍未实现。`scripts/verify_chunking_config.py` 在 `_review` 隔离数据库验证权限、索引实际效果和任务配置快照。后续按核心能力迁移清单推进，见 `docs/knowledge-roadmap.md`。


## 入库前分块预览

知识库页面保留批量直接上传，新增“入库前预览”单文件入口。选择 PDF、Word、TXT、Markdown 或 CSV 后，可调整长度/重叠并生成真实片段预览；显示总块数、最短/最长/平均字符数、页码及表格/章节位置，PDF 复用文字提取报告。仅显示前 80 个片段，每页 10 个；统计和正式入库覆盖所有片段。预览成功不代表已有向量或可检索，也不保证复杂 PDF 版式完全正确。扫描页仍需外部 OCR。

`POST /knowledge/bases/{id}/preview` 接受 multipart `file`、`chunk_size`、`chunk_overlap`（省略参数时为 450/65）。授权后复用 `parse_with_report` 和 `split_blocks`，不调用向量或生成模型，不写文档/媒体/任务。独立 Linux 子进程限制 384 MiB 地址空间、20 秒 CPU、25 秒墙钟；跨 API worker 的非阻塞文件锁限制当前容器同时一个预览，忙时返回可重试错误，无排队等待。输入沿用 10 MB / 500 PDF 页 / 100 万字符 / 1200 块上限；超时或协程取消会终止并回收子进程。浏览器关闭预览会丢弃结果；网络断开未必立即取消后端处理，后端仍受时间上限约束。

预览返回有效期 15 分钟的签名确认凭证，绑定当前账号、知识库、清理后的文件名、文件 SHA-256、处理版本与分块参数。`POST /knowledge/bases/{id}/documents` 可提交 `preview_token`，验证通过后用新增 `requested_chunking_config` 固定本次参数。处理中/排队中修改知识库默认值不会改变该次处理；成功后仍写实际 `chunking_config`。凭证过期、文件变更或处理版本变化时需重新预览。相同文件已存在时明确提示查看或重新处理，不静默用旧文件冒充新参数结果。用户主动“重新处理”会清除预览固定参数，采用当时的知识库设置。

迁移为 `0033_preview_config`，只增加可空字段，原有文档不重建。未来修改解析/分块契约须同步更新 `PREVIEW_VERSION`，使旧确认凭证失效。`tests/test_knowledge_preview.py` 覆盖解析一致性、展示限制、忙时拒绝、超时/取消回收及凭证范围；`scripts/verify_chunk_preview.py` 在隔离库验证真实 API 和索引结果。前端测试覆盖参数修改失效、过期响应丢弃和错误不允许确认。


## 检索设置、诊断与工作区

`GET /knowledge/retrieval-config` 返回当前账号设置，未保存时返回推荐默认值；`PUT` 验证并保存到 `knowledge_retrieval_preferences`，没有账号 ID 入参。设置对当前账号所有知识库与后续知识库提问生效，跨库检索使用同一份配置；无需重新建立索引。历史回答保留原来的引用和检索记录。迁移 `0034_retrieval_preferences` 只增加配置表，旧账号自动使用默认值，原有文件不变。

| 参数 | 范围 | 默认 |
|---|---|---|
| `mode` | `hybrid` / `keyword` / `semantic` | `hybrid` |
| `candidate_limit` | 每路 10–100 个 | 30 |
| `result_limit` | 1–10 个 | 6 |
| `semantic_threshold` | 0–1，余弦相似度下限 | 0.45 |
| `keyword_threshold` | 0–100，BM25 下限，仍要求正分 | 0 |
| `semantic_weight` / `keyword_weight` | 0–2，混合模式不能同时为零 | 1 / 1 |
| `rrf_k` | 10–100 | 60 |

`POST /knowledge/search` 可选 `retrieval_config` 仅覆盖该次测试，不会保存；可选 `diagnostics: true` 返回配置快照、扫描片段数、每路达到阈值数量/保留候选数、合并候选数、相邻重叠去除数、数量限制截去数、返回数及耗时。现有 `top_k` 可覆盖该次结果数量；省略时采用配置中的 `result_limit`。无论是否提供覆盖参数，知识库及文档范围均须通过原有所有权、就绪状态与限额检查。

混合模式按每路分数筛选候选，再用 `weight / (rrf_k + rank)` 合并；单路模式直接用 BM25 / 余弦得分排序。零权重的分支不参与候选生成；关键词模式跳过查询向量计算。候选源以文档 ID/片段位置排序，分数并列时稳定排序。默认阈值/权重/深度沿用原有值，但并列项排序现在明确稳定。每个命中携带分支原始分数与入选排名，未计算的分数为 null。BM25、余弦、RRF 的尺度不同，不可作为正确率或跨查询质量分数。

当前仍在有界范围内计算全量片段分数，`candidate_limit` 只控制每路进入合并阶段的候选数量，不能视作 ANN 索引深度或降低扫描量。范围上限仍为 12000 个片段。本轮后续已补可选本地模型重排和回答前邻块扩展（见下节），尚未引入新的向量数据库。聊天使用同一服务读取账号设置，并在本次工具结果中保存 `retrieval.ranking` 诊断及配置，便于后续追溯。

桌面工作区改为知识库侧栏与单一主面板；手机使用知识库下拉选择。文件管理与检索测试使用键盘可操作的页签；文件支持名称搜索、处理状态筛选、逐文件上传结果，单个文件失败继续后续文件。处理参数说明按需展开，删除知识库入口移至管理区域；预览片段独立滚动、已有分块每页 10 条，关闭分块读取窗口会取消请求，迟到响应不恢复旧窗口。账号变更时整个私有工作区重新挂载。

检索测试先载入已保存配置，加载失败时不悄悄退回默认值；调整参数或问题会清空旧结果，并丢弃旧请求的返回。只有点击“保存为账号检索设置”才持久化；高级参数收起，模式说明与问题输入优先显示；手机模式使用紧凑下拉框。暂存参数在切换知识库/离开页签后重新从已保存配置加载。

## 本地重排与回答前邻块扩展（2026-09-09）

检索配置新增 `rerank_enabled`、`rerank_limit`、`context_enabled`、`context_window`、`context_char_budget`，两项开关默认关闭。重排采用固定版本 `BAAI/bge-reranker-base` 的本地 ONNX 服务，对最多 10–20 个已授权候选评分后去重；邻块扩展使用相同查询快照，保留核心命中后在 500–2000 字符预算内补充相邻原文，合计最多 10 个独立引用。账号设置与临时测试共用接口，聊天复用并保存当次诊断。

服务仅使用内部网络与只读模型卷。首次部署需运行 `backend/scripts/provision_reranker.py` 准备固定模型文件；繁忙或超时时明确报错，不静默回退。模型分数不是置信度，512 token 输入截断会反映在诊断里。详细参数、资源实测、评测边界及回退方式见 [发布记录](releases/rerank-context-20260909.md)。

## 手动知识与 FAQ（2026-09-09）

“资料管理”新增在线编写知识和 FAQ，通过 `/bases/{base_id}/entries` 创建、`/documents/{document_id}/entry` 读取和按版本编辑。原生正文保存在账号所属文档的结构化数据中，与文件共用真实索引队列、限额和引用机制；FAQ 每个答案片段保留对应问题。编辑原子更换索引代次，旧工作任务不能覆盖，历史引用保留原文。迁移为 `0035_authored_knowledge`；原生资料存在时禁止结构降级。完整行为及边界见 [发布记录](releases/authored-20260909.md)。
