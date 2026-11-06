import Link from "next/link";
import { cn } from "@/lib/utils";

/** Chat's mark: the lightning bolt in a rounded square, set in the page's foreground. */
export function Logo({ className }: { className?: string }) {
  return (
    <Link href="/" prefetch={false} aria-label="Chat home" className={cn("flex items-center gap-2.5", className)}>
      <span className="flex size-8 items-center justify-center rounded-lg bg-foreground text-background">
        <svg
          aria-hidden
          viewBox="0 0 24 24"
          className="size-[18px]"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" />
        </svg>
      </span>
      <span className="font-display text-xl font-semibold tracking-[-0.01em]">Chat</span>
    </Link>
  );
}
