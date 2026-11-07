import {
  API_BASE,
  ApiRequestError,
  authenticatedFetch,
  readJson,
} from "@/lib/api/client";
import type { components } from "@/types/api";

type Schemas = components["schemas"];

export type PendingJiraTicketResponse = Schemas["PendingJiraTicketResponse"];
export type AdminActionResponse = Schemas["AdminActionResponse"];
export type AdminSummary = Schemas["AdminSummaryResponse"];
export type AuditLogEntry = Schemas["AuditLogResponse"];
export type AdminUser = Schemas["AdminUserResponse"];
export type AdminSession = Schemas["AdminSessionResponse"];
export type UsageSummary = Schemas["UsageSummaryResponse"];
export type UsageBreakdown = Schemas["UsageBreakdown"];

export type CursorPage<T> = {
  items: T[];
  next_cursor: string | null;
};

export const adminFetcher = async <T = unknown>(url: string): Promise<T> => {
  const res = await authenticatedFetch(url, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
  return readJson<T>(res, `Failed to fetch data (${res.status})`);
};

export async function approveTicket(ticketId: string): Promise<AdminActionResponse> {
  const res = await authenticatedFetch(`${API_BASE}/admin/approve-ticket/${ticketId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return readJson<AdminActionResponse>(
    res,
    `Failed to approve ticket (${res.status})`
  );
}

export async function rejectTicket(ticketId: string): Promise<AdminActionResponse> {
  const res = await authenticatedFetch(`${API_BASE}/admin/reject-ticket/${ticketId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return readJson<AdminActionResponse>(
    res,
    `Failed to reject ticket (${res.status})`
  );
}

async function adminAction(
  path: string,
  method: "POST" | "DELETE" = "POST"
): Promise<AdminActionResponse> {
  const res = await authenticatedFetch(`${API_BASE}${path}`, { method });
  return readJson<AdminActionResponse>(res, `Request failed (${res.status})`);
}

export const banUser = (userId: string) =>
  adminAction(`/admin/users/${userId}/ban`);

export const unbanUser = (userId: string) =>
  adminAction(`/admin/users/${userId}/unban`);

export const revokeUserSessions = (userId: string) =>
  adminAction(`/admin/users/${userId}/revoke-sessions`);

export const revokeSession = (sessionId: string) =>
  adminAction(`/admin/sessions/${sessionId}`, "DELETE");

export function getAdminErrorMessage(error: unknown): string {
  if (error instanceof ApiRequestError) {
    if (error.status === 401) {
      return "Your session has expired. Please log in again.";
    }
    if (error.status === 403) {
      return "You need admin permissions to access this dashboard.";
    }
  }

  if (error instanceof Error) {
    if (error.message === "Not authenticated") {
      return "Your session has expired. Please log in again.";
    }
    return error.message;
  }

  return "Failed to load data.";
}
