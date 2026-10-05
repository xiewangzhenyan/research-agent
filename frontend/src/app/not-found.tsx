import Link from "next/link";

import { ResearchMark } from "@/components/brand/research-mark";
import { NotFoundBackButton } from "@/components/layout/not-found-back-button";
import { ROUTES } from "@/lib/constants";

// Rendered outside the [locale] tree (no message catalog), so copy is bilingual.
export default function NotFound() {
  return (
    <main
      id="main"
      className="site dark flex min-h-dvh flex-col items-center justify-center px-6 text-center"
    >
      <div className="hero-copy flex flex-col items-center">
        <ResearchMark size={56} animated />
        <p className="site-eyebrow mt-8">404</p>
        <h1 className="doc-title">页面不存在</h1>
        <p className="doc-lede mx-auto">
          你要找的页面不存在或已被移动。
          <br />
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link href={ROUTES.HOME} className="btn-brand">
            返回首页 · Home
          </Link>
          <NotFoundBackButton />
          <Link href={ROUTES.DASHBOARD} className="btn-ghost">
            工作台 · Workspace
          </Link>
        </div>
      </div>
    </main>
  );
}
