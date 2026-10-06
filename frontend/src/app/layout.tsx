import type { Metadata, Viewport } from "next";
import { Archivo, IBM_Plex_Mono, IBM_Plex_Sans, Noto_Sans_SC } from "next/font/google";
import "./globals.css";
import { defaultLocale } from "@/i18n";
import { BRAND_ASSETS } from "@/lib/brand-assets";
import { SITE } from "@/lib/seo";

// next/font self-hosts every family at build time. The variables are only raw
// family names; globals.css composes them into --font-sans/-display/-mono with
// Noto Sans SC as the shared CJK fallback.
const cjk = Noto_Sans_SC({
  variable: "--nf-cjk",
  weight: ["400", "500", "600", "700"],
  display: "swap",
  preload: false,
});

// Variable Archivo: headings switch to its expanded cut through font-stretch.
const display = Archivo({
  subsets: ["latin"],
  variable: "--nf-display",
  axes: ["wdth"],
  display: "swap",
});

const body = IBM_Plex_Sans({
  subsets: ["latin"],
  variable: "--nf-body",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--nf-mono",
  weight: ["400", "500", "600"],
  display: "swap",
});

// Applies the persisted theme (zustand `theme-storage`, default dark) before the
// first paint so the workspace never flashes the wrong palette.
const THEME_INIT = `(function(){try{var t=(JSON.parse(localStorage.getItem("theme-storage")||"{}").state||{}).theme||"dark";if(t==="system"){t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light"}var r=document.documentElement;r.classList.add(t);r.style.colorScheme=t}catch(e){document.documentElement.classList.add("dark")}})()`;

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  title: {
    default: `${SITE.name} — ${SITE.tagline}`,
    template: `%s | ${SITE.name}`,
  },
  description: SITE.description,
  applicationName: SITE.name,
  keywords: [...SITE.keywords],
  authors: [{ name: SITE.name }],
  creator: SITE.name,
  publisher: SITE.name,
  formatDetection: { email: false, address: false, telephone: false },
  // Default OG; per-page generateMetadata can override.
  openGraph: {
    type: "website",
    siteName: SITE.name,
    title: `${SITE.name} — ${SITE.tagline}`,
    description: SITE.description,
    url: SITE.url,
    images: [{ url: "/opengraph-image", width: 1200, height: 630, alt: SITE.name }],
  },
  twitter: {
    card: "summary_large_image",
    title: `${SITE.name} — ${SITE.tagline}`,
    description: SITE.description,
    images: ["/opengraph-image"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: { index: true, follow: true, "max-image-preview": "large", "max-snippet": -1 },
  },
  icons: {
    icon: [
      { url: BRAND_ASSETS.png32, sizes: "32x32", type: "image/png" },
      { url: BRAND_ASSETS.svg, sizes: "any", type: "image/svg+xml" },
    ],
    shortcut: BRAND_ASSETS.favicon,
    apple: [{ url: BRAND_ASSETS.apple, sizes: "180x180", type: "image/png" }],
  },
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 5,
  // Required for env(safe-area-inset-*) to evaluate non-zero on iOS notches —
  // used by the mobile bottom tab bar.
  viewportFit: "cover",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#F2F1EC" },
    { media: "(prefers-color-scheme: dark)", color: SITE.themeColor },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang={defaultLocale}
      suppressHydrationWarning
      className={`${display.variable} ${body.variable} ${mono.variable} ${cjk.variable}`}
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body className="font-body">{children}</body>
    </html>
  );
}
