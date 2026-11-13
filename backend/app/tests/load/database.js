import http from "k6/http";
import { check } from "k6";
import { BASE_URL, options as opts, record } from "./lib/config.js";
import { session, conversationIds } from "./lib/auth.js";

export { handleSummary } from "./lib/summary.js";
export const options = opts("database");

const MIX = __ENV.MIX || "mixed"; // read | write | mixed
if (!["read", "write", "mixed"].includes(MIX)) {
  throw new Error(`MIX must be read|write|mixed, got ${MIX}`);
}

function read(s, ids) {
  const list = record(http.get(`${BASE_URL}/api/conversations`, { headers: s.headers, tags: { name: "list_conversations" } }));
  check(list, { "list 200": (r) => r.status === 200 });
  const id = ids[Math.floor(Math.random() * ids.length)];
  const msgs = record(http.get(`${BASE_URL}/api/conversations/${id}/messages`, { headers: s.headers, tags: { name: "list_messages" } }));
  check(msgs, { "messages 200": (r) => r.status === 200 });
}

function write(s) {
  const res = record(
    http.post(`${BASE_URL}/api/conversations`, JSON.stringify({ title: `k6 ${__VU}-${__ITER}` }), {
      headers: s.headers,
      tags: { name: "create_conversation" },
    }),
  );
  check(res, { "create 201": (r) => r.status === 201 });
}

export default function () {
  const s = session();
  const ids = conversationIds();
  if (MIX === "read") read(s, ids);
  else if (MIX === "write") write(s);
  else if (Math.random() < 0.8) read(s, ids);
  else write(s);
}
