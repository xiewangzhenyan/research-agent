"use client";

import { useState } from "react";
import { useLocale } from "next-intl";
import { toast } from "sonner";

import { Button, FormField, Input } from "@/components/ui";
import { SectionCard } from "@/components/settings/settings-section";
import { useAuth } from "@/hooks";
import { apiClient, ApiError } from "@/lib/api-client";

export default function AccountSettingsPage() {
  const locale = useLocale();
  const isZh = locale === "zh";
  const { logout } = useAuth();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [saving, setSaving] = useState(false);

  const handleChangePassword = async () => {
    if (newPassword.length < 8) {
      toast.error(isZh ? "新密码至少需要 8 个字符" : "New password must be at least 8 characters");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error(isZh ? "两次输入的密码不一致" : "Passwords do not match");
      return;
    }
    setSaving(true);
    try {
      await apiClient.post("/auth/password/change", {
        current_password: currentPassword,
        new_password: newPassword,
      });
      toast.success(isZh ? "密码已更新" : "Password updated");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      // Backend may not have this endpoint yet — surface a helpful message.
      if (err instanceof ApiError && err.status === 404) {
        toast.error(
          isZh
            ? "密码修改功能暂不可用，请联系管理员。"
            : "Password changes are temporarily unavailable. Contact support.",
        );
      } else {
        toast.error(
          err instanceof ApiError
            ? err.message
            : isZh
              ? "更新密码失败"
              : "Failed to update password",
        );
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <SectionCard
        title={isZh ? "修改密码" : "Change password"}
        description={
          isZh
            ? "请使用至少 8 个字符且不与其他网站重复的安全密码。"
            : "Use a strong, unique password with at least 8 characters."
        }
        action={
          <Button
            onClick={handleChangePassword}
            disabled={saving || !currentPassword || !newPassword}
            size="sm"
          >
            {saving ? (isZh ? "保存中…" : "Saving…") : isZh ? "更新密码" : "Update password"}
          </Button>
        }
      >
        <div className="space-y-4">
          <FormField label={isZh ? "当前密码" : "Current password"} htmlFor="current-pw">
            <Input
              id="current-pw"
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              autoComplete="current-password"
            />
          </FormField>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label={isZh ? "新密码" : "New password"} htmlFor="new-pw">
              <Input
                id="new-pw"
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
              />
            </FormField>
            <FormField label={isZh ? "确认新密码" : "Confirm new password"} htmlFor="confirm-pw">
              <Input
                id="confirm-pw"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
              />
            </FormField>
          </div>
        </div>
      </SectionCard>

      <SectionCard
        title={isZh ? "退出当前设备" : "Sign out of this device"}
        description={
          isZh
            ? "当前版本暂不支持管理其他设备的登录状态。"
            : "Managing sessions on other devices is not available."
        }
      >
        <Button variant="outline" onClick={() => logout()}>
          {isZh ? "退出登录" : "Sign out"}
        </Button>
      </SectionCard>
      <SectionCard
        title={isZh ? "删除账户" : "Delete account"}
        description={
          isZh
            ? "目前需要联系站点管理员处理账户删除。"
            : "Contact the site administrator to request account deletion."
        }
      >
        <p className="text-muted-foreground text-sm">
          {isZh ? "自助删除暂未开放。" : "Self-service deletion is not available."}
        </p>
      </SectionCard>
    </div>
  );
}
