import http from "k6/http";
import { check, fail } from "k6";
import { Counter } from "k6/metrics";
import { BASE_URL, USERS, PASSWORD, record } from "./config.js";

export const sessionLogins = new Counter("session_logins");

// Access tokens live 15 minutes; re-login after 10 by default (Review Focus 4).
const maxAgeS = () => parseFloat(__ENV.TOKEN_MAX_AGE_S || "600");

export function userEmail() {
  return `bench${(__VU - 1) % USERS}@example.com`;
}

export function jsonHeaders(token) {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

// Form login. The VU cookie jar keeps the refresh cookie.
export function login(email = userEmail(), step = "login") {
  const res = record(
    http.post(
      `${BASE_URL}/api/auth/login`,
      { username: email, password: PASSWORD },
      { tags: { name: step } },
    ),
  );
  check(res, { [`${step} 200`]: (r) => r.status === 200 });
  return res;
}

// Per-VU state (each VU has its own module instance).
let state = null; // {token, at}
let convIds = null;

function fresh() {
  const res = login(userEmail(), "session_login");
  if (res.status !== 200) fail(`session login failed: ${res.status} ${res.body}`);
  sessionLogins.add(1);
  state = { token: res.json("access_token"), at: Date.now() };
}

// Log in once per VU, and again when the token is older than TOKEN_MAX_AGE_S.
export function session() {
  if (!state || Date.now() - state.at > maxAgeS() * 1000) fresh();
  return { token: state.token, headers: jsonHeaders(state.token) };
}

// The VU's seeded conversation ids, fetched once.
export function conversationIds() {
  const s = session();
  if (convIds) return convIds;
  const res = record(
    http.get(`${BASE_URL}/api/conversations`, { headers: s.headers, tags: { name: "list_conversations" } }),
  );
  check(res, { "list conversations 200": (r) => r.status === 200 });
  convIds = res.json().map((c) => c.id);
  if (convIds.length === 0) fail("no seeded conversations for " + userEmail());
  return convIds;
}
