import { setRequestLocale } from "next-intl/server";

import { ProductInfoPage } from "@/components/marketing/product-info-page";

export default async function Page({ params }: { params: Promise<{ locale: string }> }) {
  setRequestLocale((await params).locale);
  return <ProductInfoPage kind="contact" />;
}
