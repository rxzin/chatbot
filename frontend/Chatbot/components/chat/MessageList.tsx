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
  // The container is always rendered, so auto-scroll can attach to it from the start.
  const containerRef = useAutoScroll<HTMLDivElement>([messages]);

  return (
    <div
      ref={containerRef}
      className="flex min-h-0 flex-1 flex-col overflow-y-auto"
    >
      {messages.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-5 px-4 py-6">
          {messages.map((message) => (
            <MessageBubble
              key={message.id}
              message={message}
              onSuggestion={message.id === lastId ? onSuggestion : undefined}
              suggestionsDisabled={suggestionsDisabled}
            />
          ))}
        </div>
      )}
    </div>
  );
}
