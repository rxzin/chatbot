"use client";

import { useState } from "react";
import type { PendingJiraTicketResponse } from "@/lib/api/adminApi";
import { formatConversationDate } from "@/lib/formatDate";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { EmptyPanel } from "./StatePanels";
import { TicketDetailsModal } from "./TicketDetailsModal";

interface TicketTableProps {
  tickets: PendingJiraTicketResponse[];
  onMutate: () => void;
}

export function TicketTable({ tickets, onMutate }: TicketTableProps) {
  const [activeTicket, setActiveTicket] =
    useState<PendingJiraTicketResponse | null>(null);

  const truncateUUID = (uuid: string) => uuid.split("-")[0];

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "approved":
        return (
          <Badge className="border-transparent bg-live/15 text-live hover:bg-live/15">
            Approved
          </Badge>
        );
      case "rejected":
        return <Badge variant="destructive">Rejected</Badge>;
      case "pending":
      default:
        return <Badge variant="secondary">Pending</Badge>;
    }
  };

  if (!tickets || tickets.length === 0) {
    return <EmptyPanel>No pending bug reports.</EmptyPanel>;
  }

  return (
    <div className="rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[100px]">ID</TableHead>
            <TableHead>Title</TableHead>
            <TableHead>Date Created</TableHead>
            <TableHead className="text-right">Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tickets.map((ticket) => (
            <TableRow
              key={ticket.id}
              className="cursor-pointer hover:bg-muted/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              tabIndex={0}
              role="button"
              aria-label={`Review ticket: ${ticket.title}`}
              onClick={() => setActiveTicket(ticket)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setActiveTicket(ticket);
                }
              }}
            >
              <TableCell className="font-mono text-xs text-muted-foreground">
                {truncateUUID(ticket.id)}
              </TableCell>
              <TableCell className="font-medium max-w-[300px] truncate">
                {ticket.title}
              </TableCell>
              <TableCell className="text-muted-foreground whitespace-nowrap">
                {formatConversationDate(ticket.created_at)}
              </TableCell>
              <TableCell className="text-right">
                {getStatusBadge(ticket.status)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <TicketDetailsModal
        ticket={activeTicket}
        onOpenChange={(open) => !open && setActiveTicket(null)}
        onMutate={onMutate}
      />
    </div>
  );
}
