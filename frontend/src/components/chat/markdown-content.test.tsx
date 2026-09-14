import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MarkdownContent } from "./markdown-content.impl";
import { normalizeChatMath } from "@/lib/chat-markdown";

vi.mock("next-intl", () => ({ useLocale: () => "zh" }));

describe("chat math and citations", () => {
  const drude = String.raw`\[\varepsilon(\omega)=\varepsilon_\infty-\frac{\omega_p^2}{\omega^2+i\gamma\omega}\]`;
  const separated = String.raw`\[\varepsilon(\omega)=\varepsilon_\infty-\frac{\omega_p^2}{\omega^2+\gamma^2}+i\frac{\omega_p^2\gamma}{\omega(\omega^2+\gamma^2)}\]`;
  it("renders both Drude forms, inline expressions and aligned matrices", () => {
    const { container } = render(
      <MarkdownContent
        content={[
          drude,
          separated,
          String.raw`行内 \(x^2\) 与 $y_1$`,
          String.raw`$$\begin{aligned}a&=1\\b&=\begin{pmatrix}1&2\\3&4\end{pmatrix}\end{aligned}$$`,
        ].join("\n\n")}
      />,
    );
    expect(container.querySelectorAll(".katex")).toHaveLength(5);
    expect(container.querySelector(".katex-error")).toBeNull();
    expect(container.querySelectorAll(".katex-display")).toHaveLength(3);
    expect(container.textContent).toContain("ε");
  });
  it("preserves code, currency, existing links and numeric indices within math", () => {
    const onCiteClick = vi.fn();
    const content =
      String.raw`依据 [1]；成本 $5 和 $10；行内代码 \`values[1]\`。`.replaceAll("\\`", "`") +
      "\n\n```python\nvalues[1]\n" +
      drude +
      "\n```\n\n" +
      String.raw`$a[1]$ [网站](https://example.org)`;
    const { container } = render(<MarkdownContent content={content} onCiteClick={onCiteClick} />);
    expect(screen.getAllByRole("button", { name: "1" })).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "1" }));
    expect(onCiteClick).toHaveBeenCalledWith(1);
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    expect(container.textContent).toContain("$5 和 $10");
    expect(container.querySelector("pre")?.textContent).toContain(drude);
    expect(screen.getByRole("link", { name: "网站" })).toHaveAttribute(
      "href",
      "https://example.org",
    );
  });
  it("holds unfinished display math while streaming, then renders without damaging source", () => {
    const source = drude;
    for (let i = 2; i < source.length; i++) {
      const { container, unmount } = render(
        <MarkdownContent content={source.slice(0, i)} isStreaming />,
      );
      expect(container.querySelector(".katex-error")).toBeNull();
      unmount();
    }
    const { container, rerender } = render(<MarkdownContent content={source} isStreaming />);
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    rerender(<MarkdownContent content={source} />);
    expect(container.querySelectorAll(".katex")).toHaveLength(1);
    expect(source).toBe(drude);
  });
  it("does not interpret tilde fences, escaped delimiters or dangerous LaTeX links", () => {
    const code = "~~~text\n" + drude + "\n~~~";
    expect(normalizeChatMath(code)).toBe(code);
    expect(normalizeChatMath(`    ${drude}`)).toBe(`    ${drude}`);
    expect(normalizeChatMath("a ` literal " + drude)).toContain("$$");
    expect(normalizeChatMath(String.raw`\\[not math\\]`)).toBe(String.raw`\\[not math\\]`);
    const { container } = render(
      <MarkdownContent content={String.raw`$\href{javascript:alert(1)}{click}$`} />,
    );
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
  });
});
