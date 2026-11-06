import { ArrowUpRight } from "lucide-react";
import { RailSection, SectionHeading } from "./Frame";
import { SlideButton } from "./SlideButton";
import { StripeField } from "./StripeField";

export function FinalCta() {
  return (
    <RailSection innerClassName="overflow-hidden" aria-labelledby="cta-heading">
      <StripeField />
      <div className="relative flex flex-col items-center px-5 py-28 text-center sm:py-36">
        <SectionHeading id="cta-heading" className="max-w-[22rem] sm:max-w-[26rem]">
          Ask your first question in a minute.
        </SectionHeading>
        <p className="mt-4 max-w-[26rem] text-sm leading-relaxed text-muted-foreground">
          Create an account, upload a file, and see Chat answer from it.
        </p>
        <SlideButton
          href="/register"
          className="mt-8"
          icon={<ArrowUpRight aria-hidden className="size-4" />}
        >
          Start chatting
        </SlideButton>
      </div>
    </RailSection>
  );
}
