# 测试与 CI

GitHub Actions 对每次 push / PR 运行检查。发布前应核对本次提交的远端结果：
本地相关测试通过，不等于 GitHub 全量检查已经通过。失败必须定位到具体步骤；
取消意味着未完成，跳过可能是依赖的检查尚未通过。

## 本地命令

后端使用 Python 3.12、锁定依赖和 AnyIO。执行测试时不要加载生产 `.env`。
可使用独立检出目录，或从 `/tmp` 运行并设置 `PYTHONPATH`：

```bash
uv sync --directory backend --dev --frozen --python 3.12
uv run --directory backend ruff check app tests cli
uv run --directory backend ruff format app tests cli --check
uv run --directory backend ty check
uv run --directory backend pytest tests/ --cov=app --cov-report=term:skip-covered
```

异步测试用 `@pytest.mark.anyio`。启用 `--strict-markers` 后，拼错或未安装插件的
标记会直接导致收集失败。测试使用 FunctionModel 或 mock，不使用生产模型密钥。
测试配置可用 `OPENAI_API_KEY=ci-placeholder-not-a-real-key` 与
`OPENAI_BASE_URL=http://127.0.0.1:9/v1`，避免误发真实模型请求。

覆盖率使用 Python 3.12+ 的 `sys.monitoring`（`core = "sysmon"`）。本项目在
Python 3.12 下使用传统 trace 采集时，加载 jieba 的大型词典会导致测试收集长时间
占用 CPU；切换采集方式后，全量单元测试约 23 秒完成，源码覆盖率仍约 61.7%。
这是采集方式调整，测试范围和覆盖率门槛保持不变。

```bash
cd frontend
bun install --frozen-lockfile
bun run lint
bun run type-check
bun run test:coverage
bunx playwright install --with-deps chromium
bun run test:e2e
```

Playwright 本地自动启动开发服务器，CI 先构建再自动启动生产模式服务器。
使用 `PLAYWRIGHT_BASE_URL` 可指向独立的测试前端；没有默认测试账号密码。
浏览器用 mock API 检查中文登录、错误提示、注册校验、聊天输入、记忆确认和
移动端布局，在桌面及手机 Chromium 各运行一次。这些检查不代替真实后端集成测试。
模型配置回归还检查聊天、任务、记忆、模型页之间的实际导航：共享一次生成配置请求，
手动刷新才额外请求，查看知识模型时才探测运行状态。缓存边界见
[模型配置加载](model-configuration.md)。

## 数据库与迁移测试

CI 使用含 pgvector 的 PostgreSQL 16 临时服务，而非不包含该扩展的普通镜像。
数据库名必须以 `_review` 结尾。不要指向生产或共享开发数据库。

- `RUN_MIGRATION_DB_TESTS=1` 才允许迁移升级/回退测试，子进程最多运行 60 秒。
  普通单元测试收集阶段不会再探测数据库或自动开启破坏性的迁移测试。
- 先运行迁移测试，再执行 `python -m app.worker.agent_runs --setup` 初始化 checkpoint。
- `RUN_TASK_DB_TESTS=1` 启用真实 PostgreSQL 的账号/项目隔离、候选记忆、版本冲突、
  会话持续执行与历史恢复、多角色协作、检索与文件产物检查。
- `RUN_LOCAL_MEMORY_MODEL=1` 验证记忆编码，`RUN_LOCAL_MODEL_TESTS=1` 验证原生知识编码，
  另需挂载离线 BGE 缓存；共享 CI 不下载或冒充该模型，
  这个检查会明确显示为跳过，部署时另行验证真实本地编码和线上召回。

每个 CI 测试阶段有总运行时间限制，单个后端测试超过 60 秒会输出线程栈。
测试日志、JUnit、覆盖率和浏览器失败 trace/screenshot 保留为 Actions artifacts。
Docker 构建需等待静态检查、后端单元、数据库及前端检查全部通过。

## 覆盖率门槛

原配置要求所有前后端代码 100% 覆盖，且前端将测试文件本身计入覆盖率。
目前明确以真实源码为统计范围，门槛是防退步的最低基线，**不是覆盖充分的目标**：

| 范围                         | 最低门槛                                  |
| ---------------------------- | ----------------------------------------- |
| 后端普通单元测试             | 60%（本轮实测约 61.7%，数据库工作流另测） |
| 前端源码                     | 行/语句 13.5%、分支 60%、函数 28%         |
| 认证 Cookie 与引用高亮纯函数 | 各项 100%                                 |
| 项目选择与清理逻辑           | 行/语句 100%、分支 85%、函数 80%          |
| 记忆与任务 API 代理          | 行/语句 95%、分支 70%、函数 100%          |

前端行覆盖率仍偏低，需要随功能补充测试逐步提高；不应把基线通过宣传为
全功能已验证。修改代码应增加能验证行为的测试，并逐步提高门槛。不要为了
通过 CI 排除业务文件、吞掉测试错误或继续调低最低值。


## Python 3.12 coverage collection

CI runs `python scripts/run_unit_tests.py tests/ --cov=app` from `backend/`.
The wrapper preloads only jieba on Python 3.12 before coverage monitoring begins,
because its generated probability-table dictionary can stall collection under
PEP 669 instrumentation. Application modules are still imported under coverage;
the measured source and coverage threshold remain unchanged. Python 3.13 can
run pytest directly.
