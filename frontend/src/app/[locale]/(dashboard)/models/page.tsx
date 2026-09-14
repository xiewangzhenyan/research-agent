"use client";

import Link from "next/link";
import { useState } from "react";
import { useLocale } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Cpu, Database, ListFilter, RefreshCw, ArrowUpRight, Check, Minus } from "lucide-react";
import { PageHeader } from "@/components/dashboard/page-header";
import { Button, Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui";
import { fetchCapabilities, type LocalModelInfo } from "@/lib/model-capabilities";
import { useAuthStore } from "@/stores";
import { useGenerationConfig } from "@/hooks/use-generation-config";
import { apiClient } from "@/lib/api-client";
import type { AudioConfig } from "@/lib/audio-input";

const names: Record<string, [string, string]> = {
  current_datetime: ["日期与时间", "Date and time"],
  ask_user: ["交互式提问", "User questions"],
  knowledge_retrieval: ["知识库检索与引用", "Knowledge retrieval and citations"],
  run_python: ["Python 代码执行", "Python execution"],
  create_document: ["文档生成与下载", "Document generation and download"],
  create_chart: ["图表生成工具", "Chart tool"],
  web_search: ["联网搜索", "Web search"],
  multi_agent: ["多智能体协作", "Multi-agent collaboration"],
  knowledge_collaboration: ["多角色资料协作", "Knowledge collaboration"],
  durable_tasks: ["对话持续执行与恢复", "Durable task recovery"],
};

function LocalModel({
  model,
  kind,
  zh,
}: {
  model: LocalModelInfo;
  kind: "embedding" | "rerank";
  zh: boolean;
}) {
  const status = {
    not_checked: zh ? "按需加载 · 未探测" : "On demand · not checked",
    healthy: zh ? "检测正常" : "Healthy",
    unavailable: zh ? "暂不可用" : "Unavailable",
    version_mismatch: zh ? "运行版本不匹配" : "Runtime version mismatch",
  }[model.status];
  const Icon = kind === "embedding" ? Database : ListFilter;
  return (
    <article className="border-border bg-card min-w-0 rounded-2xl border p-5 sm:p-6">
      <div className="mb-5 flex items-center justify-between gap-3">
        <span className="bg-brand/10 text-brand rounded-xl p-2.5">
          <Icon size={21} />
        </span>
        <span
          className={
            model.status === "healthy" ? "text-brand text-xs" : "text-muted-foreground text-xs"
          }
        >
          {status}
        </span>
      </div>
      <h2 className="text-lg font-semibold">
        {kind === "embedding"
          ? zh
            ? "向量模型 · Embedding"
            : "Embedding model"
          : zh
            ? "重排模型 · Rerank"
            : "Reranking model"}
      </h2>
      <p className="mt-2 font-mono text-sm break-all">{model.id}</p>
      <dl className="mt-5 space-y-3 text-sm">
        <div className="flex justify-between gap-4">
          <dt className="text-muted-foreground">{zh ? "运行位置" : "Location"}</dt>
          <dd>{zh ? "本地服务器" : "Local server"}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-muted-foreground">{zh ? "执行方式" : "Runtime"}</dt>
          <dd>{model.runtime}</dd>
        </div>
        {model.dimension && (
          <div className="flex justify-between gap-4">
            <dt className="text-muted-foreground">{zh ? "向量维度" : "Dimensions"}</dt>
            <dd>{model.dimension}</dd>
          </div>
        )}
        <div>
          <dt className="text-muted-foreground">{zh ? "模型版本" : "Revision"}</dt>
          <dd className="mt-1 font-mono text-xs break-all">
            {model.revision ?? (zh ? "当前未记录完整指纹" : "Full fingerprint not recorded")}
          </dd>
        </div>
      </dl>
      <p className="text-muted-foreground mt-5 text-xs leading-relaxed">
        {kind === "embedding"
          ? zh
            ? "离线加载本地模型文件。此页面不额外加载模型；实际处理状态请查看知识库文件记录。"
            : "Loads local model files offline. This page does not start inference; check document processing for actual results."
          : zh
            ? "按需检测服务状态与固定模型版本。下方时间对应最近一次检测，可点击刷新状态更新。是否启用重排由检索设置决定。"
            : "Health and pinned revision are checked on demand. See the last check time below or refresh the status. Retrieval settings control whether reranking is used."}
      </p>
      {model.checked_at && (
        <p className="text-muted-foreground mt-2 text-xs">
          {zh ? "检测时间：" : "Checked: "}
          {new Date(model.checked_at).toLocaleString(zh ? "zh-CN" : "en-US")}
        </p>
      )}
    </article>
  );
}

export default function ModelsPage() {
  const zh = useLocale() === "zh";
  const user = useAuthStore((s) => s.user);
  const [tab, setTab] = useState("generation");
  const query = useGenerationConfig();
  const runtime = useQuery({
    queryKey: ["agent-capabilities", user?.id],
    queryFn: ({ signal }) => fetchCapabilities(signal),
    enabled: !!user && ["knowledge", "capabilities"].includes(tab),
    staleTime: 30000,
    retry: 1,
  });
  const speech = useQuery({
    queryKey: ["audio-config", user?.id],
    queryFn: ({ signal }) => apiClient.get<AudioConfig>("/audio/config", { signal }),
    enabled: !!user && tab === "speech",
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  const data = query.data;
  const refreshing = query.isFetching || runtime.isFetching || speech.isFetching;
  return (
    <div className="models-workspace space-y-6 pb-8">
      <PageHeader
        eyebrow={zh ? "运行配置" : "CONFIGURATION"}
        title={zh ? "模型与能力" : "Models and capabilities"}
        description={
          zh
            ? "查看当前使用的模型、运行状态与已接入功能。"
            : "Inspect configured models, runtime status and connected capabilities."
        }
      />
      <div className="border-border bg-card flex flex-wrap items-center justify-between gap-3 rounded-2xl border p-4">
        <p className="text-muted-foreground text-sm">
          {zh
            ? "当前模型由部署统一管理；可在对话或任务中选择生成模型。"
            : "Read-only configuration. Model lifecycle and index rebuilding controls are planned for a later phase."}
        </p>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            void query.refetch();
            if (["knowledge", "capabilities"].includes(tab))
              void runtime.refetch({ cancelRefetch: false });
            if (tab === "speech") void speech.refetch({ cancelRefetch: false });
          }}
          disabled={refreshing}
        >
          <RefreshCw className={`mr-2 h-4 w-4 ${refreshing ? "motion-safe:animate-spin" : ""}`} />
          {refreshing ? (zh ? "正在更新…" : "Updating…") : zh ? "刷新状态" : "Refresh"}
        </Button>
      </div>
      {query.isPending && (
        <p role="status" className="text-muted-foreground py-8 text-center">
          {zh ? "正在读取模型配置…" : "Loading models…"}
        </p>
      )}
      {query.isError && (
        <div role="alert" className="border-destructive/30 bg-destructive/5 rounded-2xl border p-5">
          {data
            ? zh
              ? "更新失败，暂用上次获取的模型配置。请点击刷新状态重试。"
              : "Update failed. Showing the last configuration. Refresh to retry."
            : zh
              ? "配置加载失败，请点击刷新状态重试。"
              : "Configuration unavailable. Refresh to retry."}
        </div>
      )}
      {data && (
        <Tabs value={tab} onValueChange={setTab} className="space-y-6">
          <TabsList
            className="workspace-tabs w-full justify-start"
            aria-label={zh ? "模型分类" : "Model categories"}
          >
            <TabsTrigger value="generation">{zh ? "对话模型" : "Chat models"}</TabsTrigger>
            <TabsTrigger value="knowledge">{zh ? "知识模型" : "Knowledge models"}</TabsTrigger>
            <TabsTrigger value="speech">{zh ? "语音模型" : "Speech models"}</TabsTrigger>
            <TabsTrigger value="capabilities">{zh ? "平台能力" : "Capabilities"}</TabsTrigger>
          </TabsList>
          {["knowledge", "capabilities"].includes(tab) && runtime.isPending && (
            <p role="status" className="text-muted-foreground py-8 text-center">
              {zh ? "正在检测运行状态…" : "Checking runtime status…"}
            </p>
          )}
          {["knowledge", "capabilities"].includes(tab) && runtime.isError && (
            <p role="alert" className="text-destructive text-sm">
              {zh
                ? "运行状态更新失败，请刷新重试；已有检测结果仅供参考。"
                : "Runtime update failed. Refresh to retry; previous results may be outdated."}
            </p>
          )}
          <TabsContent value="knowledge">
            {runtime.data && (
              <section
                aria-label={zh ? "本地知识模型" : "Local knowledge models"}
                className="grid gap-5 xl:grid-cols-2"
              >
                <LocalModel model={runtime.data.embedding} kind="embedding" zh={zh} />
                <LocalModel model={runtime.data.rerank} kind="rerank" zh={zh} />
              </section>
            )}
          </TabsContent>
          <TabsContent value="speech">
            {speech.isPending && (
              <p role="status">{zh ? "正在读取语音配置…" : "Loading speech configuration…"}</p>
            )}
            {speech.isError && (
              <p role="alert">
                {zh
                  ? "语音配置读取失败，请刷新重试。"
                  : "Speech configuration unavailable. Please refresh."}
              </p>
            )}
            {speech.data && (
              <section className="border-border bg-card rounded-2xl border p-5 sm:p-6">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-lg font-semibold">
                    {zh ? "语音输入与转写" : "Voice input and transcription"}
                  </h2>
                  <span className="text-muted-foreground text-xs">
                    {speech.data.enabled
                      ? zh
                        ? "已配置 · 使用时调用"
                        : "Configured · on demand"
                      : zh
                        ? "尚未启用"
                        : "Not enabled"}
                  </span>
                </div>
                <dl className="mt-5 space-y-4 text-sm">
                  {[
                    [zh ? "服务提供方" : "Provider", zh ? "硅基流动" : "SiliconFlow"],
                    [zh ? "主用模型" : "Primary model", speech.data.model],
                    [
                      zh ? "故障兜底" : "Fallback model",
                      speech.data.fallback_model || (zh ? "未配置" : "Not configured"),
                    ],
                    [
                      zh ? "单次录音" : "Recording limit",
                      `${speech.data.max_duration_seconds} ${zh ? "秒" : "seconds"}`,
                    ],
                  ].map(([label, value]) => (
                    <div key={label} className="flex flex-wrap justify-between gap-x-6 gap-y-1">
                      <dt className="text-muted-foreground">{label}</dt>
                      <dd className="min-w-0 break-all">{value}</dd>
                    </div>
                  ))}
                </dl>
                <p className="text-muted-foreground mt-5 text-sm leading-relaxed">
                  {zh
                    ? "录音结束后转写为文字，确认后发送。主模型超时或暂时不可用时自动切换；密钥由服务端管理，原始录音不存入知识库或项目记忆。"
                    : "Record, transcribe, then review before sending. Temporary failures fall back automatically. Keys stay on the server; audio is not saved in knowledge bases or project memory."}
                </p>
              </section>
            )}
          </TabsContent>
          <TabsContent value="generation">
            <section className="border-border bg-card overflow-hidden rounded-2xl border">
              <div className="border-border flex items-start gap-3 border-b p-5 sm:p-6">
                <span className="bg-brand/10 text-brand rounded-xl p-2.5">
                  <Cpu size={21} />
                </span>
                <div>
                  <h2 className="text-lg font-semibold">
                    {zh ? "回答生成模型" : "Generation models"}
                  </h2>
                  <p className="text-muted-foreground mt-1 text-sm">
                    {zh ? "默认模型：" : "Default: "}
                    <span className="text-foreground font-mono">{data.default}</span>
                  </p>
                </div>
              </div>
              <div className="divide-border divide-y">
                {data.models.map((model) => (
                  <div
                    key={model.id}
                    className="flex flex-col justify-between gap-2 px-5 py-4 sm:flex-row sm:items-center sm:px-6"
                  >
                    <div className="min-w-0">
                      <p className="font-mono text-sm break-all">{model.id}</p>
                      <p className="text-muted-foreground mt-1 text-xs">
                        {model.status === "configured"
                          ? zh
                            ? "已配置 · 未逐一探测生成可用性"
                            : "Configured · generation availability not probed"
                          : zh
                            ? "生成凭据尚未配置"
                            : "Generation credentials not configured"}
                      </p>
                    </div>
                    <div className="text-muted-foreground flex shrink-0 flex-wrap gap-2 text-xs">
                      {model.temperature && (
                        <span className="bg-accent rounded-full px-3 py-1">
                          {zh ? "温度可调" : "Temperature"}
                        </span>
                      )}
                      {!!model.thinking_efforts.length && (
                        <span className="bg-accent rounded-full px-3 py-1">
                          {zh ? "推理强度可调" : "Reasoning effort"}
                        </span>
                      )}
                      {!model.temperature && !model.thinking_efforts.length && (
                        <span>{zh ? "沿用模型默认参数" : "Model defaults"}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              <div className="border-border text-muted-foreground space-y-2 border-t p-5 text-xs leading-relaxed sm:px-6">
                <p>
                  {zh
                    ? "参数开关来自本站部署策略，不代表对供应方能力的自动检测。模型名称是配置标识；新别名需确认支持的参数后再开放。"
                    : "Controls follow deployment policy, not automatic provider detection. Model names are configured identifiers."}
                </p>
                <p>
                  {zh
                    ? "生成答案会调用配置的模型服务，问题及选中的资料片段会随请求发送。本地向量与重排不代表生成链路完全离线。"
                    : "Questions and selected excerpts are sent to the configured generation service. Local embedding and reranking do not make generation fully offline."}
                </p>
              </div>
            </section>
          </TabsContent>
          <TabsContent value="capabilities">
            {runtime.data && (
              <section className="border-border bg-card rounded-2xl border p-5 sm:p-6">
                <h2 className="text-lg font-semibold">
                  {zh ? "平台能力" : "Platform capabilities"}
                </h2>
                <p className="text-muted-foreground mt-1 text-sm">
                  {zh
                    ? "状态对应当前运行时；知识检索由会话服务组织。"
                    : "Status reflects current runtime wiring; knowledge retrieval is managed by the session service."}
                </p>
                <ul className="mt-5 grid gap-3 sm:grid-cols-2">
                  {runtime.data.capabilities.map((item) => (
                    <li
                      key={item.id}
                      className="border-border flex items-center justify-between gap-3 rounded-xl border p-3 text-sm"
                    >
                      <span className="flex items-center gap-2">
                        {item.available ? (
                          <Check className="text-brand h-4 w-4 shrink-0" />
                        ) : (
                          <Minus className="text-muted-foreground h-4 w-4 shrink-0" />
                        )}
                        {names[item.id]?.[zh ? 0 : 1] ?? item.id}
                      </span>
                      <span className="text-muted-foreground shrink-0 text-xs">
                        {item.available
                          ? zh
                            ? "已接入"
                            : "Connected"
                          : zh
                            ? "尚未接入"
                            : "Not connected"}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </TabsContent>
          <div className="text-muted-foreground flex flex-wrap items-center justify-between gap-3 text-xs">
            <span>
              {zh ? "配置策略版本：" : "Policy version: "}
              <code>{data.policy_version}</code>
              {query.dataUpdatedAt > 0 && (
                <span className="ml-3">
                  {zh ? "更新于 " : "Updated "}
                  {new Date(query.dataUpdatedAt).toLocaleTimeString(zh ? "zh-CN" : "en-US")}
                  {zh ? " · 5 分钟内跨页面复用" : " · Reused across pages for 5 minutes"}
                </span>
              )}
            </span>
            <Link href="/knowledge" className="text-brand inline-flex min-h-10 items-center gap-1">
              {zh ? "前往知识库调整检索参数" : "Configure knowledge retrieval"}
              <ArrowUpRight size={14} />
            </Link>
          </div>
        </Tabs>
      )}
    </div>
  );
}
