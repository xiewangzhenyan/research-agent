import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";

import { RegisterForm } from "@/components/auth";
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
    title: t("registerHeading"),
    description: t("registerDescription"),
    path: "/register",
    locale,
    noindex: true,
  });
}

export default function RegisterPage() {
  return <RegisterForm />;
}
