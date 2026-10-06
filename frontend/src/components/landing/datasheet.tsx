import { getTranslations } from "next-intl/server";

const ROWS = [
  "collab",
  "retrieval",
  "citation",
  "embedding",
  "tasks",
  "clarify",
  "memory",
  "extend",
  "faq",
  "models",
  "isolation",
] as const;

/** Current capabilities as an instrument datasheet. Only shipped features belong here. */
export async function Datasheet() {
  const t = await getTranslations("landing.spec");
  return (
    <div className="datasheet">
      <table>
        <caption className="sr-only">{t("title")}</caption>
        <thead>
          <tr>
            <th scope="col">#</th>
            <th scope="col">{t("parameter")}</th>
            <th scope="col">{t("value")}</th>
          </tr>
        </thead>
        <tbody>
          {ROWS.map((row, i) => (
            <tr key={row}>
              <td>{String(i + 1).padStart(2, "0")}</td>
              <th scope="row">{t(`${row}Label`)}</th>
              <td>{t(`${row}Value`)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="datasheet-rev">{t("rev")}</p>
    </div>
  );
}
