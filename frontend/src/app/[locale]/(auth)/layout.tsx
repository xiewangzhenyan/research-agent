import Link from "next/link";
import { ArrowLeft, Database, Quote, Users } from "lucide-react";
import { getLocale, getTranslations } from "next-intl/server";

import { AuthBackdrop } from "@/components/auth/auth-backdrop";
import { AuthShowcase } from "@/components/auth/auth-showcase";
import { ResearchMark } from "@/components/brand/research-mark";
import { APP_BRAND, APP_NAME } from "@/lib/constants";

export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  const t = await getTranslations("auth.shell");
  const locale = await getLocale();
  const home = locale === "zh" ? "/" : `/${locale}`;
  return (
    <div className="auth-shell">
      <AuthBackdrop />
      <header className="auth-header">
        <Link href={home} className="auth-brand">
          <ResearchMark size={38} className="shrink-0" />
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
          <div className="auth-story-label">
            <span aria-hidden />
            {t("tagline")}
          </div>
          <h2>
            {t("heading")}
            <span>{t("headingAccent")}</span>
          </h2>
          <p className="auth-story-description">{t("description")}</p>
          <AuthShowcase />
          <ul className="auth-features">
            <li>
              <Database size={15} />
              {t("feature1")}
            </li>
            <li>
              <Users size={15} />
              {t("feature2")}
            </li>
            <li>
              <Quote size={15} />
              {t("feature3")}
            </li>
          </ul>
        </section>
        <div className="auth-form-area">
          <div className="auth-card">{children}</div>
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
