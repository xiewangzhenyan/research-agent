# 开发与发布期间的磁盘维护

这台业务主机运行多个项目。清理应在开发期间持续进行，无需等到开发完成。

## 保留范围

- 保留所有容器引用的镜像，包含停止的容器。不能根据标签新旧判断是否在用：
  API、任务 worker、入库 worker 和重排服务可能使用不同版本。
- `agent_backend` 和 `agent-frontend` 各保留最新两个未被容器引用的回滚镜像；
  当前 `dev` / `latest`、没有回滚标记的候选镜像也保留。
- 其他项目镜像、数据库、Docker 数据卷、上传文件、向量/模型缓存及
  `/home/upgrade-backups` 中的源代码和数据库备份不属于镜像清理范围。
- 同一镜像的多个标签不会重复占用整份空间，必须按镜像 ID 去重。
  Docker 镜像、构建缓存会共享层，不能把所有逻辑大小直接相加作为可释放空间。

## 发布后清理

先完成服务健康检查，再执行以下流程。不要和构建、发布、打回滚标签同时运行。

```bash
cd /home/agent
python3 infrastructure/maintenance/prune_images.py --plan /tmp/agent-image-cleanup-plan.json
# 检查输出中的 protected 和 remove，再应用同一个计划。
python3 infrastructure/maintenance/prune_images.py --plan /tmp/agent-image-cleanup-plan.json --apply
```

脚本只删除本项目两个仓库中明确带有 `rollback-*` / `before-*` 标记的过期版本，
同一版本附带的候选标签一并删除；如存在其他仓库引用则保留。应用时重新核对镜像
与容器引用，状态变化时停止，不使用强制删除。默认只生成计划。

旧发布记录提及的镜像标签可能已经按本策略清理，以最近清理计划和 Docker 实际
镜像列表为准。源代码/数据库备份仍保留；更早版本需要重新构建并重新验证兼容性，
不能直接恢复旧数据库覆盖后续业务数据。

## 构建与下载缓存

构建完成后可按需执行：

```bash
docker builder prune --force --filter until=24h --max-used-space 4GB
```

这是整台主机的可再生构建缓存清理，会使其他项目下一次构建也可能重新下载或
重新计算。保留最近 24 小时使用过的缓存，目标为 4 GB；在用、近期及共享记录
可能使实际占用仍高于该目标。不要使用 `docker system prune --volumes` 或
全主机 `docker image prune -a` 来清理本项目。

`npm cache clean --force` 和 `uv cache clean` 只在没有依赖安装任务且缓存明显
膨胀时运行，不作为每次开发的固定步骤。它们清理下载缓存，已安装的依赖仍保留，
下一次安装可能需要重新下载。模型缓存不是依赖下载缓存，不应混同清理。

## 构建方式

- 只构建有变化的服务；修改前端公开环境变量会使相应构建层自动失效，无需
  惯例性使用 `--no-cache`。
- 后端发布按 API、后台任务进程、重排服务分批更新并检查就绪状态，避免某个
  worker 停机等待拖延整个 API 启动。更新前检查运行中的任务，Celery 使用足够
  完成长任务的停止宽限期；Agent worker 使用 `SIGINT`，由 `asyncio.run` 取消
  协程并关闭检查点连接，未完成任务由持久化状态恢复。
- 后端用 `COPY --chown` 设置所有权，虚拟环境与源代码分层复制。不要对
  `/app` 再执行递归 `chown`，否则依赖树会在新镜像层中复制一遍。
- `.dockerignore` 排除宿主机虚拟环境、运行数据、模型缓存、环境配置和开发缓存。
- 本轮构建验证使用独立临时镜像，验收后删除。正常发布验证完成后及时清理旧候选
  镜像与过期回滚版本，避免一次功能修改长期保留多个构建中间版本。

## 检查与记录

```bash
df -h /
docker system df
docker builder du
python3 -m unittest discover -s infrastructure/maintenance -p 'test_*.py' -v
```

以根分区实际可用字节衡量最终收益，记录容器 ID、镜像 ID、启动时间和健康状态。
清理日志不得包含环境变量、密码或令牌。2026-09-12 的首次处理记录位于
`docs/releases/storage-20260912/`。
