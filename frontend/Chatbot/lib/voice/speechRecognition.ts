export type SpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};

export type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: SpeechRecognitionResultListLike;
};

export type SpeechRecognitionResultListLike = {
  length: number;
  [index: number]: SpeechRecognitionResultLike;
};

export type SpeechRecognitionResultLike = {
  isFinal: boolean;
  length: number;
  [index: number]: { transcript: string };
};

export type SpeechRecognitionErrorEventLike = {
  error: string;
  message?: string;
};

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  }
}

export function getSpeechRecognitionCtor():
  | (new () => SpeechRecognitionLike)
  | undefined {
  if (typeof window === "undefined") return undefined;
  return window.SpeechRecognition ?? window.webkitSpeechRecognition;
}

export function isSpeechRecognitionSupported(): boolean {
  return getSpeechRecognitionCtor() !== undefined;
}

export function normalizeTranscript(text: string): string {
  return text.trim().toLowerCase().replace(/[.,!?]+$/g, "");
}

const YES_PATTERNS = [
  "yes",
  "yeah",
  "yep",
  "yup",
  "sure",
  "ok",
  "okay",
  "affirmative",
];

const NO_PATTERNS = ["no", "nope", "nah", "negative"];

export function parseYesNo(
  transcript: string,
): "yes" | "no" | null {
  const normalized = normalizeTranscript(transcript);
  if (!normalized) return null;

  const tokens = normalized.split(/\s+/);
  const firstWord = tokens[0] ?? normalized;

  if (
    YES_PATTERNS.some(
      (pattern) =>
        normalized === pattern ||
        firstWord === pattern ||
        normalized.startsWith(`${pattern} `),
    )
  ) {
    return "yes";
  }

  if (
    NO_PATTERNS.some(
      (pattern) =>
        normalized === pattern ||
        firstWord === pattern ||
        normalized.startsWith(`${pattern} `),
    )
  ) {
    return "no";
  }

  return null;
}

export function stripMarkdownForSpeech(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " code block ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "")
    .replace(/\[([^\]]+)\]\([^)]*\)/g, "$1")
    // Citation markers like [2] or [1][3] aren't worth reading aloud.
    .replace(/\s?\[\d{1,3}\]/g, "")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/[*_~>#-]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}
