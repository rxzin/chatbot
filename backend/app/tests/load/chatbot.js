import http from "k6/http";
import { check } from "k6";
import { Trend, Rate } from "k6/metrics";
import { BASE_URL, options as opts, record, isLiveChat } from "./lib/config.js";
import { session, conversationIds } from "./lib/auth.js";

export { handleSummary } from "./lib/summary.js";
export { setup } from "./lib/auth.js";

// Paid-call guard: live mode talks to real Mistral and costs money.
if (isLiveChat() && __ENV.CONFIRM_PAID_CALLS !== "yes") {
  throw new Error("CHAT_MODE=live makes paid provider calls. Set CONFIRM_PAID_CALLS=yes to proceed.");
}

const chatTtfb = new Trend("chat_ttfb", true);
const chatDuration = new Trend("chat_duration", true);
const chatIncomplete = new Rate("chat_incomplete");

export const options = opts("chatbot", {
  trends: ["chat_ttfb", "chat_duration"],
  rates: ["chat_incomplete"],
});

// Posts to one of the VU's seeded conversations. k6 reads the whole body, so
// the server never sees a client that leaves before `done`.
export default function (data) {
  const s = session(data);
  const ids = conversationIds();
  const id = ids[(__ITER + __VU) % ids.length];

  const res = record(
    http.post(
      `${BASE_URL}/api/chat`,
      JSON.stringify({ message: `k6 message ${__VU}-${__ITER}`, conversationId: id }),
      {
        headers: { ...s.headers, Accept: "text/event-stream" },
        timeout: "60s",
        tags: { name: "chat" },
      },
    ),
  );
  check(res, { "chat 200": (r) => r.status === 200 });

  const body = typeof res.body === "string" ? res.body : "";
  chatIncomplete.add(!body.includes('"type":"done"'));
  chatTtfb.add(res.timings.waiting);
  chatDuration.add(res.timings.duration);
}
