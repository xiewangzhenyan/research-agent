import Link from "next/link";
import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface Crumb {
  label: string;
  href?: string;
}

interface PageHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  /** Visually hidden context for assistive tech (kept for existing callers). */
  eyebrow?: string;
  /** Breadcrumb trail (last item is the current page; omit href on it). */
  breadcrumbs?: Crumb[];
  /** Right-aligned actions (buttons, etc.). */
  actions?: ReactNode;
  className?: string;
}

/**
 * The single workspace page header. Shares `.workspace-page-header` with pages
 * that still hand-roll their header markup, so every title, description and
 * action row lines up the same way.
 */
export function PageHeader({
  title,
  description,
  eyebrow,
  breadcrumbs,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("workspace-page-header", className)}>
      <div>
        {breadcrumbs && breadcrumbs.length > 0 && (
          <nav aria-label="Breadcrumb" className="mb-3">
            <ol className="text-muted-foreground flex flex-wrap items-center gap-1.5 text-xs">
              {breadcrumbs.map((c, i) => {
                const last = i === breadcrumbs.length - 1;
                return (
                  <li key={`${c.label}-${i}`} className="flex items-center gap-1.5">
                    {c.href && !last ? (
                      <Link href={c.href} className="hover:text-foreground transition-colors">
                        {c.label}
                      </Link>
                    ) : (
                      <span
                        aria-current={last ? "page" : undefined}
                        className={cn(last && "text-foreground font-medium")}
                      >
                        {c.label}
                      </span>
                    )}
                    {!last && <ChevronRight className="h-3 w-3 opacity-50" />}
                  </li>
                );
              })}
            </ol>
          </nav>
        )}
        {eyebrow && <p className="sr-only">{eyebrow}</p>}
        <h1 className="text-balance">{title}</h1>
        {description && <p className="text-pretty">{description}</p>}
      </div>
      {actions && <div className="workspace-page-actions flex items-center gap-2">{actions}</div>}
    </header>
  );
}
