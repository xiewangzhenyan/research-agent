/** Recency buckets for the conversation history (pattern from WeKnora's sessionGrouping). */
export type RecencyGroupKey = "today" | "yesterday" | "week" | "month" | "earlier";

export interface RecencyGroup<T> {
  key: RecencyGroupKey;
  items: T[];
}

interface Dated {
  updated_at?: string | null;
  created_at?: string | null;
}

const DAY_MS = 24 * 60 * 60 * 1000;
const ORDER: RecencyGroupKey[] = ["today", "yesterday", "week", "month", "earlier"];

function bucketFor(timestamp: number, startOfToday: number): RecencyGroupKey {
  if (Number.isNaN(timestamp)) return "earlier";
  if (timestamp >= startOfToday) return "today";
  if (timestamp >= startOfToday - DAY_MS) return "yesterday";
  if (timestamp >= startOfToday - 7 * DAY_MS) return "week";
  if (timestamp >= startOfToday - 30 * DAY_MS) return "month";
  return "earlier";
}

/**
 * Groups items by their last activity relative to the local calendar day.
 * Order inside a group is preserved; empty groups are omitted.
 */
export function groupByRecency<T extends Dated>(items: T[], now = new Date()): RecencyGroup<T>[] {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const buckets = new Map<RecencyGroupKey, T[]>();
  for (const item of items) {
    const stamp = item.updated_at || item.created_at;
    const key = stamp ? bucketFor(Date.parse(stamp), startOfToday) : "earlier";
    const list = buckets.get(key);
    if (list) list.push(item);
    else buckets.set(key, [item]);
  }
  return ORDER.filter((key) => buckets.has(key)).map((key) => ({ key, items: buckets.get(key)! }));
}
