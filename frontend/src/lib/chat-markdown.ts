import type { Root, Text, Link } from "mdast";
import { visit, SKIP } from "unist-util-visit";

/** Normalize math before Markdown consumes backslash delimiters. Code is opaque.
 * Only the display copy changes; messages/copy/export retain their original text.
 */
export function normalizeChatMath(source: string, streaming = false): string {
  let output = "";
  let i = 0;
  while (i < source.length) {
    // Fenced code, including tilde fences and an unfinished streamed block.
    if (i === 0 || source[i - 1] === "\n") {
      const indented = /^(?: {4}|\t)[^\n]*(?:\n|$)/.exec(source.slice(i));
      if (indented) {
        output += indented[0];
        i += indented[0].length;
        continue;
      }
      const fence = /^( {0,3})(`{3,}|~{3,})[^\n]*(?:\n|$)/.exec(source.slice(i));
      if (fence) {
        const marker = fence[2]!;
        const rest = source.slice(i + fence[0].length);
        const close = new RegExp(
          `^ {0,3}${marker[0]}{${marker.length},}[ \\t]*(?:\\n|$)`,
          "m",
        ).exec(rest);
        const length = fence[0].length + (close ? close.index + close[0].length : rest.length);
        output += source.slice(i, i + length);
        i += length;
        continue;
      }
    }
    if (source[i] === "`") {
      const marker = /^`+/.exec(source.slice(i))![0];
      let end = source.indexOf(marker, i + marker.length);
      while (end >= 0 && (source[end - 1] === "`" || source[end + marker.length] === "`")) {
        end = source.indexOf(marker, end + marker.length);
      }
      // An unmatched backtick is literal Markdown, not an open code span.
      const next = end < 0 ? i + marker.length : end + marker.length;
      output += source.slice(i, next);
      i = next;
      continue;
    }
    const pair = source.slice(i, i + 2);
    if (pair === "\\[" || pair === "\\(" || pair === "$$" || source[i] === "$") {
      const display = pair === "\\[" || pair === "$$";
      const open = pair.startsWith("\\") || pair === "$$" ? pair : "$";
      const close = pair === "\\[" ? "\\]" : pair === "\\(" ? "\\)" : open;
      let end = source.indexOf(close, i + open.length);
      while (end >= 0 && source[end - 1] === "\\") end = source.indexOf(close, end + close.length);
      const body = source.slice(i + open.length, end < 0 ? source.length : end);
      // Avoid interpreting common currency prose as inline math ($5 and $10).
      const valid =
        open !== "$" ||
        (body.length > 0 && !/^\s|\s$|\n/.test(body) && !/\d/.test(source[end + 1] ?? ""));
      if (end >= 0 && valid) {
        output += display ? `\n\n$$\n${body.trim()}\n$$\n\n` : `$${body.trim()}$`;
        i = end + close.length;
        continue;
      }
      if (end < 0 && streaming && open !== "$") {
        output += "\n\n*…*";
        break;
      }
      output += open === "$" ? "\\$" : open;
      i += open.length;
      continue;
    }
    if (source[i] === "\\" && i + 1 < source.length) {
      output += source.slice(i, i + 2);
      i += 2;
      continue;
    }
    output += source[i++];
  }
  return output;
}

/** Citations are text-node transforms, never global replacements inside code,
 * math, image alt text or existing links.
 */
export function remarkChatCitations() {
  return (tree: Root) => {
    visit(tree, (node, index, parent) => {
      if (
        [
          "link",
          "linkReference",
          "image",
          "imageReference",
          "code",
          "inlineCode",
          "math",
          "inlineMath",
        ].includes(node.type)
      )
        return SKIP;
      if (node.type !== "text" || !parent || index === undefined) return;
      const parts: (Text | Link)[] = [];
      let cursor = 0;
      for (const match of node.value.matchAll(/\[(\d{1,3})\](?![(:])/g)) {
        if (match.index > cursor)
          parts.push({ type: "text", value: node.value.slice(cursor, match.index) });
        parts.push({
          type: "link",
          url: `#cite-${match[1]}`,
          children: [{ type: "text", value: match[0] }],
        });
        cursor = match.index + match[0].length;
      }
      if (!parts.length) return;
      if (cursor < node.value.length) parts.push({ type: "text", value: node.value.slice(cursor) });
      parent.children.splice(index, 1, ...parts);
      return index + parts.length;
    });
  };
}
