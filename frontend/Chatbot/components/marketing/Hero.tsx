import { ArrowUpRight } from "lucide-react";
import { RailSection } from "./Frame";
import { SlideButton } from "./SlideButton";
import { StripeField } from "./StripeField";

export default function Hero() {
  return (
    <RailSection innerClassName="overflow-hidden" aria-labelledby="hero-heading">
      <StripeField />
      <div className="relative flex min-h-[calc(100svh-73px)] flex-col items-center justify-center px-5 py-24 text-center">
        <h1
          id="hero-heading"
          className="font-display text-[2.6rem] leading-[1.12] font-medium tracking-[-0.03em] text-balance sm:text-6xl sm:leading-[1.1] lg:text-[4.25rem]"
        >
          <span className="block">AI chat that knows</span>
          <span className="mt-2 inline-block border border-dashed border-muted-foreground/40 px-3 pb-1.5 font-semibold sm:px-4">
            your documents.
          </span>
        </h1>

        <p className="mt-6 max-w-[34rem] text-[0.95rem] leading-relaxed font-light text-muted-foreground">
          Private AI chat that answers from the PDFs and text files you upload, with the
          sources it used. Replies stream in as they&apos;re written, and every conversation
          stays yours.
        </p>

        <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
          <SlideButton href="/register" icon={<ArrowUpRight aria-hidden className="size-4" />}>
            Start chatting
          </SlideButton>
          <SlideButton href="#use-cases" variant="outline" className="bg-background">
            See it at work
          </SlideButton>
        </div>
      </div>
    </RailSection>
  );
}
