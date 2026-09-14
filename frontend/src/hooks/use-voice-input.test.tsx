import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useVoiceInput } from "./use-voice-input";
import { recordingToWav, transcribeAudio, voiceScope } from "@/lib/audio-input";

vi.mock("@/lib/audio-input", () => ({
  MAX_RECORDING_SECONDS: 60,
  recordingToWav: vi.fn(),
  transcribeAudio: vi.fn(),
  voiceScope: vi.fn(() => "user:project"),
}));

class Recorder {
  static latest: Recorder;
  static isTypeSupported = () => true;
  state = "inactive";
  mimeType = "audio/webm";
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor() {
    Recorder.latest = this;
  }
  start() {
    this.state = "recording";
  }
  stop() {
    this.state = "inactive";
    this.ondataavailable?.({ data: new Blob(["audio"]) });
    this.onstop?.();
  }
}
const track = { stop: vi.fn(), onended: null };
const media = { getTracks: () => [track] };
const getUserMedia = vi.fn();

beforeEach(() => {
  vi.stubGlobal("isSecureContext", true);
  vi.stubGlobal("MediaRecorder", Recorder);
  vi.stubGlobal("OfflineAudioContext", vi.fn());
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
  getUserMedia.mockResolvedValue(media);
  vi.mocked(recordingToWav).mockResolvedValue(new Blob(["wav"]));
  vi.mocked(transcribeAudio).mockResolvedValue("LSPR 光学");
  vi.mocked(voiceScope).mockReturnValue("user:project");
});
afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("records, stops all microphone tracks and returns cloud text only once", async () => {
  const receive = vi.fn();
  const { result } = renderHook(() => useVoiceInput(true, receive));
  await act(async () => {
    await result.current.toggle();
  });
  expect(result.current.listening).toBe(true);
  expect(receive).not.toHaveBeenCalled();
  await act(async () => {
    await result.current.toggle();
  });
  await waitFor(() => expect(receive).toHaveBeenCalledWith("LSPR 光学"));
  expect(receive).toHaveBeenCalledOnce();
  expect(track.stop).toHaveBeenCalledOnce();
  expect(result.current.busy).toBe(false);
});

it("keeps the same audio for an explicit retry without asking for the microphone again", async () => {
  vi.mocked(transcribeAudio).mockRejectedValueOnce(new Error("offline"));
  const receive = vi.fn();
  const { result } = renderHook(() => useVoiceInput(true, receive));
  await act(async () => {
    await result.current.toggle();
  });
  await act(async () => {
    await result.current.toggle();
  });
  await waitFor(() => expect(result.current.canRetry).toBe(true));
  expect(receive).not.toHaveBeenCalled();
  act(() => result.current.retry());
  await waitFor(() => expect(receive).toHaveBeenCalledOnce());
  expect(getUserMedia).toHaveBeenCalledOnce();
  expect(recordingToWav).toHaveBeenCalledOnce();
  expect(result.current.canRetry).toBe(false);
});

it.each(["cancel", "unmount", "scope"])("ignores late transcriptions after %s", async (mode) => {
  let finish!: (text: string) => void;
  vi.mocked(transcribeAudio).mockReturnValue(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const receive = vi.fn();
  const { result, unmount } = renderHook(() => useVoiceInput(true, receive));
  await act(async () => {
    await result.current.toggle();
  });
  await act(async () => {
    await result.current.toggle();
  });
  const signal = vi.mocked(transcribeAudio).mock.calls[0]![1];
  if (mode === "unmount") unmount();
  else if (mode === "cancel") act(() => result.current.cancel());
  else vi.mocked(voiceScope).mockReturnValue("other:project");
  await act(async () => {
    finish("旧会话文字");
  });
  expect(receive).not.toHaveBeenCalled();
  if (mode !== "scope") expect(signal.aborted).toBe(true);
});

it("cancels pending microphone permission and stops late-granted tracks", async () => {
  let grant!: (value: typeof media) => void;
  getUserMedia.mockReturnValue(
    new Promise((resolve) => {
      grant = resolve;
    }),
  );
  const { result } = renderHook(() => useVoiceInput(true, vi.fn()));
  act(() => {
    void result.current.toggle();
  });
  expect(result.current.phase).toBe("requesting");
  act(() => result.current.cancel());
  await act(async () => grant(media));
  expect(track.stop).toHaveBeenCalledOnce();
  expect(result.current.busy).toBe(false);
  expect(transcribeAudio).not.toHaveBeenCalled();
});

it.each([
  ["NotAllowedError", "麦克风未获授权"],
  ["NotFoundError", "未找到可用"],
])("explains %s without changing the draft", async (name, message) => {
  getUserMedia.mockRejectedValue(new DOMException("", name));
  const receive = vi.fn();
  const { result } = renderHook(() => useVoiceInput(true, receive));
  await act(async () => {
    await result.current.toggle();
  });
  expect(result.current.error).toContain(message);
  expect(receive).not.toHaveBeenCalled();
  expect(result.current.busy).toBe(false);
});

it("automatically stops after 60 seconds", async () => {
  vi.useFakeTimers();
  const { result } = renderHook(() => useVoiceInput(true, vi.fn()));
  await act(async () => {
    await result.current.toggle();
  });
  await act(async () => {
    vi.advanceTimersByTime(60000);
  });
  expect(result.current.listening).toBe(false);
  expect(track.stop).toHaveBeenCalledOnce();
  expect(transcribeAudio).toHaveBeenCalledOnce();
});

it("does not turn silence into a submitted message", async () => {
  vi.mocked(transcribeAudio).mockResolvedValue("");
  const receive = vi.fn();
  const { result } = renderHook(() => useVoiceInput(true, receive));
  await act(async () => {
    await result.current.toggle();
  });
  await act(async () => {
    await result.current.toggle();
  });
  expect(result.current.error).toContain("没有识别到语音");
  expect(result.current.canRetry).toBe(false);
  expect(receive).not.toHaveBeenCalled();
});

it("asks for a new recording when decoding fails instead of retrying unreadable bytes", async () => {
  vi.mocked(recordingToWav).mockRejectedValueOnce(new Error("Invalid data"));
  const receive = vi.fn();
  const { result } = renderHook(() => useVoiceInput(true, receive));
  await act(async () => {
    await result.current.toggle();
  });
  await act(async () => {
    await result.current.toggle();
  });
  expect(result.current.error).toContain("请重新录音");
  expect(result.current.busy).toBe(false);
  expect(result.current.canRetry).toBe(false);
  expect(transcribeAudio).not.toHaveBeenCalled();
});
