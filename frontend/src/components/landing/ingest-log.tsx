import { getTranslations } from "next-intl/server";

import { Reveal } from "@/components/motion/reveal";

const STAGES = ["parse", "chunk", "embed", "index", "rerank", "cite"] as const;

/** The knowledge pipeline as a console transcript; lines type in once when scrolled to. */
export async function IngestLog() {
  const t = await getTranslations("landing.knowledge");
  return (
    <Reveal className="console">
      <header className="console-bar">
        <span>{t("logTitle")}</span>
        <span className="console-rec">
          <i aria-hidden />
          {t("logSample")}
        </span>
      </header>
      <ol className="console-body">
        <li className="console-line is-cmd">
          <span className="console-tag">$</span>
          <code>ingest “{t("file")}”</code>
        </li>
        {STAGES.map((stage, i) => (
          <li key={stage} className="console-line" style={{ "--i": i + 1 } as React.CSSProperties}>
            <span className="console-tag">[{stage.padEnd(6, " ")}]</span>
            <span className="console-text">{t(stage)}</span>
            <span className="console-ok">ok</span>
          </li>
        ))}
        <li className="console-line is-done" style={{ "--i": 7 } as React.CSSProperties}>
          <span className="console-tag">→</span>
          <span className="console-text">{t("ready")}</span>
          <span className="console-cursor" aria-hidden />
        </li>
      </ol>
    </Reveal>
  );
}
