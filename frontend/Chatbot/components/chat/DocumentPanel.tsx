"use client";

import { CheckCircle2, FileText, Loader2, RefreshCw, Trash2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatConversationDate } from "@/lib/formatDate";
import { cn } from "@/lib/utils";
import type { RagDocument } from "@/types/document";

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Indexed and processing are live states, so they use the emerald; failed is red. */
function DocumentStatus({ document }: { document: RagDocument }) {
  if (document.status === "indexed") {
    return (
      <span className="inline-flex items-center gap-1 text-live">
        <CheckCircle2 aria-hidden className="size-3.5" />
        Ready
      </span>
    );
  }
  if (document.status === "failed") {
    return (
      <span className="inline-flex items-center gap-1 text-destructive">
        <XCircle aria-hidden className="size-3.5" />
        Failed
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 text-live">
      <Loader2 aria-hidden className="size-3.5 animate-spin motion-reduce:animate-none" />
      Processing
    </span>
  );
}

type DocumentPanelProps = {
  documents: RagDocument[];
  isLoading: boolean;
  deletingId: string | null;
  error: string | null;
  refresh: () => void;
  remove: (id: string) => void;
};

export function DocumentPanel({
  documents,
  isLoading,
  deletingId,
  error,
  refresh,
  remove,
}: DocumentPanelProps) {
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-3 px-4 pt-4 pb-3">
        <p className="text-xs text-muted-foreground">Files you attached to this chat</p>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          onClick={refresh}
          disabled={isLoading}
          aria-label="Refresh documents"
          className="rounded-[4px] text-muted-foreground"
        >
          <RefreshCw className={cn(isLoading && "animate-spin motion-reduce:animate-none")} />
        </Button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-4 pb-4">
        {error && (
          <p role="alert" className="rounded-[10px] border border-destructive/40 px-3 py-2 text-xs text-destructive">
            {error}
          </p>
        )}

        {documents.length === 0 && !isLoading ? (
          <p className="rounded-[10px] border border-dashed border-line px-3 py-6 text-center text-xs leading-relaxed text-muted-foreground">
            No documents yet. Attach a PDF or text file with the paperclip in the message box.
          </p>
        ) : null}

        {documents.map((document) => (
          <div key={document.id} className="rounded-[10px] border border-line bg-background p-3">
            <div className="flex min-w-0 items-start justify-between gap-2">
              <div className="flex min-w-0 gap-2">
                <FileText aria-hidden className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0">
                  <p className="truncate text-sm text-foreground">{document.filename}</p>
                  <p className="text-xs text-muted-foreground tabular-nums">
                    {formatBytes(document.size_bytes)} · {formatConversationDate(document.created_at)}
                  </p>
                </div>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={() => remove(document.id)}
                disabled={deletingId === document.id}
                aria-label={`Delete ${document.filename}`}
                className="-mt-1 -mr-1 rounded-[4px] text-muted-foreground hover:text-destructive"
              >
                {deletingId === document.id ? (
                  <Loader2 className="animate-spin motion-reduce:animate-none" />
                ) : (
                  <Trash2 />
                )}
              </Button>
            </div>
            <div className="mt-2 flex items-center justify-between gap-2 text-xs">
              <DocumentStatus document={document} />
              {document.status === "indexed" && (
                <span className="text-muted-foreground tabular-nums">
                  {document.chunkCount} {document.chunkCount === 1 ? "chunk" : "chunks"}
                </span>
              )}
            </div>
            {document.errorMessage ? (
              <p className="mt-2 text-xs text-destructive">{document.errorMessage}</p>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}
