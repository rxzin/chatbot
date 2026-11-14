import http from "k6/http";
import { check, fail } from "k6";
import { BASE_URL, options as opts, record } from "./lib/config.js";
import { login, userEmail, jsonHeaders } from "./lib/auth.js";

export { handleSummary } from "./lib/summary.js";
export const options = opts("auth");

// Every iteration is a fresh login on purpose; the session cache is not used.
export default function () {
  const lr = login(userEmail(), "login");
  if (lr.status !== 200) fail(`login ${lr.status}`);
  const headers = jsonHeaders(lr.json("access_token"));

  const me = record(http.get(`${BASE_URL}/api/auth/me`, { headers, tags: { name: "me" } }));
  check(me, { "me 200": (r) => r.status === 200 });

  // The cookie jar holds the cookie from login; refresh rotates it and each
  // cookie is used once (reuse within 30 s is a 409).
  const rf = record(http.post(`${BASE_URL}/api/auth/refresh`, null, { tags: { name: "refresh" } }));
  check(rf, { "refresh 200": (r) => r.status === 200 });
  const next = rf.status === 200 ? jsonHeaders(rf.json("access_token")) : headers;

  const lo = record(http.post(`${BASE_URL}/api/auth/logout`, null, { headers: next, tags: { name: "logout" } }));
  check(lo, { "logout 200": (r) => r.status === 200 });
}
