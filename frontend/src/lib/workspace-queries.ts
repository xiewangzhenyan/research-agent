import { queryOptions } from "@tanstack/react-query";
import { apiClient } from "@/lib/api-client";
import type { Availability, Bindings, Capability, CapabilityKind } from "@/lib/capabilities";
import { knowledgeRequest, type KnowledgeBase } from "@/lib/knowledge";
import { memoryKey, type MemoryList } from "@/lib/memory";
import { fetchTools } from "@/lib/tool-catalog";

// One definition per workspace list, shared by the pages and the idle prefetcher, so a
// prefetched response lands in exactly the cache entry the page reads on mount.
export const knowledgeBasesQuery = (userId?: string) =>
  queryOptions({
    queryKey: ["knowledge-bases", userId],
    queryFn: () => knowledgeRequest<{ items: KnowledgeBase[] }>("bases"),
    enabled: !!userId,
  });

export const toolsQuery = (userId?: string) =>
  queryOptions({
    queryKey: ["tools", userId],
    queryFn: ({ signal }) => fetchTools(signal),
    enabled: !!userId,
    staleTime: 15_000,
  });

export const memoryQuery = () =>
  queryOptions({
    queryKey: memoryKey(),
    queryFn: () => apiClient.get<MemoryList>("/memory"),
  });

export const capabilityScope = (userId: string | undefined, projectId: string | undefined) =>
  ["capabilities", userId, projectId ?? "default"] as const;

export const capabilityAssetsQuery = (
  scope: ReturnType<typeof capabilityScope>,
  kind: CapabilityKind,
) =>
  queryOptions({
    queryKey: [...scope, kind],
    queryFn: () => apiClient.get<Capability[]>(`/capabilities/${kind}`),
    staleTime: 30_000,
  });

export const capabilityBindingsQuery = (scope: ReturnType<typeof capabilityScope>) =>
  queryOptions({
    queryKey: [...scope, "bindings"],
    queryFn: () => apiClient.get<Bindings>("/capabilities/bindings"),
    staleTime: 30_000,
  });

export const capabilityAvailabilityQuery = (scope: ReturnType<typeof capabilityScope>) =>
  queryOptions({
    queryKey: [...scope, "availability"],
    queryFn: () => apiClient.get<Availability>("/capabilities/availability"),
    staleTime: 60_000,
  });
