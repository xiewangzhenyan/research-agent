"use client";

import { useQuery } from "@tanstack/react-query";
import { apiClient, ApiError } from "@/lib/api-client";
import type { GenerationConfig } from "@/lib/model-capabilities";
import { useAuthStore } from "@/stores/auth-store";

export const GENERATION_CONFIG_STALE_TIME = 5 * 60 * 1000;
export const generationConfigKey = (userId?: string) => ["generation-config", userId] as const;

// One account-scoped cache for chat, tasks, memory and the model settings page.
// Runtime probes have a separate query and never delay a model selector.
export function useGenerationConfig(enabled = true) {
  const userId = useAuthStore((s) => s.user?.id);
  const query = useQuery({
    queryKey: generationConfigKey(userId),
    queryFn: ({ signal }) =>
      apiClient.get<GenerationConfig>("/agent/generation-config", {
        credentials: "include",
        cache: "no-store",
        signal,
      }),
    enabled: !!userId && enabled,
    staleTime: GENERATION_CONFIG_STALE_TIME,
    gcTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false,
    refetchOnReconnect: true,
    retry: (count, error) =>
      !(error instanceof ApiError && [401, 403].includes(error.status)) && count < 1,
    retryDelay: 500,
  });
  const denied = query.error instanceof ApiError && [401, 403].includes(query.error.status);
  return {
    ...query,
    // Cached display metadata never grants permission; requests still validate on the server.
    data: userId && !denied ? query.data : undefined,
    refetch: () => query.refetch({ cancelRefetch: false }),
  };
}

// Keep one observer across dashboard navigation, including while the first request
// is pending. Unmounting an individual selector must not cancel the shared request.
export function GenerationConfigWarmup() {
  useGenerationConfig();
  return null;
}
