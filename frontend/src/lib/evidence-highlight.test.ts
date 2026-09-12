import { expect, it } from "vitest";
import { evidenceSegments } from "./evidence-highlight";
it("preserves Unicode, whitespace and literal markup without injecting HTML", () => {
  const text = '🙂峰位 12\n nm，<script>alert(1)</script>';
  const parts = evidenceSegments(text, ['峰位 12\n nm', '<script>alert(1)</script>']);
  expect(parts.map((p) => p.text).join('')).toBe(text);
  expect(parts.filter((p) => p.highlighted).map((p) => p.text)).toEqual(['峰位 12\n nm', '<script>alert(1)</script>']);
});
it("merges overlapping evidence and ignores missing or blank strings", () => {
  const parts = evidenceSegments('abcdefabcdef', ['abc', 'bcd', '', 'absent']);
  expect(parts.filter((p) => p.highlighted).map((p) => p.text)).toEqual(['abcd', 'abcd']);
  expect(parts.map((p) => p.text).join('')).toBe('abcdefabcdef');
});
