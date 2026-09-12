import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { RetrievalSnapshotPanel } from "./retrieval-settings";
import type { RetrievalConfig } from "@/lib/knowledge";

const config: RetrievalConfig = {
  mode: "keyword",
  result_limit: 5,
  candidate_limit: 30,
  semantic_threshold: 0.45,
  keyword_threshold: 0,
  semantic_weight: 1,
  keyword_weight: 1,
  rrf_k: 60,
  rerank_enabled: true,
  rerank_limit: 10,
  context_enabled: false,
  context_window: 1,
  context_char_budget: 1000,
};

describe("task retrieval records", () => {
  it("does not invent a submission snapshot for historical tasks", () => {
    render(<RetrievalSnapshotPanel records={[]} zh />);
    expect(screen.getByText(/旧任务未保存提交时的参数快照/)).toBeInTheDocument();
    expect(screen.getByText("暂无已完成的检索记录")).toBeInTheDocument();
    expect(screen.queryByText(/已固定/)).not.toBeInTheDocument();
  });
  it("distinguishes fixed intent from actual execution and renders unknown status honestly", () => {
    render(
      <RetrievalSnapshotPanel
        zh
        snapshot={{
          configuration_id: "a".repeat(64),
          origin: "task_override",
          config,
          result_limit_capped: true,
        }}
        records={[
          {
            query: "<script>test</script>",
            configuration_id: "a".repeat(64),
            config,
            engine: "postgres",
            returned: 0,
            total_ms: 0,
            rerank: { status: "future_status", candidates: 0, elapsed_ms: 0 },
            context: { enabled: false },
          },
        ]}
      />,
    );
    expect(screen.getByText(/本次自定义设置/)).toBeInTheDocument();
    expect(screen.getByText(/已按资料协作预算收紧/)).toBeInTheDocument();
    expect(screen.getByText(/状态未识别/)).toBeInTheDocument();
    expect(screen.getByText(/数据库内检索/)).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });
});
