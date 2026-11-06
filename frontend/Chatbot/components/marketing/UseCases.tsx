"use client";

import {
  ChevronDown,
  ChevronRight,
  CloudSun,
  FileSearch,
  FileText,
  Globe,
  LayoutDashboard,
  MessageSquare,
  SendHorizontal,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { useId, useState } from "react";
import { cn } from "@/lib/utils";
import { RailSection, SectionHeading } from "./Frame";

type Message = { from: "user" | "chat"; text: string; note?: string };
type Source = { label: string; kind: "document" | "web" };

type UseCase = {
  id: string;
  title: string;
  description: string;
  icon: LucideIcon;
  conversation: string;
  messages?: Message[];
  sources?: Source[];
  suggestions?: string[];
  ticket?: string;
};

const useCases: UseCase[] = [
  {
    id: "documents",
    title: "Ask your documents",
    description:
      "Upload a contract, a paper or a manual, then ask about it. Each answer lists the pages it came from.",
    icon: FileSearch,
    conversation: "Flat lease",
    messages: [
      { from: "user", text: "What's the notice period if I want to move out?" },
      {
        from: "chat",
        text: "You need to give 60 days' notice in writing before the end of the term [1]. Notice by email counts, as long as it goes to the address in section 9 [2].",
      },
    ],
    sources: [
      { label: "lease-2026.pdf · p. 4", kind: "document" },
      { label: "lease-2026.pdf · p. 11", kind: "document" },
    ],
    suggestions: ["Can I end the lease early?", "Who pays for repairs?"],
  },
  {
    id: "web",
    title: "Search the web",
    description:
      "Ask about anything current. Chat searches the web, answers with numbered citations and links the pages it used.",
    icon: Globe,
    conversation: "Starting to run",
    messages: [
      { from: "user", text: "How should I start running if I've never run before?" },
      {
        from: "chat",
        note: "Searching the web",
        text: "Start with short run-walk intervals three times a week and build up slowly over a few weeks [1]. Rest days between runs matter as much as the runs themselves [2].",
      },
    ],
    sources: [
      { label: "nhs.uk · Couch to 5K", kind: "web" },
      { label: "nhs.uk · Running for beginners", kind: "web" },
    ],
  },
  {
    id: "weather",
    title: "Check the weather",
    description: "Ask about any city and get live conditions from Open-Meteo, in plain language.",
    icon: CloudSun,
    conversation: "Weekend trip",
    messages: [
      { from: "user", text: "Will it rain in Lisbon tomorrow?" },
      {
        from: "chat",
        text: "Light rain is likely in the morning, clearing by early afternoon. Expect a high of 19°C and a fresh breeze off the coast.",
      },
    ],
    sources: [{ label: "Open-Meteo forecast", kind: "web" }],
  },
  {
    id: "bugs",
    title: "Report a bug",
    description:
      "Describe what broke. Chat drafts a ticket for an admin to review, and you're emailed once it's filed in Jira.",
    icon: TriangleAlert,
    conversation: "Upload problem",
    messages: [
      { from: "user", text: "The upload button does nothing on my phone." },
      {
        from: "chat",
        note: "Drafting bug report",
        text: "I've drafted a report for the engineering team. An admin will review it shortly, and you'll get an email once it's approved.",
      },
    ],
    ticket: "Upload button unresponsive on mobile",
  },
  {
    id: "admin",
    title: "Run the admin desk",
    description:
      "Admins review bug reports, follow every request in the audit log, and end sessions or ban accounts.",
    icon: LayoutDashboard,
    conversation: "Admin dashboard",
  },
];

const auditRows = [
  ["10:42:07", "maria@example.com", "POST", "/api/chat", 200],
  ["10:41:55", "maria@example.com", "POST", "/api/conversations/…/documents/upload", 200],
  ["10:41:12", "Anonymous", "POST", "/api/auth/login", 401],
  ["10:40:48", "admin@example.com", "DELETE", "/api/admin/sessions/…", 200],
  ["10:40:31", "sam@example.com", "GET", "/api/conversations", 200],
] as const;

/** Shows "[1]" the way the app does: as a small numbered badge. */
function withCitations(text: string) {
  return text.split(/(\[\d\])/g).map((part, index) =>
    /^\[\d\]$/.test(part) ? (
      <span
        key={index}
        className="mx-0.5 inline-flex size-[1.05rem] items-center justify-center rounded-full bg-muted align-[0.1em] text-[0.6rem] text-muted-foreground"
      >
        {part.slice(1, -1)}
      </span>
    ) : (
      part
    ),
  );
}

function Bubble({ message }: { message: Message }) {
  const isUser = message.from === "user";
  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[85%] rounded-xl px-3.5 py-2.5 text-[0.8rem] leading-relaxed",
          isUser ? "bg-foreground text-background" : "border border-line bg-background text-foreground",
        )}
      >
        {message.note && <p className="mb-1 text-[0.7rem] text-muted-foreground italic">{message.note}…</p>}
        {isUser ? message.text : withCitations(message.text)}
      </div>
    </div>
  );
}

function ChatPreview({ useCase }: { useCase: UseCase }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-3 overflow-hidden p-4">
        {useCase.messages?.map((message, index) => <Bubble key={index} message={message} />)}
        {useCase.sources && (
          <div className="flex flex-wrap gap-1.5 pl-0.5">
            {useCase.sources.map((source, index) => (
              <span
                key={source.label}
                className="inline-flex items-center gap-1.5 rounded-[4px] border border-line px-2 py-1 text-[0.68rem] text-muted-foreground"
              >
                {useCase.messages?.some((m) => m.text.includes(`[${index + 1}]`)) && (
                  <span className="tabular-nums">{index + 1}</span>
                )}
                {source.kind === "web" ? (
                  <Globe aria-hidden className="size-3" />
                ) : (
                  <FileText aria-hidden className="size-3" />
                )}
                {source.label}
              </span>
            ))}
          </div>
        )}
        {useCase.suggestions && (
          <div className="flex flex-wrap gap-1.5 pl-0.5">
            {useCase.suggestions.map((suggestion) => (
              <span
                key={suggestion}
                className="rounded-[4px] border border-line px-2 py-1 text-[0.68rem] text-foreground"
              >
                {suggestion}
              </span>
            ))}
          </div>
        )}
        {useCase.ticket && (
          <div className="ml-0.5 flex max-w-[85%] items-center justify-between gap-3 rounded-lg border border-dashed border-line px-3 py-2.5">
            <div>
              <p className="text-[0.75rem] font-medium">{useCase.ticket}</p>
              <p className="text-[0.68rem] text-muted-foreground">Waiting for admin review</p>
            </div>
            <span className="rounded-[4px] bg-live/15 px-1.5 py-0.5 text-[0.65rem] font-medium text-live">Pending</span>
          </div>
        )}
      </div>
      <div className="m-3 flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-[0.75rem] text-muted-foreground">
        <span className="flex-1">Ask anything…</span>
        <SendHorizontal aria-hidden className="size-3.5" />
      </div>
    </div>
  );
}

function AdminPreview() {
  return (
    <div className="p-4">
      <div className="grid grid-cols-3 gap-2">
        {[
          ["Pending bugs", "1"],
          ["Active sessions", "12"],
          ["Requests (24h)", "1,284"],
        ].map(([label, value]) => (
          <div key={label} className="rounded-lg border border-line px-3 py-2">
            <p className="text-[0.65rem] text-muted-foreground">{label}</p>
            <p className="font-display text-lg font-medium tabular-nums">{value}</p>
          </div>
        ))}
      </div>
      <div className="mt-3 overflow-hidden rounded-lg border border-line">
        <table className="w-full text-left text-[0.68rem]">
          <thead className="text-muted-foreground">
            <tr className="border-b border-line">
              <th className="px-2.5 py-2 font-normal">Time</th>
              <th className="px-2.5 py-2 font-normal">User</th>
              <th className="px-2.5 py-2 font-normal">Request</th>
              <th className="px-2.5 py-2 text-right font-normal">Status</th>
            </tr>
          </thead>
          <tbody>
            {auditRows.map(([time, user, method, path, status]) => (
              <tr key={time} className="border-b border-line last:border-0">
                <td className="px-2.5 py-2 text-muted-foreground tabular-nums">{time}</td>
                <td className="max-w-[7rem] truncate px-2.5 py-2">{user}</td>
                <td className="max-w-[11rem] truncate px-2.5 py-2 font-mono text-[0.64rem]">
                  {method} {path}
                </td>
                <td className="px-2.5 py-2 text-right tabular-nums">
                  <span
                    className={cn(
                      "rounded-[4px] px-1.5 py-0.5",
                      status === 200 ? "bg-live/15 text-live" : "bg-muted text-muted-foreground",
                    )}
                  >
                    {status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ProductPreview({ useCase }: { useCase: UseCase }) {
  const isAdmin = useCase.id === "admin";
  return (
    <div className="flex h-full overflow-hidden rounded-lg border border-line bg-card">
      <aside className="hidden w-40 shrink-0 flex-col border-r border-line p-3 sm:flex">
        <p className="mb-3 flex items-center gap-2 text-[0.75rem] font-medium">
          <span className="flex size-5 items-center justify-center rounded-[5px] bg-foreground text-background">
            <MessageSquare aria-hidden className="size-3" />
          </span>
          Chat
        </p>
        {useCases.slice(0, 3).map((item) => (
          <p
            key={item.id}
            className={cn(
              "truncate rounded-md px-2 py-1.5 text-[0.7rem]",
              !isAdmin && item.id === useCase.id ? "bg-muted text-foreground" : "text-muted-foreground",
            )}
          >
            {item.conversation}
          </p>
        ))}
        {isAdmin && <p className="mt-1 rounded-md bg-muted px-2 py-1.5 text-[0.7rem]">Admin dashboard</p>}
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
          <p className="truncate text-[0.8rem] font-medium">{useCase.conversation}</p>
          <span className="shrink-0 rounded-full border border-line px-2 py-0.5 text-[0.62rem] text-muted-foreground">
            Example
          </span>
        </div>
        <div className="min-h-0 flex-1">{isAdmin ? <AdminPreview /> : <ChatPreview useCase={useCase} />}</div>
      </div>
    </div>
  );
}

export function UseCases() {
  const [active, setActive] = useState(useCases[0].id);
  const baseId = useId();
  const current = useCases.find((item) => item.id === active) ?? useCases[0];

  return (
    <RailSection id="use-cases" aria-labelledby="use-cases-heading">
      <div className="px-5 pt-24 pb-14 sm:px-12 sm:pt-28">
        <SectionHeading id="use-cases-heading" className="max-w-[26rem]">
          One chat for files, the web, forecasts and bug reports.
        </SectionHeading>
      </div>

      <div className="mx-5 mb-24 grid overflow-hidden rounded-xl border border-line sm:mx-12 sm:mb-28 lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)]">
        <ul className="divide-y divide-dashed divide-line border-b border-dashed border-line lg:border-r lg:border-b-0">
          {useCases.map((item) => {
            const isActive = item.id === active;
            const panelId = `${baseId}-${item.id}`;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  aria-expanded={isActive}
                  aria-controls={panelId}
                  onClick={() => setActive(item.id)}
                  className="flex w-full items-start gap-4 px-6 py-6 text-left transition-colors hover:bg-muted/40"
                >
                  <span
                    className={cn(
                      "flex size-9 shrink-0 items-center justify-center rounded-lg border border-line transition-colors",
                      isActive ? "bg-muted text-foreground" : "text-muted-foreground",
                    )}
                  >
                    <item.icon aria-hidden className="size-[18px]" strokeWidth={1.6} />
                  </span>
                  <span className="min-w-0 flex-1 pt-1.5">
                    <span className="flex items-center justify-between gap-3">
                      <span className="text-[1.05rem] font-medium">{item.title}</span>
                      {isActive ? (
                        <ChevronDown aria-hidden className="size-4 shrink-0 text-muted-foreground" />
                      ) : (
                        <ChevronRight aria-hidden className="size-4 shrink-0 text-muted-foreground" />
                      )}
                    </span>
                    <span
                      id={panelId}
                      className={cn(
                        "grid transition-[grid-template-rows,opacity] duration-500 ease-[cubic-bezier(0.16,1,0.3,1)] motion-reduce:transition-none",
                        isActive ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0",
                      )}
                    >
                      <span className="overflow-hidden">
                        <span className="block pt-2.5 text-sm leading-relaxed text-muted-foreground">
                          {item.description}
                        </span>
                      </span>
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        <div className="relative min-h-[22rem] overflow-hidden p-5 sm:p-8">
          <div
            aria-hidden
            className="absolute inset-0 [background-image:linear-gradient(to_right,var(--line)_1px,transparent_1px)] [background-size:28px_100%] opacity-60 [mask-image:linear-gradient(to_bottom,black,transparent_85%)]"
          />
          <div key={current.id} className="relative h-full animate-in duration-500 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none">
            <ProductPreview useCase={current} />
          </div>
        </div>
      </div>
    </RailSection>
  );
}
