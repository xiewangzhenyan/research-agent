export interface KnowledgeBase {
  id: string;
  name: string;
  description: string;
  document_count: number;
  chunk_count: number;
  chunking_config?: ChunkingConfig;
}
export interface KnowledgeDocument {
  id: string;
  filename: string;
  size: number;
  status: string;
  error: string | null;
  chunk_count: number;
  parse_report?: PDFParseReport | null;
  chunking_config?: ChunkingConfig | null;
  source_kind?: "file" | "manual" | "faq";
  title?: string;
  revision?: number;
}
export type KnowledgeEntry =
  | { kind: "manual"; title: string; content: string }
  | { kind: "faq"; question: string; answer: string; alternative_questions?: string[] };
export interface EntryRead {
  document_id: string;
  revision: number;
  entry: KnowledgeEntry;
}
export class KnowledgeRequestError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message);
  }
}
export interface ChunkingConfig {
  chunk_size: number;
  chunk_overlap: number;
}
export interface PDFParseReport {
  parser_version: string;
  total_pages: number;
  text_pages: number;
  empty_text_pages: number[];
  suspected_scan_pages: number[];
  two_column_pages: number[];
}
export interface KnowledgeHit {
  id: string;
  title: string;
  content: string;
  page: number | null;
  position: number;
  url: string;
  score: number;
}
export async function knowledgeRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api/knowledge/${path}`, { ...options, cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new KnowledgeRequestError(
      typeof body.error?.message === "string"
        ? body.error.message
        : typeof body.detail === "string"
          ? body.detail
          : response.status === 422
            ? "内容不符合要求，请检查必填项和长度"
            : "操作失败，请稍后重试",
      response.status,
      body.error?.code,
    );
  }
  return response.status === 204 ? (undefined as T) : response.json();
}

export interface ChunkPreviewResult {
  chunking_config: ChunkingConfig;
  parse_report: PDFParseReport | null;
  chunk_count: number;
  min_length: number;
  max_length: number;
  mean_length: number;
  truncated: boolean;
  preview_token: string;
  items: {
    position: number;
    page: number | null;
    content: string;
    location?: { section?: string; table?: number; row?: number };
  }[];
}

export interface RetrievalConfig {
  mode: "hybrid" | "keyword" | "semantic";
  candidate_limit: number;
  result_limit: number;
  semantic_threshold: number;
  keyword_threshold: number;
  semantic_weight: number;
  keyword_weight: number;
  rrf_k: number;
  rerank_enabled: boolean;
  rerank_limit: number;
  context_enabled: boolean;
  context_window: number;
  context_char_budget: number;
}
export const DEFAULT_RETRIEVAL_CONFIG: RetrievalConfig = {
  mode: "hybrid",
  candidate_limit: 30,
  result_limit: 6,
  semantic_threshold: 0.45,
  keyword_threshold: 0,
  semantic_weight: 1,
  keyword_weight: 1,
  rrf_k: 60,
  rerank_enabled: false,
  rerank_limit: 10,
  context_enabled: false,
  context_window: 1,
  context_char_budget: 1000,
};
export interface RetrievalResult {
  items: (KnowledgeHit & {
    score_type: "rrf" | "bm25" | "cosine" | "reranker" | "context";
    context_of?: string[];
    retrieval: {
      keyword_score: number | null;
      semantic_score: number | null;
      keyword_rank: number | null;
      semantic_rank: number | null;
      initial_rank?: number;
      rerank_rank?: number;
      rerank_model?: string;
    };
  })[];
  diagnostics: {
    engine?: "legacy" | "postgres";
    vector_search?: "exact";
    tokenizer?: string;
    model_fingerprint?: string;
    indexed_chunks?: number;
    config: RetrievalConfig;
    total_chunks: number;
    keyword_eligible: number;
    semantic_eligible: number;
    keyword_candidates: number;
    semantic_candidates: number;
    merged_candidates: number;
    overlap_removed: number;
    limit_removed: number;
    returned: number;
    embedding_ms: number;
    total_ms: number;
    rerank?: {
      status: "disabled" | "applied" | "no_candidates";
      candidates: number;
      elapsed_ms: number;
      model?: string;
      truncated_pairs?: number;
      max_tokens?: number;
    };
    context?: {
      enabled: boolean;
      seed_count: number;
      added: number;
      added_chars: number;
      budget_skipped: number;
      max_sources: number;
    };
  };
}
