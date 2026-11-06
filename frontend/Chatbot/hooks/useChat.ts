"use client";

import { useCallback, useEffect, useRef, useState, useMemo } from "react";
import { getConversationMessages } from "@/lib/api/conversationApi";
import { streamChat } from "@/lib/api/chatApi";
import { ApiRequestError } from "@/lib/api/client";
import type { ChatMessage, MessagePart, SourceReference } from "@/types/chat";

function createId() {
  return crypto.randomUUID();
}

/** A short status line for a tool the agent started. */
function describeTool(name: string, input: Record<string, unknown>): string {
  switch (name) {
    case "search_documents":
      return "Searching your documents";
    case "get_weather":
      return typeof input.city === "string" && input.city
        ? `Checking the weather in ${input.city}`
        : "Checking the weather";
    case "report_bug":
      return "Filing a bug report";
    default:
      return "Working on it";
  }
}

/** Text and sources for display, from a stored message's parts. */
function fromParts(parts: MessagePart[] | undefined, fallback: string) {
  if (!parts?.length) return { content: fallback, sources: undefined };
  const content = parts
    .flatMap((part) => (part.type === "text" ? [part.text] : []))
    .join("");
  const sources = parts.flatMap((part) =>
    part.type === "sources" ? part.sources : []
  );
  return { content, sources: sources.length ? sources : undefined };
}

export function useChat(conversationId: string | null, conversationKey: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [streamingAssistant, setStreamingAssistant] = useState<ChatMessage | null>(null);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const assistantRef = useRef<{ content: string; sources?: SourceReference[] }>({ content: "" });

  useEffect(() => {
    if (!conversationId) {
      const id = window.setTimeout(() => setMessages([]), 0);
      return () => window.clearTimeout(id);
    }

    let cancelled = false;

    const activeConversationId = conversationId;

    async function loadHistory() {
      setIsLoadingHistory(true);
      setError(null);
      setMessages([]);
      setStreamingAssistant(null);

      try {
        const stored = await getConversationMessages(activeConversationId);
        if (cancelled) return;

        setMessages(
          stored.map((message) => ({
            id: message.id,
            role: message.role === "user" ? "user" : "model",
            ...fromParts(message.parts, message.content),
            status: "done" as const,
          }))
        );
      } catch (err) {
        if (!cancelled) {
          const message =
            err instanceof Error ? err.message : "Failed to load chat history";
          setError(message);
        }
      } finally {
        if (!cancelled) {
          setIsLoadingHistory(false);
        }
      }
    }

    loadHistory();

    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [conversationId, conversationKey]);

  const sendText = useCallback(async (rawText: string) => {
    const text = rawText.trim();
    if (!text || !conversationId || isLoading) return;

    setInput("");
    setError(null);
    setIsLoading(true);

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const userMessage: ChatMessage = {
      id: createId(),
      role: "user",
      content: text,
      status: "done",
    };
    
    // Add user message to historical messages immediately
    setMessages((prev) => [...prev, userMessage]);

    const assistantId = createId();
    assistantRef.current = { content: "" };
    
    // Set up the streaming assistant state
    setStreamingAssistant({
      id: assistantId,
      role: "model",
      content: "",
      status: "streaming",
    });

    try {
      await streamChat({
        message: text,
        conversationId,
        signal: controller.signal,
        onEvent: (event) => {
          switch (event.type) {
            case "text-delta":
              assistantRef.current.content += event.delta;
              setStreamingAssistant((prev) =>
                prev
                  ? { ...prev, content: assistantRef.current.content, activity: undefined }
                  : null
              );
              break;
            case "tool-start":
              setStreamingAssistant((prev) =>
                prev
                  ? { ...prev, activity: describeTool(event.toolName, event.input ?? {}) }
                  : null
              );
              break;
            case "tool-result":
              setStreamingAssistant((prev) =>
                prev ? { ...prev, activity: undefined } : null
              );
              break;
            case "sources":
              assistantRef.current.sources = event.sources;
              break;
            case "done":
              break;
          }
        },
      });

      // Stream completely finished, move from streamingAssistant to messages
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: "model",
          content: assistantRef.current.content,
          status: "done",
          sources: assistantRef.current.sources,
        },
      ]);
      setStreamingAssistant(null);
    } catch (err) {
      if (controller.signal.aborted) return;
      if (err instanceof ApiRequestError && err.status === 401) {
        window.location.href = "/login/";
        return;
      }
      const message =
        err instanceof Error ? err.message : "Failed to send message";
      setError(message);
      setStreamingAssistant((prev) =>
        prev ? { ...prev, status: "error" } : null
      );
      
      // If error occurred, move the errored streaming message to messages list
      setMessages((prev) => [
        ...prev,
        {
          id: assistantId,
          role: "model",
          content: assistantRef.current.content,
          status: "error",
          sources: assistantRef.current.sources,
        },
      ]);
      setStreamingAssistant(null);
    } finally {
      setIsLoading(false);
      abortRef.current = null;
    }
  }, [conversationId, isLoading]);

  const sendMessage = useCallback(async () => {
    await sendText(input);
  }, [input, sendText]);

  const allMessages = useMemo(() => {
    return streamingAssistant ? [...messages, streamingAssistant] : messages;
  }, [messages, streamingAssistant]);

  return {
    messages: allMessages,
    input,
    setInput,
    isLoading,
    isLoadingHistory,
    error,
    sendMessage,
    sendText,
  };
}
