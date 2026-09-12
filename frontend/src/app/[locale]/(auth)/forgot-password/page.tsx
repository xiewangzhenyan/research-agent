import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { ForgotPasswordForm } from "@/components/auth";
import type { Locale } from "@/i18n";
import { pageMetadata } from "@/lib/seo";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: Locale }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "auth" });
  return pageMetadata({
    title: t("forgotHeading"),
    description: t("forgotDescription"),
    path: "/forgot-password",
    locale,
    noindex: true,
  });
}

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm />;
}
