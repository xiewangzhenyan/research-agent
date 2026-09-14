import { Blob as NodeBlob } from "node:buffer";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { pcmToWav, transcribeAudio } from "./audio-input";
import { refreshAccessToken } from "./api-client";

const scope = vi.hoisted(() => ({ id: "owner" }));
vi.mock("@/stores/auth-store", () => ({ useAuthStore: { getState: () => ({ user: scope }) } }));
vi.mock("./project-scope", () => ({ currentProject: () => null }));
vi.mock("./api-client", () => ({
  ApiError: class extends Error {
    constructor(
      public status: number,
      message: string,
    ) {
      super(message);
    }
  },
  refreshAccessToken: vi.fn(),
}));
beforeEach(() => vi.stubGlobal("Blob", NodeBlob));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  scope.id = "owner";
});

function pcm(length = 16000) {
  return {
    sampleRate: 16000,
    numberOfChannels: 2,
    length,
    getChannelData: (i: number) => new Float32Array(length).fill(i ? 0 : 1),
  } as AudioBuffer;
}
it("encodes real mono PCM WAV with a correct header and channel mix", async () => {
  const blob = pcmToWav(pcm());
  const bytes = await blob.arrayBuffer();
  const view = new DataView(bytes);
  expect(blob.type).toBe("audio/wav");
  expect(Buffer.from(bytes).subarray(0, 4).toString()).toBe("RIFF");
  expect(view.getUint16(22, true)).toBe(1);
  expect(view.getUint32(24, true)).toBe(16000);
  expect(view.getUint32(40, true)).toBe(32000);
  expect(bytes.byteLength).toBe(32044);
  expect(view.getInt16(44, true)).toBe(16384);
});
it("caps background timer overruns at 60 seconds and rejects very short recordings", () => {
  expect(pcmToWav(pcm(16000 * 62)).size).toBe(44 + 16000 * 60 * 2);
  expect(() => pcmToWav(pcm(500))).toThrow();
});
it("refreshes authentication once and posts only audio to our own server", async () => {
  vi.mocked(refreshAccessToken).mockResolvedValue(true);
  const fetcher = vi
    .fn()
    .mockResolvedValueOnce(new Response("{}", { status: 401 }))
    .mockResolvedValueOnce(Response.json({ text: " 光学 " }));
  vi.stubGlobal("fetch", fetcher);
  const blob = new Blob(["wav"], { type: "audio/wav" });
  expect(await transcribeAudio(blob, new AbortController().signal)).toBe("光学");
  expect(fetcher).toHaveBeenCalledTimes(2);
  expect(fetcher.mock.calls[0]![0]).toBe("/api/audio/transcriptions");
  expect(fetcher.mock.calls[0]![1].body).toBe(blob);
  expect(fetcher.mock.calls[0]![1].headers).toEqual({ "Content-Type": "audio/wav" });
});
it("never resends an old recording after an account change during refresh", async () => {
  vi.mocked(refreshAccessToken).mockImplementation(async () => {
    scope.id = "other";
    return true;
  });
  const fetcher = vi.fn().mockResolvedValue(new Response("{}", { status: 401 }));
  vi.stubGlobal("fetch", fetcher);
  await expect(transcribeAudio(new Blob(["wav"]), new AbortController().signal)).rejects.toThrow(
    "Scope changed",
  );
  expect(fetcher).toHaveBeenCalledOnce();
});
it("uses the backend's localized quota error", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        Response.json(
          { error: { code: "ASR_DAILY_LIMIT", message: "今日额度已用完" } },
          { status: 429 },
        ),
      ),
  );
  await expect(transcribeAudio(new Blob(["wav"]), new AbortController().signal)).rejects.toThrow(
    "今日额度已用完",
  );
});
