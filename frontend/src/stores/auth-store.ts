"use client";

import { useKnowledgeStore } from "./knowledge-store";
import { useSourcesPanelStore } from "./sources-panel-store";
import { useChatStore } from "./chat-store";
import { useConversationStore } from "./conversation-store";
import { useFilePreviewStore } from "./file-preview-store";
import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { User } from "@/types";

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  accessToken: string | null;
  avatarVersion: number;

  setUser: (user: User | null) => void;
  setLoading: (loading: boolean) => void;
  setAccessToken: (token: string | null) => void;
  checkAuth: () => Promise<void>;
  logout: () => void;
  bumpAvatarVersion: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      isLoading: true,
      accessToken: null,
      avatarVersion: 0,

      setUser: (user) =>
        set({
          user,
          isAuthenticated: user !== null,
          isLoading: false,
        }),

      setLoading: (loading) => set({ isLoading: loading }),

      setAccessToken: (token) => set({ accessToken: token }),

      bumpAvatarVersion: () => set((s) => ({ avatarVersion: s.avatarVersion + 1 })),

      checkAuth: async () => {
        try {
          set({ isLoading: true });
          const response = await fetch("/api/auth/me");
          if (response.ok) {
            const user = await response.json();
            set({ user, isAuthenticated: true, isLoading: false });
          } else {
            set({ user: null, isAuthenticated: false, isLoading: false });
          }
        } catch {
          set({ user: null, isAuthenticated: false, isLoading: false });
        }
      },

      logout: () => {
        useKnowledgeStore.getState().reset();
        useSourcesPanelStore.getState().close();
        set({
          user: null,
          isAuthenticated: false,
          isLoading: false,
          accessToken: null,
        });
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
        // Note: accessToken is intentionally NOT persisted - kept in-memory only
      }),
    },
  ),
);

// Clear all private in-memory views synchronously when the authenticated account changes.
useAuthStore.subscribe((state, previous) => {
  if (state.user?.id === previous.user?.id) return;
  useKnowledgeStore.getState().reset();
  useSourcesPanelStore.getState().close();
  useChatStore.getState().clearMessages();
  useChatStore.getState().setStreaming(false);
  useConversationStore.getState().reset();
  useFilePreviewStore.getState().close();
});
