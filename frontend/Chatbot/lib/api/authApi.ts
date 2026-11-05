import {
  API_BASE,
  AUTH_FETCH_INIT,
  authenticatedFetch,
  clearServerSession,
  parseApiError,
  readJson,
  type TokenResponse,
} from "@/lib/api/client";
import {
  clearAccessToken,
  getAccessToken,
  notifyAuthChange,
  setAccessToken,
  subscribeAuthChanges,
} from "@/lib/auth/tokenStorage";
import { clearActiveConversationId } from "@/lib/storage/conversationStorage";
import type { components } from "@/types/api";

export { subscribeAuthChanges };

export type UserMe = components["schemas"]["UserMeResponse"];

/** The permission that gives access to the admin dashboard. */
export const ADMIN_PERMISSION = "ticket:manage";

export async function fetchCurrentUser(): Promise<UserMe> {
  const response = await authenticatedFetch(`${API_BASE}/auth/me`);
  return readJson<UserMe>(response, "Failed to verify session");
}

export async function logout(): Promise<void> {
  const accessToken = getAccessToken();

  // Track whether the server session was actually revoked. fetch() does NOT throw
  // on a 401/4xx, so an expired access token would otherwise silently skip
  // revocation and leave the refresh session alive on the server.
  let revoked = false;
  try {
    if (accessToken) {
      const response = await fetch(`${API_BASE}/auth/logout`, {
        ...AUTH_FETCH_INIT,
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });
      revoked = response.ok;
    }
  } catch {
    // network error — fall back to the auth-free revocation below
  }

  if (!revoked) {
    // No token, an expired/rejected token, or a network failure: revoke the
    // refresh session via the auth-free endpoint (reads the httpOnly cookie).
    await clearServerSession();
  }

  clearAccessToken();
  notifyAuthChange();
  clearActiveConversationId();
}

export async function login(
  email: string,
  password: string
): Promise<TokenResponse> {
  const formData = new URLSearchParams();
  formData.append("username", email);
  formData.append("password", password);

  const response = await fetch(`${API_BASE}/auth/login`, {
    ...AUTH_FETCH_INIT,
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: formData.toString(),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(parseApiError(data, "Login failed"));
  }

  const tokens = data as TokenResponse;
  clearActiveConversationId();
  setAccessToken(tokens.access_token);
  notifyAuthChange();
  return tokens;
}

export async function register(
  email: string,
  password: string
): Promise<void> {
  const response = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(parseApiError(data, "Registration failed"));
  }
}
