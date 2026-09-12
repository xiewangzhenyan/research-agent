/** Literal matching only. Source text remains React text, never injected HTML. */
export function evidenceSegments(content: string, quotes: string[] = []) {
  const ranges: Array<[number, number]> = [];
  for (const quote of quotes) {
    if (!quote) continue;
    let start = content.indexOf(quote);
    while (start !== -1) {
      ranges.push([start, start + quote.length]);
      start = content.indexOf(quote, start + quote.length);
    }
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: Array<[number, number]> = [];
  for (const range of ranges) {
    const previous = merged[merged.length - 1];
    if (previous && range[0] <= previous[1]) previous[1] = Math.max(previous[1], range[1]);
    else merged.push([...range]);
  }
  const parts: Array<{ text: string; highlighted: boolean }> = [];
  let cursor = 0;
  for (const [start, end] of merged) {
    if (cursor < start) parts.push({ text: content.slice(cursor, start), highlighted: false });
    parts.push({ text: content.slice(start, end), highlighted: true });
    cursor = end;
  }
  if (cursor < content.length) parts.push({ text: content.slice(cursor), highlighted: false });
  return parts;
}
