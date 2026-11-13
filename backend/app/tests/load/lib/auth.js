import http from "k6/http";
import { check, fail } from "k6";
import { Counter } from "k6/metrics";
import { BASE_URL, USERS, PASSWORD, PROFILE, record } from "./config.js";

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

// Rate runs start iterations on up to maxVUs fresh VUs at once. If each one logged
// in (an Argon2 hash) on its first iteration, the first minute would measure a
// login storm, not the workload. So for rate runs, setup() logs every seeded user
// in before the test starts, and VUs take their user's token and conversations.
// Ramp runs add VUs gradually and keep logging in themselves.
export function setup() {
  if (PROFILE !== "rate") return {};
  const users = [];
  for (let i = 0; i < USERS; i++) {
    const res = login(`bench${i}@example.com`, "setup_login");
    if (res.status !== 200) fail(`setup login failed for user ${i}: ${res.status}`);
    const token = res.json("access_token");
    const list = http.get(`${BASE_URL}/api/conversations`, {
      headers: jsonHeaders(token),
      tags: { name: "setup_conversations" },
    });
    if (list.status !== 200) fail(`setup conversations failed for user ${i}: ${list.status}`);
    users.push({ token, ids: list.json().map((c) => c.id) });
  }
  return { users, at: Date.now() };
}

// Log in once per VU, and again when the token is older than TOKEN_MAX_AGE_S.
// data is what setup() returned; a pooled token is used instead of logging in.
export function session(data) {
  if (!state && data && data.users) {
    const u = data.users[(__VU - 1) % USERS];
    state = { token: u.token, at: data.at };
    if (u.ids.length > 0) convIds = u.ids;
  }
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
