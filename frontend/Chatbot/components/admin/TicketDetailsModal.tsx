"use client";

import { useState } from "react";
import { toast } from "sonner";
import {
  approveTicket,
  rejectTicket,
  type PendingJiraTicketResponse,
} from "@/lib/api/adminApi";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

interface TicketDetailsModalProps {
  ticket: PendingJiraTicketResponse | null;
  onOpenChange: (open: boolean) => void;
  onMutate: () => void; // Used to trigger SWR revalidation
}

type ActionType = "approve" | "reject" | null;

export function TicketDetailsModal({
  ticket,
  onOpenChange,
  onMutate,
}: TicketDetailsModalProps) {
  const [actionType, setActionType] = useState<ActionType>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (!ticket) return null;

  const truncateUUID = (uuid: string) => uuid.split("-")[0];

  const handleAction = async () => {
    if (!actionType) return;

    setIsSubmitting(true);
    try {
      if (actionType === "approve") {
        const res = await approveTicket(ticket.id);
        toast.success(res.message || "Ticket approved successfully.");
      } else {
        const res = await rejectTicket(ticket.id);
        toast.success(res.message || "Ticket rejected successfully.");
      }
      onMutate(); // Trigger revalidation in the parent SWR hook
      onOpenChange(false); // Close the modal
    } catch (error) {
      const err = error as Error;
      toast.error(
        err.message || "An error occurred while processing the ticket.",
      );
    } finally {
      setIsSubmitting(false);
      setActionType(null);
    }
  };

  return (
    <>
      <Dialog
        open={!!ticket && actionType === null}
        onOpenChange={onOpenChange}
      >
        <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle className="font-display text-xl font-medium tracking-[-0.01em]">
              {ticket.title}
            </DialogTitle>
            <DialogDescription>
              Ticket ID: {truncateUUID(ticket.id)} • Reporter:{" "}
              {ticket.user_email}
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto my-4 p-4 border rounded-md bg-muted/20 whitespace-pre-wrap text-sm">
            {ticket.description}
          </div>

          <div className="flex justify-end gap-3 mt-4">
            <Button
              variant="destructive"
              onClick={() => setActionType("reject")}
              disabled={ticket.status !== "pending"}
            >
              Reject Ticket
            </Button>
            <Button
              variant="default"
              onClick={() => setActionType("approve")}
              disabled={ticket.status !== "pending"}
            >
              Approve Ticket
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Confirmation Dialog */}
      <AlertDialog
        open={actionType !== null}
        onOpenChange={(open) => !open && setActionType(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {actionType === "approve" ? "Approve Ticket" : "Reject Ticket"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to {actionType} this ticket?
              {actionType === "approve"
                ? " This will create a Jira issue and notify the reporter via email."
                : " This will dismiss the ticket and notify the reporter via email."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isSubmitting}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              variant={actionType === "approve" ? "default" : "destructive"}
              onClick={(e) => {
                e.preventDefault();
                handleAction();
              }}
              disabled={isSubmitting}
            >
              {isSubmitting ? "Processing..." : `Yes, ${actionType}`}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
