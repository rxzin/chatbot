import http from "k6/http";
import { check, sleep, randomSeed } from "k6";
import { BASE_URL, options as opts, record } from "./lib/config.js";
import { session } from "./lib/auth.js";

export { handleSummary } from "./lib/summary.js";
export const options = opts("conversations");

randomSeed(42);

function think() {
  sleep(1 + Math.random() * 2); // 1-3 s
}

// list conversations -> open one -> read its messages -> 1 in 10 creates one.
export default function () {
  const s = session();

  const list = record(http.get(`${BASE_URL}/api/conversations`, { headers: s.headers, tags: { name: "list_conversations" } }));
  check(list, { "list 200": (r) => r.status === 200 });
  const convs = list.status === 200 ? list.json() : [];
  think();

  if (convs.length > 0) {
    const id = convs[Math.floor(Math.random() * convs.length)].id;
    const one = record(http.get(`${BASE_URL}/api/conversations/${id}`, { headers: s.headers, tags: { name: "get_conversation" } }));
    check(one, { "get 200": (r) => r.status === 200 });
    think();

    const msgs = record(http.get(`${BASE_URL}/api/conversations/${id}/messages`, { headers: s.headers, tags: { name: "list_messages" } }));
    check(msgs, { "messages 200": (r) => r.status === 200 });
    think();
  }

  if (Math.random() < 0.1) {
    const c = record(
      http.post(`${BASE_URL}/api/conversations`, JSON.stringify({ title: `k6 ${__VU}-${__ITER}` }), {
        headers: s.headers,
        tags: { name: "create_conversation" },
      }),
    );
    check(c, { "create 201": (r) => r.status === 201 });
  }
}
