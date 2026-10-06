import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, getTranslations, setRequestLocale } from "next-intl/server";
import { notFound } from "next/navigation";

import { CookieBanner } from "@/components/marketing/cookie-banner";
import { locales, type Locale } from "@/i18n";
import { OG_LOCALE, SITE } from "@/lib/seo";

import { Providers } from "../providers";

export function generateStaticParams() {
  return locales.map((locale) => ({ locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const safeLocale: Locale = locales.includes(locale as Locale)
    ? (locale as Locale)
    : SITE.defaultLocale;

  return {
    alternates: {
      // x-default points to the canonical default-locale tree.
      languages: {
        ...Object.fromEntries(
          SITE.locales.map((l) => [l, l === SITE.defaultLocale ? SITE.url : `${SITE.url}/${l}`]),
        ),
        "x-default": SITE.url,
      },
    },
    openGraph: {
      locale: OG_LOCALE[safeLocale],
      alternateLocale: SITE.locales.filter((l) => l !== safeLocale).map((l) => OG_LOCALE[l]),
    },
  };
}

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;

  if (!locales.includes(locale as Locale)) {
    notFound();
  }
  // Without this next-intl reads the locale from request headers, which makes every
  // page dynamic: prefetches come back empty and each click re-renders on the server.
  setRequestLocale(locale);

  const messages = await getMessages();
  const t = await getTranslations("common");

  return (
    <Providers>
      <NextIntlClientProvider messages={messages}>
        <a href="#main" className="skip-link">
          {t("skipToContent")}
        </a>
        {children}
        <CookieBanner />
      </NextIntlClientProvider>
    </Providers>
  );
}
