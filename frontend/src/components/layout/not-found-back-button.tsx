"use client";

import { useRouter } from "next/navigation";

export function NotFoundBackButton() {
  const router = useRouter();
  return (
    <button type="button" className="btn-ghost" onClick={() => router.back()}>
      上一页 · Back
    </button>
  );
}
