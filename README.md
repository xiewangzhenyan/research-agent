# Research Agent

**LSPRAI · 科研知识库与 AI 助手**

面向课题组知识积累与科研协作，汇集经典文献、基础知识和研究资料，支持引用问答、流式对话、可恢复后台任务及多角色资料协作。可用于 LSPR、超表面、生化基础等方向的科研入门，也可按课题组需求建设其他领域的知识库。

- 项目仓库：[xiewangzhenyan/research-agent](https://github.com/xiewangzhenyan/research-agent)
- 在线入口：[agent.lsprai.com](https://agent.lsprai.com)

## 当前能力

- **原生知识库**：文档解析、分块、处理状态、本地中文向量、混合检索、重排与原文引用。
- **常见问答**：标准答案关联多种相似问法，支持在线编辑、重新索引和重复答案去除。
- **对话工作区**：会话历史、模型选择、流式回答、资料范围选择和消息评价；会话读写按账号及分享权限校验。
- **项目空间与记忆**：知识库在账号下复用；会话、任务及记忆按项目隔离；基于 Mem0 自动整理长期事实，支持原文追踪、纠正、删除和聊天召回。
- **持久任务**：执行记录、取消、人工澄清、checkpoint 与重启恢复。
- **资料协作**：规划、研究、撰写与审校角色按固定流程协作，支持有限修订。
- **模型与工具管理**：展示生成模型、向量模型、重排模型及实际可用能力。
- **隔离计算接入**：包含独立节点管理器及输入、产物协议，需完成部署验收后启用。

项目处于持续开发阶段。通用并行多智能体、自动记忆提取与上下文压缩、完整外部知识连接仍在建设中，不能将规划功能视为已实现。会话权限已有回归测试，沙箱能力仍应按实际部署完成验收。

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 前端 | Next.js、React、TypeScript、Tailwind CSS |
| API | FastAPI、Pydantic |
| Agent 执行 | PydanticAI |
| 工作流 | LangGraph |
| 数据与检索 | PostgreSQL、pgvector、本地中文 Embedding/Rerank |
| 后台处理 | 独立任务 worker、Celery、Redis |
| 部署 | Docker Compose、Nginx、独立隔离执行节点 |

## 本地开发

准备 Docker Compose、Python 3.12、uv 和 Bun。开发环境使用独立数据库及测试配置，不连接生产数据。

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
# 编辑本地配置后启动开发服务
make dev
# 首次需要开发账号时运行
make seed
```

前端单独启动：

```bash
cd frontend
bun install --frozen-lockfile
bun dev
```

默认前端端口为 `38000`，后端端口为 `38001`。模型、地址及凭据通过本地环境变量配置，实际配置文件不进入 Git。

后台任务、知识索引及隔离执行有各自的部署步骤，见部署和模块文档；启动普通聊天不代表这些服务已就绪。

## 代码结构

```text
backend/app/
  api/             API 路由与身份依赖
  services/        知识、会话、任务及工具服务
  repositories/    数据访问
  db/              数据模型
  agents/          模型与工具适配
  worker/          后台执行
frontend/src/      页面、组件与前端 API 代理
sandbox/           隔离执行管理器与文件协议
infrastructure/    数据库镜像和维护工具
docs/              开发与部署文档
```

## 验证与维护

```bash
cd backend
uv sync --dev
uv run pytest
```

```bash
cd frontend
bun run type-check
bun run test:run
```

需要数据库、模型或执行节点的集成测试，应使用对应的独立测试环境。部署时只构建变更服务，并按保留规则清理旧镜像和构建缓存。

- [开发约定](AGENTS.md)
- [贡献指南](CONTRIBUTING.md)
- [部署说明](docs/deploy.md)
- [配置说明](docs/configuration.md)
- [沙箱说明](sandbox/README.md)
- [磁盘维护](docs/storage-maintenance.md)
- [安全说明](SECURITY.md)
- [会话权限与账号隔离](docs/conversation-access.md)
- [常见问答与相似问法](docs/faq-alternatives.md)
- [网站图标更新](docs/site-icons.md)
- [GitHub 同步说明](docs/github-sync.md)

- [项目空间与账号知识库](docs/project-spaces.md)
- [项目记忆与召回边界](docs/project-memory.md)

## 许可

适用的第三方代码许可保存在 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 及对应许可文件中。
