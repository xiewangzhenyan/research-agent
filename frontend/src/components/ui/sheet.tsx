"use client";

import * as React from "react";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { cn } from "@/lib/utils";
import { X } from "lucide-react";

interface SheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
}

interface SheetContentProps {
  children: React.ReactNode;
  className?: string;
  side?: "left" | "right";
}

export function Sheet({ open, onOpenChange, children }: SheetProps) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      {children}
    </DialogPrimitive.Root>
  );
}

export function SheetContent({ children, className, side = "left" }: SheetContentProps) {
  const opener = React.useRef<HTMLElement | null>(null);
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0 fixed inset-0 z-50 bg-black/50 backdrop-blur-[2px]" />
      <DialogPrimitive.Content
        aria-describedby={undefined}
        onOpenAutoFocus={() => {
          opener.current =
            document.activeElement instanceof HTMLElement ? document.activeElement : null;
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          if (opener.current?.isConnected) opener.current.focus();
        }}
        className={cn(
          "bg-background data-[state=open]:animate-in data-[state=closed]:animate-out fixed inset-y-0 z-50 flex w-72 max-w-[90vw] flex-col shadow-[var(--shadow-overlay)] outline-none duration-300",
          side === "left"
            ? "data-[state=open]:slide-in-from-left-full data-[state=closed]:slide-out-to-left-full left-0 border-r"
            : "data-[state=open]:slide-in-from-right-full data-[state=closed]:slide-out-to-right-full right-0 border-l",
          className,
        )}
      >
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function SheetHeader({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex items-center justify-between border-b p-4", className)}>
      {children}
    </div>
  );
}

export function SheetTitle({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <DialogPrimitive.Title className={cn("text-lg font-semibold", className)}>
      {children}
    </DialogPrimitive.Title>
  );
}

export function SheetClose({ onClick, className }: { onClick: () => void; className?: string }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "ring-offset-background rounded-sm opacity-70 transition-opacity",
        "focus:ring-ring hover:opacity-100 focus:ring-2 focus:ring-offset-2 focus:outline-none",
        "flex h-10 w-10 items-center justify-center",
        className,
      )}
    >
      <X className="h-5 w-5" />
      <span className="sr-only">Close</span>
    </button>
  );
}
