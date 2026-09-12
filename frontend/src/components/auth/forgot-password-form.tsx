"use client";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ArrowLeft, KeyRound } from "lucide-react";
import { ROUTES } from "@/lib/constants";
export function ForgotPasswordForm() {
  const t = useTranslations("auth");
  return (
    <div className="space-y-6">
      <KeyRound className="text-brand h-8 w-8" aria-hidden />
      <h1>{t("forgotHeading")}</h1>
      <p className="text-muted-foreground text-sm leading-7">{t("forgotDescription")}</p>
      <Link className="text-brand inline-flex items-center gap-2 py-2 text-sm" href={ROUTES.LOGIN}>
        <ArrowLeft size={16} aria-hidden />
        {t("backToLogin")}
      </Link>
    </div>
  );
}
