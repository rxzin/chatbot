"use client";

import { RefreshCw } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { adminFetcher, type UsageBreakdown, type UsageSummary } from "@/lib/api/adminApi";
import { API_BASE } from "@/lib/api/client";
import { EmptyPanel, ErrorPanel, LoadingPanel } from "./StatePanels";

const WINDOWS = [
  { value: "7", label: "Last 7 days" },
  { value: "30", label: "Last 30 days" },
  { value: "90", label: "Last 90 days" },
];

const PURPOSES: Record<string, string> = {
  agent: "Agent replies and tool steps",
  suggestions: "Suggested questions",
  title: "Conversation titles",
  summary: "Memory summaries",
  other: "Other",
};

const number = new Intl.NumberFormat("en", { maximumFractionDigits: 0 });
const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 });
const percent = new Intl.NumberFormat("en", { style: "percent", maximumFractionDigits: 1 });

function Kpi({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card className="gap-1.5 p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p
        className="font-display text-2xl font-medium tracking-[-0.02em] tabular-nums"
        title={hint}
      >
        {value}
      </p>
      {hint ? <p className="text-xs text-muted-foreground tabular-nums">{hint}</p> : null}
    </Card>
  );
}

function BreakdownTable({
  caption,
  rows,
  label,
}: {
  caption: string;
  rows: UsageBreakdown[];
  label: (key: string) => string;
}) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-medium">{caption}</h3>
      <div className="overflow-hidden rounded-[10px] border border-line">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{caption.startsWith("By model") ? "Model" : "Purpose"}</TableHead>
              <TableHead className="text-right">Calls</TableHead>
              <TableHead className="text-right">Input</TableHead>
              <TableHead className="text-right">Output</TableHead>
              <TableHead className="text-right">Total</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.key}>
                <TableCell>{label(row.key)}</TableCell>
                <TableCell className="text-right tabular-nums">{number.format(row.calls)}</TableCell>
                <TableCell className="text-right tabular-nums">{number.format(row.prompt_tokens)}</TableCell>
                <TableCell className="text-right tabular-nums">{number.format(row.completion_tokens)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {number.format(row.prompt_tokens + row.completion_tokens)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

/** Token usage of every model call: headline numbers and breakdowns. */
export function UsageTab() {
  const [days, setDays] = useState("30");
  const { data, error, isLoading, mutate } = useSWR<UsageSummary>(
    `${API_BASE}/admin/usage?days=${days}`,
    adminFetcher,
    { refreshInterval: 60_000 },
  );
  const windowLabel = WINDOWS.find((w) => w.value === days)?.label.toLowerCase() ?? `last ${days} days`;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-2">
        <Select value={days} onValueChange={setDays}>
          <SelectTrigger aria-label="Time window" className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {WINDOWS.map((w) => (
              <SelectItem key={w.value} value={w.value}>
                {w.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" size="sm" onClick={() => mutate()} disabled={isLoading}>
          <RefreshCw aria-hidden />
          Refresh
        </Button>
        <p className="ml-auto text-xs text-muted-foreground">
          Tokens counted by Mistral for each model call. Embeddings for document search are not included.
        </p>
      </div>

      {error ? (
        <ErrorPanel error={error} onRetry={() => mutate()} />
      ) : !data ? (
        <LoadingPanel rows={4} />
      ) : data.model_calls_window === 0 ? (
        <EmptyPanel>No model calls in the {windowLabel}.</EmptyPanel>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            <Kpi label="Tokens today" value={compact.format(data.tokens_today)} hint={`${number.format(data.tokens_today)} tokens`} />
            <Kpi label="Tokens, last 7 days" value={compact.format(data.tokens_7d)} hint={`${number.format(data.tokens_7d)} tokens`} />
            <Kpi
              label={`Tokens, ${windowLabel}`}
              value={compact.format(data.tokens_window)}
              hint={`${percent.format(data.tokens_window ? data.prompt_tokens_window / data.tokens_window : 0)} input · ${percent.format(data.tokens_window ? data.completion_tokens_window / data.tokens_window : 0)} output`}
            />
            <Kpi label="Average per reply" value={number.format(data.avg_tokens_per_reply)} hint={`${number.format(data.replies_window)} replies`} />
            <Kpi label="Model calls" value={number.format(data.model_calls_window)} hint={`${(data.replies_window ? data.model_calls_window / data.replies_window : 0).toFixed(1)} per reply`} />
            <Kpi label="Active users" value={number.format(data.active_users_window)} />
            <Kpi label="Fallback model share" value={percent.format(data.fallback_share)} hint="Calls answered by the fallback model" />
            <Kpi label="Output tokens" value={compact.format(data.completion_tokens_window)} hint={`${number.format(data.completion_tokens_window)} written by the model`} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <BreakdownTable caption="By purpose" rows={data.by_purpose} label={(k) => PURPOSES[k] ?? k} />
            <BreakdownTable caption="By model" rows={data.by_model} label={(k) => k} />
          </div>

          <div className="space-y-2">
            <h3 className="text-sm font-medium">Top users</h3>
            <div className="overflow-hidden rounded-[10px] border border-line">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>User</TableHead>
                    <TableHead className="text-right">Model calls</TableHead>
                    <TableHead className="text-right">Tokens</TableHead>
                    <TableHead className="text-right">Share</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.top_users.map((u) => (
                    <TableRow key={u.user_id}>
                      <TableCell className="max-w-64 truncate">
                        {u.email ?? <span className="text-muted-foreground">Deleted user</span>}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{number.format(u.calls)}</TableCell>
                      <TableCell className="text-right tabular-nums">{number.format(u.total_tokens)}</TableCell>
                      <TableCell className="text-right tabular-nums text-muted-foreground">
                        {percent.format(data.tokens_window ? u.total_tokens / data.tokens_window : 0)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
