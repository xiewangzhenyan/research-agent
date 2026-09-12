import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import Link from "next/link";

import { ResetPasswordForm } from "@/components/auth/reset-password-form";
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
    title: t("resetPassword.heading"),
    description: t("resetPassword.intro"),
    path: "/reset-password",
    locale,
    noindex: true,
  });
}

interface PageProps {
  searchParams: Promise<{ token?: string }>;
}

export default async function ResetPasswordPage({ searchParams }: PageProps) {
  const { token } = await searchParams;
  const t = await getTranslations("auth");

  if (!token) {
    return (
      <div className="space-y-6">
        <div className="space-y-2">
          <span className="eyebrow">{t("resetPassword.eyebrow")}</span>
          <h1>{t("missingResetHeading")}</h1>
          <p className="text-muted-foreground text-sm leading-7">{t("missingResetDescription")}</p>
        </div>
        <Link href={ROUTES.FORGOT_PASSWORD} className="text-brand inline-flex py-2 text-sm">
          {t("recoveryOptions")}
        </Link>
        <p>
          <Link
            href={ROUTES.LOGIN}
            className="text-muted-foreground text-sm underline underline-offset-4"
          >
            {t("backToLogin")}
          </Link>
        </p>
      </div>
    );
  }

  return <ResetPasswordForm token={token} />;
}
