"use client";

import { useEffect, useState } from "react";
import { useCopyToClipboard } from "@/hooks/use-copy-to-clipboard";
import { Copy, Link2, Loader2, Trash2, UserPlus } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { useLocale, useTranslations } from "next-intl";
import { useConversationShares } from "@/hooks";
import type { ConversationShare } from "@/types";
import { getErrorMessage } from "@/lib/utils";

interface ShareDialogProps {
  conversationId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ShareDialog({ conversationId, open, onOpenChange }: ShareDialogProps) {
  const t = useTranslations("chat");
  const zh = useLocale() === "zh";
  const { shares, isLoading, shareConversation, fetchShares, revokeShare } =
    useConversationShares();
  const [email, setEmail] = useState("");
  const [permission, setPermission] = useState<"view" | "edit">("view");
  const [shareLink, setShareLink] = useState<string | null>(null);
  const { copy, copied } = useCopyToClipboard();
  const [isSharing, setIsSharing] = useState(false);
  const [isGeneratingLink, setIsGeneratingLink] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);

  useEffect(() => {
    if (open && conversationId) {
      fetchShares(conversationId);
    }
  }, [open, conversationId, fetchShares]);

  const handleShare = async () => {
    if (!email.trim()) return;
    setIsSharing(true);
    try {
      await shareConversation(conversationId, {
        shared_with: email.trim(),
        permission,
      });
      setEmail("");
      toast.success(t("conversationShared"));
    } catch (err) {
      toast.error(getErrorMessage(err, t("failedToShare")));
    } finally {
      setIsSharing(false);
    }
  };

  const handleGenerateLink = async () => {
    setIsGeneratingLink(true);
    try {
      const share = await shareConversation(conversationId, {
        generate_link: true,
        permission,
      });
      if (share?.share_token) {
        const url = `${window.location.origin}/shared/${share.share_token}`;
        setShareLink(url);
        toast.success(t("linkGenerated"));
      }
    } catch (err) {
      toast.error(getErrorMessage(err, t("failedToGenerateLink")));
    } finally {
      setIsGeneratingLink(false);
    }
  };

  const handleCopyLink = async () => {
    if (shareLink) {
      await copy(shareLink);
      toast.success(t("copyLink"));
    }
  };

  const handleRevoke = async (share: ConversationShare) => {
    setRevokingId(share.id);
    try {
      await revokeShare(conversationId, share.id);
      toast.success(t("accessRevoked"));
    } catch (err) {
      toast.error(getErrorMessage(err, t("failedToRevoke")));
    } finally {
      setRevokingId(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("shareConversation")}</DialogTitle>
          <DialogDescription>{t("shareDescription")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex gap-2">
            <Input
              placeholder={t("userIdOrEmail")}
              aria-label={t("userIdOrEmail")}
              className="min-w-0 flex-1"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleShare()}
            />
            <Select value={permission} onValueChange={(v) => setPermission(v as "view" | "edit")}>
              <SelectTrigger
                className="w-24 shrink-0"
                aria-label={zh ? "分享权限" : "Share permission"}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="view">{zh ? "可查看" : "View"}</SelectItem>
                <SelectItem value="edit">{zh ? "可编辑" : "Edit"}</SelectItem>
              </SelectContent>
            </Select>
            <Button
              onClick={handleShare}
              disabled={isLoading || isSharing}
              size="icon"
              aria-label={t("shareConversation")}
              className="shrink-0"
            >
              {isSharing ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
              ) : (
                <UserPlus className="h-4 w-4" aria-hidden />
              )}
            </Button>
          </div>

          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={handleGenerateLink}
              disabled={isLoading || isGeneratingLink}
              className="flex-1"
            >
              {isGeneratingLink ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Link2 className="mr-2 h-4 w-4" />
              )}
              {t("generateShareLink")}
            </Button>
            {shareLink && (
              <Button
                variant="secondary"
                size="icon"
                onClick={handleCopyLink}
                aria-label={t("copyLink")}
              >
                <Copy className="h-4 w-4" aria-hidden />
              </Button>
            )}
          </div>
          {shareLink && (
            <p className="text-muted-foreground text-xs break-all">
              {copied ? (zh ? "已复制" : "Copied!") : shareLink}
            </p>
          )}

          {shares.length > 0 && (
            <div className="space-y-2">
              <p className="text-sm font-medium">{t("sharedWith")}</p>
              {shares.map((share) => (
                <div
                  key={share.id}
                  className="flex items-center justify-between rounded-md border p-2"
                >
                  <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
                    <span className="min-w-0 text-sm break-all">
                      {share.shared_with_email || share.shared_with || (zh ? "链接" : "Link")}
                    </span>
                    <Badge variant="secondary">
                      {share.permission === "edit"
                        ? zh
                          ? "可编辑"
                          : "Edit"
                        : zh
                          ? "可查看"
                          : "View"}
                    </Badge>
                    {share.share_token && <Badge variant="outline">{zh ? "链接" : "Link"}</Badge>}
                  </div>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleRevoke(share)}
                    disabled={revokingId === share.id}
                    className="h-8 w-8 shrink-0"
                    aria-label={t("revokeAccess")}
                  >
                    {revokingId === share.id ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
