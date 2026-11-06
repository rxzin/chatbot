import type { components } from "@/types/api";

export type Conversation = {
  id: string;
  title: string | null;
  created_at: string;
};

export type StoredMessage = components["schemas"]["MessageResponse"];
