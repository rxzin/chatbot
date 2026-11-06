import type { ReactNode } from "react";
import { AnimatedThemeToggler } from "@/components/ui/animated-theme-toggler";
import { RailSection } from "@/components/marketing/Frame";
import { Logo } from "@/components/marketing/Logo";
import { StripeField } from "@/components/marketing/StripeField";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="landing flex min-h-svh flex-col">
      <RailSection as="header">
        <div className="flex h-[72px] items-center justify-between px-5 md:px-6">
          <Logo />
          <AnimatedThemeToggler className="flex size-9 items-center justify-center rounded-[4px] text-muted-foreground transition-colors hover:text-foreground [&_svg]:size-[18px]" />
        </div>
      </RailSection>
      <RailSection className="flex-1 border-b-0" innerClassName="overflow-hidden" markers={false}>
        <StripeField />
        <main className="relative flex min-h-[calc(100svh-73px)] items-center justify-center px-5 py-16">
          {children}
        </main>
      </RailSection>
    </div>
  );
}
