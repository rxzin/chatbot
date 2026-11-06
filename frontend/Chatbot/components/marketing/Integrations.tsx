import { CloudSun, DatabaseZap, Layers } from "lucide-react";
import type { ComponentType } from "react";
import {
  SiDocker,
  SiFastapi,
  SiGmail,
  SiJira,
  SiMistralai,
  SiNextdotjs,
  SiPostgresql,
  SiPython,
  SiReact,
  SiRedis,
  SiTailwindcss,
  SiTypescript,
} from "react-icons/si";
import { RailSection, SectionHeading } from "./Frame";
import { SlideButton } from "./SlideButton";

type Tool = { name: string; icon: ComponentType<{ className?: string }> };

const tools: Tool[] = [
  { name: "Mistral", icon: SiMistralai },
  { name: "Pinecone", icon: DatabaseZap },
  { name: "Cohere Rerank", icon: Layers },
  { name: "PostgreSQL", icon: SiPostgresql },
  { name: "Redis", icon: SiRedis },
  { name: "FastAPI", icon: SiFastapi },
  { name: "Python", icon: SiPython },
  { name: "Jira", icon: SiJira },
  { name: "Email over SMTP", icon: SiGmail },
  { name: "Open-Meteo", icon: CloudSun },
  { name: "Next.js", icon: SiNextdotjs },
  { name: "React", icon: SiReact },
  { name: "TypeScript", icon: SiTypescript },
  { name: "Tailwind CSS", icon: SiTailwindcss },
  { name: "Docker", icon: SiDocker },
];

export function Integrations() {
  return (
    <RailSection id="integrations" aria-labelledby="integrations-heading">
      <div className="grid items-center gap-14 px-5 py-24 sm:px-12 sm:py-28 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div>
          <SectionHeading id="integrations-heading" className="max-w-[24rem]">
            Built on a stack you can name.
          </SectionHeading>
          <p className="mt-5 max-w-[24rem] text-sm leading-relaxed text-muted-foreground">
            Mistral writes the replies, Pinecone and Cohere find the right passages, and
            PostgreSQL and Redis hold your history. Bug reports go to Jira and email.
          </p>
          <SlideButton href="#features" variant="outline" className="mt-8">
            See what it does
          </SlideButton>
        </div>

        <ul
          aria-label="Services Chat uses"
          className="grid grid-cols-3 gap-3 sm:grid-cols-5 [mask-image:linear-gradient(to_right,transparent,black_12%,black_88%,transparent)]"
        >
          {tools.map(({ name, icon: Icon }) => (
            <li
              key={name}
              title={name}
              className="group flex aspect-square flex-col items-center justify-center gap-2 rounded-xl border border-line bg-card text-foreground/70 transition-colors hover:border-muted-foreground/50 hover:text-foreground"
            >
              <Icon aria-hidden className="size-7" />
              <span className="px-1 text-center text-[0.68rem] leading-tight text-muted-foreground">{name}</span>
            </li>
          ))}
        </ul>
      </div>
    </RailSection>
  );
}
