import type { components } from "@/types/api";

type Schemas = components["schemas"];

export type ChatRole = "user" | "model";

export type SourceReference = Schemas["SourceReference"];

/** One SSE event from POST /api/chat. The stream ends with "done" or "error". */
export type ChatStreamEvent =
  | Schemas["TextDeltaEvent"]
  | Schemas["ToolStartEvent"]
  | Schemas["ToolResultEvent"]
  | Schemas["SourcesEvent"]
  | Schemas["DoneEvent"]
  | Schemas["ErrorEvent"];

/** A stored message's content in display order. */
export type MessagePart = Schemas["TextPart"] | Schemas["SourcesPart"];

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  status?: "streaming" | "done" | "error";
  sources?: SourceReference[];
  /** What the agent is doing right now, e.g. "Searching your documents". Streaming only. */
  activity?: string;
};
