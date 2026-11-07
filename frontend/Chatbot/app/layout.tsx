import type { Metadata } from "next";
import "./globals.css";
import { Geist, Urbanist } from "next/font/google";
import { Toaster } from "sonner";
import { ThemeProvider } from "@/components/theme-provider";
import { cn } from "@/lib/utils";
import { site } from "@/lib/site";

const geist = Geist({ subsets: ["latin"], variable: "--font-geist-sans" });
const urbanist = Urbanist({ subsets: ["latin"], variable: "--font-urbanist" });

export const metadata: Metadata = {
  metadataBase: new URL(site.url),
  title: {
    default: "Chat — Private AI Chat & Document Assistant",
    template: "%s | Chat",
  },
  description: site.description,
  keywords: site.keywords,
  authors: [{ name: site.author.name, url: site.author.url }],
  creator: site.author.name,
  alternates: {
    canonical: "/",
  },
  openGraph: {
    type: "website",
    locale: "en_US",
    url: site.url,
    title: `${site.name} — ${site.tagline}`,
    description: site.description,
    siteName: site.name,
  },
  twitter: {
    card: "summary_large_image",
    title: `${site.name} — ${site.tagline}`,
    description: site.description,
  },
  robots: {
    index: true,
    follow: true,
  },
  icons: {
    icon: "/favicon.ico",
    apple: "/apple-touch-icon.png",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    // next-themes sets the theme class before React hydrates, so the server markup differs.
    <html
      lang="en"
      suppressHydrationWarning
      className={cn(geist.variable, urbanist.variable, "antialiased")}
    >
      <body className="min-h-full">
        <ThemeProvider
          attribute="class"
          defaultTheme="dark"
          enableSystem={false}
          storageKey="theme"
          disableTransitionOnChange
        >
          {children}
          <Toaster richColors position="top-right" />
        </ThemeProvider>
      </body>
    </html>
  );
}
