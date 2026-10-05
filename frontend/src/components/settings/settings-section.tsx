import type { ReactNode } from "react";

interface SectionCardProps {
  title: string;
  description?: string;
  action?: ReactNode;
  children?: ReactNode;
}

export function SectionCard({ title, description, action, children }: SectionCardProps) {
  return (
    <section className="panel">
      <header className="border-border flex flex-wrap items-start justify-between gap-3 border-b px-5 py-4">
        <div className="min-w-0 flex-1">
          <h2 className="text-foreground text-base font-semibold">{title}</h2>
          {description && <p className="text-muted-foreground text-md mt-1">{description}</p>}
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </header>
      {children && <div className="px-5 py-5">{children}</div>}
    </section>
  );
}
