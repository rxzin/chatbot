"use client";

import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/chat";
import { StreamingCursor } from "./StreamingCursor";
import ReactMarkdown from "react-markdown";
import type { ReactNode } from "react";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { FileText, Loader2 } from "lucide-react";

type MessageBubbleProps = {
  message: ChatMessage;
};

type MarkdownCodeProps = {
  inline?: boolean;
  className?: string;
  children?: ReactNode;
};

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isStreaming = message.status === "streaming";

  return (
    <div
      className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}
    >
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm sm:max-w-[75%]",
          isUser
            ? "bg-primary text-primary-foreground"
            : "border border-border bg-card text-card-foreground",
          message.status === "error" &&
            "border-destructive/50 bg-destructive/5",
        )}
      >
        {isStreaming && message.activity && (
          <p
            role="status"
            className="mb-2 flex items-center gap-2 text-xs text-muted-foreground"
          >
            <Loader2 aria-hidden className="h-3.5 w-3.5 animate-spin" />
            {message.activity}…
          </p>
        )}
        <div
          className={cn(
            "prose max-w-none wrap-break-word dark:prose-invert prose-p:leading-relaxed prose-pre:p-0",
            // If it's a user message, we want to force the prose text to be white/foreground
            isUser &&
              "prose-p:text-primary-foreground prose-headings:text-primary-foreground prose-strong:text-primary-foreground",
          )}
        >
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              // This custom component intercepts <code> tags
              code({ inline, className, children, ...props }: MarkdownCodeProps) {
                const match = /language-(\w+)/.exec(className || "");

                // If it's a code block (not inline code), use the syntax highlighter
                if (!inline && match) {
                  return (
                    <div className="my-4 overflow-hidden rounded-md border border-border">
                      <div className="bg-muted px-4 py-1 text-xs text-muted-foreground">
                        {match[1]}
                      </div>
                      <SyntaxHighlighter
                        {...props}
                        style={vscDarkPlus}
                        language={match[1]}
                        PreTag="div"
                        customStyle={{ margin: 0, padding: "1rem" }}
                      >
                        {String(children).replace(/\n$/, "")}
                      </SyntaxHighlighter>
                    </div>
                  );
                }
                return (
                  <code
                    className="rounded bg-muted px-1.5 py-0.5 text-sm font-mono text-foreground"
                    {...props}
                  >
                    {children}
                  </code>
                );
              },
            }}
          >
            {message.content || (isStreaming ? "" : "…")}
          </ReactMarkdown>

          {/* Keep your awesome streaming cursor at the end */}
          {isStreaming && <StreamingCursor />}
        </div>

        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-3 border-t border-border pt-3">
            <p className="mb-2 text-xs font-medium text-muted-foreground">
              Sources
            </p>
            <div className="flex flex-col gap-2">
              {message.sources.map((source) => (
                <div
                  key={`${source.documentId}-${source.chunkIndex}`}
                  className="rounded-md border border-border bg-background/70 p-2"
                >
                  <div className="flex min-w-0 items-center gap-2 text-xs font-medium">
                    <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                    <span className="truncate">{source.filename}</span>
                    {source.page ? (
                      <span className="shrink-0 text-muted-foreground">
                        p. {source.page}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                    {source.snippet}
                  </p>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
