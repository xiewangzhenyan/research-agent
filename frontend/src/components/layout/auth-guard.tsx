"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores";
import { runAuthCheck } from "@/hooks/use-auth";
import { ROUTES } from "@/lib/constants";
import { Spinner } from "@/components/ui";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { isAuthenticated, setUser } = useAuthStore();
  const [checking, setChecking] = useState(!isAuthenticated);

  useEffect(() => {
    if (isAuthenticated) return;

    const verify = async () => {
      await runAuthCheck(setUser);
      if (!useAuthStore.getState().isAuthenticated) router.replace(ROUTES.LOGIN);
      setChecking(false);
    };

    verify();
  }, [isAuthenticated, router, setUser]);

  if (checking && !isAuthenticated) {
    return (
      <div className="flex h-screen items-center justify-center" role="status" aria-live="polite">
        <Spinner className="text-muted-foreground h-6 w-6" />
        <span className="sr-only">Checking authentication...</span>
      </div>
    );
  }

  return isAuthenticated ? <>{children}</> : null;
}
