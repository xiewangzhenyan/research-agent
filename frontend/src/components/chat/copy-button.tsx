"use client";

import { Button } from "@/components/ui";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import { useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import { useLocale } from "next-intl";

interface CopyButtonProps {
  text: string;
  className?: string;
  size?: "sm" | "default";
}

export function CopyButton({ text, className, size = "sm" }: CopyButtonProps) {
  const zh = useLocale() === "zh";
  const { copy, copied } = useCopyToClipboard();

  const handleCopy = async (e: React.MouseEvent) => {
    e.stopPropagation();
    await copy(text);
  };

  return (
    <Button
      variant="ghost"
      size={size}
      className={cn(
        "h-7 w-7 p-0 opacity-60 transition-opacity group-hover:opacity-100 focus-visible:opacity-100",
        className,
      )}
      onClick={handleCopy}
      title={copied ? (zh ? "已复制" : "Copied!") : zh ? "复制" : "Copy"}
      aria-label={
        copied
          ? zh
            ? "已复制到剪贴板"
            : "Copied to clipboard"
          : zh
            ? "复制到剪贴板"
            : "Copy to clipboard"
      }
    >
      {copied ? (
        <Check className="h-3.5 w-3.5" aria-hidden />
      ) : (
        <Copy className="h-3.5 w-3.5" aria-hidden />
      )}
    </Button>
  );
}
