"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Plus, Trash2, Download, FileText } from "lucide-react";
import { Button, Input, Switch, Textarea } from "@/components/ui";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useProject } from "@/components/projects/project-provider";
import { useAuthStore } from "@/stores";
import { isAppAdmin } from "@/lib/utils";
import { apiClient } from "@/lib/api-client";
import {
  capabilityError,
  downloadSkill,
  entryTemplate,
  statusLabel,
  type Availability,
  type Capability,
  type CapabilityKind,
  type MCPConfig,
  type SkillConfig,
  type Version,
} from "@/lib/capabilities";

const field = "border-input bg-background h-10 w-full rounded-lg border px-3 text-sm";
const emptyMCP: MCPConfig = {
  transport: "streamable-http",
  url: "",
  command: "",
  args: [],
  enabled_tools: [],
  auto_approved_tools: [],
};
export function CapabilityEditor({
  kind,
  initial,
  availability,
  onClose,
  onChanged,
}: {
  kind: CapabilityKind;
  initial: Capability | null;
  availability?: Availability;
  onClose: () => void;
  onChanged: () => Promise<void>;
}) {
  const isSkill = kind === "skills";
  const user = useAuthStore((s) => s.user);
  const project = useProject();
  const [asset, setAsset] = useState(initial);
  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [scope, setScope] = useState<Capability["scope"]>(initial?.scope ?? "personal");
  const [enabled, setEnabled] = useState(initial?.enabled ?? true);
  const [tags, setTags] = useState(initial?.tags.join(", ") ?? "");
  const [config, setConfig] = useState<MCPConfig>(
    !isSkill && initial ? (initial.config as MCPConfig) : emptyMCP,
  );
  const [args, setArgs] = useState(config.args.join("\n"));
  const [secrets, setSecrets] = useState<{ key: string; value: string }[]>([]);
  const [replaceSecrets, setReplaceSecrets] = useState(false);
  const [entry, setEntry] = useState(
    isSkill && initial ? ((initial.config as SkillConfig).entry ?? "") : entryTemplate,
  );
  const [tab, setTab] = useState("config");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filePath, setFilePath] = useState("");
  const [fileContent, setFileContent] = useState("");
  const [dirty, setDirty] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const editable = !asset || asset.can_edit;
  const versions = useQuery({
    queryKey: ["capabilities", user?.id, "versions", asset?.id, asset?.revision],
    queryFn: () => apiClient.get<Version[]>(`/capabilities/assets/${asset!.id}/versions`),
    enabled: isSkill && !!asset && tab === "versions",
  });
  function adopt(value: Capability) {
    setAsset(value);
    setName(value.name);
    setDescription(value.description);
    setEnabled(value.enabled);
    setScope(value.scope);
    setTags(value.tags.join(", "));
    if (isSkill) setEntry((value.config as SkillConfig).entry ?? "");
    else {
      setConfig(value.config as MCPConfig);
      setArgs((value.config as MCPConfig).args.join("\n"));
    }
    setSecrets([]);
    setReplaceSecrets(false);
    setDirty(false);
  }
  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
      await onChanged();
    } catch (e) {
      setError(capabilityError(e));
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!name.trim()) throw new Error("请填写名称");
    const headers: Record<string, string> = {};
    for (const row of secrets) {
      if (!row.key.trim() || !row.value || row.key.trim() in headers)
        throw new Error("凭据名称和值不能为空，名称不能重复");
      headers[row.key.trim()] = row.value;
    }
    const data = {
      name,
      description,
      scope,
      enabled,
      tags: tags
        .split(/[,，]/)
        .map((v) => v.trim())
        .filter(Boolean),
      revision: asset?.revision,
      config: isSkill ? { entry } : { ...config, args: args.split("\n").filter(Boolean) },
      ...(!isSkill && replaceSecrets ? { secrets: headers } : {}),
    };
    const value = asset
      ? await apiClient.put<Capability>(`/capabilities/assets/${asset.id}`, data)
      : await apiClient.post<Capability>(`/capabilities/${kind}`, data);
    adopt(value);
    return value;
  }
  const tools = asset?.catalog.tools ?? [];
  function selectTool(tool: string, on: boolean, auto = false) {
    setDirty(true);
    setConfig((c) =>
      auto
        ? {
            ...c,
            auto_approved_tools: on
              ? [...c.auto_approved_tools, tool]
              : c.auto_approved_tools.filter((t) => t !== tool),
          }
        : {
            ...c,
            enabled_tools: on
              ? [...c.enabled_tools, tool]
              : c.enabled_tools.filter((t) => t !== tool),
            auto_approved_tools: on
              ? c.auto_approved_tools
              : c.auto_approved_tools.filter((t) => t !== tool),
          },
    );
  }
  const files = isSkill && asset ? (asset.config as SkillConfig).files : [];
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open && !busy) {
          if (dirty) setConfirmClose(true);
          else onClose();
        }
      }}
    >
      <DialogContent className="flex max-h-[92dvh] w-[calc(100vw-1.5rem)] max-w-4xl flex-col gap-0 overflow-hidden rounded-xl p-0 sm:max-w-4xl">
        <DialogHeader className="border-border border-b px-5 py-5 sm:px-7">
          <DialogTitle>{asset ? asset.name : isSkill ? "创建技能" : "添加 MCP 连接"}</DialogTitle>
          <DialogDescription>
            {asset
              ? statusLabel(asset)
              : isSkill
                ? "定义助手的做事方法，发布后可在项目中使用。"
                : "填写连接信息，测试成功后选择要开放的工具。"}
          </DialogDescription>
        </DialogHeader>
        <div
          className="border-border flex gap-1 overflow-x-auto border-b px-5 py-2"
          role="tablist"
          aria-label="能力设置"
        >
          {(isSkill
            ? [
                ["config", "技能内容"],
                ["files", "参考文件"],
                ["versions", "发布版本"],
              ]
            : [
                ["config", "连接配置"],
                ["tools", "工具权限"],
              ]
          ).map(([value, label]) => (
            <button
              type="button"
              role="tab"
              aria-selected={tab === value}
              key={value}
              onClick={() => {
                if (dirty && (tab === "files" || value === "files" || value === "versions")) {
                  setError("请先保存当前修改，再切换到文件或版本管理");
                  return;
                }
                setTab(value!);
              }}
              className={`min-h-10 rounded-lg px-4 text-sm whitespace-nowrap ${tab === value ? "bg-muted font-medium" : "text-muted-foreground"}`}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto px-5 py-5 sm:px-7" role="tabpanel">
          {error && (
            <p role="alert" className="text-destructive bg-destructive/5 rounded-lg p-3 text-sm">
              {error}
            </p>
          )}
          {notice && (
            <p role="status" className="bg-muted rounded-lg p-3 text-sm">
              {notice}
            </p>
          )}
          {confirmClose && (
            <div className="bg-muted flex flex-wrap items-center gap-3 rounded-lg p-3 text-sm">
              <span>有未保存的修改。</span>
              <Button variant="outline" size="sm" onClick={() => setConfirmClose(false)}>
                继续编辑
              </Button>
              <Button variant="destructive" size="sm" onClick={onClose}>
                放弃修改并关闭
              </Button>
            </div>
          )}
          {tab === "config" && (
            <fieldset
              disabled={busy || !editable}
              onChange={() => setDirty(true)}
              className="space-y-5"
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <label htmlFor="cap-field-0" className="space-y-2 text-sm">
                  <span>名称</span>
                  <Input
                    id="cap-field-0"
                    value={name}
                    maxLength={100}
                    placeholder={isSkill ? "例如：文献对比与证据整理" : "例如：文献检索服务"}
                    onChange={(e) => setName(e.target.value)}
                  />
                </label>
                <label className="space-y-2 text-sm">
                  <span>可用范围</span>
                  <select
                    className={field}
                    value={scope}
                    onChange={(e) => setScope(e.target.value as Capability["scope"])}
                  >
                    <option value="personal">我的账号 · 跨项目复用</option>
                    <option value="project" disabled={!project?.project}>
                      当前项目
                    </option>
                    {isAppAdmin(user) && <option value="system">系统级 · 所有账号可绑定</option>}
                  </select>
                </label>
              </div>
              <label htmlFor="cap-field-1" className="block space-y-2 text-sm">
                <span>说明</span>
                <Input
                  id="cap-field-1"
                  value={description}
                  maxLength={1200}
                  placeholder="什么情况下使用，能完成哪些事情"
                  onChange={(e) => setDescription(e.target.value)}
                />
              </label>
              <div className="flex flex-wrap items-center gap-4">
                <label htmlFor="cap-field-2" className="min-w-48 flex-1 space-y-2 text-sm">
                  <span>标签</span>
                  <Input
                    id="cap-field-2"
                    value={tags}
                    placeholder="多个标签用逗号分隔"
                    onChange={(e) => setTags(e.target.value)}
                  />
                </label>
                <label className="flex items-center gap-2 pt-6 text-sm">
                  <Switch
                    checked={enabled}
                    onCheckedChange={(v) => {
                      setEnabled(v);
                      setDirty(true);
                    }}
                  />
                  启用能力
                </label>
              </div>
              {isSkill ? (
                <label htmlFor="cap-field-3" className="block space-y-2 text-sm">
                  <span>SKILL.md</span>
                  <Textarea
                    id="cap-field-3"
                    aria-label="技能 Markdown 内容"
                    className="min-h-80 resize-y font-mono text-xs leading-6"
                    value={entry}
                    onChange={(e) => setEntry(e.target.value)}
                    spellCheck={false}
                  />
                  <span className="text-muted-foreground block text-xs leading-6">
                    开头保留 name 与 description。name
                    使用小写英文、数字或短横线；正文写步骤、约束与示例。辅助资料可放入 references/
                    与 templates/。
                  </span>
                </label>
              ) : (
                <>
                  <label className="block space-y-2 text-sm">
                    <span>连接方式</span>
                    <select
                      className={field}
                      value={config.transport}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          transport: e.target.value as MCPConfig["transport"],
                        })
                      }
                    >
                      <option value="streamable-http">HTTP · 推荐</option>
                      <option value="sse">SSE · 兼容旧服务</option>
                      <option value="stdio">Stdio · 隔离节点命令</option>
                    </select>
                  </label>
                  {config.transport === "stdio" ? (
                    <>
                      <p role="status" className="bg-muted rounded-lg p-3 text-sm leading-6">
                        {availability?.stdio_ready
                          ? "隔离节点已就绪：支持 Python 和 MCP SDK，单次最长 28 秒，返回最多 30 KB。每次使用全新目录，无网络、不保留文件；不支持 npx/uvx 或在线安装。需要联网请使用 HTTP/SSE。"
                          : "隔离 MCP 执行节点尚未接通。可以保存配置，暂不能测试或调用；不会在业务服务器启动命令。"}
                      </p>
                      <label htmlFor="cap-field-4" className="block space-y-2 text-sm">
                        <span>启动命令</span>
                        <Input
                          id="cap-field-4"
                          value={config.command}
                          placeholder="例如：python"
                          onChange={(e) => setConfig({ ...config, command: e.target.value })}
                        />
                      </label>
                      <label htmlFor="cap-field-5" className="block space-y-2 text-sm">
                        <span>启动参数 · 每行一个</span>
                        <Textarea
                          id="cap-field-5"
                          value={args}
                          onChange={(e) => setArgs(e.target.value)}
                          placeholder="-m&#10;your_mcp_server"
                        />
                      </label>
                    </>
                  ) : (
                    <label htmlFor="cap-field-6" className="block space-y-2 text-sm">
                      <span>服务地址</span>
                      <Input
                        id="cap-field-6"
                        type="url"
                        value={config.url}
                        placeholder="https://example.com/mcp"
                        onChange={(e) => setConfig({ ...config, url: e.target.value })}
                      />
                      <span className="text-muted-foreground text-xs">
                        填写公网 HTTP(S)
                        地址；认证信息请放在下方请求头中，暂不支持含查询参数的地址。
                      </span>
                    </label>
                  )}
                  <div className="border-border space-y-3 rounded-xl border p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <h3 className="text-sm font-medium">
                        {config.transport === "stdio" ? "环境变量" : "认证与请求头"}
                      </h3>
                      <span className="text-muted-foreground text-xs">
                        {asset?.has_credentials
                          ? "已加密保存 · 留空保留原凭据"
                          : "可选 · 仅写入，不回显"}
                      </span>
                    </div>
                    {!availability?.credentials_ready && (
                      <p className="text-muted-foreground text-xs leading-6">
                        管理员尚未配置凭据加密密钥。无认证的远程服务仍可连接；保存凭据前需完成配置。
                      </p>
                    )}
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={replaceSecrets}
                        onChange={(e) => setReplaceSecrets(e.target.checked)}
                      />
                      替换凭据（空列表表示清空）
                    </label>
                    {replaceSecrets && (
                      <>
                        {secrets.map((row, i) => (
                          <div key={i} className="flex gap-2">
                            <Input
                              aria-label={`凭据名称 ${i + 1}`}
                              placeholder={
                                config.transport === "stdio" ? "API_KEY" : "Authorization"
                              }
                              value={row.key}
                              onChange={(e) =>
                                setSecrets((v) =>
                                  v.map((r, j) => (j === i ? { ...r, key: e.target.value } : r)),
                                )
                              }
                            />
                            <Input
                              type="password"
                              autoComplete="new-password"
                              aria-label={`凭据内容 ${i + 1}`}
                              placeholder="Bearer …"
                              value={row.value}
                              onChange={(e) =>
                                setSecrets((v) =>
                                  v.map((r, j) => (j === i ? { ...r, value: e.target.value } : r)),
                                )
                              }
                            />
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              aria-label={`移除凭据 ${i + 1}`}
                              onClick={() => setSecrets((v) => v.filter((_, j) => j !== i))}
                            >
                              <Trash2 size={15} />
                            </Button>
                          </div>
                        ))}
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setSecrets((v) => [...v, { key: "", value: "" }])}
                        >
                          <Plus size={14} />
                          添加一项
                        </Button>
                      </>
                    )}
                  </div>
                  {asset?.last_tested && (
                    <p className="text-muted-foreground text-xs leading-6">
                      上次测试：{new Date(asset.last_tested).toLocaleString("zh-CN")} ·{" "}
                      {asset.status_message}
                    </p>
                  )}
                </>
              )}
            </fieldset>
          )}
          {tab === "tools" && (
            <div className="space-y-4">
              <p className="text-muted-foreground text-sm leading-6">
                先测试连接，再勾选工具。默认每次调用都会展示参数并等待确认；只有你明确勾选的工具可自动调用。
              </p>
              {tools.length === 0 ? (
                <p className="bg-muted rounded-xl p-6 text-sm">
                  {asset?.status === "ready"
                    ? "服务未提供工具，可能仅提供资源或提示模板。"
                    : "请先保存配置并测试连接。"}
                </p>
              ) : (
                tools.map((tool) => (
                  <div key={tool.name} className="border-border space-y-3 rounded-xl border p-4">
                    <label className="flex items-center gap-3 text-sm font-medium">
                      <input
                        type="checkbox"
                        disabled={!editable || busy}
                        checked={config.enabled_tools.includes(tool.name)}
                        onChange={(e) => selectTool(tool.name, e.target.checked)}
                      />
                      <span className="break-all">{tool.name}</span>
                    </label>
                    <p className="text-muted-foreground text-xs leading-6">
                      {tool.description || "服务未提供说明"}
                    </p>
                    <label className="flex items-center gap-2 text-xs">
                      <input
                        type="checkbox"
                        disabled={!editable || busy || !config.enabled_tools.includes(tool.name)}
                        checked={config.auto_approved_tools.includes(tool.name)}
                        onChange={(e) => selectTool(tool.name, e.target.checked, true)}
                      />
                      允许自动调用，无需逐次确认
                    </label>
                    <details>
                      <summary className="text-muted-foreground cursor-pointer text-xs">
                        参数结构
                      </summary>
                      <pre className="bg-muted mt-2 max-h-48 overflow-auto rounded-lg p-3 text-xs">
                        {JSON.stringify(tool.inputSchema, null, 2)}
                      </pre>
                    </details>
                  </div>
                ))
              )}
              <p className="text-muted-foreground text-xs">
                发现资源 {asset?.catalog.resources?.length ?? 0} 项、提示模板{" "}
                {asset?.catalog.prompts?.length ?? 0} 项。本版仅调用已勾选的工具。
              </p>
            </div>
          )}
          {tab === "files" && (
            <div className="space-y-4">
              {!asset ? (
                <p className="text-muted-foreground text-sm">
                  保存技能后可添加参考文件；也可在列表页导入完整技能包。
                </p>
              ) : (
                <>
                  <p className="text-muted-foreground text-xs leading-6">
                    更改只写入草稿，下次发布后生效。二进制模板保留在技能包中，可导出下载。
                  </p>
                  <div className="grid gap-4 sm:grid-cols-[180px_1fr]">
                    <nav aria-label="技能文件" className="space-y-1">
                      {files
                        .filter((f) => f.path !== "SKILL.md")
                        .map((f) => (
                          <button
                            type="button"
                            key={f.path}
                            disabled={busy}
                            className={`flex w-full items-center gap-2 rounded-lg p-2 text-left text-xs ${filePath === f.path ? "bg-muted" : ""}`}
                            onClick={() =>
                              void perform(async () => {
                                if (dirty) throw new Error("请先保存当前修改后再切换文件");
                                const result = await apiClient.get<{ content: string }>(
                                  `/capabilities/assets/${asset.id}/file`,
                                  { params: { path: f.path } },
                                );
                                setFilePath(f.path);
                                setFileContent(result.content);
                              })
                            }
                          >
                            <FileText size={14} className="shrink-0" />
                            <span className="break-all">{f.path}</span>
                          </button>
                        ))}
                    </nav>
                    <div className="space-y-3">
                      <label htmlFor="cap-field-7" className="block space-y-2 text-sm">
                        <span>文件路径</span>
                        <Input
                          id="cap-field-7"
                          disabled={!editable}
                          placeholder="references/checklist.md"
                          value={filePath}
                          onChange={(e) => {
                            setFilePath(e.target.value);
                            setDirty(true);
                          }}
                        />
                      </label>
                      <Textarea
                        aria-label="参考文件内容"
                        disabled={!editable}
                        className="min-h-56 font-mono text-xs"
                        value={fileContent}
                        onChange={(e) => {
                          setFileContent(e.target.value);
                          setDirty(true);
                        }}
                      />
                      <div className="flex flex-wrap gap-2">
                        <Button
                          variant="outline"
                          disabled={busy || !editable || !filePath || filePath === "SKILL.md"}
                          onClick={() =>
                            void perform(async () => {
                              const value = await apiClient.put<Capability>(
                                `/capabilities/assets/${asset.id}/file`,
                                { revision: asset.revision, path: filePath, content: fileContent },
                              );
                              adopt(value);
                              setNotice("参考文件已保存到草稿");
                            })
                          }
                        >
                          保存参考文件
                        </Button>
                        <Button
                          variant="ghost"
                          disabled={
                            busy ||
                            !editable ||
                            !files.some((f) => f.path === filePath) ||
                            filePath === "SKILL.md"
                          }
                          onClick={() =>
                            void perform(async () => {
                              adopt(
                                await apiClient.delete<Capability>(
                                  `/capabilities/assets/${asset.id}/file`,
                                  { params: { revision: String(asset.revision), path: filePath } },
                                ),
                              );
                              setFilePath("");
                              setFileContent("");
                            })
                          }
                        >
                          移除文件
                        </Button>
                      </div>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
          {tab === "versions" && (
            <div className="space-y-4">
              <p className="text-muted-foreground text-sm leading-6">
                发布版本不可直接改写。恢复历史版本会生成当前草稿，重新发布后才影响新对话。
              </p>
              {versions.isError && <p role="alert">版本加载失败，请稍后重试。</p>}
              {!versions.data?.length && (
                <p className="bg-muted rounded-xl p-6 text-sm">暂无发布版本</p>
              )}
              {versions.data?.map((v) => (
                <div
                  key={v.version}
                  className="border-border flex items-center justify-between gap-4 rounded-xl border p-4"
                >
                  <div>
                    <p className="text-sm font-medium">版本 {v.version}</p>
                    <p className="text-muted-foreground mt-1 text-xs">
                      {new Date(v.created_at).toLocaleString("zh-CN")}
                    </p>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy || !editable || dirty}
                    onClick={() =>
                      void perform(async () => {
                        adopt(
                          await apiClient.post<Capability>(
                            `/capabilities/assets/${asset!.id}/restore`,
                            { revision: asset!.revision, version: v.version },
                          ),
                        );
                        setTab("config");
                        setNotice("已恢复为草稿，请检查后发布");
                      })
                    }
                  >
                    恢复到草稿
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
        <footer className="border-border flex flex-wrap items-center justify-between gap-2 border-t px-5 py-4 sm:px-7">
          <div>
            {isSkill && asset && (
              <Button
                variant="ghost"
                disabled={busy}
                onClick={() => void perform(() => downloadSkill(asset.id))}
              >
                <Download size={15} />
                导出草稿
              </Button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                if (dirty) setConfirmClose(true);
                else onClose();
              }}
            >
              关闭
            </Button>
            {editable && (
              <>
                <Button
                  variant="outline"
                  disabled={busy || tab === "files"}
                  onClick={() =>
                    void perform(async () => {
                      await save();
                      setNotice(isSkill ? "草稿已保存" : "配置已保存");
                    })
                  }
                >
                  {busy ? "处理中…" : isSkill ? "保存草稿" : "保存配置"}
                </Button>
                <Button
                  disabled={
                    busy ||
                    tab === "files" ||
                    (!isSkill && config.transport === "stdio" && !availability?.stdio_ready)
                  }
                  onClick={() =>
                    void perform(async () => {
                      const current = await save();
                      const result = await apiClient.post<Capability>(
                        `/capabilities/assets/${current.id}/${isSkill ? "publish" : "test"}`,
                        { revision: current.revision },
                      );
                      adopt(result);
                      if (!isSkill) setTab("tools");
                      setNotice(
                        isSkill ? "已发布，请在列表中分配给当前助手" : result.status_message,
                      );
                    })
                  }
                >
                  {isSkill ? "保存并发布" : "保存并测试"}
                </Button>
              </>
            )}
          </div>
        </footer>
      </DialogContent>
    </Dialog>
  );
}
