import Link from "next/link";
import { getLocale } from "next-intl/server";
import { ArrowRight } from "lucide-react";

import { MarketingPageLayout } from "./marketing-page-layout";
import { ROUTES } from "@/lib/constants";

interface InfoCopy {
  eyebrow: string;
  title: string;
  lede: string;
  paragraphs?: string[];
  entries?: { date: string; title: string; body: string }[];
  cta?: { label: string; href: string };
}

const copy: Record<"zh" | "en", Record<string, InfoCopy>> = {
  zh: {
    cookies: {
      eyebrow: "隐私与存储",
      title: "Cookie 与本地存储说明",
      lede: "本站使用 Cookie 保存登录状态和语言偏好。",
      paragraphs: [
        "浏览器本地存储用于主题、引导进度和界面偏好。清除这些数据可能需要重新登录并重新设置偏好。",
        "发送消息时，对话上下文及本次附件的可解析内容会经服务器发送给管理员配置的模型服务。",
      ],
    },
    help: {
      eyebrow: "使用指南",
      title: "使用帮助",
      lede: "当前支持账号登录、AI 对话、私有知识库、原文引用、聊天附件与对话历史。",
      paragraphs: [
        "在聊天输入框添加文件，然后发送问题，助手会使用本次附带的可解析内容。附件不会自动建立可跨对话检索的知识库。",
        "连接知识库并开启严格资料问答后，对比、综述、总结类问题会自动启用规划、研究、撰写、审校四角色协作。在回答的「执行详情与文件」里可以查看每个角色的进度。",
        "聊天框会显示当前默认模型。可在模型菜单中切换；默认模型由站点管理员统一配置。",
      ],
    },
    rag: {
      eyebrow: "知识库",
      title: "你的专属知识空间",
      lede: "上传 PDF、Word、TXT、Markdown 或 CSV，查看真实处理状态，在对话中检索资料并展开原文引用。",
      paragraphs: [
        "支持多文件上传、重复文件去重、失败重试、分块预览与混合检索。单文件不超过 10 MB；扫描 PDF 请先完成 OCR。",
        "知识库、文件及检索结果按账号隔离。聊天附件只用于当次对话，不代表文件已经加入知识库。云盘同步暂未开放。",
      ],
      cta: { label: "进入知识库", href: "/knowledge" },
    },
    pricing: {
      eyebrow: "服务说明",
      title: "服务与套餐",
      lede: "当前站点尚未开放付费套餐、订阅和在线支付。",
      paragraphs: [
        "请登录使用已开放的聊天功能。可用模型由管理员配置，本站暂未发布付费额度或服务承诺。",
        "私有知识库已开放；团队邀请和云盘同步暂不可用。",
      ],
    },
    contact: {
      eyebrow: "联系与反馈",
      title: "联系与反馈",
      lede: "遇到问题时，请通过你现有的联系渠道向站点管理员反馈。",
      paragraphs: [
        "请提供发生问题的页面地址、操作步骤和时间；模型问题请附上模型名称和错误提示。",
        "本站尚未设置公开客服邮箱、销售预约或在线工单入口。请勿在反馈中提供密码或 API Key。",
      ],
    },
    changelog: {
      eyebrow: "更新日志",
      title: "更新日志",
      lede: "按时间记录面向用户的主要变化。",
      entries: [
        {
          date: "2026-10-05",
          title: "共振界面改版",
          body: "首页、登录页与工作台统一为深墨光谱设计：四角色协作演示、原文引用示例、按日期分组的对话历史、滑动导航高亮与智能体执行时间线，并完整支持深浅色与减少动态效果。",
        },
        {
          date: "2026-09-09",
          title: "知识库与宇宙工作区升级",
          body: "新增本地中文向量与混合检索、真实文件处理状态、失败重试、分块预览和原文引用。知识数据按账号隔离。同时上线深色宇宙与薄荷绿界面、动态轨道首页，兼顾手机和减少动态效果设置。",
        },
      ],
    },
  },
  en: {
    cookies: {
      eyebrow: "Privacy and storage",
      title: "Cookies and local storage",
      lede: "This site uses cookies for sign-in and language preferences.",
      paragraphs: [
        "Local storage keeps theme, onboarding progress, and interface preferences. Clearing it may require signing in and setting preferences again.",
        "When you send a message, the server forwards conversation context and readable attachment contents to the model service configured by the administrator.",
      ],
    },
    help: {
      eyebrow: "Guide",
      title: "Help",
      lede: "This deployment supports sign-in, AI chat, private knowledge bases, source citations, chat attachments and conversation history.",
      paragraphs: [
        "Attach a file in chat and send a question to use its readable contents. Attachments do not create a searchable knowledge base across conversations.",
        "With a knowledge base connected and strict source mode on, comparison, review and summary questions automatically use the planner, researcher, writer and reviewer workflow. Open the answer's execution details to follow each role.",
        "The chat controls show the default model and let you select another configured model. The site administrator configures the default.",
      ],
    },
    rag: {
      eyebrow: "Knowledge",
      title: "Your private knowledge space",
      lede: "Upload PDF, Word, TXT, Markdown or CSV files, follow their real processing status, and search them in chat with source citations.",
      paragraphs: [
        "Multi-file upload, duplicate detection, retries, chunk previews and hybrid retrieval are supported. Files are limited to 10 MB; run OCR on scanned PDFs first.",
        "Knowledge bases, files and retrieval results are isolated per account. Chat attachments are used only in that conversation and are not added to a knowledge base. Cloud sync is not enabled.",
      ],
      cta: { label: "Open knowledge", href: "/knowledge" },
    },
    pricing: {
      eyebrow: "Service",
      title: "Service availability",
      lede: "Paid plans, subscriptions, and online payments are not available on this site.",
      paragraphs: [
        "Sign in to use chat. The administrator configures available models; no paid quotas or service commitments have been published.",
        "Private knowledge bases are available. Team invitations and cloud storage sync are not enabled.",
      ],
    },
    contact: {
      eyebrow: "Contact",
      title: "Contact and feedback",
      lede: "Contact the site administrator through your existing contact channel.",
      paragraphs: [
        "Include the page URL, steps to reproduce, and time of the issue. For model issues, include the model name and error message.",
        "No public support email, sales booking, or ticket form is configured. Do not include passwords or API keys in feedback.",
      ],
    },
    changelog: {
      eyebrow: "Changelog",
      title: "Changelog",
      lede: "Notable user-facing changes, newest first.",
      entries: [
        {
          date: "2026-10-05",
          title: "Resonance interface",
          body: "The landing page, sign-in and workspace now share one deep-ink design: a four-role collaboration preview, citation examples, date-grouped chat history, a sliding navigation highlight and an agent execution timeline, with full light/dark and reduced-motion support.",
        },
        {
          date: "2026-09-09",
          title: "Native knowledge and workspace",
          body: "Added local Chinese embeddings, hybrid retrieval, processing stages, retries, chunk previews and source citations, isolated by account, together with a dark cosmic interface with mint accents and reduced-motion support.",
        },
      ],
    },
  },
};

export type ProductInfoKind = "cookies" | "help" | "rag" | "pricing" | "contact" | "changelog";

export async function ProductInfoPage({ kind }: { kind: ProductInfoKind }) {
  const locale = await getLocale();
  const isZh = locale === "zh";
  const page = (isZh ? copy.zh : copy.en)[kind]!;
  const prefix = isZh ? "" : `/${locale}`;
  const cta = page.cta ?? { label: isZh ? "打开聊天" : "Open chat", href: ROUTES.CHAT };

  return (
    <MarketingPageLayout eyebrow={page.eyebrow} title={page.title} description={page.lede}>
      <div className="doc-body">
        {page.paragraphs?.map((text) => <p key={text}>{text}</p>)}
        {page.entries && (
          <ol className="grid gap-4">
            {page.entries.map((entry) => (
              <li key={entry.date} className="doc-card">
                <p className="text-brand font-mono text-xs tracking-wider">{entry.date}</p>
                <h2 className="mt-1 text-lg font-semibold">{entry.title}</h2>
                <p className="text-muted-foreground mt-2 text-sm leading-relaxed">{entry.body}</p>
              </li>
            ))}
          </ol>
        )}
        <div className="flex flex-wrap gap-3 pt-6">
          <Link className="btn-brand" href={`${prefix}${cta.href}`}>
            {cta.label}
            <ArrowRight size={16} strokeWidth={2.2} />
          </Link>
          {kind !== "help" && (
            <Link className="btn-ghost" href={`${prefix}${ROUTES.HELP}`}>
              {isZh ? "使用帮助" : "Help"}
            </Link>
          )}
        </div>
      </div>
    </MarketingPageLayout>
  );
}
