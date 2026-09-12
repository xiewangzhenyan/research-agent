import createMiddleware from "next-intl/middleware";
import { NextRequest, NextResponse } from "next/server";
import { locales, defaultLocale, type Locale } from "./i18n";

const handleI18n = createMiddleware({
  locales,
  defaultLocale,
  // Don't prefix Simplified Chinese, the default locale.
  localePrefix: "as-needed",

  // Always serve `defaultLocale` (zh) at root, regardless of the visitor's
  // Accept-Language header. The user chooses another language via the switcher.
  localeDetection: false,
});

const LOCALE_COOKIE = "NEXT_LOCALE";
const LOCALE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365;

export default function middleware(request: NextRequest) {
  const pathname = request.nextUrl.pathname;
  const firstSegment = pathname.split("/").filter(Boolean)[0];
  const explicitLocale = locales.includes(firstSegment as Locale)
    ? (firstSegment as Locale)
    : undefined;
  const savedLocale = request.cookies.get(LOCALE_COOKIE)?.value;

  // The bare domain is the canonical Chinese homepage. Visiting it explicitly
  // also resets the saved preference to Chinese; English remains available at
  // /en and Polish at /pl.
  if (pathname === "/") {
    const response = handleI18n(request);
    response.cookies.set(LOCALE_COOKIE, defaultLocale, {
      path: "/",
      maxAge: LOCALE_COOKIE_MAX_AGE,
      sameSite: "lax",
    });
    return response;
  }

  // The component gallery is an internal development aid, not a public
  // product page. Keep it unreachable on the deployed site.
  if (/^\/(?:(?:en|pl|zh)\/)?dev(?:\/|$)/.test(pathname)) {
    const url = request.nextUrl.clone();
    url.pathname = explicitLocale && explicitLocale !== defaultLocale
      ? `/${explicitLocale}/dashboard`
      : "/dashboard";
    return NextResponse.redirect(url);
  }

  // Existing links use locale-neutral paths. Preserve the user's selected
  // non-default locale by adding its prefix before next-intl handles routing.
  if (
    !explicitLocale &&
    savedLocale &&
    savedLocale !== defaultLocale &&
    locales.includes(savedLocale as Locale)
  ) {
    const url = request.nextUrl.clone();
    url.pathname = pathname === "/" ? `/${savedLocale}` : `/${savedLocale}${pathname}`;
    return NextResponse.redirect(url);
  }

  const response = handleI18n(request);
  if (explicitLocale) {
    response.cookies.set(LOCALE_COOKIE, explicitLocale, {
      path: "/",
      maxAge: LOCALE_COOKIE_MAX_AGE,
      sameSite: "lax",
    });
  }
  return response;
}

export const config = {
  matcher: [
    // Match all pathnames except for:
    // - /api (API routes)
    // - /_next (Next.js internals)
    // - /static (inside /public)
    // - /_vercel (Vercel internals)
    // - All root files like favicon.ico, robots.txt, etc.
    // - App-router metadata convention routes (icon, apple-icon, opengraph-image,
    //   twitter-image, manifest.*, robots, sitemap) — these are dotless URLs
    //   that Next.js generates from src/app/{icon,apple-icon,…}.tsx and would
    //   otherwise be redirected to /{locale}/icon → 404.
    "/((?!api|_next|_vercel|static|icon$|apple-icon$|opengraph-image$|twitter-image$|manifest|robots$|sitemap$|.*\\..*).*)",
  ],
};
