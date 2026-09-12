import type { Metadata } from "next";
import type { Locale } from "@/i18n";
import { pageMetadata } from "@/lib/seo";
export async function generateMetadata({ params }: { params: Promise<{ locale: Locale }> }): Promise<Metadata> {
  const { locale } = await params;
  return pageMetadata({
    title: locale === "zh" ? "服务说明" : "Service availability",
    description: locale === "zh" ? "查看当前开放的功能。付费套餐与在线支付暂未开放。" : "View available features. Paid plans and online payments are not enabled.",
    path: "/pricing", locale,
  });
}
export default function PricingLayout({ children }: { children: React.ReactNode }) {
  return children;
}
