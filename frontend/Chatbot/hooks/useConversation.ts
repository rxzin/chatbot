"use client";

import { useCallback, useEffect, useState } from "react";
import {
  clearActiveConversationId,
  getActiveConversationId,
  setActiveConversationId,
} from "@/lib/storage/conversationStorage";
import {
  createConversation,
  getConversation,
  listConversations,
} from "@/lib/api/conversationApi";
import type { Conversation } from "@/types/conversation";

export function useConversation() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const applyConversation = useCallback((next: Conversation) => {
    setConversation(next);
    setActiveConversationId(next.id);
    setError(null);
  }, []);

  const selectConversation = useCallback(
    async (id: string) => {
      if (conversation?.id === id) return;

      setError(null);
      const fromList = conversations.find((item) => item.id === id);
      if (fromList) {
        applyConversation(fromList);
        return;
      }

      try {
        const fetched = await getConversation(id);
        applyConversation(fetched);
        setConversations((prev) => {
          if (prev.some((item) => item.id === fetched.id)) return prev;
          return [fetched, ...prev];
        });
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Failed to open conversation";
        setError(message);
      }
    },
    [applyConversation, conversation?.id, conversations]
  );

  const startNewChat = useCallback(async () => {
    setError(null);
    try {
      const created = await createConversation();
      setConversations((prev) => [created, ...prev]);
      applyConversation(created);
      return created;
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to start a new conversation";
      setError(message);
      return null;
    }
  }, [applyConversation]);

  useEffect(() => {
    let cancelled = false;

    async function restoreConversation() {
      setIsLoading(true);
      setError(null);

      try {
        const items = await listConversations();
        if (cancelled) return;

        setConversations(items);

        const storedId = getActiveConversationId();
        if (storedId) {
          const fromList = items.find((item) => item.id === storedId);
          if (fromList) {
            applyConversation(fromList);
            return;
          }

          try {
            const existing = await getConversation(storedId);
            if (!cancelled) {
              applyConversation(existing);
              setConversations((prev) => {
                if (prev.some((item) => item.id === existing.id)) return prev;
                return [existing, ...prev];
              });
            }
            return;
          } catch {
            clearActiveConversationId();
          }
        }

        if (items.length > 0) {
          applyConversation(items[0]);
          return;
        }

        // A new user has no conversations yet: start one so they can type right away.
        // createConversation dedupes concurrent calls, so a double mount makes one.
        const created = await createConversation();
        if (!cancelled) {
          setConversations([created]);
          applyConversation(created);
        }
      } catch (err) {
        if (!cancelled) {
          const message =
            err instanceof Error
              ? err.message
              : "Failed to load conversation";
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    restoreConversation();

    return () => {
      cancelled = true;
    };
  }, [applyConversation]);

  return {
    conversations,
    conversationId: conversation?.id ?? null,
    conversation,
    error,
    isLoading,
    isReady: !isLoading && conversation !== null,
    selectConversation,
    startNewChat,
    conversationKey: conversation?.id ?? "none",
  };
}
