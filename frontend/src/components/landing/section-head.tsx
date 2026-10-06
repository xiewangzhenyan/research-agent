import type { ReactNode } from "react";

interface SectionHeadProps {
  index: string;
  code: string;
  id: string;
  title: ReactNode;
  lede?: ReactNode;
}

/** Section heading with an instrument-style index rule: "01 ── SIGNAL CHAIN". */
export function SectionHead({ index, code, id, title, lede }: SectionHeadProps) {
  return (
    <div className="section-head">
      <p className="section-index" aria-hidden>
        <span>{index}</span>
        <i />
        <span>{code}</span>
      </p>
      <h2 id={id} className="section-title">
        {title}
      </h2>
      {lede && <p className="section-lede">{lede}</p>}
    </div>
  );
}
