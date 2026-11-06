import Link from "next/link";
import { RailSection } from "./Frame";
import { Logo } from "./Logo";

const columns = [
  {
    title: "Product",
    links: [
      { label: "Features", href: "#features" },
      { label: "Use cases", href: "#use-cases" },
      { label: "Integrations", href: "#integrations" },
      { label: "Pricing", href: "#pricing" },
      { label: "FAQ", href: "#faq" },
    ],
  },
  {
    title: "Account",
    links: [
      { label: "Sign up", href: "/register" },
      { label: "Sign in", href: "/login" },
    ],
  },
];

export function Footer() {
  return (
    <RailSection as="footer" className="border-b-0" innerClassName="overflow-hidden" markers={false}>
      <div className="relative grid gap-12 px-5 pt-16 pb-48 sm:px-12 md:grid-cols-[1fr_auto] md:pb-56">
        {/* The wordmark is drawn as a dotted outline, resting on the bottom divider. */}
        <svg
          aria-hidden
          viewBox="0 0 520 190"
          className="pointer-events-none absolute right-[2%] bottom-0 w-[min(88%,560px)] text-foreground/45"
        >
          <text
            x="0"
            y="165"
            fill="none"
            stroke="currentColor"
            // Round dots: near-zero dashes with round caps. Sized in the drawing's own
            // units so every browser scales them the same way: about 4.3px on a laptop
            // and 2.4px on a phone, big enough to read as dots at a quiet 45%.
            strokeWidth="4"
            strokeDasharray="0.01 7.6"
            strokeLinecap="round"
            className="font-display"
            style={{ fontSize: 210, fontWeight: 700, letterSpacing: "-0.04em" }}
          >
            Chat
          </text>
        </svg>
        <div className="max-w-[22rem]">
          <Logo />
          <p className="mt-6 text-sm leading-relaxed text-muted-foreground">
            Private AI chat that answers from your own documents, with streaming replies and
            the sources it used.
          </p>
        </div>
        <div className="grid grid-cols-2 gap-16">
          {columns.map((column) => (
            <nav key={column.title} aria-label={column.title}>
              <h2 className="text-sm font-medium">{column.title}</h2>
              <ul className="mt-5 space-y-3.5 text-sm text-muted-foreground">
                {column.links.map((link) => (
                  <li key={link.label}>
                    <Link href={link.href} prefetch={false} className="transition-colors hover:text-foreground">
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
      </div>

      <div className="relative flex flex-wrap items-center justify-between gap-3 border-t border-dashed border-line px-5 py-6 text-sm text-muted-foreground sm:px-12">
        <p>© {new Date().getFullYear()} Chat.</p>
        <p>Built with FastAPI, Next.js and Mistral.</p>
      </div>
    </RailSection>
  );
}
