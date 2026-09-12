# 基于本地 WeKnora 的 RAG 改造建议

检查日期：2026-09-09。当前应用：`/home/agent`；参考项目：`/opt/weknora`。

## 建议结论

保留当前 Next.js 页面、FastAPI 账号与会话、PydanticAI 聊天及现有模型网关，将 WeKnora 作为文档入库与检索服务。第一阶段让用户完成“创建知识库 → 上传文件 → 查看处理结果 → 选择知识库提问 → 查看引用”的完整流程。

这一方案能复用已部署的文档解析、分块、索引、混合检索和重排实现；业务权限与用户体验仍由当前应用负责。前端通过当前 FastAPI 适配层访问 WeKnora，服务凭证只在后端保存。

## 已确认的本地情况

| 项目 | 检查结果 |
|---|---|
| WeKnora 服务 | App、DocReader、PostgreSQL、Redis、前端正在运行；App `/health` 返回 `ok` |
| 当前运行镜像 | App 和 DocReader 标签为 `latest`，镜像标签元数据版本为 `v0.5.1`、revision 为 `fe0d24ae…` |
| 本地源码 | VERSION 为 `0.5.1`，HEAD 为 `1ae06fb`；源码提交与运行镜像提交不同 |
| 检索存储 | `RETRIEVE_DRIVER=postgres`，数据库已安装 `vector`、`pg_search` 扩展 |
| 文件解析 | 独立 DocReader，经 gRPC 调用；当前存储类型为 local |
| 模型记录 | 未删除记录只有 KnowledgeQA / VLLM 两项 `gpt-5.5`；未见 Embedding / Rerank 类型记录 |
| 入库数据 | 当前未删除的知识库数为 0，知识条目数为 0 |

本次检查为源码、配置和运行状态分析，没有改动应用或 WeKnora 部署，没有进行新文档的入库和检索质量实测。代码具备的能力不等于本地实例已经完成配置验收。接入前应固定镜像版本或摘要，并用该版本实际验证接口。

## 最值得借鉴的能力

### 1. 文档管理与异步状态

WeKnora 的知识条目包含 `pending`、`processing`、`completed`、`failed`、`deleting` 状态；处理流程包含分块、生成向量、写索引与旧索引清理。当前应用应展示文件列表、处理进度、失败原因、重试、重新解析和删除状态。

“文件接收成功”与“已经可以检索”应分别反馈。服务端同步 WeKnora 状态；重复上传、网络超时与任务重试应有幂等策略，避免产生重复文档。跨两个服务的失败需要记录和补偿，不应靠一个接口返回 200 判定流程完成。

参考：`/opt/weknora/internal/types/knowledge.go`、`internal/application/service/knowledge_process.go`。

### 2. 混合检索、重排与上下文控制

本地源码同时支持向量与关键词召回，通过 RRF 融合结果；检索流水线可进一步重排、合并和筛选。关键词检索适合产品型号、编号、人名和精确术语；向量检索适合语义相近但措辞不同的问题。

初期可用 20–30 个候选、重排后 5–8 个片段作为调参起点，最终按真实文档、延迟与上下文预算决定。相邻片段/父子片段补全可保留标题和上下文。不能把整份长文档无限加入模型输入。

现有前端按 0.4/0.7 阈值显示相关性颜色，但 RRF 分数并不等价于相似度概率；接入时应区分评分类型，避免把融合分数显示成“置信度”。

参考：`internal/application/service/knowledgebase_search_fusion.go`、`internal/application/service/chat_pipeline/rerank.go`、`internal/application/service/session_knowledge_qa.go`。

### 3. 将生成、Embedding、Rerank 配置分开

- 生成模型：继续使用当前应用的 `gpt-5.5` 和已配置网关。
- Embedding：新增真正可用的文本向量模型，用于文档和查询向量化；文档与查询必须使用兼容模型及维度。
- Rerank：作为独立可选模型配置，用真实样本评估质量与耗时。不存在时不能在界面声称已启用。

BGE-M3、Qwen3-Embedding 及相应中文/多语言重排模型可作为候选，实际选择取决于可用接口、机器资源和实测效果。本次没有确认这些模型已可调用。不能因聊天网关能返回 `gpt-5.5` 的回答，就假定它支持 embeddings 或 rerank。

模型页面应分别验证生成、向量维度、重排接口和解析能力。更换向量模型通常需要重建索引，应明确成本与处理状态。

### 4. 可验证的引用

WeKnora 返回片段 ID、文档 ID、知识库 ID、标题、片段内容、位置及评分等信息。当前项目已有 `sources-panel.tsx` 和 RAG 工具结果显示，可保留其交互，但应改为读取结构化 JSON。

现在 `parseRAGResults` 通过正则解析 `[1] Source: ...` 文本，直接接入 WeKnora JSON 不会自动显示引用。建议统一结果结构并保存到助手消息：`source_id`、`knowledge_base_id`、`document_id`、`chunk_id`、`title`、`excerpt`、`location`、`score`、`score_type`。只展示解析器实际返回的页码，不能根据片段位置编造页码。

答案引用如 `[1]` 应指向本次检索返回的片段；刷新历史对话仍能查看引用。查看原文、下载文件时再次验证权限。

参考：`/opt/weknora/internal/types/search.go`、`/home/agent/frontend/src/lib/chat-sources.ts`、`/home/agent/frontend/src/components/chat/tool-results/rag.tsx`。

### 5. 用户与租户权限

WeKnora 的 API Key 绑定租户，JWT/共享知识库还有相应权限处理。当前应用的用户 ID 不会自动变成 WeKnora 的租户或共享权限。

推荐为当前应用建立独立的 WeKnora 接入空间，在后端维护用户/租户与知识库映射。对私人资料优先使用与当前账号体系一致的隔离边界；如果选择共用服务租户，则必须由适配层对上传、检索、批量文件读取、原文下载和删除统一校验所有权与共享权限。

浏览器只能提交当前应用的资源 ID；服务端解析允许访问的上游 ID，不能透传任意 `tenant_id`、`knowledge_base_ids`、`knowledge_ids`。不要复用覆盖现有所有资料的宽权限账号作为所有用户的默认检索身份。

当前应用已有需要优先修复的具体问题：

- `chat_file_repo.get_many()` 仅按文件 ID 查询，没有 `user_id` 限制。
- `link_to_message()` 仅按文件 ID 更新关联，没有所有权限制。
- `AgentSession._build_multimodal_input()` 调用上述批量读取，未传入当前用户。

虽然单文件下载做了所有权检查，聊天附件读取链路仍缺少同等检查。应增加双用户回归测试，验证用户 B 无法读取或重新关联用户 A 的文件。本次只记录发现，没有修改此逻辑。

参考：`/opt/weknora/internal/middleware/auth.go`、`internal/handler/knowledgebase.go`；当前应用 `backend/app/repositories/chat_file.py`、`backend/app/services/agent_session.py`、`backend/app/services/agent.py`。

### 6. 检索效果与失败处理

借鉴 WeKnora 的 Recall、MRR、NDCG 等评估实现。先准备 20–30 组真实问题与对应文档，覆盖中文同义表达、精确编号、跨段落问题和资料中不存在的答案。

知识库问答模式应在生成回答前确定检索范围并执行检索；无结果时明确说明资料不足。高级 Agent 模式可再提供 `search_knowledge_base` 工具实现多轮检索。引用的文档属于不可信外部内容，不应把文档中的指令提升为系统指令。

监控入库失败率、解析/向量化耗时、检索延迟、重排耗时、有效引用率和实际模型用量。对解析、检索及模型超时分别反馈，不能将所有失败都退化为无来源的普通回答。

## 推荐接口与接入位置

| 需求 | WeKnora 本地源码接口 | 当前应用需要补充 |
|---|---|---|
| 创建与列出知识库 | `POST/GET /api/v1/knowledge-bases` | 资源映射、权限、知识库列表页 |
| 上传文档 | `POST /api/v1/knowledge-bases/:id/knowledge/file` | multipart 转发、幂等、状态回显 |
| 文档列表与详情 | `GET /api/v1/knowledge-bases/:id/knowledge`、知识详情接口 | 状态刷新、失败重试、受控原文访问 |
| 仅检索、不生成回答 | `POST /api/v1/knowledge-search` | 受控检索范围、超时、统一来源格式 |
| 底层混合召回 | `GET /api/v1/knowledge-bases/:id/hybrid-search` | 本地版本使用 GET + JSON body，只能在后端适配 |

优先评估 `POST /knowledge-search`：本地源码明确只执行检索、重排、合并和筛选，不调用 LLM 总结，适合将结果交回当前 PydanticAI 生成回答。初期无需再嵌套调用 WeKnora 的完整 Agent 对话流程。

当前应用建议新增 `backend/app/clients/weknora.py` 与独立知识库服务、路由，在 `agents/assistant.py` / `services/agent_session.py` 接入受控检索，前端补齐 `/rag` 文档管理、聊天知识库选择器及结构化引用处理。

两个 Compose 项目目前分属不同 Docker 网络。集成时为需要互通的 App 服务建立专用网络，通过服务 DNS 连接；容器内的 `127.0.0.1:18081` 不代表宿主机的 WeKnora。适配层访问 API，避免直接读写 WeKnora 数据库或共用其内部数据表。

## 实施顺序与验收

1. 修复现有附件权限链路；确定用户/租户映射；固定运行版本并确认 API 契约。
2. 配置 Embedding，创建独立测试知识库，用真实 PDF、Word、Markdown 跑通解析、索引与检索；验证需要的 OCR 服务。
3. 实现知识库管理页与上传状态。上传失败、解析失败、重试和删除都能在页面看到真实结果。
4. 将检索结果交给当前模型，支持知识库选择、无结果反馈、可点击引用和历史引用恢复。
5. 根据评估集调整混合召回、Rerank、分块与上下文预算，再考虑共享团队库、数据源同步、FAQ、图谱和 Wiki。

首版验收必须包含：新对话能检索之前入库的文档；用户间不能越权；索引失败不能显示就绪；重新解析不生成重复索引；删除后不能继续召回；问答能定位实际来源；资料不存在时不捏造引用；服务重启后文档状态与引用仍可恢复。
