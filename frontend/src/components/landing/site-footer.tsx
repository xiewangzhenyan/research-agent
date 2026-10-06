import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { ResearchMark } from "@/components/brand/research-mark";
import { APP_BRAND, APP_NAME, ROUTES } from "@/lib/constants";

export async function SiteFooter({ prefix }: { prefix: string }) {
  const t = await getTranslations("landing.footer");
  const links = [
    { href: ROUTES.HELP, label: t("help") },
    { href: ROUTES.CHANGELOG, label: t("changelog") },
    { href: ROUTES.CONTACT, label: t("contact") },
    { href: ROUTES.LEGAL_COOKIES, label: t("cookies") },
  ];
  return (
    <footer className="site-footer">
      <div className="site-container site-footer-inner">
        <div className="site-footer-brand">
          <ResearchMark size={26} />
          <span>
            {APP_NAME}
            <small>{t("tagline")}</small>
          </span>
        </div>
        <nav aria-label={t("tagline")}>
          {links.map((link) => (
            <Link key={link.href} href={`${prefix}${link.href}`}>
              {link.label}
            </Link>
          ))}
        </nav>
      </div>
      <div className="site-container">
        <div className="site-footer-meta">
          <span>
            © {new Date().getFullYear()} {APP_BRAND}
          </span>
          <span>{t("rev")}</span>
        </div>
      </div>
    </footer>
  );
}
