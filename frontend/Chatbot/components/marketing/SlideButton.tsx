import Link from "next/link";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

type SlideButtonProps = {
  href: string;
  children: ReactNode;
  variant?: "solid" | "outline";
  icon?: ReactNode;
  className?: string;
};

/**
 * The page's button: square-ish, with a label that slides up and is replaced by a copy
 * of itself on hover. The copy is hidden from assistive technology.
 */
export function SlideButton({ href, children, variant = "solid", icon, className }: SlideButtonProps) {
  return (
    // Prefetch is off because the static export doesn't ship every segment file it would
    // request. Navigation still works as a normal page load.
    <Link
      href={href}
      prefetch={false}
      className={cn(
        "group inline-flex h-10 items-center gap-2 rounded-[4px] px-5 text-sm transition-colors duration-200",
        variant === "solid"
          ? "bg-primary font-medium text-primary-foreground hover:bg-primary/90"
          : "border border-line text-foreground hover:border-muted-foreground/60",
        className,
      )}
    >
      <span className="relative block overflow-hidden">
        <span className="block transition-transform duration-400 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:-translate-y-full motion-reduce:transition-none">
          {children}
        </span>
        <span
          aria-hidden
          className="absolute inset-0 block translate-y-full transition-transform duration-400 ease-[cubic-bezier(0.16,1,0.3,1)] group-hover:translate-y-0 motion-reduce:transition-none"
        >
          {children}
        </span>
      </span>
      {icon}
    </Link>
  );
}
