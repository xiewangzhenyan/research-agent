import { Suspense } from "react";

import { LoadingState } from "@/components/states";

// Both pages read their token from the query string, which only exists in the browser,
// so the prerendered shell shows the loading state until the client takes over.
export default function AuthRedirectLayout({ children }: { children: React.ReactNode }) {
  return <Suspense fallback={<LoadingState className="min-h-screen" />}>{children}</Suspense>;
}
