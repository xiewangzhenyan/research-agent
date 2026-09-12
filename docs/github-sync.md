# GitHub 代码同步

项目：**Research Agent｜LSPRAI 科研知识库与 AI 助手**。公开仓库：
[xiewangzhenyan/research-agent](https://github.com/xiewangzhenyan/research-agent)。

## 配置当前克隆

需要 Python 3、Git，以及对 `origin` 的推送权限。凭据由 Git/SSH/GitHub CLI
管理，不写入代码或远端 URL。

```bash
python3 scripts/git_sync.py install
```

安装只作用于当前克隆，保留已有的 `pre-commit` 校验。如果已有其他
`post-commit` / `pre-push` 钩子，会停止安装并保留原文件，需要手动整合。
若后续使用 Husky 或修改 `core.hooksPath`，重新执行安装命令。

## 每轮开发

先检查改动并运行与改动相关的验证，再提交具体文件：

```bash
git diff
git add <本轮确认的文件>
git diff --cached --check
git commit -m "说明本次修改"
```

提交成功后，钩子自动将当前分支推送到 `origin` 的同名分支。保存文件本身
不会自动提交，也不会推送其他分支或标签。此流程不触发服务器自动部署。

推送前检查所有待上传的提交版本：忽略规则保护的文件、超过 10 MiB 的文件、
软链接/嵌套仓库、常见凭据格式及与本地环境配置匹配的秘密值会阻止推送。
即使敏感内容在后续提交中删除，仍会检查较早的待上传版本。检查只报告路径，
不输出凭据值；它是辅助检查，不能替代人工审阅。

`.env`、数据库、用户上传、下载模型、日志及本地验收记录保持在忽略列表中。
检查不会阻止本地提交；被拦截的提交应在公开上传前修正。

网络失败、60 秒超时或远端分支冲突时，保留本地提交并报告失败；不会强制推送、
自动合并或覆盖远端。处理原因后重试：

```bash
python3 scripts/git_sync.py push
```

远端地址变更后，需要检查目标并重新安装钩子。暂停单次自动推送：

```bash
RESEARCH_AGENT_SKIP_PUSH=1 git commit -m "暂存本地工作"
```

关闭/恢复当前克隆的自动推送：

```bash
git config --local researchAgent.autoPush false
git config --local researchAgent.autoPush true
```

## 验证

```bash
python3 scripts/git_sync.py check
python3 -m unittest discover -s scripts/tests -v
```

同步测试使用临时目录中的本地裸仓库，不连接 GitHub 或生产服务。
