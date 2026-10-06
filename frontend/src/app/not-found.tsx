import Link from "next/link";

import { ResearchMark } from "@/components/brand/research-mark";
import { NotFoundBackButton } from "@/components/layout/not-found-back-button";
import { ROUTES } from "@/lib/constants";

// Rendered outside the [locale] tree (no message catalog), so copy is bilingual.
export default function NotFound() {
  return (
    <main id="main" className="site dark lost">
      <div className="lost-screen graticule" aria-hidden>
        <ResearchMark size={64} animated />
        <span className="mono-label">SIGNAL LOST · 404</span>
      </div>
      <div className="lost-copy">
        <p className="section-index">
          <span>404</span>
          <i aria-hidden />
          <span>NOT FOUND</span>
        </p>
        <h1 className="doc-title">页面不存在</h1>
        <p className="doc-lede">
          你要找的页面不存在或已被移动。
          <br />
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <div className="lab-actions">
          <Link href={ROUTES.HOME} className="btn-signal">
            返回首页 · Home
          </Link>
          <NotFoundBackButton />
          <Link href={ROUTES.DASHBOARD} className="btn-line">
            工作台 · Workspace
          </Link>
        </div>
      </div>
    </main>
  );
}
