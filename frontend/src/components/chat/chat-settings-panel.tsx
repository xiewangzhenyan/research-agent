"use client";

import { useEffect, useState, type ReactNode } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useLocale } from "next-intl";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui";

export function ChatSettingsPanel({
  trigger,
  children,
}: {
  trigger: ReactNode;
  children: ReactNode;
}) {
  const zh = useLocale() === "zh";
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 639px)");
    const update = () => setMobile(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  if (mobile)
    return (
      <Dialog.Root>
        <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/35" />
          <Dialog.Content
            aria-describedby={undefined}
            className="bg-popover text-foreground fixed inset-x-0 bottom-0 z-50 max-h-[85dvh] overflow-y-auto rounded-t-3xl pb-[env(safe-area-inset-bottom)] shadow-xl"
          >
            <div className="flex items-center justify-between px-4 pt-3 pb-1">
              <Dialog.Title className="text-sm font-medium">
                {zh ? "模型与回答设置" : "Model and response settings"}
              </Dialog.Title>
              <Dialog.Close
                className="composer-icon"
                aria-label={zh ? "关闭设置" : "Close settings"}
              >
                <X className="h-4 w-4" />
              </Dialog.Close>
            </div>
            {children}
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    );
  return (
    <Popover>
      <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      <PopoverContent
        align="start"
        side="top"
        sideOffset={12}
        className="bg-popover w-[min(380px,calc(100vw-24px))] overflow-hidden rounded-2xl p-0 shadow-lg"
      >
        {children}
      </PopoverContent>
    </Popover>
  );
}
