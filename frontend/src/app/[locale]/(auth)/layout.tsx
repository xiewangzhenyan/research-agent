import Link from "next/link";
import { ArrowLeft, Database, Quote, Workflow } from "lucide-react";
import { getLocale, getTranslations, setRequestLocale } from "next-intl/server";

import { AuthBackdrop } from "@/components/auth/auth-backdrop";
import { AuthShowcase } from "@/components/auth/auth-showcase";
import { ResearchMark } from "@/components/brand/research-mark";
import { APP_BRAND, APP_NAME } from "@/lib/constants";

export default async function AuthLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  setRequestLocale((await params).locale);
  const t = await getTranslations("auth.shell");
  const locale = await getLocale();
  const home = locale === "zh" ? "/" : `/${locale}`;
  return (
    <div className="auth-shell">
      <AuthBackdrop />
      <header className="auth-header">
        <Link href={home} className="auth-brand">
          <ResearchMark size={34} className="shrink-0" />
          <span>
            {APP_NAME}
            <small>
              {APP_BRAND} · {t("tagline")}
            </small>
          </span>
        </Link>
        <Link href={home} className="auth-back">
          <ArrowLeft size={15} aria-hidden />
          {t("backHome")}
        </Link>
      </header>
      <main id="main" className="auth-main">
        <section className="auth-story" aria-label={t("tagline")}>
          <p className="section-index" aria-hidden>
            <span>RA</span>
            <i />
            <span>{t("tagline")}</span>
          </p>
          <h2>
            {t("heading")}
            <span>{t("headingAccent")}</span>
          </h2>
          <p className="auth-story-description">{t("description")}</p>
          <AuthShowcase />
          <ul className="auth-features">
            <li>
              <Database size={14} />
              {t("feature1")}
            </li>
            <li>
              <Workflow size={14} />
              {t("feature2")}
            </li>
            <li>
              <Quote size={14} />
              {t("feature3")}
            </li>
          </ul>
        </section>
        <div className="auth-form-area">
          <div className="auth-card">
            <div className="auth-card-bar" aria-hidden>
              <span>AUTH</span>
              <span>{APP_NAME}</span>
            </div>
            {children}
          </div>
        </div>
      </main>
      <footer className="auth-footer">
        <span>
          © {new Date().getFullYear()} {APP_NAME} · {APP_BRAND}
        </span>
        <span>{t("footer")}</span>
      </footer>
    </div>
  );
}
