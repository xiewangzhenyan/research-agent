"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { ArrowRight, Check, X } from "lucide-react";

import { OAuthBlock } from "@/components/auth/oauth-buttons";
import { Button, Input, Label } from "@/components/ui";
import { useAuth } from "@/hooks";
import { authFormErrorKey } from "@/lib/auth-form-errors";
import { ROUTES } from "@/lib/constants";
import { EMAIL_RE, getPasswordStrength } from "@/lib/utils";

export function RegisterForm() {
  const t = useTranslations("auth");
  const router = useRouter();
  const { register } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [emailTouched, setEmailTouched] = useState(false);

  const emailValid = !email || EMAIL_RE.test(email);
  const strength = useMemo(() => getPasswordStrength(password), [password]);
  const passwordsMatch = !confirmPassword || password === confirmPassword;
  const passwordLongEnough = !password || password.length >= 8;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!EMAIL_RE.test(email)) {
      setError(t("emailInvalid"));
      return;
    }
    if (password.length < 8) {
      setError(t("resetPassword.minLength"));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("passwordMismatch"));
      toast.error(t("passwordMismatch"));
      return;
    }

    setIsLoading(true);
    try {
      await register({ email, password, full_name: name || undefined });
      toast.success(t("registerSuccess"));
      router.push(ROUTES.LOGIN + "?registered=true");
    } catch (err) {
      const message = t(authFormErrorKey(err, "register"));
      setError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <span className="eyebrow text-foreground/55">{t("getStarted")}</span>
        <h1 className="text-foreground">{t("registerHeading")}</h1>
        <p className="text-foreground/65 text-sm">
          {t("hasAccount")}{" "}
          <Link
            href={ROUTES.LOGIN}
            className="text-foreground hover:text-foreground/80 font-medium underline-offset-4 hover:underline"
          >
            {t("login")}
          </Link>
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-5">
        <div className="space-y-1.5">
          <Label
            htmlFor="name"
            className="text-foreground/80 text-xs font-medium tracking-wider uppercase"
          >
            {t("nameOptional")}
          </Label>
          <Input
            id="name"
            type="text"
            placeholder={t("namePlaceholder")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={isLoading}
            autoComplete="name"
            className="h-12 rounded-xl"
          />
        </div>

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
          <Label
            htmlFor="password"
            className="text-foreground/80 text-xs font-medium tracking-wider uppercase"
          >
            {t("password")}
          </Label>
          <Input
            id="password"
            type="password"
            placeholder={t("passwordHint")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            disabled={isLoading}
            autoComplete="new-password"
            className={`h-12 rounded-xl ${password && !passwordLongEnough ? "border-destructive" : ""}`}
          />
          {password && (
            <div className="space-y-1.5 pt-1">
              <div className="flex gap-1">
                {[1, 2, 3, 4].map((i) => (
                  <div
                    key={i}
                    className={`h-1 flex-1 rounded-full transition-colors ${
                      i <= strength.score ? strength.color : "bg-foreground/10"
                    }`}
                  />
                ))}
              </div>
              <div className="flex items-center justify-between">
                <p className="text-foreground/55 font-mono text-[11px] tracking-wider uppercase">
                  {t(
                    `resetPassword.${strength.score <= 1 ? "strengthWeak" : strength.score === 2 ? "strengthFair" : strength.score === 3 ? "strengthGood" : "strengthStrong"}`,
                  )}
                </p>
                <div className="flex items-center gap-1.5 text-xs">
                  {password.length >= 8 ? (
                    <span className="text-brand inline-flex items-center gap-1">
                      <Check className="h-3 w-3" />
                      {t("passwordMinimum")}
                    </span>
                  ) : (
                    <span className="text-foreground/55 inline-flex items-center gap-1">
                      <X className="h-3 w-3" />
                      {t("passwordMinimum")}
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="space-y-1.5">
          <Label
            htmlFor="confirmPassword"
            className="text-foreground/80 text-xs font-medium tracking-wider uppercase"
          >
            {t("confirmPassword")}
          </Label>
          <Input
            id="confirmPassword"
            type="password"
            placeholder={t("repeatPassword")}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
            disabled={isLoading}
            autoComplete="new-password"
            className={`h-12 rounded-xl ${confirmPassword && !passwordsMatch ? "border-destructive" : ""}`}
          />
          {confirmPassword && !passwordsMatch && (
            <p className="text-destructive inline-flex items-center gap-1 text-xs">
              <X className="h-3 w-3" />
              {t("passwordMismatch")}
            </p>
          )}
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
            t("creatingAccount")
          ) : (
            <>
              {t("register")}
              <ArrowRight className="ml-2 h-4 w-4" />
            </>
          )}
        </Button>

        <p className="text-foreground/50 text-center text-xs">
          <Link href={ROUTES.HELP} className="underline underline-offset-4">
            {t("usageHelp")}
          </Link>
        </p>
      </form>

      <OAuthBlock label={t("orSignUpWith")} variant="signup" />
    </div>
  );
}
