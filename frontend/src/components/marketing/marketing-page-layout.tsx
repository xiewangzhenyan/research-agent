import type { ReactNode } from "react";
import { getLocale, getTranslations } from "next-intl/server";

import { SiteFooter } from "@/components/landing/site-footer";
import { SiteNav } from "@/components/landing/site-nav";
import { ROUTES } from "@/lib/constants";

interface MarketingPageLayoutProps {
  eyebrow?: string;
  title: string;
  description?: string;
  children: ReactNode;
}

/** Product information pages share the landing page's dark shell, nav and footer. */
export async function MarketingPageLayout({
  eyebrow,
  title,
  description,
  children,
}: MarketingPageLayoutProps) {
  const locale = await getLocale();
  const t = await getTranslations("landing.nav");
  const prefix = locale === "zh" ? "" : `/${locale}`;
  const home = prefix || "/";

  return (
    <div className="site dark">
      <SiteNav
        homeHref={home}
        homeLabel={t("home")}
        navLabel={t("label")}
        links={[
          { href: `${home}#workflow`, label: t("workflow") },
          { href: `${home}#evidence`, label: t("evidence") },
          { href: `${home}#knowledge`, label: t("knowledge") },
          { href: `${home}#spec`, label: t("spec") },
          { href: `${prefix}${ROUTES.HELP}`, label: t("guide") },
        ]}
        cta={{ href: `${prefix}${ROUTES.CHAT}`, label: t("enter") }}
      />
      <main id="main">
        <section className="doc-hero">
          <div className="site-container doc-hero-inner">
            {eyebrow && (
              <p className="section-index">
                <span>DOC</span>
                <i aria-hidden />
                <span>{eyebrow}</span>
              </p>
            )}
            <h1 className="doc-title">{title}</h1>
            {description && <p className="doc-lede">{description}</p>}
          </div>
        </section>
        <div className="site-container">{children}</div>
      </main>
      <SiteFooter prefix={prefix} />
    </div>
  );
}
