import {
  Globe,
  History,
  MessageCircleQuestion,
  Quote,
  Radio,
  ShieldCheck,
  FileText,
  TicketCheck,
  type LucideIcon,
} from "lucide-react";
import { RailSection, SectionHeading } from "./Frame";

const features: { title: string; description: string; icon: LucideIcon }[] = [
  {
    title: "Private accounts",
    description:
      "Sign in with email and password. Logging out ends your session at once, and only you can see your conversations.",
    icon: ShieldCheck,
  },
  {
    title: "Replies that stream",
    description:
      "Answers appear word by word as Mistral writes them, and Chat shows when it's searching or checking something.",
    icon: Radio,
  },
  {
    title: "Documents per conversation",
    description:
      "Attach PDF or TXT files to one conversation. They stay there and never mix into your other chats.",
    icon: FileText,
  },
  {
    title: "Inline citations",
    description:
      "Claims from your files or the web carry a numbered citation. Hover one to see the passage or page it came from.",
    icon: Quote,
  },
  {
    title: "Searches the web when needed",
    description:
      "Ask about something recent and Chat searches the web with Exa, then links every page it used.",
    icon: Globe,
  },
  {
    title: "Memory for long chats",
    description:
      "Recent messages stay quick to reach in Redis, and older ones are summarised, so long conversations keep their context.",
    icon: History,
  },
  {
    title: "Bug reports with a human check",
    description:
      "Describe a problem and Chat drafts a ticket. An admin approves it before it reaches Jira, and you get an email.",
    icon: TicketCheck,
  },
  {
    title: "Suggested next questions",
    description:
      "After each answer, Chat offers three follow-up questions you can send with one click.",
    icon: MessageCircleQuestion,
  },
];

export function FeaturesSection() {
  return (
    <RailSection id="features" aria-labelledby="features-heading">
      <div className="px-5 pt-24 pb-20 text-center sm:pt-28">
        <SectionHeading id="features-heading" className="mx-auto max-w-[30rem]">
          Everything private AI chat needs, already wired up
        </SectionHeading>
      </div>
      <ul className="grid border-t border-dashed border-line md:grid-cols-2">
        {features.map(({ title, description, icon: Icon }, index) => (
          <li
            key={title}
            className={[
              "border-dashed border-line px-6 py-10 sm:px-12",
              index < features.length - 1 ? "border-b" : "",
              index === features.length - 2 ? "md:border-b-0" : "",
              index % 2 === 0 ? "md:border-r" : "",
            ].join(" ")}
          >
            <h3 className="flex items-center gap-3 text-base font-medium">
              <Icon aria-hidden className="size-[18px] text-foreground/80" strokeWidth={1.6} />
              {title}
            </h3>
            <p className="mt-3 max-w-[26rem] text-sm leading-relaxed text-muted-foreground">{description}</p>
          </li>
        ))}
      </ul>
    </RailSection>
  );
}
