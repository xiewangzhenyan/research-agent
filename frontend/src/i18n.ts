import { getRequestConfig } from "next-intl/server";
export const locales = ["zh", "en", "pl"] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = "zh";

export default getRequestConfig(async ({ requestLocale }) => {
  let locale = await requestLocale;

  if (!locale || !locales.includes(locale as Locale)) {
    locale = defaultLocale;
  }

  return {
    locale,
    messages: (await import(`../messages/${locale}.json`)).default,
  };
});

export function getLocaleLabel(locale: Locale): string {
  const labels: Record<Locale, string> = {
    en: "English",
    pl: "Polski",
    zh: "简体中文",
  };
  return labels[locale];
}

export function getLocaleFlag(locale: Locale): string {
  const flags: Record<Locale, string> = {
    en: "🇬🇧",
    pl: "🇵🇱",
    zh: "🇨🇳",
  };
  return flags[locale];
}
