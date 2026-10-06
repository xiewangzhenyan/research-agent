import Link from "next/link";
import type { Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { ArrowRight, Combine, FileText, ShieldCheck } from "lucide-react";

import { Datasheet } from "@/components/landing/datasheet";
import { EvidenceSheet } from "@/components/landing/evidence-sheet";
import { HeroField } from "@/components/landing/hero-field";
import { IngestLog } from "@/components/landing/ingest-log";
import { SectionHead } from "@/components/landing/section-head";
import { SignalChain } from "@/components/landing/signal-chain";
import { SiteFooter } from "@/components/landing/site-footer";
import { SiteNav } from "@/components/landing/site-nav";
import { Spectrometer } from "@/components/landing/spectrometer";
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

// Resonance peak behind the closing call to action (viewBox 400 × 200, apex at x = 260).
const FINAL_PEAK = `M${Array.from({ length: 101 }, (_, i) => `${i * 4} ${(190 - 170 / (1 + ((i * 4 - 260) / 26) ** 2)).toFixed(1)}`).join("L")}`;

const EVIDENCE_POINTS = [
  ["hybrid", Combine],
  ["locate", FileText],
  ["honest", ShieldCheck],
] as const;

export default async function HomePage({ params }: { params: Promise<{ locale: Locale }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations("landing");
  const prefix = locale === "zh" ? "" : `/${locale}`;
  const href = (path: string) => `${prefix}${path}`;
  const spectro = (key: string) => t(`lspr.${key}`);

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
          { href: "#spec", label: t("nav.spec") },
          { href: href(ROUTES.HELP), label: t("nav.guide") },
        ]}
        cta={{ href: href(ROUTES.CHAT), label: t("nav.enter") }}
      />

      <main id="main">
        <section className="lab-hero" aria-labelledby="hero-title">
          <HeroField
            labels={{
              figure: t("field.figure"),
              hint: t("field.hint"),
              hintTouch: t("field.hintTouch"),
              still: t("field.still"),
              probe: t("field.probe"),
              amplitude: t("field.amplitude"),
              steps: t("field.steps"),
            }}
          />
          <div className="site-container lab-hero-inner">
            <p className="lab-kicker">
              <span aria-hidden>RA/01</span>
              {t("hero.kicker")}
            </p>
            <h1 id="hero-title" className={locale === "zh" ? "lab-title is-cjk" : "lab-title"}>
              <span>{t("hero.titleLead")}</span>
              <span className="is-accent">{t("hero.titleAccent")}</span>
            </h1>
            <p className="lab-lede">{t("hero.lede")}</p>
            <div className="lab-actions">
              <Link href={href(ROUTES.CHAT)} className="btn-signal">
                {t("hero.primary")}
                <ArrowRight size={16} strokeWidth={2.2} />
              </Link>
              <a href="#workflow" className="btn-line">
                {t("hero.secondary")}
              </a>
            </div>
            <dl className="lab-specs">
              {(["Cite", "Roles", "Tasks"] as const).map((key) => (
                <div key={key}>
                  <dt>{t(`hero.spec${key}`)}</dt>
                  <dd>{t(`hero.spec${key}Value`)}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section id="workflow" className="site-section" aria-labelledby="workflow-title">
          <div className="site-container">
            <SectionHead
              index="01"
              code={t("workflow.code")}
              id="workflow-title"
              title={t("workflow.title")}
              lede={t("workflow.lede")}
            />
            <SignalChain />
            <p className="section-note">{t("workflow.note")}</p>
          </div>
        </section>

        <section id="evidence" className="site-section" aria-labelledby="evidence-title">
          <div className="site-container evidence-grid">
            <Reveal className="reveal-item">
              <SectionHead
                index="02"
                code={t("evidence.code")}
                id="evidence-title"
                title={t("evidence.title")}
                lede={t("evidence.lede")}
              />
              <ul className="evidence-points">
                {EVIDENCE_POINTS.map(([key, Icon]) => (
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
            </Reveal>
            <EvidenceSheet />
          </div>
        </section>

        <section id="lspr" className="site-section" aria-labelledby="lspr-title">
          <div className="site-container">
            <SectionHead
              index="03"
              code={t("lspr.code")}
              id="lspr-title"
              title={t("lspr.title")}
              lede={t("lspr.lede")}
            />
            <Spectrometer
              labels={{
                index: spectro("index"),
                particle: spectro("particle"),
                sphere: spectro("sphere"),
                rod: spectro("rod"),
                peak: spectro("peak"),
                shift: spectro("shift"),
                fwhm: spectro("fwhm"),
                sensitivity: spectro("sensitivity"),
                fom: spectro("fom"),
                axisX: spectro("axisX"),
                axisY: spectro("axisY"),
                reference: spectro("reference"),
                note: spectro("note"),
                plotLabel: t.raw("lspr.plotLabel") as string,
              }}
            />
          </div>
        </section>

        <section id="knowledge" className="site-section" aria-labelledby="knowledge-title">
          <div className="site-container knowledge-grid">
            <SectionHead
              index="04"
              code={t("knowledge.code")}
              id="knowledge-title"
              title={t("knowledge.title")}
              lede={t("knowledge.lede")}
            />
            <IngestLog />
          </div>
        </section>

        <section id="spec" className="site-section" aria-labelledby="spec-title">
          <div className="site-container">
            <SectionHead
              index="05"
              code={t("spec.code")}
              id="spec-title"
              title={t("spec.title")}
              lede={t("spec.lede")}
            />
            <Datasheet />
          </div>
        </section>

        <section className="site-section final" aria-labelledby="final-title">
          <div className="site-container">
            <div className="final-cta">
              <svg
                className="final-peak"
                viewBox="0 0 400 200"
                preserveAspectRatio="none"
                aria-hidden
              >
                <line x1="0" x2="400" y1="190" y2="190" />
                <path d={FINAL_PEAK} />
              </svg>
              <p className="section-index" aria-hidden>
                <span>06</span>
                <i />
                <span>RUN</span>
              </p>
              <h2 id="final-title" className="final-title">
                {t("final.title")}
                <span className="final-caret" aria-hidden />
              </h2>
              <p className="section-lede">{t("final.lede")}</p>
              <div className="lab-actions">
                <Link href={href(ROUTES.CHAT)} className="btn-signal">
                  {t("final.primary")}
                  <ArrowRight size={16} strokeWidth={2.2} />
                </Link>
                <Link href={href(ROUTES.HELP)} className="btn-line">
                  {t("final.secondary")}
                </Link>
              </div>
            </div>
          </div>
        </section>
      </main>

      <SiteFooter prefix={prefix} />
    </div>
  );
}
