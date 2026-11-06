"use client";

import { RefreshCw } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { useCursorPages } from "@/hooks/useCursorPages";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import type { AuditLogEntry } from "@/lib/api/adminApi";
import { API_BASE } from "@/lib/api/client";
import { formatDateTime } from "@/lib/formatDate";
import { EmptyPanel, ErrorPanel, LoadingPanel } from "./StatePanels";

const ALL = "all";
const METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];
const STATUS_CLASSES = ["2xx", "3xx", "4xx", "5xx"];

function StatusBadge({ code }: { code: number }) {
  if (code >= 500) return <Badge variant="destructive">{code}</Badge>;
  if (code >= 400) return <Badge variant="secondary">{code}</Badge>;
  return <Badge className="border-transparent bg-live/15 text-live hover:bg-live/15 tabular-nums">{code}</Badge>;
}

export function AuditLogTab() {
  const [email, setEmail] = useState("");
  const [path, setPath] = useState("");
  const [method, setMethod] = useState(ALL);
  const [statusClass, setStatusClass] = useState(ALL);
  const debouncedEmail = useDebouncedValue(email);
  const debouncedPath = useDebouncedValue(path);

  const { items, hasMore, error, isLoading, isValidating, loadMore, refresh } =
    useCursorPages<AuditLogEntry>(`${API_BASE}/admin/audit-logs`, {
      email: debouncedEmail,
      path: debouncedPath,
      method: method === ALL ? undefined : method,
      status_class: statusClass === ALL ? undefined : statusClass,
    });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Input
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="Filter by user email"
          aria-label="Filter by user email"
          className="w-full sm:w-56"
        />
        <Input
          value={path}
          onChange={(event) => setPath(event.target.value)}
          placeholder="Filter by path"
          aria-label="Filter by path"
          className="w-full sm:w-48"
        />
        <Select value={method} onValueChange={setMethod}>
          <SelectTrigger aria-label="Filter by method" className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All methods</SelectItem>
            {METHODS.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={statusClass} onValueChange={setStatusClass}>
          <SelectTrigger aria-label="Filter by status" className="w-32">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All statuses</SelectItem>
            {STATUS_CLASSES.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          variant="outline"
          size="sm"
          className="sm:ml-auto"
          onClick={() => refresh()}
          disabled={isValidating}
        >
          <RefreshCw className={isValidating ? "animate-spin" : undefined} />
          Refresh
        </Button>
      </div>

      {error ? (
        <ErrorPanel error={error} onRetry={() => refresh()} />
      ) : isLoading ? (
        <LoadingPanel rows={8} />
      ) : items.length === 0 ? (
        <EmptyPanel>No requests match these filters.</EmptyPanel>
      ) : (
        <>
          <div className="rounded-lg border bg-card">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Time</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Method</TableHead>
                  <TableHead>Path</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Duration</TableHead>
                  <TableHead>IP</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="whitespace-nowrap text-muted-foreground">
                      {formatDateTime(entry.created_at)}
                    </TableCell>
                    <TableCell className="max-w-52 truncate">
                      {entry.user_email ?? (
                        <span className="text-muted-foreground">Anonymous</span>
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {entry.method}
                    </TableCell>
                    <TableCell
                      className="max-w-72 truncate font-mono text-xs"
                      title={entry.path}
                    >
                      {entry.path}
                    </TableCell>
                    <TableCell>
                      <StatusBadge code={entry.status_code} />
                    </TableCell>
                    <TableCell className="text-right tabular-nums text-muted-foreground">
                      {entry.duration_ms.toLocaleString()} ms
                    </TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {entry.ip_address ?? "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-muted-foreground">
              Duration for streamed replies is the time until streaming starts.
              New requests can take a few seconds to appear.
            </p>
            {hasMore && (
              <Button
                variant="outline"
                size="sm"
                onClick={loadMore}
                disabled={isValidating}
              >
                Load more
              </Button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
