"use client";

import { ChatContainer } from "@/components/chat";

export default function ChatPage() {
  // Selection restores from the URL or account/project history; useChat loads the transcript.
  return (
    <div className="console-chat-layout flex min-h-0 flex-1">
      <div className="min-w-0 flex-1">
        <ChatContainer />
      </div>
    </div>
  );
}
