"use client";

import type { ChatMessage } from "@/types/chat";
import { useAutoScroll } from "@/hooks/useAutoScroll";
import { EmptyState } from "./EmptyState";
import { MessageBubble } from "./MessageBubble";

type MessageListProps = {
  messages: ChatMessage[];
  /** Sends a suggested question. Suggestions only show under the latest reply. */
  onSuggestion?: (text: string) => void;
  suggestionsDisabled?: boolean;
};

export function MessageList({
  messages,
  onSuggestion,
  suggestionsDisabled = false,
}: MessageListProps) {
  const lastId = messages.at(-1)?.id;

  const bottomRef = useAutoScroll<HTMLDivElement>([messages]);

  if (messages.length === 0) {
    return <EmptyState />;
  }

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-4 py-6">
      {messages.map((message) => (
        <MessageBubble
          key={message.id}
          message={message}
          onSuggestion={message.id === lastId ? onSuggestion : undefined}
          suggestionsDisabled={suggestionsDisabled}
        />
      ))}
      <div ref={bottomRef} className="h-px shrink-0" aria-hidden />
    </div>
  );
}
