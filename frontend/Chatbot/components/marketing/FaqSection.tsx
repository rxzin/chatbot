"use client";

import { PlusIcon } from "lucide-react";
import { Accordion as AccordionPrimitive } from "radix-ui";
import { Accordion, AccordionContent, AccordionItem } from "@/components/ui/accordion";
import { RailSection, SectionHeading } from "./Frame";

const items = [
  {
    title: "What is Chat?",
    content:
      "Chat is a full-stack AI chat app with private accounts, saved conversations and streaming replies from Mistral. It answers from documents you upload and from the web, and cites its sources inline.",
  },
  {
    title: "How does document chat work?",
    content:
      "Upload a PDF or TXT file inside a conversation. Once it's indexed, Chat searches it when your question needs it and cites each passage it used with a number you can hover.",
  },
  {
    title: "Can I ask general questions too?",
    content:
      "Yes. For each message Chat decides whether to answer directly, search your documents, search the web or check the weather, and it can combine them.",
  },
  {
    title: "Are documents shared across conversations?",
    content:
      "No. Documents belong to the conversation they were uploaded to, so files in one chat never affect answers in another.",
  },
  {
    title: "Is my conversation history saved?",
    content:
      "Yes. Conversations are stored in PostgreSQL and only you can see them. You can reopen any past conversation from the sidebar.",
  },
  {
    title: "Is there a daily limit?",
    content:
      "Yes. Each account can send 200 messages and run 30 web searches a day. Both reset at midnight UTC.",
  },
  {
    title: "Is Chat free?",
    content:
      "Yes, while it's in development. The plans above are examples of how pricing could work, and no billing is set up.",
  },
];

export function FaqSection() {
  return (
    <RailSection id="faq" aria-labelledby="faq-heading">
      <div className="grid gap-12 px-5 py-24 sm:px-12 sm:py-28 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <SectionHeading id="faq-heading" className="max-w-[18rem]">
          Questions about Chat?
        </SectionHeading>

        <Accordion type="single" collapsible defaultValue="item-0">
          {items.map((item, index) => (
            <AccordionItem
              key={item.title}
              value={`item-${index}`}
              className="border-b border-dashed border-line last:border-b"
            >
              <AccordionPrimitive.Header className="flex">
                <AccordionPrimitive.Trigger className="flex flex-1 items-center justify-between gap-4 py-5 text-left text-[0.95rem] transition-colors outline-none hover:text-foreground [&[data-state=open]>svg]:rotate-45">
                  {item.title}
                  <PlusIcon
                    aria-hidden
                    className="size-4 shrink-0 text-muted-foreground transition-transform duration-300"
                  />
                </AccordionPrimitive.Trigger>
              </AccordionPrimitive.Header>
              <AccordionContent className="max-w-[36rem] pb-5 leading-relaxed text-muted-foreground">
                {item.content}
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </div>
    </RailSection>
  );
}
