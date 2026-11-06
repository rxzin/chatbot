"use client";

import { FileText, Globe } from "lucide-react";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "@/components/ui/hover-card";
import type { SourceReference, WebSource } from "@/types/chat";

export type CitedSource =
  | { kind: "document"; number: number; source: SourceReference }
  | { kind: "web"; number: number; source: WebSource; host: string; href: string };

const CITATION_HREF = "#cite-";

/** Only http and https links are rendered, whatever the server sent. */
export function safeWebUrl(url: string): URL | null {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed : null;
  } catch {
    return null;
  }
}

/** Numbered sources of a message, by citation number. Unnumbered (older) ones are left out. */
export function citationMap(
  sources: SourceReference[] = [],
  webSources: WebSource[] = []
): Map<number, CitedSource> {
  const map = new Map<number, CitedSource>();
  for (const source of sources) {
    if (source.number) map.set(source.number, { kind: "document", number: source.number, source });
  }
  for (const source of webSources) {
    const url = source.number ? safeWebUrl(source.url) : null;
    if (url && source.number) {
      map.set(source.number, {
        kind: "web",
        number: source.number,
        source,
        host: url.hostname.replace(/^www\./, ""),
        href: url.href,
      });
    }
  }
  return map;
}

/**
 * Turn "[2]" into a markdown link the renderer swaps for a badge. Only numbers that
 * match a source are touched, and fenced or inline code is left as written.
 */
export function linkCitations(text: string, numbers: Set<number>): string {
  if (numbers.size === 0) return text;
  return text
    .split(/(```[\s\S]*?```|`[^`\n]*`)/g)
    .map((segment, index) =>
      index % 2 === 1
        ? segment
        : segment.replace(/\[(\d{1,3})\](?![(\[:])/g, (match, digits: string) =>
            numbers.has(Number(digits)) ? `[${digits}](${CITATION_HREF}${digits})` : match
          )
    )
    .join("");
}

export function citationNumber(href: string | undefined): number | null {
  if (!href?.startsWith(CITATION_HREF)) return null;
  const number = Number(href.slice(CITATION_HREF.length));
  return Number.isInteger(number) ? number : null;
}

const badgeClass =
  "mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] items-center justify-center rounded-full bg-muted px-1 align-[0.1em] text-[0.68rem] font-medium leading-none text-muted-foreground no-underline transition-colors hover:bg-primary hover:text-primary-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/** An inline "[n]" badge; hovering or focusing it shows the source. */
export function CitationBadge({ cited }: { cited: CitedSource }) {
  const label =
    cited.kind === "web"
      ? `Source ${cited.number}: ${cited.source.title} (${cited.host})`
      : `Source ${cited.number}: ${cited.source.filename}`;

  return (
    <HoverCard openDelay={150} closeDelay={100}>
      <HoverCardTrigger asChild>
        {cited.kind === "web" ? (
          <a
            href={cited.href}
            target="_blank"
            rel="noopener noreferrer nofollow"
            aria-label={label}
            className={badgeClass}
          >
            {cited.number}
          </a>
        ) : (
          <span tabIndex={0} role="note" aria-label={label} className={badgeClass}>
            {cited.number}
          </span>
        )}
      </HoverCardTrigger>
      <HoverCardContent align="start" className="w-80 p-3">
        <div className="flex min-w-0 items-center gap-2 text-xs font-medium">
          {cited.kind === "web" ? (
            <Globe aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
          ) : (
            <FileText aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
          )}
          <span className="truncate">
            {cited.kind === "web" ? cited.source.title : cited.source.filename}
          </span>
          <span className="ml-auto shrink-0 text-muted-foreground">
            {cited.kind === "web"
              ? cited.host
              : cited.source.page
                ? `p. ${cited.source.page}`
                : null}
          </span>
        </div>
        <p className="mt-2 line-clamp-4 text-xs leading-relaxed text-muted-foreground">
          {cited.source.snippet}
        </p>
      </HoverCardContent>
    </HoverCard>
  );
}
