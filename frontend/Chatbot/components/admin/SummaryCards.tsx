"use client";

import {
  Activity,
  AlertTriangle,
  Ban,
  KeyRound,
  TicketCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import useSWR from "swr";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { API_BASE } from "@/lib/api/client";
import { adminFetcher, type AdminSummary } from "@/lib/api/adminApi";

export const SUMMARY_KEY = `${API_BASE}/admin/summary`;

const CARDS: { key: keyof AdminSummary; label: string; icon: LucideIcon }[] = [
  { key: "pending_tickets", label: "Pending bugs", icon: TicketCheck },
  { key: "total_users", label: "Users", icon: Users },
  { key: "banned_users", label: "Banned", icon: Ban },
  { key: "active_sessions", label: "Active sessions", icon: KeyRound },
  { key: "requests_24h", label: "Requests (24h)", icon: Activity },
  { key: "failed_requests_24h", label: "Server errors (24h)", icon: AlertTriangle },
];

export function SummaryCards() {
  const { data, error } = useSWR<AdminSummary>(SUMMARY_KEY, adminFetcher, {
    shouldRetryOnError: false,
    refreshInterval: 30_000,
  });

  if (error) return null;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
      {CARDS.map(({ key, label, icon: Icon }) => (
        <Card key={key} className="gap-2 p-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Icon className="size-3.5 shrink-0" aria-hidden />
            <span className="truncate">{label}</span>
          </div>
          {data ? (
            <p className="text-2xl font-semibold tabular-nums">
              {data[key].toLocaleString()}
            </p>
          ) : (
            <Skeleton className="h-8 w-14" />
          )}
        </Card>
      ))}
    </div>
  );
}
