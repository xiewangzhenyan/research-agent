"use client";
import { useEffect } from "react";

/** Protect unsubmitted input during project switches and browser navigation. */
export function useUnsavedInput(dirty: boolean) {
  useEffect(() => {
    if (!dirty) return;
    const protect = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, [dirty]);
}
