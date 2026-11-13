import http from "k6/http";
import { check } from "k6";
import { BASE_URL, options as opts, record } from "./lib/config.js";
import { session } from "./lib/auth.js";

export { handleSummary } from "./lib/summary.js";
export const options = opts("health");

export default function () {
  const s = session();

  const health = record(http.get(`${BASE_URL}/health/`, { tags: { name: "health" } }));
  check(health, { "health 200": (r) => r.status === 200 });

  const me = record(http.get(`${BASE_URL}/api/auth/me`, { headers: s.headers, tags: { name: "me" } }));
  check(me, { "me 200": (r) => r.status === 200 });
}
