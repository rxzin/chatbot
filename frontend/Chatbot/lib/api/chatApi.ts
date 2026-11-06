import {
  API_BASE,
  ApiRequestError,
  authenticatedFetch,
  parseApiError,
} from "@/lib/api/client";
import { parseSSEBuffer } from "@/lib/stream/sseParser";
import type { ChatStreamEvent } from "@/types/chat";

/** Every event except "error", which streamChat throws instead. */
export type ChatStreamUpdate = Exclude<ChatStreamEvent, { type: "error" }>;

export type StreamChatParams = {
  message: string;
  conversationId: string;
  signal?: AbortSignal;
  onEvent: (event: ChatStreamUpdate) => void;
};

/**
 * Streams a reply. Resolves after the "done" event; throws on an "error" event, or
 * when the connection ends without "done", so a cut-off reply isn't shown as finished.
 */
export async function streamChat({
  message,
  conversationId,
  signal,
  onEvent,
}: StreamChatParams): Promise<void> {
  const response = await authenticatedFetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, conversationId }),
    signal,
  });

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new ApiRequestError(
      parseApiError(data, `Request failed (${response.status})`),
      response.status
    );
  }

  if (!response.body) {
    throw new Error("No response body from chat stream");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;

  const handle = (events: ChatStreamEvent[]) => {
    for (const event of events) {
      if (finished) return;
      if (event.type === "error") throw new Error(event.error.message);
      if (event.type === "done") finished = true;
      onEvent(event);
    }
  };

  // Read to the end even after "done": the server saves the turn after sending it,
  // and skips saving if the client has already disconnected.
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const { events, remainder } = parseSSEBuffer<ChatStreamEvent>(buffer);
    buffer = remainder;
    handle(events);
  }

  if (buffer.trim()) {
    handle(parseSSEBuffer<ChatStreamEvent>(`${buffer}\n\n`).events);
  }

  if (!finished) {
    throw new Error("The reply was interrupted. Please try again.");
  }
}
