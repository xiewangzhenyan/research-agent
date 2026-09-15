# 独立 Python 与 MCP 执行节点

控制面部署于独立 runsc 节点。Python 与 MCP 使用分别固定的镜像 ID 和独立就绪检查；源码和模拟测试不能代替目标节点实机验收。

本服务只能部署到独立执行服务器，不加入业务数据库、Redis 或模型服务所在网络。只有 manager 持有该节点的 Docker socket；API、任务 worker 和代码容器均不能获取 Docker 调度权限。不要把此 compose 合并到业务服务器的 production compose。

## 部署与配置

1. 在独立 Linux 节点安装 Docker 与兼容该架构的 gVisor/runsc，按官方说明注册 Docker runtime。官方文档：https://gvisor.dev/docs/user_guide/install/ 。先验证该节点可以使用 `--runtime=runsc` 运行可信测试程序。
2. 构建固定 runner：`docker build -t agent-python:1 -f Dockerfile.runner .`。预装 Python 标准库、NumPy 2.2.6、pandas 2.3.3、Matplotlib 3.10.8，不允许运行时安装包。
3. 使用 `docker image inspect agent-python:1 --format '{{.Id}}'` 获取本地不可变 image ID，写入该节点的 `SANDBOX_IMAGE`。生成至少 32 字符的独立随机 `SANDBOX_TOKEN`，保存到权限为 0600 的环境文件，不复用业务密钥。
4. 配置下方独立 watchdog，再执行 `docker compose --env-file .env -f compose.yml up -d --build`。服务只监听本机端口 38006。
5. 使用受控 HTTPS 反向代理或安全隧道连接执行节点，不开放 Docker TCP API。业务配置 `SANDBOX_URL`、`SANDBOX_TOKEN`、`SANDBOX_IMAGE_ID`（与节点镜像 ID 一致）。默认 `SANDBOX_ALLOW_PUBLIC=false`，仅管理员可在节点就绪时显式授权 Python。
6. 带 Bearer 调用 `/health`。健康检查先校验 runsc 与固定镜像，再在隔离容器内执行可信 UID、runner 文件与数据分析依赖自检；失败返回脱敏 503，不回退 runc。健康结果短暂缓存，不能代替节点的完整隔离验收。
7. 先完成管理员端真实执行、超时、取消、断网、内存、进程数、只读根目录、跨任务与产物清理测试。满足独立节点条件后，才由部署配置开放普通账号。此开关不是自动发现独立宿主机的证明。

不要在有活动任务时更换控制节点 URL、凭据或镜像 ID；先停接新计算任务并完成取消/排空。当前没有支持跨控制节点迁移活动执行的路由注册中心。

## 独立 watchdog

manager 自己不可用时，仍须回收执行进程。将 `watchdog.py` 放在执行节点受 root 管理的只读目录（例如 `/opt/agent-sandbox/watchdog.py`），安装 systemd service/timer：

```ini
# /etc/systemd/system/agent-sandbox-watchdog.service
[Unit]
Description=Reap expired agent code containers
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /opt/agent-sandbox/watchdog.py
```

```ini
# /etc/systemd/system/agent-sandbox-watchdog.timer
[Unit]
Description=Run sandbox cleanup independently of its manager
[Timer]
OnBootSec=15s
OnUnitActiveSec=15s
[Install]
WantedBy=timers.target
```

执行 `systemctl daemon-reload`、`systemctl enable --now agent-sandbox-watchdog.timer`。回收带 `agent.sandbox=v1` 标签、创建超过 120 秒的容器；另按精确名称及标签回收过期 `v2-input` 命名卷，卷仍被容器使用时不强制删除。完整节点验收必须包括杀死 manager 后仍能回收容器。正常执行限时 30 秒（包括管理器排队）；manager 故障时由独立 watchdog 兜底，不能声称这种情况下仍严格 30 秒停止。

## 行为契约

- 单次独立工作区；无跨调用 Python 内存/文件状态。协议 1 保留标准库和 stdout/stderr 接口。协议 2 支持只读输入与文件产物（见下）。
- 非 root、runsc、禁网、只读根、无 capabilities/no-new-privileges，无宿主机挂载和业务凭据。
- 1 CPU、协议 1 为 256 MiB / 协议 2 为 512 MiB 内存，容器进程上限 64（节点默认并发 1）且禁止额外 swap、16 MiB 工作区和 8 MiB 临时目录。日志最多返回 32 KiB，达到上限终止并标记截断。
- 管理器最多同时执行 2 项、排队和执行共 16 项、最多保留 2000 项记录；已存输入与结果超过 256 MiB 后拒绝新提交（并发在途请求最多额外约 112 MiB，SQLite/WAL 及文件系统额外开销仍须磁盘配额控制）；记录保留 8 天。容量到限拒绝新请求。生产为状态卷配置独立磁盘配额和监控。
- 执行 ID 由业务服务根据 Run ID、协议版本、代码与输入摘要生成。相同任务内相同代码及输入复用结果；不同任务不会共用 ID。idempotency 参数变更返回 409。
- SQLite 先记录执行，再创建确定性命名容器。控制面重启后检查同名容器，不重新启动已经执行过的代码；已登记 running 但容器丢失时返回失败，拒绝盲目重做。
- `/runs/{id}` 取消先保存 tombstone，再停止实际容器，确认进程退出后才响应 stopped。无法确认停止时返回 503；业务任务保持“正在取消”，持续对账。
- 管理器每 5 秒恢复未完成执行、清理终态容器和过期记录。原始代码在终态回写时从控制面清除；任务审计事件仍按账号保存代码和输出。

代码与输出是不可信数据。不得直接在宿主机执行，不得作为 HTML 渲染，不应将其内容拼入宿主机 shell 命令。

## 测试

`PYTHONPATH=.. pytest tests`（在本目录执行，需安装 pytest/httpx/FastAPI）。单元测试使用模拟 Docker Engine，验证配置边界、拒绝降级、幂等、取消确认、崩溃对账和日志上限。真实 gVisor 运行与逃逸面测试必须在目标节点单独完成，模拟测试不替代这一验收。


## 文件执行协议 2

`POST /executions` 增加 `protocol: 2` 和 `inputs: [{name, content_base64, sha256}]`。最多 5 个输入、解码后合计 5 MiB，整个 HTTP 请求限制 8 MiB，独立节点的 HTTPS 反向代理须允许至少 8 MiB 请求体并关闭代理层响应缓存。业务端仅接受当前账号已上传的 CSV/JSON/TXT/MD/PNG/JPEG，提交时记录名称、大小与 SHA-256，执行前再次校验所有权和内容。任务 worker 对业务上传目录只有只读访问。

管理器通过固定的 staging 容器将有界 tar 写入专属命名卷，文件权限 0444。该容器仅执行受控的目录权限初始化与等待命令，不执行用户代码。执行容器将该卷只读挂载在 `/inputs`；不会得到业务目录、密钥或 Docker socket。代码只在 `/work` 与 `/tmp` 限额 tmpfs 中写入。`/work/outputs` 下最多收集 10 个平级 CSV/JSON/TXT/MD/PNG/JPEG/PDF；单个 2 MiB，总计 4 MiB。文件名支持中文；拒绝路径穿越、链接、稀疏文件、设备、目录嵌套、重复名及不支持的类型。归档不解压到宿主机。

固定 supervisor 执行代码后保持 tmpfs 存活，管理器冻结整个容器后重新校验完成标记、读取产物，再停止全部进程。supervisor 和完成标记都不是可信安全证明；整个容器的输出始终视为不可信。失败、超时、取消、日志超限或产物校验失败均不发布产物。停止确认失败时保持待对账状态，不伪报终态。

业务后端再次校验 MIME、大小、Base64 和摘要；成功产物原子写入 PostgreSQL BYTEA。事件及模型工具结果仅含元数据，不传二进制。回写需通过账号锁、任务状态及 worker attempt 核验；相同执行、名称和摘要使用相同产物 ID。单任务 20 MiB/200 文件，单账号 100 MiB；任务结束后用户可删除旧产物。

`GET /api/v1/runs/{run_id}/artifacts` 列出元数据；`GET/DELETE /api/v1/runs/{run_id}/artifacts/{artifact_id}` 下载/删除。全部需要当前账号认证，下载为 attachment，设置 nosniff、无缓存和限制性 CSP。前端只提供下载，不直接展示主动内容。

### 当前验证边界

模拟控制面测试与独立 PostgreSQL 集成测试分别验证文件协议和业务边界；这些测试不能替代目标节点的文件执行验收。Stdio MCP 的握手与隔离验收也不能替代 Python 文件协议 2 的验收。

独立 runsc 节点的实际计算、只读卷写入拒绝、冻结 tmpfs 后产物采集、资源超限和杀死 manager 后的 watchdog 回收，仍须在执行节点验收；不满足就绪校验时保持关闭，不退回业务主机 runc 执行。文件版本节点迁移前先排空旧任务，不混用旧 runner 镜像。

## Stdio MCP 部署

构建 `docker build -t agent-mcp:1 -f Dockerfile.mcp .`，将镜像 ID 写入节点
`SANDBOX_MCP_IMAGE` 和业务端 `SANDBOX_MCP_IMAGE_ID`，然后升级 manager。
已提供 `agent-sandbox-watchdog.service` 与 `.timer`，安装到 systemd 后启用 timer；
默认脚本路径为 `/opt/agent-sandbox/source/watchdog.py`。

`GET /mcp/health` 验证固定镜像并运行真实 MCP 握手；`POST /mcp/exchange` 接受
run_id、command、args、env、operation、name、arguments，统一 Bearer 认证。
只支持镜像中已有的 Python 与 MCP SDK，不支持联网、动态安装或跨调用工作区。
Stdio 和代码运行共享 semaphore；忙碌返回 429，异常返回脱敏错误。环境变量不写入
SQLite 或审计日志，临时容器删除后清除 Docker 元数据。
详细配额、生命周期和业务权限见 [能力管理](../docs/user-capabilities.md#隔离-stdio-mcp)。
