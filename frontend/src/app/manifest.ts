import type { MetadataRoute } from "next";

import { BRAND_ASSETS } from "@/lib/brand-assets";
import { SITE } from "@/lib/seo";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: SITE.name,
    short_name: SITE.name,
    description: SITE.description,
    start_url: "/",
    display: "standalone",
    orientation: "portrait",
    background_color: "#0E0E0C",
    theme_color: SITE.themeColor,
    categories: ["productivity", "education"],
    icons: [
      { src: BRAND_ASSETS.png192, sizes: "192x192", type: "image/png", purpose: "any" },
      { src: BRAND_ASSETS.png512, sizes: "512x512", type: "image/png", purpose: "any" },
      { src: BRAND_ASSETS.maskable, sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
