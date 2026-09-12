import { create } from "zustand";
interface KnowledgeState {
  ids: string[];
  documentIds: string[] | null;
  documentsReady: boolean;
  strict: boolean;
  scopeId: string | null;
  ready: boolean;
  busy: boolean;
  error: string | null;
  setIds: (ids: string[]) => void;
  reset: () => void;
}
const initial = { ids: [] as string[], documentIds: null as string[] | null, documentsReady: false, strict: true, scopeId: null, ready: false, busy: false, error: null };
export const useKnowledgeStore = create<KnowledgeState>((set) => ({
  ...initial,
  setIds: (ids) => set({ ids }),
  reset: () => set(initial),
}));
