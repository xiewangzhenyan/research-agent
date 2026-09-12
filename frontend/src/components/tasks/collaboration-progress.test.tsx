import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { CollaborationProgress, type RoleEvent } from "./collaboration-progress";

describe("collaboration progress", () => {
  it("uses real events and leaves skipped roles unstarted", () => {
    render(
      <CollaborationProgress
        events={[
          {
            seq: 1,
            kind: "role_completed",
            data: { role: "planner", message: "核对条件", queries: ["服务期限"] },
          },
        ]}
        status="completed"
        zh
      />,
    );
    expect(screen.getByText("服务期限")).toBeInTheDocument();
    expect(screen.getAllByText("未执行")).toHaveLength(3);
    expect(screen.queryByText("执行中")).not.toBeInTheDocument();
  });
  it("reflects latest revision and marks interrupted roles", () => {
    const events: RoleEvent[] = [
      {
        seq: 1,
        kind: "role_completed",
        data: { role: "critic", approved: false, issues: ["补充证据"] },
      },
      { seq: 2, kind: "role_started", data: { role: "critic", round: 1, message: "重新审校" } },
    ];
    const { rerender } = render(<CollaborationProgress events={events} status="running" zh />);
    expect(screen.getByText("执行中")).toBeInTheDocument();
    expect(screen.queryByText("补充证据")).not.toBeInTheDocument();
    rerender(<CollaborationProgress events={events} status="cancelled" zh />);
    expect(screen.queryByText("执行中")).not.toBeInTheDocument();
    expect(screen.getByText("已中断")).toBeInTheDocument();
  });
  it("renders untrusted review content as text", () => {
    render(
      <CollaborationProgress
        status="completed"
        zh
        events={[
          {
            seq: 1,
            kind: "role_completed",
            data: { role: "critic", approved: false, issues: ["<script>alert(1)</script>"] },
          },
        ]}
      />,
    );
    expect(screen.getByText("有待解决项")).toBeInTheDocument();
    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
  });
});
