"use client";

import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpRight,
  FileText,
  Layers,
  Database,
  List,
  MessageSquare,
  Plus,
  Star,
} from "lucide-react";
import { OnboardingBanner } from "@/components/dashboard/onboarding-banner";
import { PageHeader } from "@/components/dashboard/page-header";
import { RecentActivity } from "@/components/dashboard/recent-activity";
import { StatCard } from "@/components/dashboard/stat-card";
import { Button } from "@/components/ui";
import { useAuth } from "@/hooks";
import { apiClient } from "@/lib/api-client";
import { ROUTES } from "@/lib/constants";
import { isAppAdmin } from "@/lib/utils";
import { knowledgeRequest, type KnowledgeBase } from "@/lib/knowledge";
interface ConversationsResponse {
  total?: number;
  items: Array<{ id: string }>;
}

function getGreeting(t: (key: string) => string): string {
  const hour = new Date().getHours();
  if (hour < 12) return t("greetingMorning");
  if (hour < 18) return t("greetingAfternoon");
  return t("greetingEvening");
}

export default function DashboardPage() {
  const { user } = useAuth();
  const t = useTranslations("dashboard");

  const zh = useLocale() === "zh";
  const bases = useQuery({
    queryKey: ["knowledge-bases", user?.id],
    queryFn: () => knowledgeRequest<{ items: KnowledgeBase[] }>("bases"),
    enabled: !!user,
  });
  const conversations = useQuery({
    queryKey: ["conversations", "count", user?.id],
    queryFn: () => apiClient.get<ConversationsResponse>("/conversations?limit=1"),
    enabled: !!user,
  });
  const allBases = bases.isError ? undefined : bases.data?.items;
  const metric = (field: "document_count" | "chunk_count") =>
    allBases ? allBases.reduce((sum, base) => sum + base[field], 0).toLocaleString() : "—";
  const firstName = user?.full_name?.split(" ")[0] || user?.email?.split("@")[0];

  return (
    <div className="space-y-6 pb-8">
      <OnboardingBanner />

      <PageHeader
        eyebrow={t("eyebrow")}
        title={firstName ? `${getGreeting(t)}, ${firstName}` : getGreeting(t)}
        description={t("description")}
        actions={
          <Button asChild>
            <Link href={ROUTES.CHAT}>
              <Plus className="h-4 w-4" />
              {t("newChat")}
            </Link>
          </Button>
        }
      />

      <div
        className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4"
        aria-label={zh ? "工作空间统计" : "Workspace statistics"}
      >
        <StatCard
          label={zh ? "知识库" : "Knowledge bases"}
          value={allBases?.length ?? "—"}
          icon={Database}
          footer={zh ? "当前账号的知识空间" : "Your knowledge spaces"}
          loading={bases.isLoading}
        />
        <StatCard
          label={zh ? "资料总数" : "Documents"}
          value={metric("document_count")}
          icon={FileText}
          footer={zh ? "文件、知识条目与 FAQ" : "Files, articles and FAQs"}
          loading={bases.isLoading}
        />
        <StatCard
          label={zh ? "知识分块" : "Knowledge chunks"}
          value={metric("chunk_count")}
          icon={Layers}
          footer={zh ? "已生成的内容片段" : "Generated content passages"}
          loading={bases.isLoading}
        />
        <StatCard
          label={t("conversations")}
          value={conversations.isError ? "—" : (conversations.data?.total?.toLocaleString() ?? "—")}
          icon={MessageSquare}
          footer={t("acrossAllChats")}
          loading={conversations.isLoading}
        />
      </div>
      {(bases.isError || conversations.isError) && (
        <p role="status" className="text-muted-foreground text-sm">
          {zh ? "部分统计暂时无法加载。" : "Some statistics could not be loaded."}{" "}
          <button
            type="button"
            className="text-primary underline"
            onClick={() => {
              void bases.refetch();
              void conversations.refetch();
            }}
          >
            {t("retry")}
          </button>
        </p>
      )}

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <RecentActivity />
        <section className="border-border bg-card min-w-0 rounded-xl border p-5 lg:p-6">
          <div className="mb-5 flex items-center justify-between gap-3">
            <h2 className="text-base font-semibold">{zh ? "我的知识库" : "My knowledge bases"}</h2>
            <Link
              href="/knowledge"
              className="text-muted-foreground flex items-center gap-1 text-xs"
            >
              {zh ? "管理资料" : "Manage"}
              <ArrowUpRight size={14} />
            </Link>
          </div>
          {bases.isLoading && (
            <p className="text-muted-foreground py-8 text-sm" role="status">
              {zh ? "正在加载知识库…" : "Loading knowledge bases…"}
            </p>
          )}
          {bases.isError && (
            <p className="text-muted-foreground py-8 text-sm">
              {zh
                ? "暂时无法读取知识库，请稍后重试。"
                : "Unable to load knowledge bases. Please retry."}
            </p>
          )}
          {allBases?.length === 0 && (
            <div className="py-8 text-center">
              <Database className="text-primary mx-auto mb-4 h-7 w-7" />
              <h3 className="text-sm font-medium">
                {zh ? "从第一份资料开始" : "Start with your first document"}
              </h3>
              <p className="text-muted-foreground mx-auto mt-2 max-w-xs text-xs leading-6">
                {zh
                  ? "创建知识库，上传文件或编写知识，再到对话中提问并查看原文引用。"
                  : "Create a knowledge base, add documents, then ask questions with source citations."}
              </p>
              <Button asChild variant="outline" size="sm" className="mt-5">
                <Link href="/knowledge">{zh ? "创建知识库" : "Create knowledge base"}</Link>
              </Button>
            </div>
          )}
          {!!allBases?.length && (
            <ul className="divide-border divide-y">
              {allBases.slice(0, 5).map((base) => (
                <li key={base.id}>
                  <Link
                    href={`/knowledge?base=${encodeURIComponent(base.id)}`}
                    className="hover:bg-muted flex items-center gap-3 rounded-lg py-4"
                  >
                    <span className="bg-primary/10 text-primary flex h-10 w-10 shrink-0 items-center justify-center rounded-lg">
                      <Database size={18} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <h3 className="truncate text-sm font-medium">{base.name}</h3>
                      <p className="text-muted-foreground mt-1 text-xs">
                        {zh
                          ? `${base.document_count} 份资料 · ${base.chunk_count} 个分块`
                          : `${base.document_count} documents · ${base.chunk_count} chunks`}
                      </p>
                    </div>
                    <ArrowUpRight size={16} className="text-muted-foreground shrink-0" />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {isAppAdmin(user) && (
        <div>
          <h2 className="font-display text-foreground mb-3 text-base font-semibold">
            {t("adminActions")}
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            <AdminTile
              icon={Star}
              label={t("responseRatings")}
              description={t("manageRatings")}
              href={ROUTES.ADMIN_RATINGS}
            />
            <AdminTile
              icon={List}
              label={t("allConversations")}
              description={t("inspectChats")}
              href={ROUTES.ADMIN_CONVERSATIONS}
            />
          </div>
        </div>
      )}
    </div>
  );
}

function AdminTile({
  icon: Icon,
  label,
  description,
  href,
}: {
  icon: typeof Star;
  label: string;
  description: string;
  href: string;
}) {
  return (
    <Link
      href={href}
      className="border-border hover:border-foreground/30 bg-card hover:bg-accent flex items-center gap-3 rounded-xl border p-4 transition-colors"
    >
      <span className="bg-foreground/8 text-foreground flex h-9 w-9 items-center justify-center rounded-full">
        <Icon className="h-4 w-4" />
      </span>
      <div className="flex-1">
        <p className="text-foreground text-sm font-semibold">{label}</p>
        <p className="text-muted-foreground text-xs">{description}</p>
      </div>
    </Link>
  );
}
