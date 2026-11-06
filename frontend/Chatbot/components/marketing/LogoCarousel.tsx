import { BrainCircuit, DatabaseZap, Radio, ShieldCheck } from "lucide-react";
import type { ComponentType } from "react";
import {
  SiFastapi,
  SiMistralai,
  SiNextdotjs,
  SiPostgresql,
  SiReact,
  SiRedis,
  SiTailwindcss,
  SiTypescript,
} from "react-icons/si";
import { Marquee } from "@/components/ui/marquee";
import { RailSection } from "./Frame";

const techStack: { name: string; icon: ComponentType<{ className?: string }> }[] = [
  { name: "Mistral", icon: SiMistralai },
  { name: "FastAPI", icon: SiFastapi },
  { name: "PostgreSQL", icon: SiPostgresql },
  { name: "Redis", icon: SiRedis },
  { name: "Pinecone", icon: DatabaseZap },
  { name: "Mistral Embeddings", icon: BrainCircuit },
  { name: "Next.js", icon: SiNextdotjs },
  { name: "React", icon: SiReact },
  { name: "SSE Streaming", icon: Radio },
  { name: "JWT Auth", icon: ShieldCheck },
  { name: "Tailwind CSS", icon: SiTailwindcss },
  { name: "TypeScript", icon: SiTypescript },
];

export function LogoCarousel() {
  return (
    <RailSection aria-label="Built with">
      <div className="flex flex-col items-center gap-7 px-5 py-11">
        <p className="text-sm text-balance text-muted-foreground">Built on the tools behind real-time chat</p>
        <div className="w-full max-w-5xl overflow-hidden [mask-image:linear-gradient(to_right,transparent,black_10%,black_90%,transparent)]">
          <Marquee pauseOnHover repeat={2} className="p-0 [--duration:44s] [--gap:3.5rem]">
            {techStack.map(({ name, icon: Icon }) => (
              <span
                key={name}
                className="flex shrink-0 items-center gap-2.5 text-lg font-medium whitespace-nowrap text-foreground/75"
              >
                <Icon className="size-5" />
                {name}
              </span>
            ))}
          </Marquee>
        </div>
      </div>
    </RailSection>
  );
}
