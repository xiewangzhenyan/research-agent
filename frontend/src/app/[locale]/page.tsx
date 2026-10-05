import Link from "next/link";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import {
  ArrowDownWideNarrow,
  ArrowRight,
  BookOpenCheck,
  Combine,
  Cpu,
  FileText,
  FolderKanban,
  Layers,
  ListTree,
  LockKeyhole,
  MessagesSquare,
  PenLine,
  Plug,
  Quote,
  RotateCcw,
  ScanText,
  Search,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

import { AgentConstellation } from "@/components/landing/agent-constellation";
import { ResonanceDivider } from "@/components/landing/resonance-divider";
import { SiteFooter } from "@/components/landing/site-footer";
import { SiteNav } from "@/components/landing/site-nav";
import { Reveal } from "@/components/motion/reveal";
import type { Locale } from "@/i18n";
import { APP_NAME, ROUTES } from "@/lib/constants";
import { pageMetadata } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: Locale }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "landing.meta" });
  return pageMetadata({ title: APP_NAME, description: t("description"), path: "/", locale });
}

const WORKFLOW = [
  { key: "plan", tag: "PLAN", icon: ListTree },
  { key: "research", tag: "RESEARCH", icon: Search },
  { key: "write", tag: "WRITE", icon: PenLine },
  { key: "review", tag: "REVIEW", icon: ShieldCheck },
] as const;

const PIPELINE = [
  { key: "parse", icon: ScanText },
  { key: "chunk", icon: Layers },
  { key: "embed", icon: Cpu },
  { key: "hybrid", icon: Combine },
  { key: "rerank", icon: ArrowDownWideNarrow },
  { key: "cite", icon: Quote },
] as const;

const CAPABILITIES = [
  { key: "tasks", icon: RotateCcw, role: "plan" },
  { key: "memory", icon: FolderKanban, role: "research" },
  { key: "clarify", icon: MessagesSquare, role: "review" },
  { key: "tools", icon: Plug, role: "plan" },
  { key: "models", icon: Sparkles, role: "write" },
  { key: "faq", icon: BookOpenCheck, role: "research" },
] as const;

export default async function HomePage({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = await params;
  const t = await getTranslations("landing");
  const prefix = locale === "zh" ? "" : `/${locale}`;
  const href = (path: string) => `${prefix}${path}`;

  return (
    <div className="site dark">
      <SiteNav
        homeHref={prefix || "/"}
        homeLabel={t("nav.home")}
        navLabel={t("nav.label")}
        links={[
          { href: "#workflow", label: t("nav.workflow") },
          { href: "#evidence", label: t("nav.evidence") },
          { href: "#knowledge", label: t("nav.knowledge") },
          { href: href(ROUTES.HELP), label: t("nav.guide") },
        ]}
        cta={{ href: href(ROUTES.CHAT), label: t("nav.enter") }}
      />

      <main id="main">
        <section className="hero">
          <div className="hero-backdrop" aria-hidden />
          <div className="site-container hero-grid">
            <div className="hero-copy">
              <p className="site-eyebrow">{t("hero.eyebrow")}</p>
              <h1 className="hero-title">
                <span>{t("hero.titleLead")}</span>
                <span className="gradient-text">{t("hero.titleAccent")}</span>
              </h1>
              <p className="hero-lede">{t("hero.lede")}</p>
              <div className="hero-actions">
                <Link href={href(ROUTES.CHAT)} className="btn-brand">
                  {t("hero.primary")}
                  <ArrowRight size={16} strokeWidth={2.2} />
                </Link>
                <a href="#workflow" className="btn-ghost">
                  {t("hero.secondary")}
                </a>
              </div>
              <ul className="hero-trust">
                <li>
                  <LockKeyhole size={14} />
                  {t("hero.trustIsolation")}
                </li>
                <li>
                  <Quote size={14} />
                  {t("hero.trustCitation")}
                </li>
                <li>
                  <RotateCcw size={14} />
                  {t("hero.trustDurable")}
                </li>
              </ul>
            </div>
            <AgentConstellation />
          </div>
        </section>

        <ResonanceDivider />

        <section id="workflow" className="site-section" aria-labelledby="workflow-title">
          <Reveal className="site-container">
            <div className="section-head is-center reveal-item">
              <p className="site-eyebrow">{t("workflow.eyebrow")}</p>
              <h2 id="workflow-title" className="section-title">
                {t("workflow.title")}
              </h2>
              <p className="section-lede">{t("workflow.lede")}</p>
            </div>
            <ol className="workflow-track">
              {WORKFLOW.map((step, i) => (
                <li
                  key={step.key}
                  className={`workflow-step role-${step.key} reveal-item`}
                  style={{ "--i": i + 1 } as React.CSSProperties}
                >
                  <span className="workflow-index">0{i + 1}</span>
                  <span className="icon-chip">
                    <step.icon size={16} strokeWidth={2} />
                  </span>
                  <h3>
                    {t(`workflow.${step.key}Title`)}
                    <span>{step.tag}</span>
                  </h3>
                  <p>{t(`workflow.${step.key}Desc`)}</p>
                  <span className="workflow-output">
                    <ArrowRight size={11} />
                    {t(`workflow.${step.key}Output`)}
                  </span>
                </li>
              ))}
            </ol>
            <p className="workflow-note reveal-item text-center" style={{ "--i": 5 } as React.CSSProperties}>
              {t("workflow.note")}
            </p>
          </Reveal>
        </section>

        <section id="evidence" className="site-section" aria-labelledby="evidence-title">
          <Reveal className="site-container evidence-grid">
            <div className="reveal-item">
              <p className="site-eyebrow">{t("evidence.eyebrow")}</p>
              <h2 id="evidence-title" className="section-title">
                {t("evidence.title")}
              </h2>
              <p className="section-lede">{t("evidence.lede")}</p>
              <ul className="evidence-points">
                {(
                  [
                    ["hybrid", Combine],
                    ["locate", FileText],
                    ["honest", ShieldCheck],
                  ] as const
                ).map(([key, Icon]) => (
                  <li key={key}>
                    <span className="icon-chip">
                      <Icon size={16} />
                    </span>
                    <span>
                      <strong>{t(`evidence.${key}Title`)}</strong>
                      {t(`evidence.${key}`)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="evidence-demo reveal-item" style={{ "--i": 1 } as React.CSSProperties}>
              <div className="evidence-answer">
                <div className="evidence-meta">
                  <span className="bg-brand h-1.5 w-1.5 rounded-full" />
                  {t("evidence.demoLabel")}
                </div>
                <p className="text-muted-foreground">{t("evidence.demoQuestion")}</p>
                <p>
                  {t("evidence.demoAnswer")}
                  <span className="citation-chip">1</span>
                  {t("evidence.demoAnswerTail")}
                </p>
              </div>
              <div className="evidence-source">
                <div className="evidence-meta">
                  <FileText size={13} className="text-brand" />
                  {t("evidence.demoSourceTitle")} · {t("evidence.demoSourceMeta")}
                </div>
                <p>
                  {t("evidence.demoSourceLead")}
                  <mark className="evidence-mark">{t("evidence.demoSourceMark")}</mark>
                  {t("evidence.demoSourceTail")}
                </p>
              </div>
            </div>
          </Reveal>
        </section>

        <section id="knowledge" className="site-section" aria-labelledby="knowledge-title">
          <Reveal className="site-container">
            <div className="section-head is-center reveal-item">
              <p className="site-eyebrow">{t("knowledge.eyebrow")}</p>
              <h2 id="knowledge-title" className="section-title">
                {t("knowledge.title")}
              </h2>
              <p className="section-lede">{t("knowledge.lede")}</p>
            </div>
            <div className="pipeline-wrap">
              <span className="pipeline-flow" aria-hidden />
              <ol className="pipeline">
                {PIPELINE.map((step, i) => (
                  <li
                    key={step.key}
                    className="pipeline-node reveal-item"
                    style={{ "--i": i + 1 } as React.CSSProperties}
                  >
                    <span className="icon-chip">
                      <step.icon size={20} strokeWidth={1.8} />
                    </span>
                    <h3>{t(`knowledge.${step.key}Title`)}</h3>
                    <p>{t(`knowledge.${step.key}`)}</p>
                  </li>
                ))}
              </ol>
            </div>
          </Reveal>
        </section>

        <section className="site-section" aria-labelledby="capabilities-title">
          <Reveal className="site-container">
            <div className="section-head reveal-item">
              <p className="site-eyebrow">{t("capabilities.eyebrow")}</p>
              <h2 id="capabilities-title" className="section-title">
                {t("capabilities.title")}
              </h2>
            </div>
            <ul className="capability-grid">
              {CAPABILITIES.map((item, i) => (
                <li
                  key={item.key}
                  className={`capability-card role-${item.role} reveal-item`}
                  style={{ "--i": i + 1 } as React.CSSProperties}
                >
                  <span className="icon-chip">
                    <item.icon size={17} strokeWidth={1.9} />
                  </span>
                  <h3>{t(`capabilities.${item.key}Title`)}</h3>
                  <p>{t(`capabilities.${item.key}`)}</p>
                </li>
              ))}
            </ul>
          </Reveal>
        </section>

        <section className="site-section pt-0">
          <Reveal className="site-container">
            <div className="final-cta reveal-item">
              <ResonanceDivider />
              <div className="final-cta-inner">
                <div className="max-w-xl">
                  <h2 className="section-title mt-0">{t("final.title")}</h2>
                  <p className="section-lede">{t("final.lede")}</p>
                </div>
                <div className="flex flex-wrap gap-3">
                  <Link href={href(ROUTES.CHAT)} className="btn-brand">
                    {t("final.primary")}
                    <ArrowRight size={16} strokeWidth={2.2} />
                  </Link>
                  <Link href={href(ROUTES.HELP)} className="btn-ghost">
                    {t("final.secondary")}
                  </Link>
                </div>
              </div>
            </div>
          </Reveal>
        </section>
      </main>

      <SiteFooter prefix={prefix} />
    </div>
  );
}
