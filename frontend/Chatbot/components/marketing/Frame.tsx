import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/** The small downward triangle where a section's dashed rail meets the next one. */
function RailMarker({ side }: { side: "left" | "right" }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 10 9"
      className={cn(
        "pointer-events-none absolute top-full z-10 size-2.5 fill-current text-muted-foreground/45",
        side === "left" ? "-left-[5px]" : "-right-[5.5px]",
      )}
    >
      <path d="M0 0h10L5 9z" />
    </svg>
  );
}

type RailSectionProps = {
  children: ReactNode;
  id?: string;
  className?: string;
  innerClassName?: string;
  as?: "section" | "header" | "footer";
  markers?: boolean;
  "aria-labelledby"?: string;
};

/**
 * One band of the page: a dashed rule underneath, dashed rails on both sides of the
 * content column, and markers where the rails cross into the next band.
 */
export function RailSection({
  children,
  id,
  className,
  innerClassName,
  as: Tag = "section",
  markers = true,
  ...rest
}: RailSectionProps) {
  return (
    <Tag
      id={id}
      className={cn("scroll-mt-4 border-b border-dashed border-line", className)}
      {...rest}
    >
      <div className="mx-auto w-full max-w-[1440px] px-4 md:px-16 lg:px-24 xl:px-32">
        <div className={cn("relative border-x border-dashed border-line", innerClassName)}>
          {markers && (
            <>
              <RailMarker side="left" />
              <RailMarker side="right" />
            </>
          )}
          {children}
        </div>
      </div>
    </Tag>
  );
}

export function SectionHeading({
  id,
  children,
  className,
}: {
  id?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <h2
      id={id}
      className={cn(
        "font-display text-[2rem] leading-[1.2] font-medium tracking-[-0.02em] text-balance sm:text-[2.5rem] sm:leading-[1.25]",
        className,
      )}
    >
      {children}
    </h2>
  );
}
