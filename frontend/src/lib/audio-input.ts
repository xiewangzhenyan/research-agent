import { ApiError, refreshAccessToken } from "./api-client";
import { useAuthStore } from "@/stores/auth-store";
import { currentProject } from "./project-scope";

export const MAX_RECORDING_SECONDS = 60;
export const voiceScope = () =>
  `${useAuthStore.getState().user?.id ?? ""}:${currentProject()?.id ?? ""}`;

export interface AudioConfig {
  provider: string;
  enabled: boolean;
  model: string;
  fallback_model: string | null;
  max_duration_seconds: number;
  daily_audio_seconds: number;
}

// The browser decodes/resamples its own WebM/MP4/Opus recording. No server FFmpeg.
export async function recordingToWav(recording: Blob): Promise<Blob> {
  const decoder = new OfflineAudioContext(1, 1, 16000);
  const decoded = await decoder.decodeAudioData(await recording.arrayBuffer());
  return pcmToWav(decoded);
}

export function pcmToWav(audio: AudioBuffer): Blob {
  if (audio.sampleRate !== 16000 || audio.numberOfChannels < 1 || audio.length < 4000)
    throw new Error("Invalid recording");
  // Backgrounded tabs may delay timers; keep the advertised first 60 seconds.
  const frames = Math.min(audio.length, 16000 * MAX_RECORDING_SECONDS);
  const buffer = new ArrayBuffer(44 + frames * 2);
  const view = new DataView(buffer);
  const ascii = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
  };
  ascii(0, "RIFF");
  view.setUint32(4, 36 + frames * 2, true);
  ascii(8, "WAVE");
  ascii(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true);
  view.setUint32(28, 32000, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  ascii(36, "data");
  view.setUint32(40, frames * 2, true);
  const channels = Array.from({ length: audio.numberOfChannels }, (_, i) =>
    audio.getChannelData(i),
  );
  for (let i = 0; i < frames; i++) {
    let sum = 0;
    for (const channel of channels) sum += channel[i] ?? 0;
    const sample = Math.max(-1, Math.min(1, sum / channels.length));
    view.setInt16(44 + i * 2, Math.round(sample * (sample < 0 ? 32768 : 32767)), true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export async function transcribeAudio(audio: Blob, signal: AbortSignal): Promise<string> {
  const scope = voiceScope();
  const check = () => {
    signal.throwIfAborted();
    if (voiceScope() !== scope) throw new DOMException("Scope changed", "AbortError");
  };
  const send = () => {
    check();
    return fetch("/api/audio/transcriptions", {
      method: "POST",
      body: audio,
      headers: { "Content-Type": "audio/wav" },
      cache: "no-store",
      credentials: "include",
      signal,
    });
  };
  let response = await send();
  check();
  if (response.status === 401 && (await refreshAccessToken())) response = await send();
  check();
  const data = await response.json().catch(() => null);
  check();
  if (!response.ok)
    throw new ApiError(
      response.status,
      data?.error?.message || data?.message || data?.detail || "转写失败",
      data,
    );
  if (typeof data?.text !== "string") throw new Error("Invalid transcription response");
  return data.text.trim();
}
