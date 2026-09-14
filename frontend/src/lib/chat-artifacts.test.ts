import { expect, it } from "vitest";
import type { ChatMessage } from "@/types";
import { extractArtifacts } from "./chat-artifacts";

const run = "eeeeeeee-5555-4555-8555-555555555555";
const file = {
  id: "aaaaaaaa-1111-4111-8111-111111111111",
  run_id: run,
  name: "实验报告.docx",
  size: 1234,
  mime_type: "application/octet-stream",
  url: "https://untrusted.invalid",
};
const message = (result: unknown, name = "create_document"): ChatMessage => ({
  id: "answer",
  role: "assistant",
  content: "报告已生成",
  timestamp: new Date(),
  execution: { id: run, status: "completed" },
  toolCalls: [{ id: "call", name, status: "completed", args: {}, result }],
});
it("extracts only stored metadata and discards arbitrary URLs", () => {
  const raw = JSON.stringify({ artifacts: [file, file] });
  const files = extractArtifacts(message(raw));
  expect(files).toHaveLength(1);
  expect(files[0]?.name).toBe("实验报告.docx");
  expect(files[0]).not.toHaveProperty("url");
});
it("rejects foreign runs, malformed identifiers, unknown tools and failed calls", () => {
  expect(extractArtifacts(message({ artifacts: [{ ...file, run_id: "another-run" }] }))).toEqual(
    [],
  );
  expect(extractArtifacts(message({ artifacts: [{ ...file, id: "../../private" }] }))).toEqual([]);
  expect(extractArtifacts(message({ artifacts: [file] }, "untrusted_tool"))).toEqual([]);
  expect(extractArtifacts(message("not json"))).toEqual([]);
  const failed = message({ artifacts: [file] });
  failed.toolCalls![0]!.status = "error";
  expect(extractArtifacts(failed)).toEqual([]);
});
