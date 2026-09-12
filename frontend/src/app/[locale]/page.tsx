import Link from "next/link";
import type { Metadata } from "next";
import { ArrowUpRight, Database, FileText, Quote, ShieldCheck, Search } from "lucide-react";
import type { Locale } from "@/i18n";
import { pageMetadata } from "@/lib/seo";
import { APP_BRAND, APP_DESCRIPTION, APP_NAME } from "@/lib/constants";
import { CosmicOrbit } from "@/components/marketing/cosmic-orbit";
import { ResearchMark } from "@/components/brand/research-mark";
export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: Locale }>;
}): Promise<Metadata> {
  const { locale } = await params;
  return pageMetadata({
    title: APP_NAME,
    description:
      locale === "zh"
        ? APP_DESCRIPTION
        : "LSPRAI research knowledge base and AI assistant. Connect research literature, foundational knowledge and answers with traceable sources.",
    path: "/",
    locale,
  });
}
export default async function HomePage({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = await params;
  const zh = locale === "zh";
  const href = (path: string) => `${locale === "zh" ? "" : `/${locale}`}${path}`;
  const cards = zh
    ? [
        {
          icon: FileText,
          title: "散落的资料，有了归处。",
          body: "从 PDF、Word 到学习笔记，放进你的专属知识空间。每一份资料的处理过程，都清晰可见。",
          tag: "01 / COLLECT",
        },
        {
          icon: Search,
          title: "不止搜到，更能读懂。",
          body: "把关键词与语义连接起来。即使换一种问法，也能找到资料里真正相关的段落。",
          tag: "02 / CONNECT",
        },
        {
          icon: Quote,
          title: "每个答案，都有来处。",
          body: "在对话中连接知识库，展开引用即可阅读原文。保留思考的流畅，也保留核对的余地。",
          tag: "03 / DISCOVER",
        },
      ]
    : [
        {
          icon: FileText,
          title: "A home for every document.",
          body: "Bring PDFs, Word files and notes into your private knowledge space, with visible processing stages.",
          tag: "01 / COLLECT",
        },
        {
          icon: Search,
          title: "Find meaning, beyond keywords.",
          body: "Semantic and keyword search work together to surface relevant passages, even when you ask differently.",
          tag: "02 / CONNECT",
        },
        {
          icon: Quote,
          title: "Every answer has a beginning.",
          body: "Connect your knowledge in chat. Open citations to read the source, and keep your thinking moving.",
          tag: "03 / DISCOVER",
        },
      ];
  return (
    <div className="cosmic-landing theme-dark">
      <nav
        aria-label={zh ? "主导航" : "Main navigation"}
        className="cosmic-nav mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-6 sm:px-10"
      >
        <Link
          href={href("/")}
          className="flex items-center gap-2 text-sm font-semibold tracking-tight sm:gap-3 sm:text-lg"
        >
          <ResearchMark size={36} className="shrink-0" />
          <span className="whitespace-nowrap">
            {APP_NAME}
            <small className="text-brand block text-[10px] font-medium tracking-[0.15em]">
              {APP_BRAND}
            </small>
          </span>
        </Link>
        <div className="hidden items-center gap-8 text-sm text-slate-400 md:flex">
          <a href="#possibilities">{zh ? "探索能力" : "Explore"}</a>
          <Link href={href("/knowledge")}>{zh ? "知识空间" : "Knowledge"}</Link>
          <Link href={href("/help")}>{zh ? "使用指南" : "Guide"}</Link>
        </div>
        <Link
          href={href("/login")}
          className="cosmic-nav-login shrink-0 rounded-full border px-3 py-2.5 text-sm whitespace-nowrap sm:px-5"
        >
          {zh ? "进入工作区" : "Workspace"}
          <ArrowUpRight className="ml-2 inline h-3 w-3" />
        </Link>
      </nav>
      <main id="main">
        <section className="cosmic-hero relative mx-auto grid max-w-7xl items-center gap-6 px-6 pt-12 pb-16 sm:px-10 lg:grid-cols-[1.05fr_1fr] lg:pt-20 lg:pb-24">
          <div className="relative z-10">
            <p className="text-brand mb-8 flex items-center gap-3 font-mono text-[11px] tracking-[0.24em]">
              <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
              {zh ? `${APP_BRAND} · 科研知识与智能协作` : `${APP_BRAND} · RESEARCH & KNOWLEDGE`}
            </p>
            <h1 className="cosmic-title">
              {zh ? (
                <>
                  连接你的
                  <br />
                  <span>知识宇宙。</span>
                </>
              ) : (
                <>
                  Your knowledge.
                  <br />
                  <span>In a new orbit.</span>
                </>
              )}
            </h1>
            <p className="mt-7 max-w-md text-base leading-8 text-slate-400 sm:text-lg">
              {zh
                ? "让散落的资料，汇聚成清晰的答案。一个属于你的 AI 工作空间，陪你阅读、探索，也陪灵感走得更远。"
                : "Turn scattered documents into clear answers. A private AI space to read, explore, and follow your next idea."}
            </p>
            <div className="mt-9 flex flex-wrap items-center gap-4">
              <Link
                href={href("/chat")}
                className="mint-action inline-flex items-center gap-5 rounded-full px-7 py-4 text-sm font-semibold"
              >
                {zh ? "开启探索" : "Start exploring"}
                <ArrowUpRight className="h-4 w-4" />
              </Link>
              <Link
                href={href("/knowledge")}
                className="rounded-full border border-white/15 px-6 py-4 text-sm text-slate-300 hover:border-emerald-300/50"
              >
                {zh ? "建立我的知识库" : "Build my knowledge base"}
              </Link>
            </div>
            <div className="mt-9 flex flex-wrap gap-5 text-xs text-slate-500">
              <span>
                <ShieldCheck className="mr-1.5 inline h-3.5 w-3.5" />
                {zh ? "账号独立空间" : "Account isolation"}
              </span>
              <span>
                <Quote className="mr-1.5 inline h-3.5 w-3.5" />
                {zh ? "回答可追溯" : "Traceable sources"}
              </span>
            </div>
          </div>
          <CosmicOrbit chinese={zh} />
        </section>
        <section id="possibilities" className="mx-auto max-w-7xl px-6 py-16 sm:px-10">
          <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
            <div>
              <p className="mb-4 font-mono text-[10px] tracking-[0.25em] text-slate-500">
                LESS SEARCHING. MORE UNDERSTANDING.
              </p>
              <h2 className="text-2xl font-medium sm:text-3xl">
                {zh ? "从一份资料，到新的发现。" : "From a document to a discovery."}
              </h2>
            </div>
            <span className="text-xs text-slate-500">
              {zh ? "你的知识，始终围绕你。" : "Your knowledge, centered on you."}
            </span>
          </div>
          <div className="grid gap-5 md:grid-cols-3">
            {cards.map((c) => (
              <article key={c.tag} className="cosmic-feature rounded-2xl p-7">
                <div className="mb-12 flex items-center justify-between">
                  <c.icon className="text-brand h-6 w-6" />
                  <span className="font-mono text-[10px] tracking-widest text-slate-500">
                    {c.tag}
                  </span>
                </div>
                <h3 className="mb-4 text-xl font-medium">{c.title}</h3>
                <p className="text-sm leading-7 text-slate-400">{c.body}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="mx-auto max-w-7xl px-6 py-12 sm:px-10">
          <div className="cosmic-invitation flex flex-wrap items-center justify-between gap-8 rounded-3xl p-8 sm:p-12">
            <div>
              <p className="text-brand mb-4 text-xs tracking-widest">READY WHEN YOU ARE</p>
              <h2 className="text-2xl font-medium sm:text-3xl">
                {zh ? "下一次灵感，从这里出发。" : "Your next idea starts here."}
              </h2>
              <p className="mt-4 text-sm text-slate-400">
                {zh
                  ? "上传第一份资料，给你的知识一条新的轨道。"
                  : "Upload your first document. Give your knowledge a new orbit."}
              </p>
            </div>
            <Link
              href={href("/knowledge")}
              className="mint-action inline-flex items-center gap-4 rounded-full px-6 py-4 text-sm"
            >
              {zh ? "创建知识空间" : "Create your space"}
              <Database className="h-4 w-4" />
            </Link>
          </div>
        </section>
      </main>
      <footer className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-5 px-6 py-10 text-xs text-slate-500 sm:px-10">
        <span>
          © {new Date().getFullYear()} {APP_NAME} · {APP_BRAND}
        </span>
        <div className="flex gap-6">
          <Link href={href("/help")}>{zh ? "帮助" : "Help"}</Link>
          <Link href={href("/legal/privacy")}>{zh ? "隐私" : "Privacy"}</Link>
          <Link href={href("/contact")}>{zh ? "联系我们" : "Contact"}</Link>
        </div>
      </footer>
    </div>
  );
}
