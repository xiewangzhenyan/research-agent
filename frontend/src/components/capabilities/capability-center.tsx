"use client";
import { useRef, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Plug,
  Plus,
  Search,
  Upload,
  Pencil,
  Trash2,
  RefreshCw,
  ArrowUpRight,
} from "lucide-react";
import { Button, Input, Switch } from "@/components/ui";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useProject } from "@/components/projects/project-provider";
import { useAuthStore } from "@/stores";
import { apiClient } from "@/lib/api-client";
import {
  capabilityError,
  capabilityFetch,
  statusLabel,
  type Availability,
  type Bindings,
  type Capability,
  type CapabilityKind,
} from "@/lib/capabilities";
import { CapabilityEditor } from "./capability-editor";

export function CapabilityCenter({ kind }: { kind: CapabilityKind }) {
  const userId = useAuthStore((s) => s.user?.id);
  const project = useProject();
  return <Center key={`${userId}:${project?.project?.id ?? "default"}:${kind}`} kind={kind} />;
}
function Center({ kind }: { kind: CapabilityKind }) {
  const userId = useAuthStore((s) => s.user?.id);
  const project = useProject();
  const cache = useQueryClient();
  const key = ["capabilities", userId, project?.project?.id ?? "default"];
  const assets = useQuery({
    queryKey: [...key, kind],
    queryFn: () => apiClient.get<Capability[]>(`/capabilities/${kind}`),
    enabled: !!userId && !!project?.ready,
    staleTime: 30000,
  });
  const bindings = useQuery({
    queryKey: [...key, "bindings"],
    queryFn: () => apiClient.get<Bindings>("/capabilities/bindings"),
    enabled: !!userId && !!project?.ready,
    staleTime: 30000,
  });
  const availability = useQuery({
    queryKey: [...key, "availability"],
    queryFn: () => apiClient.get<Availability>("/capabilities/availability"),
    enabled: !!userId,
    staleTime: 60000,
  });
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState("all");
  const [editor, setEditor] = useState<Capability | "new" | null>(null);
  const [removing, setRemoving] = useState<Capability | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const upload = useRef<HTMLInputElement>(null);
  const directory = useRef<HTMLInputElement>(null);
  const refresh = async () => {
    await cache.invalidateQueries({ queryKey: key });
  };
  async function perform(action: () => Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await action();
      await refresh();
    } catch (e) {
      setError(capabilityError(e));
    } finally {
      setBusy(false);
    }
  }
  async function edit(asset: Capability) {
    await perform(async () =>
      setEditor(await apiClient.get<Capability>(`/capabilities/assets/${asset.id}`)),
    );
  }
  async function bind(asset: Capability, on: boolean) {
    if (!bindings.data) return;
    await perform(() =>
      apiClient.put("/capabilities/bindings", {
        revision: bindings.data!.revision,
        asset_ids: on
          ? [...bindings.data!.asset_ids, asset.id]
          : bindings.data!.asset_ids.filter((id) => id !== asset.id),
      }),
    );
  }
  async function importFiles(files: FileList | null, isDirectory = false) {
    if (!files?.length) return;
    const selected = Array.from(files);
    await perform(async () => {
      if (
        selected.length > 100 ||
        selected.reduce((n, f) => n + f.size, 0) > (isDirectory ? 8 : 4) * 1024 * 1024
      )
        throw new Error("技能包过大，最多 100 个文件；ZIP 4 MiB，目录 8 MiB");
      const form = new FormData();
      form.append("scope", scope === "project" && project?.project ? "project" : "personal");
      for (const file of selected)
        form.append(
          isDirectory ? "files" : "file",
          file,
          isDirectory ? file.webkitRelativePath : file.name,
        );
      const response = await capabilityFetch(
        `skills/${isDirectory ? "import-directory" : "import"}`,
        { method: "POST", body: form },
      );
      setEditor(await response.json());
    });
  }
  const isSkill = kind === "skills";
  const Icon = isSkill ? BookOpen : Plug;
  const visible =
    assets.data?.filter(
      (a) =>
        (scope === "all" || a.scope === scope) &&
        `${a.name} ${a.description} ${a.tags.join(" ")}`
          .toLocaleLowerCase()
          .includes(search.toLocaleLowerCase()),
    ) ?? [];
  return (
    <div className="mx-auto w-full max-w-6xl space-y-6 px-4 py-7 sm:px-8 sm:py-10">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-muted-foreground mb-2 text-xs">扩展助手能力</p>
          <h1 className="text-2xl font-semibold tracking-tight">
            {isSkill ? "Skills 中心" : "MCP Servers"}
          </h1>
          <p className="text-muted-foreground mt-3 max-w-2xl text-sm leading-7">
            {isSkill
              ? "把常用流程保存为技能，教助手按你的方法完成任务。先发布，再分配给当前项目的助手。"
              : "连接外部服务，让助手使用你选择的工具。先测试连接，再选择工具并分配给助手。"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {isSkill && (
            <>
              <input
                ref={upload}
                type="file"
                accept=".md,.zip"
                className="hidden"
                aria-label="上传技能包"
                onChange={(e) => {
                  void importFiles(e.target.files);
                  e.target.value = "";
                }}
              />
              <input
                ref={directory}
                type="file"
                multiple
                {...{ webkitdirectory: "" }}
                className="hidden"
                aria-label="上传技能目录"
                onChange={(e) => {
                  void importFiles(e.target.files, true);
                  e.target.value = "";
                }}
              />
              <Button variant="outline" disabled={busy} onClick={() => upload.current?.click()}>
                <Upload size={15} />
                导入技能
              </Button>
              <Button variant="ghost" disabled={busy} onClick={() => directory.current?.click()}>
                导入目录
              </Button>
            </>
          )}
          <Button disabled={busy} onClick={() => setEditor("new")}>
            <Plus size={16} />
            {isSkill ? "创建技能" : "添加 MCP"}
          </Button>
        </div>
      </header>
      <div className="border-border bg-card flex flex-wrap items-center justify-between gap-3 rounded-xl border px-4 py-3 text-sm">
        <span>
          当前助手 · <strong className="font-medium">{project?.project?.name ?? "默认项目"}</strong>
        </span>
        <span className="text-muted-foreground text-xs">
          账号级能力可跨项目复用；本页的使用开关只绑定当前项目。
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-48 flex-1">
          <Search size={16} className="text-muted-foreground absolute top-3 left-3" />
          <Input
            aria-label="搜索能力"
            className="pl-9"
            placeholder={isSkill ? "搜索技能、说明或标签" : "搜索连接"}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <select
          aria-label="能力范围"
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          className="border-input bg-background h-10 rounded-lg border px-3 text-sm"
        >
          <option value="all">全部范围</option>
          <option value="personal">我的账号</option>
          <option value="project">项目级</option>
          <option value="system">系统级</option>
        </select>
        <Button
          variant="ghost"
          size="icon"
          aria-label="刷新能力列表"
          disabled={busy}
          onClick={() => void refresh()}
        >
          <RefreshCw size={16} />
        </Button>
      </div>
      {(error || assets.isError || bindings.isError) && (
        <p role="alert" className="text-destructive bg-destructive/5 rounded-lg p-3 text-sm">
          {error || "加载失败，请刷新重试"}
        </p>
      )}
      {assets.isPending ? (
        <p className="text-muted-foreground py-12 text-center text-sm">正在读取能力列表…</p>
      ) : visible.length === 0 ? (
        <div className="border-border bg-card rounded-2xl border border-dashed px-6 py-16 text-center">
          <Icon size={32} className="text-muted-foreground mx-auto mb-4" />
          <h2 className="font-medium">
            {search || scope !== "all"
              ? "没有匹配的能力"
              : isSkill
                ? "让常用方法成为可复用的技能"
                : "连接你的第一个外部服务"}
          </h2>
          <p className="text-muted-foreground mx-auto mt-3 max-w-md text-sm leading-7">
            {isSkill
              ? "可直接编写 SKILL.md，或导入包含参考资料与模板的技能包。导入后保存为草稿，发布前不会用于对话。"
              : "支持远程 HTTP 与 SSE。配置保存在当前账号，认证信息仅写入，不会在页面回显。"}
          </p>
        </div>
      ) : (
        <section className="grid gap-4 md:grid-cols-2" aria-label="能力列表">
          {visible.map((a) => {
            const bound = bindings.data?.asset_ids.includes(a.id) ?? false;
            const ready =
              a.enabled && a.can_bind && (isSkill ? !!a.published_version : a.status === "ready");
            return (
              <article
                key={a.id}
                className="border-border bg-card flex min-w-0 flex-col rounded-2xl border p-5"
              >
                <div className="flex items-start gap-3">
                  <div className="bg-muted flex h-10 w-10 shrink-0 items-center justify-center rounded-xl">
                    <Icon size={20} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h2 className="truncate font-semibold">{a.name}</h2>
                    <p className="text-muted-foreground mt-1 text-xs">
                      {a.scope === "personal"
                        ? "我的账号"
                        : a.scope === "system"
                          ? "系统共享"
                          : "项目级"}{" "}
                      · {statusLabel(a)}
                    </p>
                  </div>
                  {a.can_edit && (
                    <Switch
                      aria-label={`启用 ${a.name}`}
                      checked={a.enabled}
                      disabled={busy}
                      onCheckedChange={(enabled) =>
                        void perform(() =>
                          apiClient.post(`/capabilities/assets/${a.id}/toggle`, {
                            enabled,
                            revision: a.revision,
                          }),
                        )
                      }
                    />
                  )}
                </div>
                <p className="text-muted-foreground mt-4 line-clamp-2 min-h-10 text-sm leading-6">
                  {a.description || (isSkill ? "未填写说明" : "外部工具连接")}
                </p>
                {!isSkill && (
                  <p className="text-muted-foreground mt-3 text-xs">
                    {a.catalog.tools?.length ?? 0} 个工具 · {a.catalog.resources?.length ?? 0}{" "}
                    个资源 · {a.catalog.prompts?.length ?? 0} 个提示模板
                  </p>
                )}
                <div className="border-border mt-5 flex flex-wrap items-center justify-between gap-2 border-t pt-4">
                  <label className="flex items-center gap-2 text-xs">
                    <Switch
                      checked={bound}
                      disabled={busy || !bindings.data || (!bound && !ready)}
                      onCheckedChange={(on) => void bind(a, on)}
                      aria-label={`当前助手使用 ${a.name}`}
                    />
                    当前助手使用
                  </label>
                  <div className="flex gap-1">
                    {a.can_edit && !isSkill && (
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        onClick={() =>
                          void perform(() =>
                            apiClient.post(`/capabilities/assets/${a.id}/test`, {
                              revision: a.revision,
                            }),
                          )
                        }
                      >
                        测试
                      </Button>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={busy}
                      aria-label={`${a.can_edit ? "编辑" : "查看"} ${a.name}`}
                      onClick={() => void edit(a)}
                    >
                      <Pencil size={15} />
                    </Button>
                    {a.can_edit && (
                      <Button
                        variant="ghost"
                        size="icon"
                        disabled={busy}
                        aria-label={`删除 ${a.name}`}
                        onClick={() => setRemoving(a)}
                      >
                        <Trash2 size={15} />
                      </Button>
                    )}
                  </div>
                </div>
                {!a.can_bind && (
                  <p className="text-muted-foreground mt-2 text-xs">
                    请切换到该能力所属项目后使用。
                  </p>
                )}
                {a.status === "unavailable" && (
                  <p className="text-destructive mt-2 text-xs leading-5">{a.status_message}</p>
                )}
              </article>
            );
          })}
        </section>
      )}
      <p className="text-muted-foreground flex flex-wrap items-center justify-between gap-2 text-xs">
        <span>
          {isSkill
            ? "仅在需要时加载技能正文与参考文件，脚本文件不会在业务主机执行。"
            : "工具默认逐次确认。资源与提示模板目前用于展示服务目录。"}
        </span>
        <Link href="/chat" className="inline-flex min-h-10 items-center gap-1">
          返回对话
          <ArrowUpRight size={13} />
        </Link>
      </p>
      {editor && (
        <CapabilityEditor
          kind={kind}
          initial={editor === "new" ? null : editor}
          availability={availability.data}
          onClose={() => setEditor(null)}
          onChanged={refresh}
        />
      )}
      <ConfirmDialog
        open={!!removing}
        onOpenChange={(open) => {
          if (!open && !busy) setRemoving(null);
        }}
        title={`删除 ${removing?.name ?? ""}？`}
        description="删除后助手将无法再使用该能力，已有对话记录会保留。"
        confirmLabel="删除"
        cancelLabel="取消"
        destructive
        loading={busy}
        onConfirm={() =>
          perform(async () => {
            await apiClient.delete(`/capabilities/assets/${removing!.id}`, {
              params: { revision: String(removing!.revision) },
            });
            setRemoving(null);
          })
        }
      />
    </div>
  );
}
