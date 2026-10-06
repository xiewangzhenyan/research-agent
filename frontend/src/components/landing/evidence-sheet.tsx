import { getTranslations } from "next-intl/server";
import { FileText } from "lucide-react";

import { Reveal } from "@/components/motion/reveal";

/**
 * An answer and the passage it cites, laid out like a lab notebook page next to
 * the source. Pointing at the marker lights the cited span (CSS :has, no JS).
 */
export async function EvidenceSheet() {
  const t = await getTranslations("landing.evidence");
  return (
    <Reveal className="sheet">
      <article className="sheet-page sheet-answer reveal-item">
        <header>
          <span className="mono-label">{t("answerLabel")} · A-01</span>
          <span className="mono-label">{t("demoLabel")}</span>
        </header>
        <p className="sheet-q">
          <span className="sheet-prompt" aria-hidden>
            Q
          </span>
          {t("demoQuestion")}
        </p>
        <p className="sheet-a">
          {t("demoAnswer")}
          <span className="sheet-cite">1</span>
          {t("demoAnswerTail")}
        </p>
        <p className="sheet-hint">{t("link")}</p>
      </article>
      <div
        className="sheet-wire reveal-item"
        style={{ "--i": 1 } as React.CSSProperties}
        aria-hidden
      >
        <span>REF [1]</span>
      </div>
      <article
        className="sheet-page sheet-source reveal-item"
        style={{ "--i": 2 } as React.CSSProperties}
      >
        <header>
          <span className="mono-label">
            <FileText size={12} aria-hidden /> {t("sourceLabel")} · {t("demoSourceMeta")}
          </span>
        </header>
        <h3>{t("demoSourceTitle")}</h3>
        <p>
          {t("demoSourceLead")}
          <mark className="evidence-mark">{t("demoSourceMark")}</mark>
          {t("demoSourceTail")}
        </p>
      </article>
    </Reveal>
  );
}
