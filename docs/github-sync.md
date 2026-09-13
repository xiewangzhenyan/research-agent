# GitHub 代码同步

项目：**Research Agent｜LSPRAI 科研知识库与 AI 助手**。公开仓库：
[xiewangzhenyan/research-agent](https://github.com/xiewangzhenyan/research-agent)。

默认采用批量交付：平时在本地累计修改、完成相关测试，到完整功能阶段或明确要求
发布时，再统一推送 GitHub、构建镜像并部署。不要每完成一个小改动就走一遍发布流程。
本地可按需要保留检查点提交；本地修改、提交、远端同步和线上部署是不同状态。

## 配置当前克隆

需要 Python 3、Git，以及对 `origin` 的推送权限。凭据由 Git/SSH/GitHub CLI
管理，不写入代码或远端 URL。

```bash
python3 scripts/git_sync.py install
git config --local researchAgent.autoPush false
```

安装只作用于当前克隆，保留已有的 `pre-commit` 校验。如果已有其他
`post-commit` / `pre-push` 钩子，会停止安装并保留原文件，需要手动整合。
若后续使用 Husky 或修改 `core.hooksPath`，重新执行上面两条命令。现有安装器会
打开自动推送，因此必须紧接着关闭；上传前的安全审查钩子仍保留。

## 本地开发与批量发布

日常开发只需检查改动并运行相关验证，可按需要提交本地检查点：

```bash
git diff
git add <本轮确认的文件>
git diff --cached --check
git commit -m "说明本次修改"
```

自动推送关闭后，提交只留在本地。发布时汇总这批功能、审阅累计改动并完成回归，
再显式上传：

```bash
python3 scripts/git_sync.py check
git push origin main
```

推送仍经过 `pre-push` 安全检查。推送不触发服务器自动部署；批次通过检查后，
按部署流程只构建、更新相关服务。记录哪些修改已同步、哪些已经上线。

推送前检查所有待上传的提交版本：忽略规则保护的文件、超过 10 MiB 的文件、
软链接/嵌套仓库、常见凭据格式及与本地环境配置匹配的秘密值会阻止推送。
即使敏感内容在后续提交中删除，仍会检查较早的待上传版本。检查只报告路径，
不输出凭据值；它是辅助检查，不能替代人工审阅。

`.env`、数据库、用户上传、下载模型、日志及本地验收记录保持在忽略列表中。
检查不会阻止本地提交；被拦截的提交应在公开上传前修正。

网络失败、60 秒超时或远端分支冲突时，保留本地提交并报告失败；不会强制推送、
自动合并或覆盖远端。处理原因后重试：

```bash
git push origin main
```

远端地址变更后，需要检查目标并重新安装钩子，同时保持自动推送关闭。
`python3 scripts/git_sync.py push` 是自动推送辅助程序，关闭自动推送时会直接跳过，
不能将它的成功退出当作已上传。以前的单次跳过方式仍可使用：

```bash
RESEARCH_AGENT_SKIP_PUSH=1 git commit -m "暂存本地工作"
```

当前克隆应保持以下配置：

```bash
git config --local researchAgent.autoPush false
```

仅当项目所有者明确改变交付偏好时，才可将该配置改为 `true` 恢复提交后自动推送。

## 验证

```bash
python3 scripts/git_sync.py check
python3 -m unittest discover -s scripts/tests -v
```

同步测试使用临时目录中的本地裸仓库，不连接 GitHub 或生产服务。
