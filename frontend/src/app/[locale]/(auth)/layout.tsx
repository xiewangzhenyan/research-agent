import Link from "next/link";
import { ArrowLeft, Database, FileText, MessageSquare, Quote } from "lucide-react";
import { getLocale, getTranslations } from "next-intl/server";
import { APP_BRAND, APP_NAME } from "@/lib/constants";
import { ResearchMark } from "@/components/brand/research-mark";

export default async function AuthLayout({ children }: { children: React.ReactNode }) {
  const t = await getTranslations("auth.shell");
  const locale = await getLocale();
  const home = locale === "zh" ? "/" : `/${locale}`;
  return (
    <div className="auth-shell">
      <header className="auth-header">
        <Link href={home} className="auth-brand">
          <ResearchMark size={40} className="shrink-0" />
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
          <div className="auth-orbit" aria-hidden>
            <div className="auth-orbit-ring" />
            <div className="auth-orbit-ring auth-orbit-ring-inner" />
            <div className="auth-orbit-center">
              <ResearchMark size={48} />
            </div>
            <div className="auth-orbit-node auth-orbit-doc">
              <FileText size={19} />
              <span>{t("documents")}</span>
            </div>
            <div className="auth-orbit-node auth-orbit-kb">
              <Database size={19} />
              <span>{t("knowledge")}</span>
            </div>
            <div className="auth-orbit-node auth-orbit-chat">
              <MessageSquare size={19} />
              <span>{t("answers")}</span>
            </div>
          </div>
          <ul className="auth-features">
            <li>
              <Database size={15} />
              {t("feature1")}
            </li>
            <li>
              <MessageSquare size={15} />
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
