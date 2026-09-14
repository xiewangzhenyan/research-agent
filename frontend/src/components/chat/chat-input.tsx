"use client";
import { useUnsavedInput } from "@/hooks/use-unsaved-input";

import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import { Badge, Spinner } from "@/components/ui";
import { ArrowUp, Mic, Square, X, FileText, Upload } from "lucide-react";
import Image from "next/image";
import { toast } from "sonner";
import { useLocale, useTranslations } from "next-intl";
import { uploadFile, getFileUrl, type FileUploadResponse } from "@/lib/file-api";
import { getErrorMessage, MAX_UPLOAD_SIZE_MB } from "@/lib/utils";
import {
  BUILTIN_COMMANDS,
  searchCommands,
  type SlashCommand,
  type SlashCommandContext,
} from "./slash-commands";
import { SlashCommandPalette } from "./slash-command-palette";
import { ChatToolsMenu } from "./chat-tools-menu";
import { useVoiceInput } from "@/hooks/use-voice-input";

interface ChatInputProps {
  onSend: (message: string, fileIds?: string[], files?: FileUploadResponse[]) => boolean | void;
  disabled?: boolean;
  isProcessing?: boolean;
  /** When set, a stop control replaces the send button while processing. */
  onStop?: () => void;
  /** Local actions for slash commands. Wire from <ChatContainer>. */
  slashContext?: SlashCommandContext;
  /** Effective slash commands (built-ins + user customs, after overrides). */
  commands?: SlashCommand[];
  controls?: React.ReactNode;
  onPythonChange?: (enabled: boolean) => void;
}

export function ChatInput({
  onSend,
  disabled,
  isProcessing,
  onStop,
  slashContext,
  commands,
  controls,
  onPythonChange,
}: ChatInputProps) {
  const t = useTranslations("chat");
  const isZh = useLocale() === "zh";
  const [message, setMessage] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<FileUploadResponse[]>([]);
  const [isUploading, setIsUploading] = useState(false);
  const voice = useVoiceInput(isZh, (text) => {
    setMessage((draft) => (draft ? `${draft}${/\s$/.test(draft) ? "" : " "}${text}` : text));
  });
  const isListening = voice.listening;
  const voiceBusy = voice.busy;
  const cancelVoice = voice.cancel;
  const composing = useRef(false);
  useUnsavedInput(
    !!message.trim() || attachedFiles.length > 0 || isUploading || voiceBusy || voice.canRetry,
  );
  // Slash-command palette state. Open while message starts with "/" and the
  // caller wired a context — without one, commands have nothing to do.
  const [paletteIndex, setPaletteIndex] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const showPalette = !!slashContext && message.startsWith("/") && !message.includes("\n");
  const allCommands = commands ?? BUILTIN_COMMANDS;
  const filteredCommands = useMemo(
    () => (showPalette ? searchCommands(allCommands, message) : []),
    [showPalette, message, allCommands],
  );

  useEffect(() => {
    setPaletteIndex(0);
  }, [filteredCommands.length, message]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [message]);

  const runSlashCommand = useCallback(
    (cmd: SlashCommand) => {
      if (disabled || isUploading || voiceBusy) return;
      if (cmd.action.kind === "client") {
        cancelVoice();
        cmd.action.run(slashContext!);
        setMessage("");
        return;
      }
      // send-as-message — replace the slash with the canned prompt and send
      // through the normal flow so it lands as a regular user turn.
      const fileIds = attachedFiles.length > 0 ? attachedFiles.map((f) => f.id) : undefined;
      const files = attachedFiles.length > 0 ? attachedFiles : undefined;
      if (onSend(cmd.action.replaceWith, fileIds, files) === false) return;
      cancelVoice();
      setMessage("");
      setAttachedFiles([]);
    },
    [attachedFiles, onSend, slashContext, disabled, isUploading, voiceBusy, cancelVoice],
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (disabled || isUploading || voiceBusy || composing.current) return;
    if (showPalette && filteredCommands[paletteIndex]) {
      runSlashCommand(filteredCommands[paletteIndex]);
      return;
    }
    const trimmed = message.trim();
    if (!trimmed && attachedFiles.length === 0) return;
    if (disabled || isUploading) return;

    const fileIds = attachedFiles.length > 0 ? attachedFiles.map((f) => f.id) : undefined;
    const files = attachedFiles.length > 0 ? attachedFiles : undefined;
    if (
      onSend(
        trimmed || (isZh ? "请分析附件。" : "Analyze the attached file(s)"),
        fileIds,
        files,
      ) === false
    )
      return;
    cancelVoice();
    setMessage("");
    setAttachedFiles([]);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (composing.current || e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (showPalette && filteredCommands.length > 0) {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setPaletteIndex((i) => (i + 1) % filteredCommands.length);
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setPaletteIndex((i) => (i - 1 + filteredCommands.length) % filteredCommands.length);
        return;
      }
      if (e.key === "Tab") {
        // Tab autocompletes to the highlighted command name.
        e.preventDefault();
        const cmd = filteredCommands[paletteIndex];
        if (cmd) setMessage("/" + cmd.name + " ");
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        setMessage("");
        return;
      }
    }
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  // File upload to backend — shared by the file picker and drag-and-drop.
  const uploadFiles = useCallback(
    async (files: File[]) => {
      if (disabled || files.length === 0) return;
      for (const file of files) {
        if (file.size > MAX_UPLOAD_SIZE_MB * 1024 * 1024) {
          toast.error(
            `${file.name}: ${isZh ? `文件过大，最大支持 ${MAX_UPLOAD_SIZE_MB}MB。` : `File too large. Maximum ${MAX_UPLOAD_SIZE_MB}MB.`}`,
          );
          continue;
        }

        setIsUploading(true);
        try {
          const result = await uploadFile(file);
          setAttachedFiles((prev) => [...prev, result]);
        } catch (err) {
          toast.error(`${file.name}: ${getErrorMessage(err, isZh ? "上传失败" : "Upload failed")}`);
        } finally {
          setIsUploading(false);
        }
      }
    },
    [isZh, disabled],
  );

  const handleFileSelect = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files || files.length === 0) return;
      const selected = Array.from(files);
      e.target.value = "";
      await uploadFiles(selected);
    },
    [uploadFiles],
  );

  // Drag-and-drop files anywhere onto the composer. A counter handles nested
  // dragenter/dragleave so the overlay doesn't flicker over child elements.
  const [isDragging, setIsDragging] = useState(false);
  const dragDepth = useRef(0);
  const isFileDrag = (e: React.DragEvent) => Array.from(e.dataTransfer.types).includes("Files");
  const handleDragEnter = (e: React.DragEvent) => {
    if (!isFileDrag(e)) return;
    e.preventDefault();
    dragDepth.current += 1;
    setIsDragging(true);
  };
  const handleDragOver = (e: React.DragEvent) => {
    if (isFileDrag(e)) e.preventDefault();
  };
  const handleDragLeave = (e: React.DragEvent) => {
    if (!isFileDrag(e)) return;
    dragDepth.current -= 1;
    if (dragDepth.current <= 0) {
      dragDepth.current = 0;
      setIsDragging(false);
    }
  };
  const handleDrop = (e: React.DragEvent) => {
    if (!isFileDrag(e)) return;
    e.preventDefault();
    dragDepth.current = 0;
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length) void uploadFiles(files);
  };

  const removeFile = (fileId: string) => {
    setAttachedFiles((prev) => prev.filter((f) => f.id !== fileId));
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="chat-composer relative"
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div className="border-foreground/40 bg-card/95 text-foreground absolute inset-0 z-30 flex items-center justify-center rounded-2xl border-2 border-dashed text-sm font-medium backdrop-blur-sm">
          <span className="flex items-center gap-2">
            <Upload className="h-4 w-4" /> {isZh ? "拖放文件即可添加附件" : "Drop files to attach"}
          </span>
        </div>
      )}
      {showPalette && (
        <SlashCommandPalette
          commands={filteredCommands}
          selectedIndex={paletteIndex}
          onSelectIndex={setPaletteIndex}
          onPick={runSlashCommand}
        />
      )}
      {attachedFiles.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 pb-2">
          {attachedFiles.map((file) => (
            <div key={file.id} className="relative">
              {file.file_type === "image" ? (
                <div className="group relative h-16 w-16 overflow-hidden rounded-lg border">
                  <Image
                    src={getFileUrl(file.id)}
                    alt={file.filename}
                    fill
                    className="object-cover"
                    unoptimized
                  />
                  <button
                    type="button"
                    onClick={() => removeFile(file.id)}
                    className="bg-destructive text-destructive-foreground absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full opacity-0 transition-opacity group-hover:opacity-100"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </div>
              ) : (
                <Badge variant="secondary" className="gap-1.5 pr-1">
                  <FileText className="h-3 w-3" />
                  <span className="max-w-[150px] truncate text-xs">{file.filename}</span>
                  <button
                    type="button"
                    onClick={() => removeFile(file.id)}
                    className="hover:bg-muted ml-0.5 rounded p-0.5"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              )}
            </div>
          ))}
          {isUploading && (
            <div className="flex h-16 w-16 items-center justify-center rounded-lg border border-dashed">
              <Spinner className="text-muted-foreground h-5 w-5" />
            </div>
          )}
        </div>
      )}

      <textarea
        ref={textareaRef}
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        onKeyDown={handleKeyDown}
        onCompositionStart={() => {
          composing.current = true;
        }}
        onCompositionEnd={() => {
          composing.current = false;
        }}
        placeholder={t("sendMessage")}
        aria-label={isZh ? "输入消息" : "Message"}
        disabled={disabled}
        readOnly={isListening}
        rows={2}
        className="composer-textarea placeholder:text-muted-foreground w-full resize-none scrollbar-thin bg-transparent px-4 pt-3 pb-2 text-base disabled:cursor-not-allowed disabled:opacity-50 sm:px-5"
      />
      {voice.error && (
        <div
          role="alert"
          className="text-muted-foreground flex items-start gap-2 px-4 pb-2 text-xs leading-5"
        >
          <span className="flex-1">{voice.error}</span>
          {voice.canRetry && (
            <button
              type="button"
              onClick={voice.retry}
              disabled={disabled}
              className="text-foreground shrink-0 underline underline-offset-2"
            >
              {isZh ? "重试转写" : "Retry transcription"}
            </button>
          )}
          <button
            type="button"
            onClick={voice.clearError}
            aria-label={isZh ? "关闭语音提示" : "Dismiss voice message"}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {voiceBusy && (
        <div className="text-muted-foreground flex items-center gap-2 px-4 pb-2 text-xs">
          <p role="status" className="flex-1">
            {voice.phase === "requesting"
              ? isZh
                ? "请允许使用麦克风…"
                : "Waiting for microphone access…"
              : isListening
                ? isZh
                  ? `正在录音 ${voice.elapsed} / 60 秒 · 结束后转写为文字`
                  : `Recording ${voice.elapsed} / 60 s · Stop to transcribe`
                : isZh
                  ? "正在转写… 完成后可编辑并发送。"
                  : "Transcribing… Review the text before sending."}
          </p>
          <button
            type="button"
            onClick={voice.cancel}
            className="shrink-0 underline underline-offset-2"
          >
            {isZh ? "取消" : "Cancel"}
          </button>
        </div>
      )}
      <div className="composer-toolbar flex items-center gap-1 px-2 pb-2 sm:px-3">
        <ChatToolsMenu
          onAttach={() => fileInputRef.current?.click()}
          onPythonChange={onPythonChange}
          disabled={disabled || isUploading}
        />
        {isUploading && <Spinner className="text-muted-foreground h-4 w-4" />}
        <div className="min-w-0 flex-1">{controls}</div>
        <button
          type="button"
          onClick={() => {
            void voice.toggle();
          }}
          disabled={(disabled && !isListening) || (voiceBusy && !isListening)}
          className="composer-icon"
          aria-pressed={isListening}
          title={
            isListening ? (isZh ? "结束录音" : "Stop recording") : isZh ? "语音输入" : "Voice input"
          }
          aria-label={
            isListening ? (isZh ? "结束录音" : "Stop recording") : isZh ? "语音输入" : "Voice input"
          }
        >
          {isListening ? (
            <Square className="h-4 w-4 fill-current" />
          ) : voiceBusy ? (
            <Spinner className="h-4 w-4" />
          ) : (
            <Mic className="h-5 w-5" />
          )}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          onChange={handleFileSelect}
          accept="image/jpeg,image/png,image/gif,image/webp,.txt,.md,.csv,.json,.py,.js,.ts,.tsx,.html,.css,.yaml,.yml,.toml,.xml,.sql,.sh,.pdf,.docx"
          multiple
          className="hidden"
        />
        {isProcessing && onStop && !message.trim() && attachedFiles.length === 0 ? (
          <button
            type="button"
            onClick={onStop}
            className="composer-send"
            aria-label={isZh ? "停止生成" : "Stop generating"}
          >
            <Square className="h-3.5 w-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="submit"
            disabled={
              disabled ||
              isUploading ||
              voiceBusy ||
              (!message.trim() && attachedFiles.length === 0)
            }
            className="composer-send"
            aria-label={isZh ? "发送消息" : "Send message"}
          >
            <ArrowUp className="h-5 w-5" />
          </button>
        )}
      </div>
    </form>
  );
}
