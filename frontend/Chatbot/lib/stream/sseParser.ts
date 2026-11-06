/** Splits complete SSE frames off the buffer and parses each "data:" line as JSON. */
export function parseSSEBuffer<T>(buffer: string): {
  events: T[];
  remainder: string;
} {
  const parts = buffer.split("\n\n");
  const remainder = parts.pop() ?? "";
  const events: T[] = [];

  for (const part of parts) {
    const line = part
      .split("\n")
      .map((l) => l.trim())
      .find((l) => l.startsWith("data:"));
    if (!line) continue;

    const json = line.slice(5).trim();
    if (!json) continue;

    try {
      events.push(JSON.parse(json) as T);
    } catch {
      // Stay resilient (don't break the stream) but surface the dropped frame
      // so a malformed error/data chunk is observable instead of silent.
      console.warn("Discarded malformed SSE chunk", json);
    }
  }

  return { events, remainder };
}
