"use client";

import { SquarePen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatConversationDate } from "@/lib/formatDate";
import { cn } from "@/lib/utils";
import type { Conversation } from "@/types/conversation";

type ConversationListProps = {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  isLoading?: boolean;
  isSwitching?: boolean;
};

export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onNewChat,
  isLoading = false,
  isSwitching = false,
}: ConversationListProps) {
  return (
    <nav aria-label="Conversations" className="flex h-full min-h-0 flex-col">
      <div className="px-3 pt-3 pb-2">
        <Button
          type="button"
          variant="outline"
          onClick={onNewChat}
          disabled={isLoading || isSwitching}
          className="h-9 w-full justify-start rounded-[4px] border-line bg-transparent"
        >
          <SquarePen aria-hidden />
          New chat
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {isLoading ? (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">
            Loading conversations…
          </p>
        ) : conversations.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">
            No conversations yet.
          </p>
        ) : (
          <ul role="list" className="space-y-0.5">
            {conversations.map((item) => {
              const isActive = item.id === activeId;
              return (
                <li key={item.id}>
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => onSelect(item.id)}
                    disabled={isSwitching}
                    aria-current={isActive ? "page" : undefined}
                    className={cn(
                      "h-auto w-full flex-col items-start gap-0.5 rounded-[4px] px-2.5 py-2 text-left font-normal whitespace-normal",
                      isActive ? "bg-muted text-foreground" : "text-muted-foreground hover:text-foreground"
                    )}
                  >
                    <span className="line-clamp-1 w-full text-sm text-foreground">
                      {item.title ?? "New conversation"}
                    </span>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {formatConversationDate(item.created_at)}
                    </span>
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </nav>
  );
}
