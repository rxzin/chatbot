import type { components } from "@/types/api";

type Schemas = components["schemas"];

export type ChatRole = "user" | "model";

export type SourceReference = Schemas["SourceReference"];
export type WebSource = Schemas["WebSource"];

/** One SSE event from POST /api/chat. The stream ends with "done" or "error". */
export type ChatStreamEvent =
  | Schemas["TextDeltaEvent"]
  | Schemas["ToolStartEvent"]
  | Schemas["ToolResultEvent"]
  | Schemas["SourcesEvent"]
  | Schemas["SuggestionsEvent"]
  | Schemas["TitleEvent"]
  | Schemas["DoneEvent"]
  | Schemas["ErrorEvent"];

/** A stored message's content in display order. */
export type MessagePart =
  | Schemas["TextPart"]
  | Schemas["SourcesPart"]
  | Schemas["SuggestionsPart"];

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  status?: "streaming" | "done" | "error";
  sources?: SourceReference[];
  webSources?: WebSource[];
  /** Follow-up questions; shown under the latest reply only. */
  suggestions?: string[];
  /** What the agent is doing right now, e.g. "Searching your documents". Streaming only. */
  activity?: string;
};
