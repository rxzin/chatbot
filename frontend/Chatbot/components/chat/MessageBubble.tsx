"use client";

import { cn } from "@/lib/utils";
import type { ChatMessage } from "@/types/chat";
import { StreamingCursor } from "./StreamingCursor";
import ReactMarkdown from "react-markdown";
import type { ReactNode } from "react";
import remarkGfm from "remark-gfm";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { FileText, Globe, Loader2 } from "lucide-react";
import {
  CitationBadge,
  citationMap,
  citationNumber,
  linkCitations,
  safeWebUrl,
} from "./Citation";

type MessageBubbleProps = {
  message: ChatMessage;
  /** Set only on the latest reply, which is the one that shows suggestions. */
  onSuggestion?: (text: string) => void;
  suggestionsDisabled?: boolean;
};

type MarkdownCodeProps = {
  inline?: boolean;
  className?: string;
  children?: ReactNode;
};

type MarkdownLinkProps = {
  href?: string;
  children?: ReactNode;
};

export function MessageBubble({
  message,
  onSuggestion,
  suggestionsDisabled = false,
}: MessageBubbleProps) {
  const isUser = message.role === "user";
  const isStreaming = message.status === "streaming";
  const cited = citationMap(message.sources, message.webSources);

  // Numbered sources first, in citation order; replies saved before numbering follow.
  const byNumber = (a?: number | null, b?: number | null) =>
    (a ?? Number.MAX_SAFE_INTEGER) - (b ?? Number.MAX_SAFE_INTEGER);
  const docSources = [...(message.sources ?? [])].sort((a, b) => byNumber(a.number, b.number));
  const webSources = (message.webSources ?? [])
    .flatMap((source) => {
      const url = safeWebUrl(source.url);
      return url
        ? [{ ...source, href: url.href, host: url.hostname.replace(/^www\./, "") }]
        : [];
    })
    .sort((a, b) => byNumber(a.number, b.number));

  const content = isUser
    ? message.content
    : linkCitations(message.content, new Set(cited.keys()));
  const suggestions =
    !isUser && !isStreaming && onSuggestion ? (message.suggestions ?? []) : [];

  return (
    <div
      className={cn(
        "flex w-full flex-col gap-2",
        isUser ? "items-end" : "items-start"
      )}
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
              // "[2]" citations become badges; other links open in a new tab.
              a({ href, children }: MarkdownLinkProps) {
                const number = citationNumber(href);
                const source = number === null ? undefined : cited.get(number);
                if (source) return <CitationBadge cited={source} />;
                const url = href ? safeWebUrl(href) : null;
                if (!url) return <>{children}</>;
                return (
                  <a href={url.href} target="_blank" rel="noopener noreferrer nofollow">
                    {children}
                  </a>
                );
              },
            }}
          >
            {content || (isStreaming ? "" : "…")}
          </ReactMarkdown>

          {/* Keep your awesome streaming cursor at the end */}
          {isStreaming && <StreamingCursor />}
        </div>

        {!isUser && (docSources.length > 0 || webSources.length > 0) && (
          <div className="mt-3 border-t border-border pt-3">
            <p className="mb-2 text-xs font-medium text-muted-foreground">
              Sources
            </p>
            <ol className="flex flex-col gap-2">
              {docSources.map((source) => (
                <li
                  key={`${source.documentId}-${source.chunkIndex}`}
                  className="rounded-md border border-border bg-background/70 p-2"
                >
                  <div className="flex min-w-0 items-center gap-2 text-xs font-medium">
                    <SourceNumber number={source.number} />
                    <FileText aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
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
                </li>
              ))}
              {webSources.map((source) => (
                <li key={source.url}>
                  <a
                    href={source.href}
                    target="_blank"
                    rel="noopener noreferrer nofollow"
                    className="block rounded-md border border-border bg-background/70 p-2 transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <div className="flex min-w-0 items-center gap-2 text-xs font-medium">
                      <SourceNumber number={source.number} />
                      <Globe aria-hidden className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate">{source.title}</span>
                      <span className="shrink-0 text-muted-foreground">{source.host}</span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-muted-foreground">
                      {source.snippet}
                    </p>
                  </a>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>

      {suggestions.length > 0 && onSuggestion && (
        <div
          role="group"
          aria-label="Suggested questions"
          className="flex max-w-[85%] flex-wrap gap-2 sm:max-w-[75%]"
        >
          {suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              disabled={suggestionsDisabled}
              onClick={() => onSuggestion(suggestion)}
              className="rounded-full border border-border bg-background px-3 py-1.5 text-left text-xs text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function SourceNumber({ number }: { number?: number | null }) {
  if (!number) return null;
  return (
    <span className="inline-flex h-4 min-w-4 shrink-0 items-center justify-center rounded-full bg-muted px-1 text-[0.65rem] text-muted-foreground">
      {number}
    </span>
  );
}
