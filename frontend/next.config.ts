import withBundleAnalyzer from "@next/bundle-analyzer";
import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";
import { BRAND_ASSETS } from "./src/lib/brand-assets";

const withNextIntl = createNextIntlPlugin("./src/i18n.ts");

// Bundle analyzer — only active when ANALYZE=true (e.g. `bun run analyze`).
const withAnalyzer = withBundleAnalyzer({
  enabled: process.env.ANALYZE === "true",
});

// Content Security Policy directives
const _frameAncestors = "frame-ancestors 'none';";

const ContentSecurityPolicy = `
  default-src 'self';
  script-src 'self' 'unsafe-eval' 'unsafe-inline';
  style-src 'self' 'unsafe-inline';
  img-src 'self' blob: data: https:;
  font-src 'self' data:;
  connect-src 'self' ws: wss: http://localhost:* https://localhost:*;
  ${_frameAncestors}
  base-uri 'self';
  form-action 'self';
`
  .replace(/\n/g, " ")
  .trim();

const securityHeaders = [
  {
    key: "Content-Security-Policy",
    value: ContentSecurityPolicy,
  },
  {
    key: "X-Content-Type-Options",
    value: "nosniff",
  },
  {
    key: "X-Frame-Options",
    value: "DENY",
  },
  {
    key: "X-XSS-Protection",
    value: "1; mode=block",
  },
  {
    key: "Referrer-Policy",
    value: "strict-origin-when-cross-origin",
  },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(self), geolocation=()",
  },
];

const nextConfig: NextConfig = {
  output: "standalone",

  async redirects() {
    return [
      { source: "/icon", destination: BRAND_ASSETS.png32, permanent: false },
      { source: "/apple-icon", destination: BRAND_ASSETS.apple, permanent: false },
    ];
  },

  // Security headers
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
      {
        source: "/brand/:asset*",
        headers: [{ key: "Cache-Control", value: "public, max-age=31536000, immutable" }],
      },
      {
        source: "/favicon.ico",
        headers: [{ key: "Cache-Control", value: "public, max-age=0, must-revalidate" }],
      },
      // Relax framing for the file endpoint so the chat preview panel can
      // embed PDFs/HTML in an iframe from the same origin. Listed AFTER the
      // catch-all so its values win for matching headers.
      {
        source: "/api/files/:path*",
        headers: [
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "Content-Security-Policy", value: "frame-ancestors 'self'" },
        ],
      },
    ];
  },

  // Environment variables available on the server side only
  serverRuntimeConfig: {
    apiUrl: process.env.BACKEND_URL || "http://localhost:38001",
  },

  // Environment variables available on both server and client
  publicRuntimeConfig: {
    appName: "agent",
  },
};
export default withAnalyzer(withNextIntl(nextConfig));
