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
        <div className="flex items-center gap-3">
          <ResearchMark size={26} />
          <span>
            © {new Date().getFullYear()} {APP_NAME} · {APP_BRAND}
            <span className="text-subtle hidden sm:inline"> — {t("tagline")}</span>
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
    </footer>
  );
}
