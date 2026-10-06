"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowUpRight } from "lucide-react";

import { ResearchMark } from "@/components/brand/research-mark";
import { LanguageSwitcherIcon } from "@/components/language-switcher";
import { APP_BRAND, APP_NAME } from "@/lib/constants";

export interface SiteNavLink {
  href: string;
  label: string;
}

interface SiteNavProps {
  homeHref: string;
  homeLabel: string;
  navLabel: string;
  links: SiteNavLink[];
  cta: SiteNavLink;
}

/** Public-site header shared by the landing page and the product info pages. */
export function SiteNav({ homeHref, homeLabel, navLabel, links, cta }: SiteNavProps) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const update = () => setScrolled(window.scrollY > 8);
    update();
    window.addEventListener("scroll", update, { passive: true });
    return () => window.removeEventListener("scroll", update);
  }, []);

  return (
    <header className="site-nav" data-scrolled={scrolled}>
      <div className="site-container site-nav-inner">
        <Link href={homeHref} aria-label={homeLabel} className="site-brand">
          <ResearchMark size={28} />
          <span>
            {APP_NAME}
            <small>{APP_BRAND}</small>
          </span>
        </Link>
        <nav aria-label={navLabel} className="site-links">
          {links.map((link, i) => (
            <a key={link.href} href={link.href}>
              <span aria-hidden>{String(i + 1).padStart(2, "0")}</span>
              {link.label}
            </a>
          ))}
        </nav>
        <div className="flex items-center gap-1.5">
          <div className="hidden sm:block">
            <LanguageSwitcherIcon />
          </div>
          <Link href={cta.href} className="btn-signal btn-sm">
            {cta.label}
            <ArrowUpRight size={15} strokeWidth={2.2} />
          </Link>
        </div>
      </div>
    </header>
  );
}
