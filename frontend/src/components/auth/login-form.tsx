"use client";

import { useState } from "react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { ArrowRight, Eye, EyeOff } from "lucide-react";

import { OAuthBlock } from "@/components/auth/oauth-buttons";
import { Button, Input, Label } from "@/components/ui";
import { useAuth } from "@/hooks";
import { authFormErrorKey } from "@/lib/auth-form-errors";
import { ROUTES } from "@/lib/constants";
import { EMAIL_RE } from "@/lib/utils";

export function LoginForm() {
  const t = useTranslations("auth");
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [emailTouched, setEmailTouched] = useState(false);

  const emailValid = !email || EMAIL_RE.test(email);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError("");

    try {
      await login({ email, password });
      toast.success(t("loginSuccess"));
    } catch (err) {
      const message = t(authFormErrorKey(err, "login"));
      setError(message);
      toast.error(message);
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <span className="eyebrow text-foreground/55">{t("welcomeBack")}</span>
        <h1 className="text-foreground">{t("loginHeading")}</h1>
        <p className="text-foreground/65 text-sm">
          {t("noAccount")}{" "}
          <Link
            href={ROUTES.REGISTER}
            className="text-foreground hover:text-foreground/80 font-medium underline-offset-4 hover:underline"
          >
            {t("register")}
          </Link>
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="space-y-1.5">
          <Label
            htmlFor="email"
            className="text-foreground/80 text-xs font-medium tracking-wider uppercase"
          >
            {t("email")}
          </Label>
          <Input
            id="email"
            type="email"
            placeholder={t("emailPlaceholder")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onBlur={() => setEmailTouched(true)}
            required
            disabled={isLoading}
            autoComplete="email"
            className={`h-12 rounded-xl ${emailTouched && email && !emailValid ? "border-destructive" : ""}`}
          />
          {emailTouched && email && !emailValid && (
            <p className="text-destructive text-xs">{t("emailInvalid")}</p>
          )}
        </div>

        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <Label
              htmlFor="password"
              className="text-foreground/80 text-xs font-medium tracking-wider uppercase"
            >
              {t("password")}
            </Label>
            <Link
              href={ROUTES.FORGOT_PASSWORD}
              className="text-foreground/55 hover:text-foreground text-xs font-medium underline-offset-4 hover:underline"
            >
              {t("forgotPassword")}
            </Link>
          </div>
          <div className="relative">
            <Input
              id="password"
              type={showPassword ? "text" : "password"}
              placeholder={t("passwordPlaceholder")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={isLoading}
              autoComplete="current-password"
              className="h-12 rounded-xl pr-12"
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              aria-label={t(showPassword ? "hidePassword" : "showPassword")}
              aria-pressed={showPassword}
              className="text-muted-foreground hover:text-foreground absolute top-0 right-0 flex h-12 w-12 items-center justify-center rounded-r-xl"
              disabled={isLoading}
            >
              {showPassword ? <EyeOff size={18} aria-hidden /> : <Eye size={18} aria-hidden />}
            </button>
          </div>
        </div>

        {error && (
          <p
            role="alert"
            className="border-destructive/30 bg-destructive/5 text-destructive rounded-lg border px-3 py-2 text-sm"
          >
            {error}
          </p>
        )}

        <Button
          type="submit"
          disabled={isLoading}
          className="bg-foreground text-background hover:bg-foreground/90 h-12 w-full rounded-full text-base font-medium"
        >
          {isLoading ? (
            t("loggingIn")
          ) : (
            <>
              {t("login")}
              <ArrowRight className="ml-2 h-4 w-4" />
            </>
          )}
        </Button>
      </form>

      <OAuthBlock label={t("orSignInWith")} />
    </div>
  );
}
