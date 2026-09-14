"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api-client";
import {
  MAX_RECORDING_SECONDS,
  recordingToWav,
  transcribeAudio,
  voiceScope,
} from "@/lib/audio-input";

type Phase = "idle" | "requesting" | "recording" | "transcribing";
type Recording = { raw: Blob; wav?: Blob };

export function useVoiceInput(zh: boolean, onTranscript: (text: string) => void) {
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [canRetry, setCanRetry] = useState(false);
  const receive = useRef(onTranscript);
  receive.current = onTranscript;
  const generation = useRef(0);
  const activePhase = useRef<Phase>("idle");
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const controller = useRef<AbortController | null>(null);
  const recording = useRef<Recording | null>(null);
  const owner = useRef("");
  const changePhase = useCallback((next: Phase) => {
    activePhase.current = next;
    setPhase(next);
  }, []);

  const stopTracks = useCallback(() => {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach((track) => {
      track.onended = null;
      track.stop();
    });
    stream.current = null;
  }, []);
  const release = useCallback(() => {
    generation.current += 1;
    const current = recorder.current;
    recorder.current = null;
    if (current) {
      current.ondataavailable = null;
      current.onstop = null;
      current.onerror = null;
      if (current.state !== "inactive") {
        try {
          current.stop();
        } catch {
          /* Already stopped. */
        }
      }
    }
    stopTracks();
    controller.current?.abort();
    controller.current = null;
    recording.current = null;
    activePhase.current = "idle";
  }, [stopTracks]);
  useEffect(() => release, [release]);
  const cancel = useCallback(() => {
    release();
    setPhase("idle");
    setError(null);
    setCanRetry(false);
    setElapsed(0);
  }, [release]);
  const isCurrent = useCallback(
    (id: number) => generation.current === id && voiceScope() === owner.current,
    [],
  );

  const transcribe = useCallback(
    async (id: number) => {
      const pending = recording.current;
      if (!pending || !isCurrent(id)) return;
      changePhase("transcribing");
      setError(null);
      setCanRetry(false);
      const abort = new AbortController();
      controller.current = abort;
      const deadline = setTimeout(() => abort.abort(), 120000);
      try {
        try {
          pending.wav ??= await recordingToWav(pending.raw);
        } catch {
          if (isCurrent(id)) {
            recording.current = null;
            setError(
              zh
                ? "录音过短或无法读取，请重新录音或更换浏览器。"
                : "Recording is too short or unreadable. Record again or try another browser.",
            );
          }
          return;
        }
        if (!isCurrent(id)) return;
        const text = await transcribeAudio(pending.wav, abort.signal);
        if (!isCurrent(id)) return;
        if (!text) {
          setError(
            zh ? "没有识别到语音，请重新录音。" : "No speech detected. Please record again.",
          );
          recording.current = null;
        } else {
          receive.current(text);
          recording.current = null;
        }
      } catch (e) {
        if (!isCurrent(id)) return;
        setCanRetry(true);
        setError(
          e instanceof ApiError && zh
            ? e.message
            : zh
              ? "语音转写失败或超时，录音已保留，可重试。"
              : "Transcription failed or timed out. Your recording is kept for retry.",
        );
      } finally {
        clearTimeout(deadline);
        if (isCurrent(id)) {
          controller.current = null;
          changePhase("idle");
        }
      }
    },
    [changePhase, isCurrent, zh],
  );

  const stop = useCallback(() => {
    if (recorder.current?.state === "recording") {
      changePhase("transcribing");
      recorder.current.stop();
      stopTracks();
    }
  }, [changePhase, stopTracks]);

  const toggle = useCallback(async () => {
    if (activePhase.current === "recording") {
      stop();
      return;
    }
    if (activePhase.current !== "idle") return;
    release();
    setError(null);
    setCanRetry(false);
    setElapsed(0);
    if (!window.isSecureContext) {
      setError(zh ? "语音输入需要通过 HTTPS 打开网站。" : "Voice input requires HTTPS.");
      return;
    }
    if (
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined" ||
      typeof OfflineAudioContext === "undefined"
    ) {
      setError(
        zh
          ? "当前浏览器不支持录音，请更新浏览器后重试。"
          : "This browser does not support recording. Please update it.",
      );
      return;
    }
    const id = generation.current;
    owner.current = voiceScope();
    changePhase("requesting");
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      if (!isCurrent(id)) {
        media.getTracks().forEach((track) => track.stop());
        return;
      }
      stream.current = media;
      const mime = [
        "audio/webm;codecs=opus",
        "audio/mp4",
        "audio/webm",
        "audio/ogg;codecs=opus",
      ].find((type) => MediaRecorder.isTypeSupported(type));
      const current = new MediaRecorder(media, {
        ...(mime ? { mimeType: mime } : {}),
        audioBitsPerSecond: 64000,
      });
      recorder.current = current;
      const chunks: Blob[] = [];
      let size = 0;
      current.ondataavailable = (event) => {
        if (!isCurrent(id) || !event.data.size) return;
        size += event.data.size;
        if (size > 4 * 1024 * 1024) {
          cancel();
          setError(
            zh ? "录音过长，请分段录制。" : "Recording is too long. Please use shorter clips.",
          );
          return;
        }
        chunks.push(event.data);
      };
      current.onstop = () => {
        if (!isCurrent(id)) return;
        stopTracks();
        recorder.current = null;
        recording.current = { raw: new Blob(chunks, { type: current.mimeType || mime }) };
        void transcribe(id);
      };
      current.onerror = () => {
        if (!isCurrent(id)) return;
        cancel();
        setError(
          zh ? "录音中断，请检查麦克风后重试。" : "Recording interrupted. Check your microphone.",
        );
      };
      media.getTracks().forEach((track) => {
        track.onended = stop;
      });
      current.start(250);
      changePhase("recording");
      const started = Date.now();
      timer.current = setInterval(() => {
        const seconds = Math.floor((Date.now() - started) / 1000);
        setElapsed(Math.min(MAX_RECORDING_SECONDS, seconds));
        if (seconds >= MAX_RECORDING_SECONDS) stop();
      }, 250);
    } catch (e) {
      if (!isCurrent(id)) return;
      release();
      setPhase("idle");
      const name = e instanceof DOMException ? e.name : "";
      setError(
        name === "NotAllowedError"
          ? zh
            ? "麦克风未获授权，请在浏览器的网站设置中允许使用麦克风。"
            : "Allow microphone access in your browser settings."
          : name === "NotFoundError"
            ? zh
              ? "未找到可用的麦克风，请检查设备连接。"
              : "No microphone found. Check your device."
            : zh
              ? "暂时无法录音，请检查麦克风是否被占用。"
              : "Cannot record. Check whether the microphone is in use.",
      );
    }
  }, [cancel, changePhase, isCurrent, release, stop, stopTracks, transcribe, zh]);

  const retry = useCallback(() => {
    if (activePhase.current === "idle" && recording.current) void transcribe(generation.current);
  }, [transcribe]);
  return {
    phase,
    listening: phase === "recording",
    busy: phase !== "idle",
    elapsed,
    error,
    canRetry,
    toggle,
    cancel,
    retry,
    clearError: cancel,
  };
}
