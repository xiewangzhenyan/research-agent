"use client";

import { create } from "zustand";
import type { ConversationMessage } from "@/types";

interface ConversationState {
  // UI state only. The conversations LIST is owned by React Query
  // (qk.conversations.list). This store holds the current selection, the
  // loaded messages for that selection, and the fetch/select status.
  currentConversationId: string | null;
  selectionVersion: number;
  currentMessages: ConversationMessage[];
  isLoading: boolean;
  error: string | null;

  setCurrentConversationId: (id: string | null) => void;
  setCurrentMessages: (messages: ConversationMessage[]) => void;
  addMessage: (message: ConversationMessage) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  reset: () => void;
}

const initialState = {
  currentConversationId: null,
  selectionVersion: 0,
  currentMessages: [],
  isLoading: false,
  error: null,
};

export const useConversationStore = create<ConversationState>((set) => ({
  ...initialState,

  setCurrentConversationId: (id) =>
    set((state) => ({ currentConversationId: id, selectionVersion: state.selectionVersion + 1 })),

  setCurrentMessages: (messages) => set({ currentMessages: messages }),

  addMessage: (message) =>
    set((state) => ({
      currentMessages: [...(state.currentMessages || []), message],
    })),

  setLoading: (loading) => set({ isLoading: loading }),

  setError: (error) => set({ error }),

  reset: () => set(initialState),
}));
