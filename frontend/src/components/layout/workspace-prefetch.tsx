"use client";

import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useProject } from "@/components/projects/project-provider";
import {
  capabilityAssetsQuery,
  capabilityAvailabilityQuery,
  capabilityBindingsQuery,
  capabilityScope,
  knowledgeBasesQuery,
  memoryQuery,
  toolsQuery,
} from "@/lib/workspace-queries";
import { useAuthStore } from "@/stores";

type IdleWindow = Window & {
  requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number;
  cancelIdleCallback?: (handle: number) => void;
};

/**
 * Warm the list behind each workspace section after the current page settles, one
 * request per idle slot, so switching sections paints cached data instead of
 * waiting on a fresh request per click. Skipped when the browser asks to save data.
 */
export function WorkspacePrefetch() {
  const client = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id);
  const workspace = useProject();
  const ready = !!workspace?.ready;
  const projectId = workspace?.project?.id;

  useEffect(() => {
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean } })
      .connection;
    if (!userId || !ready || connection?.saveData) return;
    const scope = capabilityScope(userId, projectId);
    const queue = [
      () => client.prefetchQuery(knowledgeBasesQuery(userId)),
      () => client.prefetchQuery(memoryQuery()),
      () => client.prefetchQuery(toolsQuery(userId)),
      () => client.prefetchQuery(capabilityAssetsQuery(scope, "mcp")),
      () => client.prefetchQuery(capabilityAssetsQuery(scope, "skills")),
      () => client.prefetchQuery(capabilityBindingsQuery(scope)),
      () => client.prefetchQuery(capabilityAvailabilityQuery(scope)),
    ];
    const w = window as IdleWindow;
    let cancelled = false;
    let timer = 0;
    let idle = 0;
    const schedule = () => {
      if (cancelled) return;
      if (w.requestIdleCallback) idle = w.requestIdleCallback(run, { timeout: 4000 });
      else timer = window.setTimeout(run, 300);
    };
    const run = () => {
      const task = queue.shift();
      if (!cancelled && task) void task().finally(schedule);
    };
    // Leave the first second to the page the user actually opened.
    timer = window.setTimeout(schedule, 1200);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      w.cancelIdleCallback?.(idle);
    };
  }, [client, userId, ready, projectId]);

  return null;
}
