import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";
import { ArrowLeft, Mail } from "lucide-react";

import type { Locale } from "@/i18n";
import { ROUTES } from "@/lib/constants";
import { pageMetadata } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: Locale }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "auth" });
  return pageMetadata({
    title: t("emailLinkHeading"),
    description: t("emailLinkDescription"),
    path: "/magic-link-sent",
    locale,
    noindex: true,
  });
}

interface PageProps {
  searchParams: Promise<{ email?: string }>;
}

export default async function MagicLinkSentPage({ searchParams }: PageProps) {
  const { email } = await searchParams;
  const t = await getTranslations("auth");
  return (
    <div className="space-y-6">
      <Mail className="text-brand h-8 w-8" aria-hidden />
      <div className="space-y-3">
        <span className="eyebrow">{t("emailLinkLabel")}</span>
        <h1>{t("emailLinkHeading")}</h1>
        <p className="text-muted-foreground text-sm leading-7">{t("emailLinkDescription")}</p>
        {email && (
          <p className="text-sm break-all">
            {t("emailLinkRecipient", { email: email.slice(0, 254) })}
          </p>
        )}
      </div>
      <p className="text-muted-foreground text-sm leading-7">{t("emailLinkHint")}</p>
      <Link href={ROUTES.LOGIN} className="text-brand inline-flex items-center gap-2 text-sm">
        <ArrowLeft size={16} aria-hidden />
        {t("backToLogin")}
      </Link>
    </div>
  );
}
