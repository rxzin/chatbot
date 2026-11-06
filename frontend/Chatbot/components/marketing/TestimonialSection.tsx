import { Quote } from "lucide-react";
import { Marquee } from "@/components/ui/marquee";
import { RailSection, SectionHeading } from "./Frame";

// Written to show what each feature is like to use. They are examples, not reviews.
const examples = [
  {
    role: "Student",
    body: "I add my lecture notes before an exam and ask questions. The page numbers under each answer save me hunting through the PDF.",
  },
  {
    role: "Researcher",
    body: "Long threads used to lose their early details. Here the summary keeps the context, even a week into a conversation.",
  },
  {
    role: "Product manager",
    body: "When something breaks I just describe it. The ticket waits for review instead of getting buried in a chat log.",
  },
  {
    role: "Consultant",
    body: "Each client's files live in their own conversation, so answers never mix one project into another.",
  },
  {
    role: "IT admin",
    body: "The audit log shows every request with its status, so tracking down a failed sign-in takes seconds.",
  },
  {
    role: "Writer",
    body: "Replies start appearing straight away. It feels like a conversation, not a loading screen.",
  },
];

const firstRow = examples.slice(0, 3);
const secondRow = examples.slice(3);

function ExampleCard({ role, body }: { role: string; body: string }) {
  return (
    <figure className="flex w-72 flex-col justify-between gap-5 rounded-xl border border-line bg-card p-5">
      <blockquote className="text-sm leading-relaxed text-foreground/90">
        <Quote aria-hidden className="mb-3 size-4 text-live" />
        {body}
      </blockquote>
      <figcaption className="flex items-center justify-between text-xs">
        <span className="font-medium">{role}</span>
        <span className="text-muted-foreground">Example</span>
      </figcaption>
    </figure>
  );
}

export function TestimonialSection() {
  return (
    <RailSection id="examples" aria-labelledby="examples-heading">
      <div className="px-5 pt-24 pb-14 text-center sm:pt-28">
        <SectionHeading id="examples-heading" className="mx-auto max-w-[28rem]">
          What a day with Chat could look like
        </SectionHeading>
        <p className="mx-auto mt-4 max-w-[30rem] text-sm leading-relaxed text-muted-foreground">
          These are written examples of how people might use each feature. Chat doesn&apos;t
          have published customer reviews yet.
        </p>
      </div>
      <div className="flex flex-col gap-4 pb-24 [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)] sm:pb-28">
        <Marquee pauseOnHover repeat={3} className="p-0 [--duration:48s] [--gap:1rem]">
          {firstRow.map((example) => (
            <ExampleCard key={example.role} {...example} />
          ))}
        </Marquee>
        <Marquee reverse pauseOnHover repeat={3} className="p-0 [--duration:48s] [--gap:1rem]">
          {secondRow.map((example) => (
            <ExampleCard key={example.role} {...example} />
          ))}
        </Marquee>
      </div>
    </RailSection>
  );
}
